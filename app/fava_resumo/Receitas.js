// Aba "Receitas": fonte × mês, concentração, previsão e lista de recebimentos.

// empresas que pagam/reembolsam (config/accounts.yaml → empresas): id da conta -> nome para exibir
const EMP = () => { try { return JSON.parse(document.getElementById("fin-cfg").textContent).empresas || {}; } catch { return {}; } };
const empNome = (k) => EMP()[k] || k;
const empId = (nome) => Object.keys(EMP()).find((k) => EMP()[k] === nome) || nome;
const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
const LONGOS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
const brl = (v, c = false) =>
  (v < 0 ? "−" : "") + Math.abs(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: c ? 2 : 0, maximumFractionDigits: c ? 2 : 0 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function start() {
  const root = document.getElementById("rc");
  const src = document.getElementById("rc-data");
  if (!root || !src) return;
  const $ = (id) => document.getElementById(id);
  const { rows, previsto, regras, hoje, mei, reembolsos, conferencia, salario, notas } = JSON.parse(src.textContent);

  // cor fixa por fonte (ordem alfabética da conta), nunca pelo ranking
  const contas = [...new Set([...rows.map((r) => r.acc), ...previsto.map((p) => p.acc)])].sort();
  const cor = (acc) => (contas.indexOf(acc) < 5 ? `var(--f${contas.indexOf(acc) + 1})` : "var(--f-other)");
  const nome = Object.fromEntries([...rows, ...previsto].map((r) => [r.acc, r.fonte]));

  const years = [...new Set(rows.map((r) => +r.d.slice(0, 4)))].sort();
  const q = new URLSearchParams(location.search);
  const st = {
    ano: years.includes(+q.get("ano")) ? +q.get("ano") : years[years.length - 1],
    mes: q.get("mes") || "",
    fonte: q.get("fonte") || "",
  };
  const anoHoje = +hoje.slice(0, 4);

  function render() {
    const doAno = rows.filter((r) => +r.d.slice(0, 4) === st.ano);
    const prevAno = st.ano === anoHoje ? previsto.filter((p) => +p.ym.slice(0, 4) === st.ano) : [];
    const selF = (r) => !st.fonte || r.acc === st.fonte;

    $("rc-years").innerHTML = years.map((y) => `<a href="#" data-ano="${y}" class="${y === st.ano ? "on" : ""}">${y}</a>`).join("");
    const fontesAno = contas.filter((a) => doAno.some((r) => r.acc === a) || prevAno.some((p) => p.acc === a));
    $("rc-fontes").innerHTML = [`<button type="button" class="chip${!st.fonte ? " on" : ""}" data-fonte="">Todas</button>`]
      .concat(fontesAno.map((a) => `<button type="button" class="chip${st.fonte === a ? " on" : ""}" data-fonte="${esc(a)}"><i class="dotf" style="background:${cor(a)}"></i>${esc(nome[a])}</button>`))
      .join("");
    const mesesComDado = [...new Set(doAno.map((r) => r.d.slice(5, 7)))].sort();
    $("rc-mes").innerHTML = `<option value="">Ano inteiro</option>` + mesesComDado.map((m) => `<option value="${m}"${m === st.mes ? " selected" : ""}>${LONGOS[+m - 1]}</option>`).join("");

    // matriz fonte × mês (realizado e previsto)
    const real = {}, prev = {};
    doAno.forEach((r) => ((real[r.acc] ||= Array(12).fill(0))[+r.d.slice(5, 7) - 1] += r.v));
    prevAno.forEach((p) => ((prev[p.acc] ||= Array(12).fill(0))[+p.ym.slice(5, 7) - 1] += p.v));
    const fcMes = new Set(prevAno.map((p) => +p.ym.slice(5, 7) - 1));
    const totMes = (obj, filtro) => Array.from({ length: 12 }, (_, i) => Object.entries(obj).filter(([a]) => !filtro || a === filtro).reduce((s, [, v]) => s + v[i], 0));
    const realMes = totMes(real, st.fonte), prevMes = totMes(prev, st.fonte);
    const ativos = realMes.map((v, i) => [v, i]).filter(([v]) => v);

    // KPIs
    const fr = doAno.filter((r) => selF(r) && (!st.mes || r.d.slice(5, 7) === st.mes));
    const total = fr.reduce((s, r) => s + r.v, 0);
    const media = ativos.length ? ativos.reduce((s, [v]) => s + v, 0) / ativos.length : 0;
    const quem = st.fonte ? nome[st.fonte] : "todas as fontes";
    $("k1-l").textContent = st.mes ? `Recebido em ${LONGOS[+st.mes - 1]}` : `Recebido em ${st.ano}`;
    $("k1").textContent = `R$ ${brl(total)}`;
    $("k1-s").textContent = `${fr.length} recebimentos · ${quem}`;
    $("k2").textContent = `R$ ${brl(media)}`;
    $("k2-s").textContent = `${ativos.length} meses com receita`;
    const ref = st.mes ? +st.mes - 1 : ativos.length ? ativos[ativos.length - 1][1] : -1;
    const ant = ref > 0 ? realMes[ref - 1] : 0;
    const parcial = ref === new Date().getMonth() && st.ano === new Date().getFullYear();
    $("k3-l").textContent = ref >= 0 ? `${MESES[ref]}${parcial ? " (até hoje)" : ""} vs ${MESES[Math.max(ref - 1, 0)]}` : "Comparado ao mês anterior";
    if (ref > 0 && ant) {
      const p = Math.round(((realMes[ref] - ant) / ant) * 100);
      $("k3").innerHTML = `<span class="${p >= 0 ? "pos" : "neg"}">${p > 0 ? "+" : ""}${p}%</span>`;
      $("k3-s").textContent = `R$ ${brl(realMes[ref])} contra R$ ${brl(ant)}`;
    } else {
      $("k3").textContent = "–";
      $("k3-s").textContent = "sem mês anterior para comparar";
    }
    const totPrev = prevMes.reduce((a, b) => a + b, 0);
    $("k4").textContent = totPrev ? `R$ ${brl(totPrev)}` : "–";
    $("k4-s").innerHTML = totPrev ? `${fcMes.size} meses · <a href="../Planejamento/">ajustar</a>` : st.ano === anoHoje ? "sem previsão" : "ano encerrado";

    // gráfico empilhado por fonte
    const W = 960, H = 260, pl = 48, pb = 26, pt = 10, col = (W - pl) / 12, bw = Math.min(34, col * 0.5);
    const fontesG = st.fonte ? [st.fonte] : fontesAno;
    const alturas = Array.from({ length: 12 }, (_, i) => fontesG.reduce((s, a) => s + (fcMes.has(i) ? prev[a]?.[i] || 0 : real[a]?.[i] || 0), 0));
    const peak = Math.max(...alturas, 1);
    const step = [500, 1000, 2000, 2500, 5000, 10000, 20000].find((s) => peak / s <= 5) || 50000;
    const top = step * (Math.floor(peak / step) + 1);
    const y = (v) => pt + (H - pt - pb) * (1 - v / top);
    let svg = `<g class="grid">`;
    for (let v = 0; v <= top; v += step) svg += `<line x1="${pl}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><text x="${pl - 8}" y="${y(v) + 4}" text-anchor="end">${brl(v)}</text>`;
    svg += `</g>`;
    for (let i = 0; i < 12; i++) {
      const x = pl + col * i + (col - bw) / 2;
      let base = 0;
      const fc = fcMes.has(i);
      fontesG.forEach((a) => {
        const v = fc ? prev[a]?.[i] || 0 : real[a]?.[i] || 0;
        if (v <= 0) return;
        const y1 = y(base + v), h = y(base) - y1 - 2;
        const dim = st.mes && +st.mes - 1 !== i;
        svg += `<rect class="seg${fc ? " fc" : ""}${dim ? " dim" : ""}" x="${x}" y="${y1}" width="${bw}" height="${Math.max(h, 1)}" rx="3" fill="${cor(a)}" stroke="${cor(a)}" data-mes="${fc ? "" : String(i + 1).padStart(2, "0")}" data-tip="${MESES[i]} · ${esc(nome[a])}${fc ? " · previsto" : ""}: R$ ${brl(v, true)}"/>`;
        base += v;
      });
      svg += `<text x="${pl + col * i + col / 2}" y="${H - 8}" text-anchor="middle" class="${st.mes && +st.mes - 1 === i ? "on" : ""}">${MESES[i]}</text>`;
    }
    svg += `<line class="base" x1="${pl}" x2="${W}" y1="${y(0)}" y2="${y(0)}"/>`;
    $("rc-chart").innerHTML = svg;
    $("rc-legend").innerHTML = fontesG.map((a) => `<span><i class="dotf" style="background:${cor(a)}"></i>${esc(nome[a])}</span>`).join("") +
      (fcMes.size ? `<span><i class="dotf" style="border:1.5px dashed var(--ink-2);background:none"></i>previsto</span>` : "");

    // concentração (ano realizado, todas as fontes)
    const porFonte = fontesAno.map((a) => [a, (real[a] || []).reduce((s, v) => s + v, 0)]).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    const totAno = porFonte.reduce((s, [, v]) => s + v, 0) || 1;
    const maior = porFonte[0];
    $("rc-conc").innerHTML = porFonte.length
      ? `<div class="bar">${porFonte.map(([a, v]) => `<i style="width:${(v / totAno) * 100}%;background:${cor(a)}" data-tip="${esc(nome[a])}: ${Math.round((v / totAno) * 100)}%"></i>`).join("")}</div>` +
        porFonte.map(([a, v]) => `<div class="row"><span><i class="dotf" style="background:${cor(a)};margin-right:8px"></i>${esc(nome[a])} <small style="color:var(--muted)">previsão por ${esc(regras[a] || "média")}</small></span><b>R$ ${brl(v)}</b><span class="pc">${Math.round((v / totAno) * 100)}%</span></div>`).join("") +
        (maior && maior[1] / totAno >= 0.5
          ? `<div class="warn">${Math.round((maior[1] / totAno) * 100)}% da receita do ano vem de <b>${esc(nome[maior[0]])}</b>. Se essa fonte atrasar ou parar, o mês não fecha.</div>`
          : "")
      : `<p class="empty">Sem receitas neste ano.</p>`;

    // tabela fonte × mês
    const cell = (v, fc) => `<td class="n${fc ? " fc" : ""}">${v ? brl(v) : '<span class="z">·</span>'}</td>`;
    const linha = (a) => {
      const r = real[a] || Array(12).fill(0), p = prev[a] || Array(12).fill(0);
      const tot = r.reduce((s, v) => s + v, 0);
      return `<tr class="cat"><td><span style="display:inline-flex;align-items:center;gap:8px"><i class="dotf" style="background:${cor(a)}"></i>${esc(nome[a])}</span></td>${r.map((v, i) => cell(fcMes.has(i) ? p[i] : v, fcMes.has(i))).join("")}<td class="n tot">${brl(tot)}</td></tr>`;
    };
    const totR = totMes(real), totP = totMes(prev);
    $("rc-table").innerHTML =
      `<colgroup><col class="c-name">${MESES.map(() => "<col>").join("")}<col class="c-t"></colgroup>` +
      `<thead><tr><th></th>${MESES.map((m, i) => `<th>${m}${fcMes.has(i) ? '<small class="fc-h">previsto</small>' : ""}</th>`).join("")}<th>Total</th></tr></thead><tbody>` +
      fontesAno.map(linha).join("") +
      `<tr class="subtotal"><td>Total</td>${totR.map((v, i) => cell(fcMes.has(i) ? totP[i] : v, fcMes.has(i))).join("")}<td class="n tot">${brl(totR.reduce((s, v) => s + v, 0))}</td></tr></tbody>`;

    // MEI: faturamento do ano contra o limite
    // bruto: salário + reembolsos que entraram no CNPJ (se vêm na nota fiscal, contam para o limite)
    const fat = doAno.reduce((s, r) => s + r.v + (r.reemb || 0), 0);
    const reembAno = doAno.reduce((s, r) => s + (r.reemb || 0), 0);
    const fatPrev = fat + prevAno.reduce((s, p) => s + p.v, 0);
    const pc = (fat / mei.limite) * 100, pcPrev = (fatPrev / mei.limite) * 100;
    const cls = pcPrev >= 100 ? "bad" : pcPrev >= 85 ? "warn" : "";
    $("rc-mei").innerHTML = `
      <div>
        <p class="eyebrow">Faturamento MEI em ${st.ano}</p>
        <div class="big">R$ ${brl(fat)} <span style="font-size:15px;color:var(--muted);font-weight:500">de R$ ${brl(mei.limite)}</span></div>
        <div class="lim" data-tip="Realizado ${pc.toFixed(0)}% · com a previsão ${pcPrev.toFixed(0)}%"><i class="prev" style="width:${Math.min(pcPrev, 100)}%"></i><i class="real ${cls}" style="width:${Math.min(pc, 100)}%"></i></div>
        <div class="scale"><span>${pc.toFixed(0)}% usado</span><span>${st.ano === anoHoje ? `previsão dez: ${pcPrev.toFixed(0)}% (R$ ${brl(fatPrev)})` : ""}</span></div>
      </div>
      <ul>
        <li>${pcPrev < 85 ? "<b>Dentro do limite</b> com folga, mesmo com a previsão até dezembro." : pcPrev < 100 ? "<b>Perto do limite</b>: acompanhe, acima dele o MEI é desenquadrado." : "<b>A previsão passa do limite do MEI.</b> Converse com um contador antes de dezembro."}</li>
        ${reembAno ? `<li>Inclui <b>R$ ${brl(reembAno)} de reembolsos</b> que entraram no CNPJ: se eles vêm na nota fiscal, contam para o limite do MEI.</li>` : ""}
        <li><b>DAS</b> vence todo dia 20 (aparece na aba Ciclo).</li>
        <li><b>Nota fiscal</b>: MEI precisa emitir para clientes que são empresa (CNPJ), como as empresas que pagam você. Confirme com seu contador.</li>
        <li><b>Declaração anual (DASN-SIMEI)</b> até 31/05: use o total de ${st.ano} desta tela.</li>
      </ul>`;

    // reembolsos
    const RB = reembolsos;
    const fontesRB = [...new Set([...Object.keys(RB.pendente), ...Object.keys(RB.marcados).map((k) => k.split("|")[0])])];
    const acimaAno = RB.acima.filter((a) => +a.d.slice(0, 4) === st.ano);
    // notas fiscais emitidas × recebido
    const NT = notas || { linhas: [] };
    const nts = NT.linhas.filter((l) => +(l.recebido_em || l.emissao).slice(0, 4) === st.ano);
    const dmy = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(2, 4)}` : "—");
    const ST = { ok: "✓ confere", diferente: "valor diferente", sem_nota: "sem nota", aguardando: "aguardando pagamento" };
    const problemas = nts.filter((l) => l.status === "diferente" || l.status === "sem_nota").length;
    $("rc-notas").innerHTML = `
      <div class="blk-head"><div><h3>Notas fiscais</h3><p>Cada NFS-e emitida conferida com o que caiu na conta. Arraste o XML (e o PDF) da nota para a aba Importar.</p></div>
        <div class="blk-sum"><span class="v">R$ ${brl(NT.total_ano?.[st.ano] || 0)}</span><span class="p">em notas em ${st.ano}${problemas ? ` · <b style="color:var(--warn-ink)">${problemas} para ver</b>` : ""}</span></div></div>
      ${nts.length ? `<div class="tw"><table class="list"><thead><tr><th style="text-align:left">Nota</th><th style="text-align:left">Empresa</th><th style="text-align:left">Competência</th><th>Valor da nota</th><th>Recebido</th><th style="text-align:left">Situação</th></tr></thead><tbody>` +
        nts.map((l) => `<tr class="cat"><td>${l.numero ? `nº ${l.numero}<small>emitida ${dmy(l.emissao)}${l.pdf ? " · PDF" : ""}</small>` : "—"}</td>
          <td>${esc(l.fonte)}${l.descricao ? `<small>${esc(l.descricao)}</small>` : ""}</td>
          <td>${l.competencia ? `${l.competencia.slice(5, 7)}/${l.competencia.slice(0, 4)}` : "—"}</td>
          <td class="n">${l.valor != null ? brl(l.valor, true) : "—"}</td>
          <td class="n">${l.recebido != null ? `${brl(l.recebido, true)}<small>${dmy(l.recebido_em)}</small>` : "—"}</td>
          <td><span class="nt-st ${l.status}">${ST[l.status]}${l.status === "diferente" ? ` (${l.dif > 0 ? "+" : "−"}R$ ${brl(Math.abs(l.dif), true)})` : ""}</span></td></tr>`).join("") +
        `</tbody></table></div>` : `<p class="note">Nenhuma nota em ${st.ano}.</p>`}
      ${NT.desde ? `<p class="note">Pagamentos sem nota só são cobrados a partir da primeira nota importada (${dmy(NT.desde)}). Para conferir meses anteriores, importe as notas antigas.</p>` : ""}`;

    $("rc-reemb").innerHTML = `
      <div class="blk-head"><div><h3>Reembolsos</h3><p>Gastos que a empresa devolve junto com o pagamento. Não contam como receita nem como despesa sua.</p></div></div>
      <div class="kpis" style="margin-top:14px">
        ${(fontesRB.length ? fontesRB : Object.values(EMP())).map((f) => `
          <div><p class="eyebrow">${esc(f)} · a receber</p><div class="v" style="font-size:22px;font-weight:700">R$ ${brl(RB.pendente[f] || 0, true)}</div>
          <div class="s" style="font-size:12px;color:var(--muted)">em ${st.ano}: R$ ${brl(RB.marcados[`${f}|${st.ano}`] || 0)} marcados · R$ ${brl(RB.recebidos[`${f}|${st.ano}`] || 0)} recebidos</div>
          <a href="../Contas/?conta=${encodeURIComponent("Assets:Reembolsos:" + empId(f))}" style="font-size:12px;font-weight:600;color:var(--accent);text-decoration:none">ver os gastos</a></div>`).join("")}
      </div>

      <p class="note">Para marcar: na aba Gastos ou Buscar, clique no botão <b>Reembolso</b> do lançamento; no Lançar, escolha a empresa em "Reembolsável?". A parte fixa de cada empresa fica em <code>config/reembolsos.yaml</code>.</p>`;

    // conferência: esperado × recebido
    const conf = conferencia.filter((c) => +c.d.slice(0, 4) === st.ano && (!st.fonte || nome[st.fonte] === c.fonte));
    const status = (c) => Math.abs(c.dif) < 1
      ? `<span class="pos">✓ bateu</span>`
      : c.dif > 0 ? `<span class="warn-t">+R$ ${brl(c.dif, true)} a mais</span><small>Hora extra? Informe no <a href="../Planejamento/">Planejamento</a>. Reembolso? Marque o gasto com ↩ em <a href="../Gastos/">Gastos</a>.</small>`
      : `<span class="neg">−R$ ${brl(-c.dif, true)} a menos</span><small>desconto, atraso ou pagamento parcial?</small>`;
    $("rc-conf").innerHTML = `
      <div class="blk-head"><div><h3>Conferência dos pagamentos</h3><p>Esperado = salário vigente + hora extra/bônus informados no <a href="../Planejamento/">Planejamento</a>. Reembolsos de gastos marcados são explicados à parte.</p></div></div>
      <div class="tw"><table class="list"><thead><tr><th style="text-align:left">Data</th><th style="text-align:left">Fonte</th><th>Esperado</th><th>Recebido</th><th style="text-align:left">Como foi separado</th><th style="text-align:left">Situação</th></tr></thead><tbody>
      ${conf.map((c) => `<tr class="cat"><td>${c.d.slice(8, 10)}/${c.d.slice(5, 7)}</td><td>${esc(c.fonte)}</td><td class="n">${brl(c.esperado, true)}</td><td class="n">${brl(c.recebido, true)}</td>
        <td>salário ${brl(c.recebido - c.extra - c.reemb - Math.max(c.dif, 0), true)}${c.extra ? ` + hora extra ${brl(c.extra, true)}` : ""}${c.reemb ? ` + reembolso ${brl(c.reemb, true)}` : ""}${c.dif >= 1 ? ` + <b class="warn-t">${brl(c.dif, true)} a identificar</b>` : ""}</td><td>${status(c)}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Nenhum pagamento com valor esperado neste ano.</td></tr>`}
      </tbody></table></div>`;

    // lista
    $("rc-sub").textContent = `${fr.length} recebimentos${st.mes ? ` em ${LONGOS[+st.mes - 1]}` : ` em ${st.ano}`}${st.fonte ? ` · ${nome[st.fonte]}` : ""}`;
    $("rc-list").innerHTML =
      `<thead><tr><th style="text-align:left">Data</th><th style="text-align:left">Fonte</th><th style="text-align:left">Descrição</th><th style="text-align:left">Entrou em</th><th>Valor</th></tr></thead><tbody>` +
      (fr.length
        ? fr.map((r) => `<tr class="cat"><td>${r.d.slice(8, 10)}/${r.d.slice(5, 7)}</td><td><span style="display:inline-flex;align-items:center;gap:6px"><i class="dotf" style="background:${cor(r.acc)}"></i>${esc(r.fonte)}</span></td><td class="desc" title="${esc(r.desc)}">${esc(r.desc)}${r.origem !== "extrato" ? `<span class="tag">${esc(r.origem)}</span>` : ""}${r.reemb ? `<small>+ R$ ${brl(r.reemb, true)} de reembolso no mesmo Pix (não conta como receita)</small>` : ""}</td><td>${esc(r.onde)}</td><td class="n">${brl(r.v, true)}</td></tr>`).join("")
        : `<tr><td colspan="5" class="empty">Nenhum recebimento com esses filtros.</td></tr>`) +
      `</tbody>`;
  }

  root.addEventListener("click", (e) => {
    const t = e.target.closest("[data-ano],[data-fonte],[data-mes]");
    if (!t) return;
    e.preventDefault();
    if (t.dataset.ano) { st.ano = +t.dataset.ano; st.mes = ""; }
    else if (t.dataset.fonte !== undefined) st.fonte = t.dataset.fonte;
    else if (t.dataset.mes) st.mes = st.mes === t.dataset.mes ? "" : t.dataset.mes;
    render();
  });
  $("rc-mes").addEventListener("change", (e) => { st.mes = e.target.value; render(); });

  // tooltip (mesmo estilo das outras abas)
  let tip = document.getElementById("rs-tip");
  if (!tip) { tip = document.createElement("div"); tip.id = "rs-tip"; document.body.appendChild(tip); }
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
  salarioEditor(root, salario, hoje, reembolsos.pendente || {});
}

// ------------------------------------------------------------------ salário (todo mês) e extras (uma vez)
function salarioEditor(root, sal, hoje, pendentes) {
  const box = document.getElementById("rc-sal");
  if (!box) return;
  const st = JSON.parse(JSON.stringify(sal));
  const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const ymTxt = (ym) => (ym ? `${MES[+ym.slice(5, 7) - 1]}/${ym.slice(2, 4)}` : "");
  const ymAnt = (ym) => { const [y, m] = ym.split("-").map(Number); return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`; };
  const valorEm = (f, ym) => { let v = +f.valor || 0; (f.aumentos || []).slice().sort((a, b) => a.desde.localeCompare(b.desde)).forEach((a) => { if (a.desde <= ym) v = +a.valor; }); return v; };
  let aberto = null; // qual formulário inline está aberto: "aum:<i>" ou "ext:<i>"

  async function salvar(msg) {
    box.querySelector(".sal-msg").textContent = "Salvando…";
    const res = await fetch("salvar_salario", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(st) });
    if (!res.ok) { box.querySelector(".sal-msg").textContent = "Não consegui salvar."; return; }
    try { sessionStorage.setItem("sal-msg", msg); } catch { /* ok */ }
    location.reload();
  }

  function fonteHtml(f, i) {
    const aum = (f.aumentos || []).slice().sort((a, b) => a.desde.localeCompare(b.desde));
    const prox = f.proximo ? f.proximo.slice(0, 7) : "";
    const extras = st.extras.map((x, k) => ({ ...x, k })).filter((x) => x.fonte === f.account);
    const extrasProx = extras.filter((x) => x.mes === prox).reduce((s, x) => s + (+x.valor || 0), 0);
    const salProx = f.modo === "fixo" && prox ? valorEm(f, prox) : null;
    // linha do tempo do salário: valor inicial -> cada aumento
    const passos = f.modo === "fixo"
      ? [{ txt: aum.length ? `até ${ymTxt(ymAnt(aum[0].desde))}` : "todo mês", v: +f.valor, i: -1 },
         ...aum.map((a, k) => ({ txt: `a partir de ${ymTxt(a.desde)}`, v: +a.valor, i: k }))]
      : [];
    return `
      <div class="src">
        <div class="src-h">
          <h4>${esc(f.name)}</h4>
          ${f.proximo ? `<span class="prox">próximo pagamento ~${f.proximo.slice(8, 10)}/${f.proximo.slice(5, 7)}</span>` : ""}
        </div>

        <div class="lane">
          <div class="lane-t">Todo mês <small>salário</small></div>
          <div class="lane-b">
            ${f.modo === "fixo" ? passos.map((p, n) => `${n ? '<span class="arr">→</span>' : ""}
              <span class="chip-v"><small>${p.txt}</small><b>R$ ${brl(p.v, true)}</b>${p.i >= 0 ? `<button class="x" data-delaum="${i}:${p.i}" title="Remover aumento">×</button>` : `<button class="ed" data-editbase="${i}" title="Corrigir valor">✎</button>`}</span>`).join("")
              : `<span class="muted">pela média dos últimos meses</span> <button class="mini-btn" data-fixo="${i}">usar valor fixo</button>`}
            ${f.modo === "fixo" ? (aberto === `aum:${i}`
              ? `<span class="inline">a partir de <input type="month" id="aum-m" value="${prox || hoje.slice(0, 7)}"> R$ <input type="number" step="0.01" id="aum-v" value="${valorEm(f, prox || hoje.slice(0, 7))}"> <button class="mini-btn primary" data-okaum="${i}">Registrar aumento</button> <button class="x" data-fechar>cancelar</button></span>`
              : aberto === `base:${i}`
              ? `<span class="inline">valor atual R$ <input type="number" step="0.01" id="base-v" value="${f.valor}"> <button class="mini-btn primary" data-okbase="${i}">Salvar</button> <button class="x" data-fechar>cancelar</button></span>`
              : `<button class="mini-btn" data-abrir="aum:${i}">+ aumento</button>`) : ""}
          </div>
        </div>

        <div class="lane">
          <div class="lane-t">Só uma vez <small>hora extra, bônus</small></div>
          <div class="lane-b">
            ${extras.map((x) => `<span class="chip-v ext"><small>${ymTxt(x.mes)}${x.descricao ? " · " + esc(x.descricao) : ""}</small><b>R$ ${brl(+x.valor, true)}</b><button class="x" data-delx="${x.k}" title="Remover">×</button></span>`).join("") || `<span class="muted">nenhum</span>`}
            ${aberto === `ext:${i}`
              ? `<span class="inline">recebe em <input type="month" id="ext-m" value="${prox || hoje.slice(0, 7)}"> R$ <input type="number" step="0.01" id="ext-v" placeholder="0,00"> <input class="desc" id="ext-d" placeholder="descrição (opcional)"> <button class="mini-btn primary" data-okext="${i}">Adicionar</button> <button class="x" data-fechar>cancelar</button></span>`
              : `<button class="mini-btn" data-abrir="ext:${i}">+ extra</button>`}
          </div>
        </div>

        ${salProx !== null ? (() => {
          const empresa = empNome(f.account.split(":").pop());
          const reemb = +(pendentes[empresa] || 0);
          const partes = [`<b>R$ ${brl(salProx, true)}</b> de salário`];
          if (extrasProx) partes.push(`<b>R$ ${brl(extrasProx, true)}</b> de extras`);
          if (reemb > 0) partes.push(`<b>R$ ${brl(reemb, true)}</b> de reembolsos <a href="../Contas/?conta=${encodeURIComponent("Assets:Reembolsos:" + empId(empresa))}">(ver)</a>`);
          const total = salProx + extrasProx + (reemb > 0 ? reemb : 0);
          return `<div class="soma">Em ${f.proximo.slice(8, 10)}/${f.proximo.slice(5, 7)} o esperado é ${partes.join(" + ")}${partes.length > 1 ? ` = <b>R$ ${brl(total, true)}</b>` : ""}. ` +
            `Quando cair, o sistema separa sozinho${reemb > 0 ? " (se vier menos, o que faltar dos reembolsos continua a receber)" : ""}.</div>`;
        })() : ""}
      </div>`;
  }

  function draw() {
    box.innerHTML = `
      <div class="blk-head"><div><h3>Salário e extras</h3><p><b>Todo mês</b>: o salário e os aumentos (valem dali em diante). <b>Só uma vez</b>: hora extra e bônus de um mês. Tudo salva na hora.</p></div><span class="sal-msg note"></span></div>
      ${st.fontes.map(fonteHtml).join("")}`;
    box.querySelector("#aum-v, #ext-v, #base-v")?.focus();
  }

  box.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    e.preventDefault();
    const ds = b.dataset;
    if (ds.abrir) { aberto = ds.abrir; return draw(); }
    if ("fechar" in ds) { aberto = null; return draw(); }
    if (ds.editbase !== undefined) { aberto = `base:${ds.editbase}`; return draw(); }
    if (ds.fixo !== undefined) { const f = st.fontes[+ds.fixo]; f.modo = "fixo"; f.valor = 0; aberto = `base:${ds.fixo}`; return draw(); }
    if (ds.okbase !== undefined) { st.fontes[+ds.okbase].valor = +box.querySelector("#base-v").value || 0; return salvar("Salário atualizado"); }
    if (ds.okaum !== undefined) {
      const f = st.fontes[+ds.okaum], desde = box.querySelector("#aum-m").value, v = +box.querySelector("#aum-v").value;
      if (!desde || !v) return;
      f.aumentos = [...(f.aumentos || []).filter((a) => a.desde !== desde), { desde, valor: v }];
      return salvar(`Aumento de ${f.name} registrado: R$ ${brl(v, true)} a partir de ${ymTxt(desde)}`);
    }
    if (ds.delaum) { const [i, k] = ds.delaum.split(":").map(Number); const f = st.fontes[i]; const aum = f.aumentos.slice().sort((a, b) => a.desde.localeCompare(b.desde)); aum.splice(k, 1); f.aumentos = aum; return salvar("Aumento removido"); }
    if (ds.okext !== undefined) {
      const f = st.fontes[+ds.okext], mes = box.querySelector("#ext-m").value, v = +box.querySelector("#ext-v").value;
      if (!mes || !v) return;
      st.extras.push({ fonte: f.account, mes, valor: v, descricao: box.querySelector("#ext-d").value });
      return salvar(`Extra de R$ ${brl(v, true)} em ${ymTxt(mes)} adicionado`);
    }
    if (ds.delx !== undefined) { st.extras.splice(+ds.delx, 1); return salvar("Extra removido"); }
  });
  box.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.closest(".inline")) { e.preventDefault(); e.target.closest(".inline").querySelector(".primary")?.click(); }
    if (e.key === "Escape" && aberto) { aberto = null; draw(); }
  });
  draw();
  try { const m = sessionStorage.getItem("sal-msg"); if (m) { box.querySelector(".sal-msg").textContent = "✓ " + m; sessionStorage.removeItem("sal-msg"); } } catch { /* ok */ }
}

export default { onExtensionPageLoad() { start(); } };
