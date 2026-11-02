// Aba "Pendências": cada item se resolve ali mesmo (categoria, regra, hora extra, destino da transferência…).

const brl = (v) => Math.abs(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const dm = (d) => `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(2, 4)}`;

function start() {
  const root = document.getElementById("pd");
  const src = document.getElementById("pd-data");
  if (!root || !src) return;
  const $ = (id) => document.getElementById(id);
  const d = JSON.parse(src.textContent);
  let ordem = "data";
  try { ordem = localStorage.getItem("pd-ordem") || "data"; } catch { /* ok */ }
  const recente = (g) => g.itens[0].d; // itens já vêm do mais novo para o mais antigo
  if (ordem === "data") {
    d.sem_cat.sort((a, b) => recente(b).localeCompare(recente(a)) || b.total - a.total);
    d.conf.sort((a, b) => b.d.localeCompare(a.d));
    d.transf.sort((a, b) => b.d.localeCompare(a.d));
  } else {
    d.sem_cat.sort((a, b) => b.total - a.total);
    d.conf.sort((a, b) => Math.abs(b.dif) - Math.abs(a.dif));
    d.transf.sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
  }
  const opts = (list, ph) => `<option value="">${ph}</option>` + list.map((o) => `<option value="${esc(o.a)}">${esc(o.n)}</option>`).join("");
  const sec = (titulo, n, desc, corpo) => (n ? `<section class="card sec"><h3>${titulo} <span class="n">${n}</span></h3><p>${desc}</p>${corpo}</section>` : "");

  const semCatItem = (g, i) => `
    <div class="it" data-g="${i}">
      <div><div class="t">${esc(g.nome)}</div>
        <div class="s"><b>${dm(g.itens[0].d)}</b>${g.itens.length > 1 ? ` (último de ${g.itens.length})` : ""} · <b class="${g.entrada ? "in" : "out"}">${g.entrada ? "entrou" : "saiu"} R$ ${brl(g.total)}</b> · ${g.itens[0].meio || ""}</div>
        ${g.itens.length > 1 ? `<details><summary>ver lançamentos</summary><ul>${g.itens.map((x) => `<li>${dm(x.d)} · R$ ${brl(x.v)} · ${esc(x.desc)}</li>`).join("")}</ul></details>` : ""}
      </div>
      <div class="act">
        <select aria-label="Categoria de ${esc(g.nome)}">${opts(g.entrada ? d.cats_in : d.cats_out, "O que é isso?")}</select>
        <label class="chk"><input type="checkbox" checked> sempre que aparecer</label>
        <button class="btn" type="button" data-cat="${i}" disabled>Resolver</button>
      </div>
    </div>`;

  const confItem = (c, i) => `
    <div class="it">
      <div><div class="t">${esc(c.fonte)} pagou ${c.dif > 0 ? "R$ " + brl(c.dif) + " a mais" : "R$ " + brl(-c.dif) + " a menos"} em ${dm(c.d)}</div>
        <div class="s">Esperado R$ ${brl(c.esperado)} · recebido R$ ${brl(c.recebido)}</div></div>
      <div class="act">
        ${c.dif > 0 ? `<button class="btn" type="button" data-hx="${i}">É hora extra / bônus</button><a class="btn ghost" href="../Gastos/?ano=${c.d.slice(0, 4)}&tipo=">É reembolso → marcar gastos</a>` : ""}
        <button class="btn ghost" type="button" data-ign="${esc(c.id)}">Está certo</button>
      </div>
    </div>`;

  const transfItem = (t, i) => `
    <div class="it" data-t="${i}">
      <div><div class="t">${esc(t.desc)}</div>
        <div class="s">${dm(t.d)} · <b class="${t.v > 0 ? "in" : "out"}">${t.v > 0 ? "entrou" : "saiu"} R$ ${brl(t.v)}</b> · não há extrato da outra conta</div></div>
      <div class="act">
        <select aria-label="Destino">${opts(d.destinos, t.v > 0 ? "De onde veio?" : "Para onde foi?")}</select>
        <button class="btn" type="button" data-tr="${i}" disabled>Resolver</button>
        <button class="btn ghost" type="button" data-ign="${esc(t.id)}">Está certo</button>
      </div>
    </div>`;

  const outros = [
    ...d.atrasados.map((f) => `<div class="it"><div><div class="t">Baixar extrato: ${esc(f.nome)}</div><div class="s">${esc(f.como)}</div></div><div class="act"><a class="btn" href="../Importar/">Importar</a></div></div>`),
    ...d.inbox.map((n) => `<div class="it"><div><div class="t">Arquivo não reconhecido: ${esc(n)}</div><div class="s">Ficou na inbox.</div></div><div class="act"><a class="btn ghost" href="../Importar/">Ver</a></div></div>`),
    ...d.prov.map((p) => `<div class="it"><div><div class="t">Provisório sem confirmação: ${esc(p.desc)}</div><div class="s">${dm(p.d)} · R$ ${brl(p.v)} · lançado à mão há mais de 45 dias e o extrato não trouxe</div></div><div class="act"><a class="btn ghost" href="../Lancar/">Ver no Lançar</a></div></div>`),
  ].join("");

  // itens arquivados (antes do marco zero) usam os mesmos controles, com índices próprios
  const A = d.arquivadas;
  const off = { g: d.sem_cat.length, c: d.conf.length, t: d.transf.length };
  if (A) { d.sem_cat.push(...A.sem_cat); d.conf.push(...A.conf); d.transf.push(...A.transf); }
  const htmlG = (lista, base) => lista.map((g, k) => semCatItem(g, base + k)).join("");
  const htmlT = (lista, base) => lista.map((t, k) => transfItem(t, base + k)).join("");
  const htmlC = (lista, base) => lista.map((c, k) => confItem(c, base + k)).join("");

  const nSem = d.sem_cat.slice(0, off.g).reduce((s, g) => s + g.itens.length, 0);
  const fmtD = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  const marcoBox = d.marco
    ? `<section class="card marco"><div><b>Marco zero em ${fmtD(d.marco)}.</b> Mostrando só o que aconteceu a partir dessa data. ${A && A.n ? `${A.n} antigas estão arquivadas abaixo.` : ""}</div><button class="btn ghost" type="button" data-marco="">Desfazer marco zero</button></section>`
    : `<section class="card marco"><div><b>Começar do zero?</b> Arquiva as pendências anteriores ao ciclo atual (antes de ${fmtD(d.ciclo_ini)}). Elas não somem: ficam numa seção separada para resolver quando quiser.</div><button class="btn" type="button" data-marco="${d.ciclo_ini}">Começar do zero neste ciclo</button></section>`;
  $("pd-total").textContent = d.total ? `· ${d.total}` : "";
  $("pd-ordem").innerHTML = ["data", "valor"].map((o) => `<a href="#" data-ordem="${o}" class="${o === ordem ? "on" : ""}">${o === "data" ? "Mais recentes" : "Maior valor"}</a>`).join("");
  const semCat = htmlG(d.sem_cat.slice(0, off.g), 0);
  const conf = htmlC(d.conf.slice(0, off.c), 0);
  const transf = htmlT(d.transf.slice(0, off.t), 0);
  const arquivo = A && A.n
    ? `<details class="card arq"><summary><b>Arquivadas (antes do marco zero)</b> · ${A.n} · resolver quando quiser</summary>
        ${A.sem_cat.length ? `<h4>Sem categoria</h4>${htmlG(A.sem_cat, off.g)}` : ""}
        ${A.conf.length ? `<h4>Pagamentos diferentes do esperado</h4>${htmlC(A.conf, off.c)}` : ""}
        ${A.transf.length ? `<h4>Transferências sem destino</h4>${htmlT(A.transf, off.t)}` : ""}
      </details>` : "";
  $("pd-body").innerHTML = marcoBox + (d.total
    ? sec("Sem categoria", nSem, "Escolha o que é. Com \"sempre que aparecer\" marcado, vira uma regra e os próximos lançamentos iguais já entram certos.", semCat) +
      sec("Pagamentos diferentes do esperado", off.c, "O pagamento não bateu com o salário + extras informados.", conf) +
      sec("Transferências sem destino conhecido", off.t, "Dinheiro que foi ou veio de uma conta sua que não é importada. Diga para onde foi.", transf) +
      sec("Outros", d.atrasados.length + d.inbox.length + d.prov.length, "Extratos para baixar, arquivos parados e lançamentos provisórios.", outros)
    : `<section class="card done"><div class="big">✓</div><h2>Nada pendente</h2><p class="note">Quando você importar um extrato, o que o sistema não souber aparece aqui.</p></section>`) + arquivo;

  const toast = (t) => { $("pd-toast").textContent = t; $("pd-toast").classList.add("on"); };
  async function resolver(body, msg) {
    toast("Salvando e reimportando…");
    const res = await fetch("resolver", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) { toast((await res.json().catch(() => ({}))).erro || "Não consegui salvar."); return; }
    try { sessionStorage.setItem("pd-msg", msg); } catch { /* ok */ }
    location.reload();
  }

  root.addEventListener("change", (e) => {
    const sel = e.target.closest("select");
    if (sel) sel.closest(".it").querySelector("[data-cat],[data-tr]").disabled = !sel.value;
  });
  root.addEventListener("click", (e) => {
    const mz = e.target.closest("[data-marco]");
    if (mz) {
      resolver({ tipo: "marco", data: mz.dataset.marco }, mz.dataset.marco ? "Marco zero definido" : "Marco zero desfeito");
      return;
    }
    const o = e.target.closest("[data-ordem]");
    if (o) {
      e.preventDefault();
      try { localStorage.setItem("pd-ordem", o.dataset.ordem); } catch { /* ok */ }
      location.reload();
      return;
    }
    const b = e.target.closest("button");
    if (!b) return;
    const it = b.closest(".it");
    if (b.dataset.cat !== undefined) {
      const g = d.sem_cat[+b.dataset.cat];
      const conta = it.querySelector("select").value;
      const regra = it.querySelector("input[type=checkbox]").checked;
      resolver({ tipo: "categoria", conta, regra, padrao: g.regra, keys: g.itens.map((x) => x.key) },
        `${g.nome}: resolvido${regra ? " (regra criada)" : ""}`);
    } else if (b.dataset.tr !== undefined) {
      const t = d.transf[+b.dataset.tr];
      resolver({ tipo: "categoria", conta: it.querySelector("select").value, keys: [t.key] }, "Transferência resolvida");
    } else if (b.dataset.hx !== undefined) {
      const c = d.conf[+b.dataset.hx];
      resolver({ tipo: "hora_extra", fonte: c.fonte, d: c.d, valor: c.dif }, `Hora extra de R$ ${brl(c.dif)} registrada`);
    } else if (b.dataset.ign) {
      resolver({ tipo: "ignorar", id: b.dataset.ign }, "Marcado como certo");
    }
  });
  try { const m = sessionStorage.getItem("pd-msg"); if (m) { toast("✓ " + m); sessionStorage.removeItem("pd-msg"); setTimeout(() => $("pd-toast").classList.remove("on"), 2500); } } catch { /* ok */ }
}

export default { onExtensionPageLoad() { start(); } };
