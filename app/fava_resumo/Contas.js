// Aba "Contas": escolhe uma conta ou cartão e vê a movimentação por data (mais recente primeiro), com saldo.

// empresas que pagam/reembolsam (config/accounts.yaml → empresas): id da conta -> nome para exibir
const EMP = () => { try { return JSON.parse(document.getElementById("fin-cfg").textContent).empresas || {}; } catch { return {}; } };
const empNome = (k) => EMP()[k] || k;
const empId = (nome) => Object.keys(EMP()).find((k) => EMP()[k] === nome) || nome;
const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const brl = (v) => Math.abs(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const sinal = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + "R$ " + brl(v);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const sem = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const dm = (d) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;
const dmy = (d) => `${dm(d)}/${d.slice(2, 4)}`;
const GRUPOS = { conta: "Contas", cartao: "Cartões de crédito", reembolso: "A receber das empresas", outra: "Outras" };
const PASSO = 150;

function render(root) {
  const data = JSON.parse(document.getElementById("ct-data").textContent);
  const st = { acc: new URLSearchParams(location.search).get("conta") || data.contas[0]?.acc, q: "", mes: "", cartao: "", f: "", lim: PASSO };
  const $ = (s) => root.querySelector(s);

  function cards() {
    let html = "";
    for (const [tipo, titulo] of Object.entries(GRUPOS)) {
      const cs = data.contas.filter((c) => c.tipo === tipo);
      if (!cs.length) continue;
      html += `<p class="grp">${titulo}</p><div class="accs">` + cs.map((c) => {
        const cartao = c.tipo === "cartao";
        const rot = c.sub ? `${c.aberta ? "na fatura de" : "na última fatura,"} ${dm(c.vence)}` : cartao ? (c.saldo < 0 ? "fatura em aberto · total" : "sem dívida") : "saldo";
        const conf = c.sub ? `${c.n} compras · última ${c.ultimo ? dmy(c.ultimo) : "—"}` : c.conferido ? `<span class="ok">✓ conferido</span> em ${dmy(c.conferido.d)}` : `até ${c.ultimo ? dmy(c.ultimo) : "—"}`;
        return `<button type="button" class="acc" data-acc="${esc(c.acc)}" aria-pressed="${c.acc === st.acc}">
          <span class="k">${rot}</span><span class="nm">${esc(c.nome)}</span>
          <span class="v${!cartao && c.saldo < 0 ? " neg" : ""}">R$ ${brl(c.saldo)}</span>
          <span class="s">${c.sub ? conf : `${c.n} movimentos · ${conf}`}</span></button>`;
      }).join("") + "</div>";
    }
    $("#ct-accs").innerHTML = html;
    $("#ct-accs").querySelectorAll(".acc").forEach((b) => b.addEventListener("click", () => {
      st.acc = b.dataset.acc; st.mes = ""; st.cartao = ""; st.q = ""; st.lim = PASSO; $("#ct-q").value = "";
      const u = new URL(location.href); u.searchParams.set("conta", st.acc); history.replaceState(null, "", u);
      cards(); filtros(); form(); lista();
    }));
  }

  function conta() { return data.contas.find((c) => c.acc === st.acc) || data.contas[0]; }

  function filtros() {
    const c = conta();
    const meses = [...new Set(c.rows.map((r) => r.d.slice(0, 7)))];
    $("#ct-mes").innerHTML = `<option value="">todos os meses</option>` +
      meses.map((m) => `<option value="${m}"${m === st.mes ? " selected" : ""}>${MESES[+m.slice(5) - 1]} ${m.slice(0, 4)}</option>`).join("");
    const sel = $("#ct-cartao");
    sel.hidden = c.cartoes.length < 2;
    sel.innerHTML = `<option value="">todos os cartões</option>` + c.cartoes.map((n) => `<option${n === st.cartao ? " selected" : ""}>${esc(n)}</option>`).join("");
    $("#ct-title").textContent = c.nome;
    const cartao = c.tipo === "cartao";
    $("#ct-sub").textContent = c.sub
      ? `Só as compras deste cartão. A fatura é a mesma do ${data.contas.find((x) => x.acc === c.pai)?.nome || "cartão principal"}: o pagamento e o saldo ficam lá.`
      : cartao
      ? "Compras pela data da compra. Parcelas futuras aparecem esmaecidas. Saldo = quanto você deve no cartão."
      : c.tipo === "reembolso" ? "Gastos marcados como reembolso e o que a empresa já devolveu." : "Tudo que entrou e saiu, com o saldo depois de cada movimento.";
  }

  // formulário "novo gasto a receber" (só nos cards de reembolso): usa o mesmo lançamento da aba Lançar
  function form() {
    const c = conta();
    const f = $("#ct-nr");
    f.hidden = c.tipo !== "reembolso";
    if (f.hidden) return;
    const empresa = c.acc.split(":").pop();
    $("#ct-nr .nr-t").textContent = `Novo gasto a receber da ${empNome(empresa)}`;
    if (!$("#nr-c").options.length) {
      $("#nr-c").innerHTML = data.cats.map((x) => `<option value="${esc(x.account)}">${esc(x.label)}</option>`).join("");
      $("#nr-c").value = data.cats.some((x) => x.account === "Expenses:Variaveis:Restaurantes") ? "Expenses:Variaveis:Restaurantes" : data.cats[0]?.account;
      $("#nr-p").innerHTML = data.pag.map((o) => `<option value="${esc(o.account)}">${esc(o.label)}</option>`).join("");
      $("#nr-dt").value = data.hoje;
    }
    f.dataset.empresa = empresa;
  }
  $("#ct-nr").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = (t, ok) => { $("#nr-msg").textContent = t; $("#nr-msg").className = `nr-msg ${ok ? "ok" : "err"}`; };
    const valor = $("#nr-v").value.trim().replace(/\./g, "").replace(",", ".");
    if (!valor || isNaN(+valor) || +valor <= 0) { msg("Digite o valor exato da compra.", false); $("#nr-v").focus(); return; }
    $("#nr-go").disabled = true;
    const body = { tipo: "despesa", valor, descricao: $("#nr-d").value, categoria: $("#nr-c").value, data: $("#nr-dt").value,
      pagamento: $("#nr-p").value, parcelas: 1, reembolso: $("#ct-nr").dataset.empresa };
    try {
      const res = await fetch("../Lancar/lancar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const j = await res.json().catch(() => ({}));
      if (!res.ok || !j.ok) throw new Error(j.erro || "Não consegui adicionar.");
      try { sessionStorage.setItem("ct-ok", `Adicionado: ${body.descricao || "gasto"} · R$ ${brl(+valor)}`); } catch { /* ok */ }
      location.reload();
    } catch (err) { msg(err.message, false); $("#nr-go").disabled = false; }
  });

  function lista() {
    const c = conta();
    const words = sem(st.q).split(/\s+/).filter(Boolean);
    const rs = c.rows.filter((r) =>
      (!st.mes || r.d.startsWith(st.mes)) && (!st.cartao || r.cartao === st.cartao) &&
      (!st.f || (st.f === "in" ? r.v > 0 : r.v < 0)) &&
      words.every((w) => sem(`${r.desc} ${r.outro} ${r.meio} ${r.cartao} ${brl(r.v)}`).includes(w)));
    const ent = rs.filter((r) => r.v > 0).reduce((s, r) => s + r.v, 0);
    const sai = rs.filter((r) => r.v < 0).reduce((s, r) => s + r.v, 0);
    $("#ct-tot").innerHTML = `<span>${rs.length} movimentos</span><span>Entradas <b style="color:var(--good)">R$ ${brl(ent)}</b></span>` +
      `<span>Saídas <b>R$ ${brl(sai)}</b></span><span>Líquido <b>${sinal(ent + sai)}</b></span>`;
    if (!rs.length) {
      $("#ct-tab").innerHTML = `<tr><td class="empty">Nada encontrado com esses filtros.</td></tr>`;
      $("#ct-more").hidden = true;
      return;
    }
    const mostra = !c.sub && !st.cartao && !words.length && !st.f; // saldo só faz sentido sem filtro que tira linhas
    const checks = new Map(c.checks.map((k) => [k.d, k.v]));
    let html = `<tr class="mh"><td>Data</td><td>Descrição</td><td class="n">Valor</td>${mostra ? '<td class="n sd">Saldo</td>' : ""}</tr>`;
    let mes = "";
    for (const r of rs.slice(0, st.lim)) {
      const m = r.d.slice(0, 7);
      if (m !== mes) {
        mes = m;
        const doMes = rs.filter((x) => x.d.startsWith(m));
        const liq = doMes.reduce((s, x) => s + x.v, 0);
        html += `<tr class="mh"><td colspan="2">${MESES[+m.slice(5) - 1]} ${m.slice(0, 4)}</td><td class="n">${sinal(liq)}</td>${mostra ? "<td class='sd'></td>" : ""}</tr>`;
      }
      if (mostra && checks.has(r.d) && Math.abs(checks.get(r.d) - r.saldo) < 0.005) {
        html += `<tr class="ck"><td></td><td colspan="${mostra ? 3 : 2}">✓ saldo de ${dm(r.d)} confere com o banco: R$ ${brl(r.saldo)}</td></tr>`;
        checks.delete(r.d);
      }
      const selos = [
        r.parc && `<span class="b">parcela ${esc(r.parc)}</span>`,
        r.tipo === "transf" && `<span class="b tr">transferência</span>`,
        r.tipo === "recebido" && `<span class="b rb">recebido</span>`,
        r.prov && `<span class="b pv">provisório</span>`,
        r.manual && !r.prov && `<span class="b">manual</span>`,
        r.futuro && `<span class="b">futuro</span>`,
      ].filter(Boolean).join("");
      const det = [r.categoria || r.outro, r.meio, r.cartao, r.fatura && c.tipo === "cartao" ? `fatura ${esc(r.fatura).slice(0, 7)}` : ""].filter(Boolean).join(" · ");
      const gasto = c.tipo === "reembolso" ? r.v > 0 : r.v < 0;
      const clipe = (r.comp || []).map((k, n) => `<button type="button" class="clip" data-ver="${esc(k.arquivo)}" title="Ver comprovante${k.loja ? " · " + esc(k.loja) : ""}">📎${r.comp.length > 1 ? n + 1 : ""}</button>`).join("");
      const anexar = gasto && !r.pad ? `<button type="button" data-anx data-d="${r.d}" data-v="${Math.abs(r.v)}" data-n="${esc(r.desc)}">${r.comp?.length ? "+ comprovante" : "anexar comprovante"}</button>` : "";
      const acoes = (r.line || anexar) ? `<span class="acts">${r.line ? `<button type="button" data-ed="${r.line}" data-d="${r.d}" data-v="${Math.abs(r.v)}" data-n="${esc(r.desc)}">editar</button><button type="button" data-rm="${r.line}">apagar</button>` : ""}${anexar}</span>` : "";
      html += `<tr class="${r.futuro ? "fut" : ""}"><td class="dt">${dm(r.d)}</td>
        <td class="ds">${esc(r.desc)}${clipe}${selos}${acoes}<small class="${r.revisar ? "rv" : ""}">${r.revisar ? "sem categoria · resolva em Pendências" : esc(det)}</small></td>
        <td class="n v${r.v > 0 ? " in" : ""}">${sinal(r.v)}</td>${mostra ? `<td class="n sd">R$ ${r.saldo < 0 ? "−" : ""}${brl(r.saldo)}</td>` : ""}</tr>`;
    }
    $("#ct-tab").innerHTML = html;
    $("#ct-more").hidden = rs.length <= st.lim;
  }

  // editar / apagar lançamentos feitos à mão
  $("#ct-tab").addEventListener("click", async (e) => {
    const ed = e.target.closest("[data-ed]"), rm = e.target.closest("[data-rm]"), ok = e.target.closest("[data-ok]"), no = e.target.closest("[data-no]");
    const post = async (url, body) => {
      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const j = await res.json().catch(() => ({}));
      if (!res.ok || !j.ok) throw new Error(j.erro || "Não consegui salvar.");
    };
    if (ed) {
      const tr = ed.closest("tr");
      const cols = tr.children.length;
      tr.insertAdjacentHTML("afterend", `<tr class="edrow"><td colspan="${cols}"><div class="edf">
        <label>Data<input type="date" value="${ed.dataset.d}" data-f="data"></label>
        <label>Valor<input inputmode="decimal" value="${brl(+ed.dataset.v)}" data-f="valor"></label>
        <label>Descrição<input value="${ed.dataset.n}" data-f="descricao"></label>
        <button type="button" data-ok="${ed.dataset.ed}">Salvar</button><button type="button" class="gh" data-no>Cancelar</button>
        <span class="em"></span></div></td></tr>`);
      ed.disabled = true;
      tr.nextElementSibling.querySelector("input").focus();
    } else if (no) {
      const row = no.closest("tr"); row.previousElementSibling.querySelector("[data-ed]").disabled = false; row.remove();
    } else if (ok) {
      const row = ok.closest("tr"), get = (f) => row.querySelector(`[data-f="${f}"]`).value;
      ok.disabled = true;
      try {
        await post("../Lancar/editar", { line: +ok.dataset.ok, data: get("data"), valor: get("valor").replace(/\./g, "").replace(",", "."), descricao: get("descricao") });
        try { sessionStorage.setItem("ct-ok", "Lançamento corrigido."); } catch { /* ok */ }
        location.reload();
      } catch (err) { row.querySelector(".em").textContent = err.message; ok.disabled = false; }
    } else if (rm) {
      if (!confirm("Apagar este lançamento feito à mão?")) return;
      rm.disabled = true;
      try { await post("../Lancar/remover", { line: +rm.dataset.rm }); location.reload(); }
      catch (err) { alert(err.message); rm.disabled = false; }
    }
  });

  // comprovantes: ver (janela sobre a página) e anexar (foto ou PDF)
  let anxAlvo = null;
  const anxInput = Object.assign(document.createElement("input"), { type: "file", accept: "image/*,.heic,application/pdf", hidden: true });
  document.body.appendChild(anxInput);
  anxInput.addEventListener("change", async () => {
    const f = anxInput.files[0];
    if (!f || !anxAlvo) return;
    const b = anxAlvo; anxAlvo = null;
    b.textContent = "enviando…"; b.disabled = true;
    const fd = new FormData();
    fd.append("arquivo", f); fd.append("data", b.dataset.d); fd.append("valor", b.dataset.v); fd.append("loja", b.dataset.n);
    const res = await fetch("anexar", { method: "POST", body: fd });
    const j = await res.json().catch(() => ({}));
    if (res.ok && j.ok) { try { sessionStorage.setItem("ct-ok", "Comprovante anexado."); } catch { /* ok */ } location.reload(); }
    else { b.textContent = j.erro || "não deu"; b.disabled = false; }
    anxInput.value = "";
  });
  function verComprovante(arq) {
    const url = `comprovante?f=${encodeURIComponent(arq)}`;
    const pdf = /\.pdf$/i.test(arq);
    const box = document.createElement("div");
    box.className = "ct-lightbox";
    box.innerHTML = `<div class="lb-in" role="dialog" aria-label="Comprovante">${pdf ? `<iframe src="${url}" title="Comprovante"></iframe>` : `<img src="${url}" alt="Comprovante">`}
      <div class="lb-bar"><span>${esc(arq.split("/").pop())}</span><a href="${url}" target="_blank" rel="noopener">abrir em nova aba</a><button type="button">fechar ✕</button></div></div>`;
    const fechar = () => { box.remove(); document.removeEventListener("keydown", esc_); };
    const esc_ = (e) => { if (e.key === "Escape") fechar(); };
    box.addEventListener("click", (e) => { if (e.target === box || e.target.closest(".lb-bar button")) fechar(); });
    document.addEventListener("keydown", esc_);
    document.body.appendChild(box);
  }
  $("#ct-tab").addEventListener("click", (e) => {
    const ver = e.target.closest("[data-ver]"), anx = e.target.closest("[data-anx]");
    if (ver) verComprovante(ver.dataset.ver);
    if (anx) { anxAlvo = anx; anxInput.click(); }
  });

  $("#ct-q").addEventListener("input", (e) => { st.q = e.target.value; st.lim = PASSO; lista(); });
  $("#ct-mes").addEventListener("change", (e) => { st.mes = e.target.value; st.lim = PASSO; lista(); });
  $("#ct-cartao").addEventListener("change", (e) => { st.cartao = e.target.value; lista(); });
  $("#ct-more").addEventListener("click", () => { st.lim += PASSO; lista(); });
  root.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
    st.f = b.dataset.f;
    root.querySelectorAll(".seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    lista();
  }));
  cards(); filtros(); form(); lista();
  try { const ok = sessionStorage.getItem("ct-ok"); if (ok) { $("#nr-msg").textContent = ok; $("#nr-msg").className = "nr-msg ok"; sessionStorage.removeItem("ct-ok"); } } catch { /* ok */ }
}

export default {
  onExtensionPageLoad() {
    const root = document.getElementById("ct");
    if (root) render(root);
  },
};
