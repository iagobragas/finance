// Aba "Gastos": filtros por meio de pagamento, cartão, tipo, grupo, mês, categoria e busca.

// empresas que pagam/reembolsam (config/accounts.yaml → empresas): id da conta -> nome para exibir
const EMP = () => { try { return JSON.parse(document.getElementById("fin-cfg").textContent).empresas || {}; } catch { return {}; } };
const empNome = (k) => EMP()[k] || k;
const empId = (nome) => Object.keys(EMP()).find((k) => EMP()[k] === nome) || nome;
const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
const COR_MEIO = {
  "Crédito Inter": "var(--m1)", "Crédito Nubank": "var(--m2)", Pix: "var(--m3)",
  "Débito Inter": "var(--m4)", "Débito Nubank": "var(--m5)", "Pix no crédito": "var(--m6)",
};
const cor = (m) => COR_MEIO[m] || "var(--m-other)";
const brl = (v, cents = false) =>
  (v < 0 ? "−" : "") +
  Math.abs(v).toLocaleString("pt-BR", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 });
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const fmtData = (d) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;

function load(key, fallback) {
  try {
    const v = JSON.parse(localStorage.getItem(key));
    return v ?? fallback;
  } catch {
    return fallback;
  }
}
function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* sem armazenamento: filtros só nesta visita */
  }
}

