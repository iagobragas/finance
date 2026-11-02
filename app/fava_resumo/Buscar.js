// Aba "Buscar": uma caixa que entende texto, valores (33,96 · ~130 · >500 · 100-200) e datas (21/09 · set · set/26).

// empresas que pagam/reembolsam (config/accounts.yaml → empresas): id da conta -> nome para exibir
const EMP = () => { try { return JSON.parse(document.getElementById("fin-cfg").textContent).empresas || {}; } catch { return {}; } };
const empNome = (k) => EMP()[k] || k;
const empId = (nome) => Object.keys(EMP()).find((k) => EMP()[k] === nome) || nome;
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const brl = (v) => Math.abs(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const sem = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const num = (s) => +String(s).replace(/\./g, "").replace(",", ".");

// interpreta a busca em partes: valores, datas, palavras e palavras-chave de selo/tipo
export function parse(q, hoje) {
  const out = { words: [], vmin: null, vmax: null, dmin: "", dmax: "", flags: [], tipo: "", chips: [] };
  const ano = hoje.slice(0, 4);
  for (const tok of q.trim().split(/\s+/).filter(Boolean)) {
    const t = sem(tok);
    let m;
    if ((m = t.match(/^([<>])=?(\d[\d.,]*)$/))) {
      if (m[1] === ">") out.vmin = num(m[2]); else out.vmax = num(m[2]);
      out.chips.push(`valor ${m[1]} R$ ${brl(num(m[2]))}`);
    } else if ((m = t.match(/^(\d[\d.,]*)-(\d[\d.,]*)$/))) {
      out.vmin = num(m[1]); out.vmax = num(m[2]);
      out.chips.push(`valor entre R$ ${brl(out.vmin)} e R$ ${brl(out.vmax)}`);
    } else if ((m = t.match(/^~(\d[\d.,]*)$/))) {
      const v = num(m[1]); out.vmin = v * 0.95; out.vmax = v * 1.05;
      out.chips.push(`valor perto de R$ ${brl(v)}`);
    } else if ((m = t.match(/^(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?$/))) {
      const y = m[3] ? (m[3].length === 2 ? "20" + m[3] : m[3]) : ano;
      const d = `${y}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
      out.dmin = out.dmax = d; out.chips.push(`data ${m[1].padStart(2, "0")}/${m[2].padStart(2, "0")}/${y}`);
    } else if ((m = t.match(/^(\d[\d.]*,\d{1,2}|\d+\.\d{2}|\d+)$/)) && !/^\d{4}$/.test(t)) {
      const v = num(m[1]); out.exato = v; out.vmin = v * 0.95; out.vmax = v * 1.05;
      out.chips.push(`valor R$ ${brl(v)} (e parecidos)`);
    } else if ((m = t.match(/^([a-zç]{3,9})(?:\/(\d{2,4}))?$/)) && (MESES.includes(m[1].slice(0, 3)) && (MESES.includes(m[1]) || MESES_LONGOS.map(sem).includes(m[1])))) {
      const i = MESES.indexOf(m[1].slice(0, 3));
      const y = m[2] ? (m[2].length === 2 ? "20" + m[2] : m[2]) : ano;
      const mm = String(i + 1).padStart(2, "0");
      out.dmin = `${y}-${mm}-01`; out.dmax = `${y}-${mm}-31`;
      out.chips.push(`${MESES_LONGOS[i]} de ${y}`);
    } else if (/^\d{4}$/.test(t)) {
      out.dmin = `${t}-01-01`; out.dmax = `${t}-12-31`; out.chips.push(`ano ${t}`);
    } else if (["gasto", "gastos", "despesa"].includes(t)) { out.tipo = "gasto"; out.chips.push("só gastos"); }
    else if (["receita", "receitas", "entrada"].includes(t)) { out.tipo = "receita"; out.chips.push("só receitas"); }
    else if (["transferencia", "transferencias"].includes(t)) { out.tipo = "transferência"; out.chips.push("só transferências"); }
    else if (["parcela", "parcelas", "parcelado"].includes(t)) { out.flags.push("parc"); out.chips.push("parceladas"); }
    else if (["reembolsavel", "reembolso"].includes(t)) { out.flags.push("reemb"); out.chips.push("reembolsáveis"); }
    else if (["provisorio", "provisorios"].includes(t)) { out.flags.push("prov"); out.chips.push("provisórios"); }
    else if (["manual", "manuais"].includes(t)) { out.flags.push("manual"); out.chips.push("lançados à mão"); }
    else if (["assinatura", "assinaturas"].includes(t)) { out.words.push("assinaturas"); out.chips.push("assinaturas"); }
    else if (["fixa", "fixas"].includes(t)) { out.flags.push("fixa"); out.chips.push("fixas"); }
    else if (["variavel", "variaveis"].includes(t)) { out.flags.push("var"); out.chips.push("variáveis"); }
    else { out.words.push(t); out.chips.push(`“${tok}”`); }
  }
  return out;
}

function start() {
  const root = document.getElementById("bs");
  const src = document.getElementById("bs-data");
  if (!root || !src) return;
  const $ = (id) => document.getElementById(id);
  const { rows, hoje } = JSON.parse(src.textContent);
  rows.forEach((r) => (r._t = sem([r.desc, r.cat, r.meio, r.cartao, r.conta, r.reemb].join(" "))));

  const meios = [...new Set(rows.map((r) => r.meio).filter(Boolean))].sort();
  const cats = [...new Set(rows.map((r) => r.cat).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt"));
  $("f-meio").innerHTML += meios.map((m) => `<option>${esc(m)}</option>`).join("");
  $("f-cat").innerHTML += cats.map((c) => `<option>${esc(c)}</option>`).join("");

  let limite = 100, aberto = -1;
  const q0 = new URLSearchParams(location.search).get("q");
  if (q0) $("bs-q").value = q0;

  function selos(r) {
    const b = [];
    if (r.tipo === "receita") b.push(`<span class="b rc">receita</span>`);
    if (r.tipo === "transferência") b.push(`<span class="b tr">transferência</span>`);
    if (r.grupo === "Fixa") b.push(`<span class="b fx">Fixa</span>`);
    if (r.grupo === "Variável") b.push(`<span class="b vr">Variável</span>`);
    if (r.parc) b.push(`<span class="b pc">parcela ${esc(r.parc.replace("/", " de "))}</span>`);
    if (r.reemb) b.push(`<span class="b re">reembolsável · ${esc(empNome(r.reemb))}</span>`);
    if (r.prov) b.push(`<span class="b pv">provisório</span>`);
    else if (r.manual) b.push(`<span class="b mn">manual</span>`);
    return b.join("");
  }

  function render() {
    const p = parse($("bs-q").value, hoje);
    const adv = { tipo: $("f-tipo").value, vmin: $("f-vmin").value, vmax: $("f-vmax").value, dmin: $("f-dmin").value,
      dmax: $("f-dmax").value, meio: $("f-meio").value, cat: $("f-cat").value };
    const tipo = adv.tipo || p.tipo;
    const vmin = adv.vmin !== "" ? +adv.vmin : p.vmin, vmax = adv.vmax !== "" ? +adv.vmax : p.vmax;
    const dmin = adv.dmin || p.dmin, dmax = adv.dmax || p.dmax;
    let res = rows.filter((r) =>
      (!tipo || r.tipo === tipo) &&
      (vmin === null || Math.abs(r.v) >= vmin) && (vmax === null || Math.abs(r.v) <= vmax) &&
      (!dmin || r.d >= dmin) && (!dmax || r.d <= dmax) &&
      (!adv.meio || r.meio === adv.meio) && (!adv.cat || r.cat === adv.cat) &&
      p.flags.every((f) => (f === "fixa" ? r.grupo === "Fixa" : f === "var" ? r.grupo === "Variável" : r[f])) &&
      p.words.every((w) => r._t.includes(w)));

    // busca por valor exato: exatos primeiro (destacados), depois os parecidos (±5%)
    const exato = adv.vmin === "" && adv.vmax === "" && p.exato != null ? p.exato : null;
    const isEx = (r) => exato != null && Math.abs(Math.abs(r.v) - exato) < 0.005;
    if (exato != null) res = [...res.filter(isEx), ...res.filter((r) => !isEx(r)).sort((a, b) => Math.abs(Math.abs(a.v) - exato) - Math.abs(Math.abs(b.v) - exato))];
    const nEx = res.filter(isEx).length;
    $("bs-chips").innerHTML = p.chips.map((c) => `<span>${esc(c)}</span>`).join("");
    const g = res.filter((r) => r.tipo === "gasto").reduce((s, r) => s + r.v, 0);
    const rc = res.filter((r) => r.tipo === "receita").reduce((s, r) => s + r.v, 0);
    const vazio = !$("bs-q").value.trim() && !Object.values(adv).some(Boolean);
    $("bs-sum").innerHTML = vazio
      ? `<span>Digite para buscar em <b>${rows.length}</b> lançamentos.</span>`
      : exato != null
      ? `<span><b>${nEx}</b> com valor exato de R$ ${brl(exato)}</span><span style="color:var(--muted)">+ ${res.length - nEx} parecidos (±5%)</span>`
      : `<span><b>${res.length}</b> encontrados</span>${g ? `<span>gastos <b>R$ ${brl(g)}</b></span>` : ""}${rc ? `<span>receitas <b style="color:var(--good)">R$ ${brl(rc)}</b></span>` : ""}`;

    const hl = (s) => {
      let h = esc(s);
      p.words.forEach((w) => {
        if (w.length < 2) return;
        const re = new RegExp(`(${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig");
        // destaca ignorando acento: compara pela versão sem acento
        const base = sem(s), idx = [];
        let k = base.indexOf(w);
        while (k >= 0) { idx.push(k); k = base.indexOf(w, k + w.length); }
        if (idx.length) {
          let o = "", last = 0;
          idx.forEach((i) => { o += esc(s.slice(last, i)) + "<mark>" + esc(s.slice(i, i + w.length)) + "</mark>"; last = i + w.length; });
          h = o + esc(s.slice(last));
        } else h = h.replace(re, "<mark>$1</mark>");
      });
      return h;
    };
    const shown = vazio ? res.slice(0, 20) : res.slice(0, limite);
    $("bs-res").innerHTML = shown.length
      ? `<thead><tr><th style="text-align:left">Data</th><th style="text-align:left">Descrição</th><th style="text-align:left">Categoria</th><th style="text-align:left">Meio</th><th>Valor</th></tr></thead><tbody>` +
        shown.map((r, i) => `${exato != null && i === 0 && nEx ? `<tr class="sep"><td colspan="5">Valor exato</td></tr>` : ""}${exato != null && i === nEx ? `<tr class="sep"><td colspan="5">${nEx ? "Parecidos (±5%)" : "Nenhum com o valor exato. Parecidos (±5%):"}</td></tr>` : ""}<tr class="hit${isEx(r) ? " exact" : exato != null ? " near" : ""}" data-i="${i}">
          <td>${r.d.slice(8, 10)}/${r.d.slice(5, 7)}/${r.d.slice(2, 4)}</td>
          <td class="dsc">${hl(r.desc)}<small>${selos(r)}</small></td>
          <td class="ct">${hl(r.cat)}</td>
          <td>${hl(r.meio || "")}${r.cartao ? `<small style="display:block;color:var(--muted);font-size:11px">${esc(r.cartao)}</small>` : ""}</td>
          <td class="v ${r.tipo === "receita" ? "in" : ""}">${isEx(r) ? "<mark>" : ""}${r.tipo === "receita" ? "+" : r.tipo === "gasto" ? "−" : ""}R$ ${brl(r.v)}${isEx(r) ? "</mark>" : ""}</td></tr>
          ${aberto === i ? detalhe(r) : ""}`).join("") + `</tbody>`
      : `<tbody><tr><td class="empty">Nada encontrado. Tente menos palavras ou um valor aproximado (ex.: ~130).</td></tr></tbody>`;
    $("bs-more").hidden = vazio || res.length <= limite;
    if (vazio) $("bs-sum").innerHTML += `<span style="color:var(--muted)">· mostrando os 20 mais recentes</span>`;
  }

  function detalhe(r) {
    const mes = r.d.slice(0, 7);
    const link = r.tipo === "receita" ? `../Receitas/?ano=${r.d.slice(0, 4)}&mes=${r.d.slice(5, 7)}`
      : r.tipo === "gasto" ? `../Gastos/?ano=${r.d.slice(0, 4)}&mes=${r.d.slice(5, 7)}&conta=${encodeURIComponent(r.conta)}` : "";
    return `<tr class="det"><td colspan="5"><div class="grid">
      ${r.postings.map((p) => `<div><span>${p.v >= 0 ? "entrou em" : "saiu de"}</span> ${esc(p.n)} · R$ ${brl(p.v)}</div>`).join("")}
      ${r.arquivo ? `<div><span>arquivo:</span> ${esc(r.arquivo)}</div>` : ""}
      ${r.fatura ? `<div><span>fatura:</span> ${esc(r.fatura)}</div>` : ""}
      </div><div class="acts">
        ${r.key ? (r.reemb
          ? `<button type="button" data-rb="${esc(r.key)}" data-f="">Não é reembolsável</button>`
          : Object.entries(EMP()).map(([k, n]) => `<button type="button" data-rb="${esc(r.key)}" data-f="${esc(k)}">Reembolsável pela ${esc(n)}</button>`).join("")) : ""}
        ${link ? `<a href="${link}">Ver no contexto (${MESES[+mes.slice(5, 7) - 1]}/${mes.slice(2, 4)})</a>` : ""}</div></td></tr>`;
  }

  let t;
  $("bs-q").addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { limite = 100; aberto = -1; render(); }, 120); });
  root.querySelectorAll(".adv input, .adv select").forEach((el) => el.addEventListener("input", () => { aberto = -1; render(); }));
  root.addEventListener("click", async (e) => {
    const rb = e.target.closest("[data-rb]");
    if (rb) {
      e.stopPropagation();
      rb.disabled = true;
      rb.textContent = "Salvando…";
      const res = await fetch("../Gastos/reembolso", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: rb.dataset.rb, fonte: rb.dataset.f }) });
      if (res.ok) location.reload(); else { rb.textContent = "Não consegui salvar"; }
      return;
    }
    const ex = e.target.closest("[data-ex]");
    if (ex) { $("bs-q").value = ex.dataset.ex; aberto = -1; render(); $("bs-q").focus(); return; }
    if (e.target.closest("tr.det")) return;
    const row = e.target.closest("tr.hit");
    if (row) { aberto = aberto === +row.dataset.i ? -1 : +row.dataset.i; render(); return; }
    if (e.target.id === "bs-more") { limite += 200; render(); }
  });
  render();
  $("bs-q").focus();
}

export default { onExtensionPageLoad() { start(); } };
