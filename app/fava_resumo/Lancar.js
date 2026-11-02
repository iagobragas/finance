// Aba "Lançar": formulário rápido. Valor + descrição -> categoria sugerida -> Enter.

// empresas que pagam/reembolsam (config/accounts.yaml → empresas): id da conta -> nome para exibir
const EMP = () => { try { return JSON.parse(document.getElementById("fin-cfg").textContent).empresas || {}; } catch { return {}; } };
const empNome = (k) => EMP()[k] || k;
const empId = (nome) => Object.keys(EMP()).find((k) => EMP()[k] === nome) || nome;
const brl = (v) => Math.abs(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function load(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }
function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* sem armazenamento */ } }

function start() {
  const root = document.getElementById("ln");
  const src = document.getElementById("ln-data");
  if (!root || !src) return;
  const $ = (id) => document.getElementById(id);
  const data = JSON.parse(src.textContent);
  const rules = data.rules.map((r) => { try { return { re: new RegExp(r.match, "i"), account: r.account }; } catch { return null; } }).filter(Boolean);

  const st = { tipo: "despesa", pay: load("ln-pay", {}), catManual: false, reemb: "" };
  const REEMB = [["", "Não"], ...Object.entries(EMP())];

  function sugerir(desc) {
    const t = desc.trim().toLowerCase();
    if (t.length < 2) return null;
    const cats = new Set(data.cats.filter((c) => c.tipo === st.tipo).map((c) => c.account));
    // 1) histórico: mesma descrição ou que começa igual (o que você já lançou/importou antes)
    const votos = {};
    data.hist.forEach(([d, a]) => { if (cats.has(a) && (d.includes(t) || (t.length >= 4 && t.includes(d.slice(0, 12))))) votos[a] = (votos[a] || 0) + 1; });
    const best = Object.entries(votos).sort((a, b) => b[1] - a[1])[0];
    if (best) return best[0];
    // 2) regras de categorização
    const r = rules.find((x) => cats.has(x.account) && x.re.test(desc));
    return r ? r.account : null;
  }

  function renderTipo() {
    root.querySelectorAll(".tipo button").forEach((b) => {
      const on = b.dataset.t === st.tipo;
      b.classList.toggle("on", on);
      b.setAttribute("aria-checked", String(on));
    });
    const cats = data.cats.filter((c) => c.tipo === st.tipo);
    const grupos = {};
    cats.forEach((c) => { const g = c.label.startsWith("Devolução · ") ? "Alguém te devolveu parte de um gasto (abate o gasto)"
        : c.label.includes(" · ") && st.tipo === "despesa" ? c.label.split(" · ")[0] : "Receitas"; (grupos[g] ||= []).push(c); });
    const atual = $("ln-cat").value;
    $("ln-cat").innerHTML = Object.entries(grupos).map(([g, cs]) =>
      `<optgroup label="${esc(g)}">${cs.map((c) => `<option value="${esc(c.account)}">${esc(st.tipo === "despesa" ? c.label.split(" · ").slice(1).join(" · ") || c.label : c.label)}</option>`).join("")}</optgroup>`).join("");
    if (cats.some((c) => c.account === atual)) $("ln-cat").value = atual;
    else $("ln-cat").value = st.tipo === "despesa" ? "Expenses:Variaveis:Outros" : "Income:Outras:Outros";
    const opts = data.pag[st.tipo];
    if (!opts.some((o) => o.account === st.pay[st.tipo])) st.pay[st.tipo] = opts[0].account;
    $("ln-pays").innerHTML = opts.map((o) => `<button type="button" data-pay="${esc(o.account)}" class="${o.account === st.pay[st.tipo] ? "on" : ""}">${esc(o.label)}</button>`).join("");
    $("ln-pay-l").textContent = st.tipo === "despesa" ? "Pago com" : "Entrou em";
    $("ln-prov").hidden = !opts.find((o) => o.account === st.pay[st.tipo])?.prov;
    $("ln-go").textContent = st.tipo === "despesa" ? "Lançar despesa" : "Lançar receita";
    $("ln-re-box").hidden = st.tipo !== "despesa";
    const cartao = /Cartao/.test(st.pay[st.tipo] || "");
    const empresa = REEMB.find(([v]) => v === st.reemb)?.[1];
    $("ln-re-hint").hidden = !st.reemb;
    $("ln-re-hint").textContent = st.reemb
      ? `Vai para "A receber · ${empresa}" (não conta como gasto seu) e é abatido quando a ${empresa} pagar.` +
        (cartao ? " Use o valor exato da compra para casar com a fatura." : "")
      : "";
    $("ln-re").innerHTML = REEMB.map(([v, n]) => `<button type="button" data-re="${v}" class="${st.reemb === v ? "on" : ""}">${n}</button>`).join("");
  }

  function renderList() {
    const m = data.manual;
    $("ln-sub").textContent = m.length ? `${m.length} lançamentos em ledger/manual.beancount` : "Nada lançado à mão ainda.";
    $("ln-list").innerHTML = m.length
      ? `<thead><tr><th style="text-align:left">Data</th><th style="text-align:left">Descrição</th><th style="text-align:left">Categoria</th><th style="text-align:left">Conta</th><th>Valor</th><th></th></tr></thead><tbody>` +
        m.map((r) => `<tr class="cat"><td>${r.d.slice(8, 10)}/${r.d.slice(5, 7)}/${r.d.slice(2, 4)}</td><td>${esc(r.desc)}${r.prov ? '<span class="tag" title="Será trocado pelo extrato quando ele chegar">provisório</span>' : ""}</td><td>${esc(r.cat)}</td><td>${esc(r.pay)}</td><td class="n v${r.receita ? " rec" : ""}">${r.receita ? "+" : "−"}${brl(r.v)}</td><td class="n"><button type="button" class="x" data-del="${r.line}" aria-label="Apagar lançamento">×</button></td></tr>`).join("") + `</tbody>`
      : "";
  }

  function msg(t, ok) { $("ln-msg").textContent = t; $("ln-msg").className = `msg ${ok ? "ok" : "err"}`; }

  root.addEventListener("click", async (e) => {
    const t = e.target.closest("[data-t],[data-pay],[data-del],[data-re]");
    if (!t) return;
    if (t.dataset.re !== undefined) { st.reemb = t.dataset.re; renderTipo(); return; }
    if (t.dataset.t) { st.tipo = t.dataset.t; st.catManual = false; renderTipo(); onDesc(); $("ln-valor").focus(); }
    else if (t.dataset.pay) { st.pay[st.tipo] = t.dataset.pay; save("ln-pay", st.pay); renderTipo(); }
    else if (t.dataset.del) {
      t.disabled = true;
      const res = await fetch("remover", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ line: +t.dataset.del }) });
      if (res.ok) location.reload();
      else { msg((await res.json().catch(() => ({}))).erro || "Não consegui apagar.", false); t.disabled = false; }
    }
  });

  function onDesc() {
    if (st.catManual) return;
    const s = sugerir($("ln-desc").value);
    $("ln-auto").hidden = !s;
    if (s) $("ln-cat").value = s;
  }
  $("ln-desc").addEventListener("input", onDesc);
  $("ln-cat").addEventListener("change", () => { st.catManual = true; $("ln-auto").hidden = true; });

  $("ln-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const valor = $("ln-valor").value.trim().replace(/\./g, "").replace(",", ".");
    if (!valor || isNaN(+valor) || +valor <= 0) { msg("Digite o valor.", false); $("ln-valor").focus(); return; }
    $("ln-go").disabled = true;
    const body = { tipo: st.tipo, valor, descricao: $("ln-desc").value, categoria: $("ln-cat").value,
      data: $("ln-data-in").value, pagamento: st.pay[st.tipo], parcelas: +$("ln-parc").value || 1,
      reembolso: st.tipo === "despesa" ? st.reemb : "" };
    try {
      const res = await fetch("lancar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const j = await res.json().catch(() => ({}));
      if (!res.ok || !j.ok) throw new Error(j.erro || "Não consegui lançar.");
      try { sessionStorage.setItem("ln-ok", `Lançado: ${body.descricao || "sem descrição"} · R$ ${brl(+valor)}` + (body.reembolso ? ` · reembolso ${empNome(body.reembolso)}` : "")); } catch { /* ok */ }
      location.reload();
    } catch (err) {
      msg(err.message, false);
      $("ln-go").disabled = false;
    }
  });

  $("ln-data-in").value = data.hoje;
  renderTipo();
  renderList();
  try { const ok = sessionStorage.getItem("ln-ok"); if (ok) { msg(ok, true); sessionStorage.removeItem("ln-ok"); } } catch { /* ok */ }
  $("ln-valor").focus();
}

export default { onExtensionPageLoad() { start(); } };