function start() {
  const root = document.getElementById("gs");
  const src = document.getElementById("gs-data");
  if (!root || !src) return;
  const { rows, meios, per, viagens = [] } = JSON.parse(src.textContent);
  // parcela escrita no texto de lançamentos manuais "(parcela n de t)" vale como parcela também
  // e a descrição fica limpa: "Calça (Shinka, parcela 2 de 2)" -> "Calça (Shinka)" + selo "parcela 2 de 2"
  rows.forEach((r) => {
    const m = String(r.desc).match(/parcela\s*0*(\d+)\s*de\s*0*(\d+)/i);
    if (m && !r.parc) r.parc = `${+m[1]}/${+m[2]}`;
    r.nome = String(r.desc)
      .replace(/\s*\(\s*parcela[^)]*\)/i, "")          // "(Parcela 04 de 10)"
      .replace(/,\s*parcela\s*\d+\s*de\s*\d+/i, "")   // ", parcela 2 de 2"
      .replace(/\(\s*\)/, "")
      .trim();
  });
  // assinatura: categoria Assinaturas/Celular, ou a mesma cobrança em 3+ meses com valor parecido (±10%) e sem ser parcela
  const chave = (d) => String(d).toLowerCase().replace(/\(parcela.*$/, "").replace(/[\d*#.\-/]+/g, " ").replace(/\s+/g, " ").trim();
  const grupos = {};
  rows.forEach((r) => { if (!r.parc && r.v >= 5 && r.g === "Fixas") (grupos[chave(r.desc)] ||= []).push(r); });
  Object.values(grupos).forEach((g) => {
    const meses = new Set(g.map((r) => r.d.slice(0, 7)));
    if (meses.size < 3) return;
    const vals = g.map((r) => r.v).sort((a, b) => a - b);
    const med = vals[Math.floor(vals.length / 2)];
    const parecidos = g.filter((r) => Math.abs(r.v - med) <= med * 0.1);
    if (new Set(parecidos.map((r) => r.d.slice(0, 7))).size >= 3) parecidos.forEach((r) => (r.assin = "conta"));
  });
  rows.forEach((r) => { if (!r.parc && /Assinaturas|Celular/.test(r.acc)) r.assin = "assinatura"; });
  const $ = (id) => document.getElementById(id);

  const years = [...new Set(rows.map((r) => +r.d.slice(0, 4)))].sort();
  const saved = load("gs-filtros", {});
  // links vindos do Resumo (?ano=&mes=&conta=&grupo=) substituem os filtros salvos
  const q = new URLSearchParams(location.search);
  const fromLink = ["mes", "conta", "grupo", "de"].some((k) => q.has(k));
  const base0 = fromLink ? {} : saved;
  const st = {
    ano: years.includes(+q.get("ano")) ? +q.get("ano") : years.includes(saved.ano) ? saved.ano : years[years.length - 1],
    meio: new Set(base0.meio || []),
    cartao: new Set(base0.cartao || []),
    tipo: new Set(base0.tipo || []),
    grupo: new Set(q.get("grupo") ? [q.get("grupo")] : base0.grupo || []),
    mes: q.get("mes") || "", cat: "", busca: "", conta: q.get("conta") || "",
    de: q.get("de") || "", ate: q.get("ate") || "",
    sort: { k: "d", dir: -1 },
    all: false,
    per: "",
  };

  // atalhos de período: Este mês (padrão) · Este ciclo · Mês passado · Ano
  const hoje = per.hoje;
  const mesAnt = (() => { const [y, m] = hoje.split("-").map(Number); return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`; })();
  const ultimoDia = (ym) => { const [y, m] = ym.split("-").map(Number); return new Date(y, m, 0).getDate(); };
  function periodo(p) {
    st.per = p;
    st.mes = ""; st.de = ""; st.ate = "";
    if (p === "mes") { st.ano = +hoje.slice(0, 4); st.mes = hoje.slice(5, 7); }
    else if (p === "ciclo") { st.de = per.ciclo_de; st.ate = per.ciclo_ate; }
    else if (p === "mespass") { st.ano = +mesAnt.slice(0, 4); st.mes = mesAnt.slice(5, 7); }
    else if (p === "ano") { st.ano = +hoje.slice(0, 4); }
  }
  if (!["mes", "conta", "grupo", "de"].some((k) => q.has(k))) periodo(load("gs-per", "mes"));
  else if (q.has("de") && !q.has("conta") && !q.has("grupo")) st.per = q.get("de") === per.ciclo_de ? "ciclo" : "";

  // selos da coluna "Tipo": fixa/variável, parcela (quantas faltam) e reembolsável
  function tipoHtml(r) {
    const out = [];
    if (r.reemb) out.push(`<span class="b re">reembolsável · ${esc(empNome(r.reemb))}</span>`);
    else if (r.g === "Fixas") out.push(`<span class="b fx">Fixa</span>`);
    else if (r.g) out.push(`<span class="b vr">Variável</span>`);
    if (r.assin === "assinatura" && !r.parc) out.push(`<span class="b as" data-tip="Serviço cobrado todo mês até você cancelar">assinatura · mensal</span>`);
    if (r.assin === "conta" && !r.parc) out.push(`<span class="b as" data-tip="Conta que se repete todo mês com valor parecido (mensalidade, imposto)">conta mensal</span>`);
    if (r.parc) {
      const [n, t] = String(r.parc).split("/").map(Number);
      const faltam = t - n;
      out.push(`<span class="b pc" data-tip="Compra de ~R$ ${brl(r.v * t, true)} em ${t}x">parcela ${n} de ${t}${faltam ? ` · faltam ${faltam}` : " · última"}</span>`);
    }
    return out.join("");
  }
  const tipoDe = (r) => (r.reemb ? "Reembolsável" : r.parc ? "Parcelado" : r.assin ? "Recorrente" : "À vista");
  const match = (r, skip) =>
    (st.de ? r.d >= st.de && r.d <= st.ate : +r.d.slice(0, 4) === st.ano) &&
    (skip === "meio" || !st.meio.size || st.meio.has(r.meio)) &&
    (skip === "cartao" || !st.cartao.size || st.cartao.has(r.cartao)) &&
    (skip === "tipo" || st.lote || (st.tipo.size ? st.tipo.has(tipoDe(r)) : !r.reemb)) &&
    (skip === "grupo" || !st.grupo.size || st.grupo.has(r.g)) &&
    (skip === "mes" || !st.mes || r.d.slice(5, 7) === st.mes) &&
    (!st.conta || r.acc === st.conta || r.acc.startsWith(st.conta + ":")) &&
    (!st.cat || r.c === st.cat) &&
    (!st.busca || r.desc.toLowerCase().includes(st.busca));

  // chips com contagem calculada ignorando o próprio filtro (mostra o que cada opção traria)
  function chips(el, key, values, dot) {
    const base = rows.filter((r) => match(r, key));
    el.innerHTML = values
      .map((v) => {
        const n = base.filter((r) => (key === "tipo" ? tipoDe(r) : r[key === "grupo" ? "g" : key]) === v).length;
        const on = st[key].has(v);
        return `<button type="button" class="chip${on ? " on" : ""}" data-k="${key}" data-v="${esc(v)}" aria-pressed="${on}">
          ${dot ? `<i class="dotm" style="background:${cor(v)}"></i>` : ""}${esc(v)} <span class="n">${n}</span></button>`;
      })
      .join("");
  }

  function render() {
    save("gs-filtros", { ano: st.ano, meio: [...st.meio], cartao: [...st.cartao], tipo: [...st.tipo], grupo: [...st.grupo] });
    const doAno = rows.filter((r) => +r.d.slice(0, 4) === st.ano);

    $("gs-per").innerHTML = [["mes", "Este mês"], ["ciclo", "Este ciclo"], ["mespass", "Mês passado"], ["ano", "Ano"]]
      .map(([k, n]) => `<a href="#" data-per="${k}" class="${st.per === k ? "on" : ""}">${n}</a>`).join("") +
      (st.de && st.per !== "ciclo" ? `<a href="#" class="on" data-per="ciclo-sel" onclick="return false">${+st.de.slice(8, 10) === 16 ? "Ciclo " : ""}${fmtData(st.de)} → ${fmtData(st.ate)}</a>` : "");
    $("gs-years").style.display = (st.per && st.per !== "ano") || st.de ? "none" : "";
    $("gs-years").innerHTML = years.map((y) => `<a href="#" data-ano="${y}" class="${y === st.ano && !st.de ? "on" : ""}">${y}</a>`).join("");
    const presentes = new Set(doAno.map((r) => r.meio));
    chips($("f-meio"), "meio", meios.filter((m) => presentes.has(m)).concat([...presentes].filter((m) => !meios.includes(m))), true);
    const cartoes = [...new Set(doAno.map((r) => r.cartao).filter(Boolean))].sort();
    $("row-cartao").hidden = !cartoes.length;
    chips($("f-cartao"), "cartao", cartoes, false);
    chips($("f-tipo"), "tipo", ["À vista", "Parcelado", "Recorrente", "Reembolsável"], false);
    chips($("f-grupo"), "grupo", ["Fixas", "Variáveis"], false);

    const mesSel = $("f-mes");
    const meses = [...new Set(doAno.map((r) => r.d.slice(5, 7)))].sort();
    mesSel.innerHTML = `<option value="">Ano inteiro</option>` + meses.map((m) => `<option value="${m}"${m === st.mes ? " selected" : ""}>${MESES[+m - 1]}</option>`).join("");
    const cats = [...new Set(doAno.map((r) => r.c))].sort((a, b) => a.localeCompare(b, "pt"));
    $("f-cat").innerHTML = `<option value="">Todas as categorias</option>` + cats.map((c) => `<option${c === st.cat ? " selected" : ""}>${esc(c)}</option>`).join("");

    const nomeConta = (acc) => {
      const r = rows.find((x) => x.acc === acc || x.acc.startsWith(acc + ":"));
      if (!r) return acc;
      return r.acc === acc && r.s ? `${r.c} · ${r.s}` : r.c;
    };
    $("f-conta").innerHTML = st.conta ? `<span class="fchip">${esc(nomeConta(st.conta))}<button type="button" id="f-conta-x" aria-label="Remover filtro de categoria">×</button></span>` : "";

    const fr = rows.filter((r) => match(r));
    detail(fr, nomeConta);
    const total = fr.reduce((s, r) => s + r.v, 0);
    const compras = fr.filter((r) => r.v > 0);
    const maior = compras.reduce((m, r) => (!m || r.v > m.v ? r : m), null);
    const nMeses = new Set(fr.map((r) => r.d.slice(0, 7))).size || 1;
    $("k-total").textContent = `R$ ${brl(total)}`;
    if (st.per === "mes") {
      // ritmo: até hoje neste mês × até o mesmo dia no mês passado (mesmos filtros)
      const dia = hoje.slice(8, 10);
      const ateDia = Math.min(+dia, ultimoDia(mesAnt));
      const salvo = { ano: st.ano, mes: st.mes };
      st.ano = +mesAnt.slice(0, 4); st.mes = mesAnt.slice(5, 7);
      const antes = rows.filter((r) => match(r) && +r.d.slice(8, 10) <= ateDia).reduce((s, r) => s + r.v, 0);
      Object.assign(st, salvo);
      const dif = antes > 0 ? Math.round(((total - antes) / antes) * 100) : null; // base negativa (estornos) não dá %
      $("k-total-s").innerHTML = `até dia ${+dia} · mês passado no mesmo dia: R$ ${brl(antes)}` +
        (dif !== null ? ` <b style="color:var(${dif > 0 ? "--bad" : "--good"})">${dif > 0 ? "+" : ""}${dif}%</b>` : "");
    } else {
      $("k-total-s").textContent = st.de ? `${fmtData(st.de)} → ${fmtData(st.ate)}` : st.mes ? MESES[+st.mes - 1] + " de " + st.ano : `média R$ ${brl(total / nMeses)}/mês`;
    }
    $("k-n").textContent = fr.length.toLocaleString("pt-BR");
    $("k-n-s").textContent = `${compras.length} compras · ${fr.length - compras.length} estornos`;
    $("k-avg").textContent = `R$ ${brl(compras.length ? compras.reduce((s, r) => s + r.v, 0) / compras.length : 0, true)}`;
    $("k-max").textContent = maior ? `R$ ${brl(maior.v)}` : "–";
    $("k-max-s").textContent = maior ? `${fmtData(maior.d)} · ${maior.nome}` : "";

    // por meio (ignora o filtro de meio, para comparar; os não selecionados ficam apagados)
    const base = rows.filter((r) => match(r, "meio"));
    const porMeio = {};
    base.forEach((r) => (porMeio[r.meio] = (porMeio[r.meio] || 0) + r.v));
    const tot = Object.values(porMeio).reduce((a, b) => a + b, 0) || 1;
    const max = Math.max(...Object.values(porMeio), 1);
    $("by-meio").innerHTML = Object.entries(porMeio)
      .sort((a, b) => b[1] - a[1])
      .map(([m, v]) => `<button type="button" data-k="meio" data-v="${esc(m)}" class="${st.meio.size && !st.meio.has(m) ? "off" : ""}" data-tip="${esc(m)} · R$ ${brl(v, true)}">
          <span class="nm"><i class="dotm" style="background:${cor(m)}"></i>${esc(m)}</span>
          <span class="bar"><i style="width:${Math.max(0, (v / max) * 100)}%;background:${cor(m)}"></i></span>
          <span class="val">R$ ${brl(v)}</span><span class="pc">${Math.round((v / tot) * 100)}%</span></button>`)
      .join("") || `<p class="empty">Nenhum gasto com esses filtros.</p>`;

    // por categoria (o que mais pesou no período)
    const porCat = {};
    fr.forEach((r) => { const k = r.c + (r.g ? "|" + r.g : ""); porCat[k] = (porCat[k] || 0) + r.v; });
    const catList = Object.entries(porCat).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    const maxC = catList.length ? catList[0][1] : 1;
    $("by-cat").innerHTML = catList.map(([k, v]) => {
      const [c, g] = k.split("|");
      return `<button type="button" data-catf="${esc(c)}" class="${st.cat && st.cat !== c ? "off" : ""}" data-tip="${esc(c)} · R$ ${brl(v, true)}">
        <span class="nm"><i class="dotm" style="background:${g === "Fixas" ? "var(--fix)" : "var(--var)"}"></i>${esc(c)}</span>
        <span class="bar"><i style="width:${(v / maxC) * 100}%;background:${g === "Fixas" ? "var(--fix)" : "var(--var)"}"></i></span>
        <span class="val">R$ ${brl(v)}</span><span class="pc">${Math.round((v / (total || 1)) * 100)}%</span></button>`;
    }).join("") || `<p class="empty">Nenhum gasto com esses filtros.</p>`;
    // a tabela mês a mês só faz sentido olhando o ano
    $("t-mes").closest("section").style.display = st.mes || st.de ? "none" : "";

    // tabela mês × meio
    const grid = {};
    fr.forEach((r) => {
      const m = +r.d.slice(5, 7) - 1;
      (grid[r.meio] ||= Array(12).fill(0))[m] += r.v;
    });
    const linhas = Object.entries(grid).sort((a, b) => b[1].reduce((x, y) => x + y) - a[1].reduce((x, y) => x + y));
    const colTot = Array(12).fill(0);
    linhas.forEach(([, ms]) => ms.forEach((v, i) => (colTot[i] += v)));
    const cell = (v) => (v ? brl(v) : `<span class="z">·</span>`);
    $("t-mes").innerHTML =
      `<colgroup><col class="c-name">${MESES.map(() => "<col>").join("")}<col class="c-t"></colgroup>` +
      `<thead><tr><th></th>${MESES.map((m) => `<th>${m}</th>`).join("")}<th>Total</th></tr></thead><tbody>` +
      linhas.map(([m, ms]) => `<tr class="cat"><td><span style="display:inline-flex;align-items:center;gap:8px"><i class="dotm" style="background:${cor(m)}"></i>${esc(m)}</span></td>${ms.map((v, i) => `<td class="n" ${v ? `data-tip="${MESES[i]} · ${esc(m)} · R$ ${brl(v, true)}"` : ""}>${cell(v)}</td>`).join("")}<td class="n tot">${brl(ms.reduce((a, b) => a + b))}</td></tr>`).join("") +
      `<tr class="subtotal"><td>Total</td>${colTot.map((v) => `<td class="n">${cell(v)}</td>`).join("")}<td class="n tot">${brl(total)}</td></tr></tbody>`;

    // lista
    const { k, dir } = st.sort;
    const ord = [...fr].sort((a, b) => (k === "v" ? (a.v - b.v) * dir : a.d.localeCompare(b.d) * dir));
    const shown = st.all ? ord : ord.slice(0, 100);
    const arrow = (key) => (k === key ? (dir < 0 ? " ↓" : " ↑") : "");
    const L = st.lote;
    const marcaveis = L ? ord.filter((r) => r.key && r.v > 0 && !r.reemb) : [];
    if (L) { L.vis = new Set(marcaveis.map((r) => r.key)); }
    const ckTh = L ? `<th class="ck"><input type="checkbox" id="lote-all" aria-label="Selecionar todos" ${marcaveis.length && marcaveis.every((r) => L.sel.has(r.key)) ? "checked" : ""}></th>` : "";
    const ckTd = (r) => (L ? `<td class="ck">${r.key && r.v > 0 && !r.reemb ? `<input type="checkbox" data-ck="${esc(r.key)}" ${L.sel.has(r.key) ? "checked" : ""} aria-label="Selecionar">` : ""}</td>` : "");
    $("t-list").innerHTML =
      `<thead><tr>${ckTh}<th class="sort" data-sort="d" style="text-align:left">Data${arrow("d")}</th><th style="text-align:left">Descrição</th><th style="text-align:left">Tipo</th><th style="text-align:left">Categoria</th><th style="text-align:left">Meio</th><th class="sort" data-sort="v">Valor${arrow("v")}</th><th style="text-align:left">Reembolso</th></tr></thead><tbody>` +
      (shown.length
        ? (L ? ord : shown).map((r) => `<tr class="cat">${ckTd(r)}<td>${fmtData(r.d)}</td><td class="desc" title="${esc(r.desc)}">${esc(r.nome)}</td><td class="tipo">${tipoHtml(r)}</td><td class="cat"><a href="../../account/${esc(r.acc)}/">${esc(r.c)}</a>${r.s ? `<small>${esc(r.s)}</small>` : ""}</td><td class="meio"><span style="display:inline-flex;align-items:center;gap:6px"><i class="dotm" style="background:${cor(r.meio)}"></i>${esc(r.meio)}</span>${r.cartao ? `<small>${esc(r.cartao)}</small>` : ""}</td><td class="n ${r.v < 0 ? "neg" : ""}">${brl(r.v, true)}</td><td>${r.key ? `<button type="button" class="rbtn${r.reemb ? " on" : ""}" data-rb="${esc(r.key)}" data-cur="${esc(r.reemb)}">${r.reemb ? `✓ ${esc(empNome(r.reemb))}` : "Reembolso"}</button>` : ""}</td></tr>`).join("")
        : `<tr><td colspan="${L ? 8 : 7}" class="empty">Nenhum gasto com esses filtros.</td></tr>`) +
      `</tbody>`;
    $("l-sub").textContent = `${fr.length} lançamentos${fr.length > shown.length ? ` · mostrando os ${shown.length} primeiros` : ""}`;
    $("l-more").hidden = !!L || st.all || fr.length <= 100;
    if (L) loteResumo(ord);
  }

  function detail(fr, nomeConta) {
    const box = $("detail");
    const alvo = st.conta ? nomeConta(st.conta) : st.grupo.size === 1 && !st.cat ? `Despesas ${[...st.grupo][0].toLowerCase()}` : st.cat;
    box.hidden = !alvo;
    if (!alvo) return;
    const mesNome = st.mes ? ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"][+st.mes - 1] : "";
    $("d-eyebrow").textContent = st.de ? `Ciclo ${fmtData(st.de)} → ${fmtData(st.ate)}` : st.mes ? `${mesNome} de ${st.ano}` : `${st.ano} inteiro`;
    $("d-title").textContent = alvo;

    // evolução: mesmos filtros, todos os meses
    const ano = rows.filter((r) => match(r, "mes"));
    const porMes = Array(12).fill(0);
    ano.forEach((r) => (porMes[+r.d.slice(5, 7) - 1] += r.v));
    const ativos = porMes.filter((v) => v);
    const media = ativos.length ? ativos.reduce((a, b) => a + b) / ativos.length : 0;
    const total = fr.reduce((s, r) => s + r.v, 0);
    const mi = st.mes ? +st.mes - 1 : -1;
    const ant = mi > 0 ? porMes[mi - 1] : null;
    const diff = (a, b) => {
      if (!b) return "";
      const p = Math.round(((a - b) / b) * 100);
      return `<b class="${p > 0 ? "up" : "down"}">${p > 0 ? "+" : ""}${p}%</b>`;
    };
    $("d-stats").innerHTML =
      `<div class="big">R$ ${brl(total, true)}</div>` +
      `<div class="drow"><span>Compras</span><b>${fr.filter((r) => r.v > 0).length}</b></div>` +
      (st.mes ? `<div class="drow"><span>Média mensal no ano (R$ ${brl(media)})</span>${diff(total, media) || "<b>–</b>"}</div>` : `<div class="drow"><span>Média por mês</span><b>R$ ${brl(media)}</b></div>`) +
      (ant !== null ? `<div class="drow"><span>Mês anterior (R$ ${brl(ant)})</span>${diff(total, ant) || "<b>–</b>"}</div>` : "") +
      `<div class="drow"><span>Total no ano</span><b>R$ ${brl(porMes.reduce((a, b) => a + b, 0))}</b></div>`;

    const W = 600, H = 150, pb = 18, col = W / 12, bw = col * 0.56;
    const peak = Math.max(...porMes, 1);
    const y = (v) => (H - pb) - (v / peak) * (H - pb - 10);
    $("d-trend").innerHTML =
      `<line x1="0" x2="${W}" y1="${H - pb}" y2="${H - pb}"/>` +
      (media ? `<line class="avg" x1="0" x2="${W}" y1="${y(media)}" y2="${y(media)}"/>` : "") +
      porMes.map((v, i) => (v > 0 ? `<rect data-mes="${String(i + 1).padStart(2, "0")}" class="${i === mi ? "sel" : ""}" x="${col * i + (col - bw) / 2}" y="${y(v)}" width="${bw}" height="${H - pb - y(v)}" rx="3" data-tip="${MESES[i]} · R$ ${brl(v, true)}"/>` : "")).join("") +
      MESES.map((m, i) => `<text x="${col * i + col / 2}" y="${H - 4}" text-anchor="middle" class="${i === mi ? "on" : ""}">${m}</text>`).join("");

    // onde: agrupa pela descrição (sem o número da parcela)
    const top = {};
    fr.forEach((r) => {
      const k = r.nome.replace(/^(Compra no débito|Pix enviado) - /, "");
      top[k] = (top[k] || 0) + r.v;
    });
    const lista = Object.entries(top).sort((a, b) => b[1] - a[1]).slice(0, 7);
    const mx = lista.length ? lista[0][1] : 1;
    $("d-top").innerHTML = lista.map(([k, v]) => `<a href="#" data-busca="${esc(k)}" class="variaveis"><span class="l"><span>${esc(k)}</span><span>R$ ${brl(v)}</span></span><span class="bar"><i style="width:${Math.max(0, (v / mx) * 100)}%"></i></span></a>`).join("") || `<p class="empty">Nada neste período.</p>`;
  }

  // ---- marcar vários como reembolso (período de uma viagem)
  function loteResumo(ord) {
    const L = st.lote;
    const sel = ord.filter((r) => L.sel.has(r.key));
    const tot = sel.reduce((s, r) => s + r.v, 0);
    $("lote-n").innerHTML = sel.length ? `<b>${sel.length}</b> selecionados · <b>R$ ${brl(tot, true)}</b>` : "Nenhum selecionado";
    root.querySelectorAll("[data-lote]").forEach((b) => (b.disabled = !sel.length && !$("lote-mem").checked));
  }
  function loteAbrir() {
    const hoje = new Date().toISOString().slice(0, 10);
    const de = st.de || hoje, ate = st.ate || hoje;
    st.lote = { sel: new Set(), vis: new Set(), prev: { de: st.de, ate: st.ate, mes: st.mes, per: st.per } };
    $("lote").hidden = false; $("lote-on").hidden = true;
    $("lote-de").value = de; $("lote-ate").value = ate;
    lotePeriodo();
  }
  function lotePeriodo() {
    const de = $("lote-de").value, ate = $("lote-ate").value;
    if (!de || !ate) return;
    st.de = de <= ate ? de : ate; st.ate = de <= ate ? ate : de; st.mes = "";
    st.ano = +st.de.slice(0, 4);
    render();
    // período novo: pré-seleciona o que parece da viagem; fica de fora o que quase nunca é reembolsado
    // (cartão de alguém da família, contas fixas e assinaturas, saúde, tarifas)
    const fora = (r) => /Familia|Saude|Tarifas/.test(r.acc) || r.g === "Fixas" || r.assin || /Nubank/.test(r.meio);
    st.lote.sel = new Set(rows.filter((r) => st.lote.vis.has(r.key) && !fora(r)).map((r) => r.key));
    render();
  }
  function loteFechar() {
    const p = st.lote.prev;
    st.lote = null; Object.assign(st, p);
    $("lote").hidden = true; $("lote-on").hidden = false;
    render();
  }
  // períodos lembrados (viagens): chips com ✕ para esquecer
  const dmy = (d) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;
  if (viagens.length) {
    $("viagens").hidden = false;
    $("viagens").innerHTML = "Períodos lembrados:" + viagens.map((v) =>
      `<span class="vg" title="Todo gasto nesse período entra como reembolso ${esc(empNome(v.fonte))}, inclusive o que ainda vai chegar">${esc(v.nome || "Viagem")} · ${dmy(v.de)}→${dmy(v.ate)} · ${esc(empNome(v.fonte))}<button type="button" data-vg-de="${v.de}" data-vg-ate="${v.ate}" aria-label="Esquecer período">×</button></span>`).join("");
    $("viagens").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-vg-de]");
      if (!b || !confirm("Esquecer este período? Os gastos marcados só por ele voltam a ser seus.")) return;
      b.disabled = true;
      const res = await fetch("periodo_remover", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ de: b.dataset.vgDe, ate: b.dataset.vgAte }) });
      if (res.ok) location.reload();
    });
  }
  $("lote-mem").addEventListener("change", () => loteResumo([]) || render());
  $("lote-on").addEventListener("click", loteAbrir);
  $("lote-off").addEventListener("click", loteFechar);
  $("lote-de").addEventListener("change", lotePeriodo);
  $("lote-ate").addEventListener("change", lotePeriodo);
  root.addEventListener("change", (e) => {
    if (!st.lote) return;
    const ck = e.target.closest("[data-ck]");
    if (ck) { ck.checked ? st.lote.sel.add(ck.dataset.ck) : st.lote.sel.delete(ck.dataset.ck); return render(); }
    if (e.target.id === "lote-all") {
      st.lote.sel = e.target.checked ? new Set(st.lote.vis) : new Set();
      return render();
    }
  });
  root.querySelectorAll("[data-lote]").forEach((b) => b.addEventListener("click", async () => {
    const keys = [...st.lote.sel];
    if (!keys.length && !$("lote-mem").checked) return;
    root.querySelectorAll("[data-lote]").forEach((x) => (x.disabled = true));
    $("lote-n").textContent = "Marcando e reimportando…";
    const periodo = $("lote-mem").checked ? { de: $("lote-de").value, ate: $("lote-ate").value, nome: $("lote-nome").value.trim() } : null;
    const res = await fetch("reembolso", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ keys, fonte: b.dataset.lote, periodo }) });
    if (res.ok) location.reload();
    else { $("lote-n").textContent = (await res.json().catch(() => ({}))).erro || "Não consegui marcar."; loteResumo([]); }
  }));

  let pop;
  function closePop() { pop?.remove(); pop = null; }
  async function marcar(key, fonte) {
    closePop();
    $("l-sub").textContent = "Reimportando…";
    const res = await fetch("reembolso", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key, fonte }) });
    if (res.ok) location.reload();
    else $("l-sub").textContent = (await res.json().catch(() => ({}))).erro || "Não consegui marcar.";
  }
  document.addEventListener("click", (e) => { if (pop && !e.target.closest(".rb-pop,[data-rb]")) closePop(); });

  root.addEventListener("change", (e) => {
    const sel = e.target.closest("select[data-rbk]");
    if (sel) { sel.disabled = true; marcar(sel.dataset.rbk, sel.value); }
  });
  root.addEventListener("click", (e) => {
    const rb = e.target.closest("[data-rb]");
    if (rb) {
      closePop();
      pop = document.createElement("div");
      pop.className = "rb-pop";
      const cs = getComputedStyle(root); // o popover fica fora de .rs: copia as cores do tema
      ["--surface", "--surface-2", "--line-2", "--ink", "--ink-2", "--good", "--bad"].forEach((v) => pop.style.setProperty(v, cs.getPropertyValue(v)));
      const cur = rb.dataset.cur;
      pop.innerHTML = `<p>Quem vai te reembolsar?</p>` +
        Object.entries(EMP()).map(([v, n]) => `<button type="button" data-f="${v}" class="${cur === v ? "on" : ""}">${n}</button>`).join("") +
        (cur ? `<button type="button" data-f="" class="off">Não é reembolsável</button>` : "");
      const r = rb.getBoundingClientRect();
      pop.style.top = `${r.bottom + 6 + scrollY}px`;
      pop.style.left = `${Math.max(8, r.right - 220 + scrollX)}px`;
      document.body.appendChild(pop);
      pop.addEventListener("click", (ev) => { const b = ev.target.closest("[data-f]"); if (b) marcar(rb.dataset.rb, b.dataset.f); });
      return;
    }
    const cf = e.target.closest("[data-catf]");
    if (cf) {
      st.cat = st.cat === cf.dataset.catf ? "" : cf.dataset.catf;
      return render();
    }
    const barra = e.target.closest("#d-trend [data-mes]");
    if (barra) {
      st.mes = st.mes === barra.dataset.mes ? "" : barra.dataset.mes;
      return render();
    }
    const busca = e.target.closest("[data-busca]");
    if (busca) {
      e.preventDefault();
      st.busca = busca.dataset.busca.toLowerCase();
      $("f-busca").value = busca.dataset.busca;
      return render();
    }
    if (e.target.id === "f-conta-x" || e.target.id === "d-close") {
      st.conta = "";
      st.de = st.ate = "";
      st.cat = "";
      if (e.target.id === "d-close") st.grupo.clear();
      return render();
    }
    const chip = e.target.closest("[data-k]");
    if (chip) {
      const set = st[chip.dataset.k];
      set.has(chip.dataset.v) ? set.delete(chip.dataset.v) : set.add(chip.dataset.v);
      st.all = false;
      return render();
    }
    const pe = e.target.closest("[data-per]");
    if (pe && pe.dataset.per === "ciclo-sel") { e.preventDefault(); return; }
    if (pe) {
      e.preventDefault();
      periodo(pe.dataset.per);
      save("gs-per", pe.dataset.per);
      return render();
    }
    const ano = e.target.closest("[data-ano]");
    if (ano) {
      e.preventDefault();
      st.per = "ano";
      st.de = st.ate = "";
      st.ano = +ano.dataset.ano;
      st.mes = "";
      st.cat = "";
      return render();
    }
    const sort = e.target.closest("[data-sort]");
    if (sort) {
      const key = sort.dataset.sort;
      st.sort = { k: key, dir: st.sort.k === key ? -st.sort.dir : -1 };
      return render();
    }
    if (e.target.id === "l-more") {
      st.all = true;
      return render();
    }
    if (e.target.id === "f-limpar") {
      ["meio", "cartao", "tipo", "grupo"].forEach((k) => st[k].clear());
      st.mes = st.cat = st.busca = st.conta = st.de = st.ate = "";
      $("f-busca").value = "";
      return render();
    }
  });
  $("f-mes").addEventListener("change", (e) => ((st.mes = e.target.value), (st.per = e.target.value ? "" : "ano"), render()));
  $("f-cat").addEventListener("change", (e) => ((st.cat = e.target.value), render()));
  let t;
  $("f-busca").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => ((st.busca = e.target.value.trim().toLowerCase()), render()), 150);
  });

  // tooltip (mesmo estilo da página Resumo)
  let tip = document.getElementById("rs-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "rs-tip";
    document.body.appendChild(tip);
  }
  root.addEventListener("mousemove", (e) => {
    const el = e.target.closest("[data-tip]");
    if (!el) return void (tip.style.opacity = "0");
    tip.textContent = el.dataset.tip;
    tip.style.left = `${Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8)}px`;
    tip.style.top = `${e.clientY + 16}px`;
    tip.style.opacity = "1";
  });
  root.addEventListener("mouseleave", () => (tip.style.opacity = "0"));

  render();
}

export default {
  onExtensionPageLoad() {
    start();
  },
};
