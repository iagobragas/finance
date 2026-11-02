// Aba "Planejamento": edita o plano de previsão com prévia ao vivo (POST simular) e grava (POST salvar).

const brl = (v, cents = false) =>
  (v < 0 ? "−" : "") +
  Math.abs(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
const ymLabel = (ym) => (ym ? `${MESES[+ym.slice(5, 7) - 1]}/${ym.slice(2, 4)}` : "");
const TIPOS = { gasto: "Gasto", investimento: "Investimento", receita: "Receita" };

function start() {
  const root = document.getElementById("pl");
  const src = document.getElementById("pl-data");
  if (!root || !src) return;
  const $ = (id) => document.getElementById(id);
  let data = JSON.parse(src.textContent);
  const saved = JSON.stringify(data.config);
  let cfg = JSON.parse(saved);
  cfg.receitas ||= {};
  cfg.categorias ||= {};
  cfg.compromissos ||= [];
  cfg.extras ||= [];
  cfg.metas ||= {};
  cfg.extras_receita ||= [];
  const fontes = () => data.receitas.map((r) => r.account).filter((a) => !a.endsWith(":Extra"));

  const optConta = (sel, tipo) =>
    data.contas
      .filter((c) => (tipo === "receita" ? c.account.startsWith("Income") : c.account.startsWith("Expenses")))
      .map((c) => `<option value="${esc(c.account)}"${c.account === sel ? " selected" : ""}>${esc(c.name)}</option>`)
      .join("");
  const proxMes = () => data.rows[0]?.ym || "";

  // ------------------------------------------------------------------ tabela de previsão
  function renderTable() {
    const r = data.rows;
    const temInvest = r.some((x) => x.invest);
    const cell = (v, cls = "") => `<td class="n ${cls}">${v ? brl(v) : '<span class="z">·</span>'}</td>`;
    const pill = (v) => `<td class="n"><span class="pill ${v >= 0 ? "up" : "down"}">${v > 0 ? "+" : ""}${brl(v)}</span></td>`;
    $("pl-table").innerHTML =
      `<colgroup><col class="c-op"><col class="c-lb">${r.map(() => "<col>").join("")}</colgroup>` +
      `<thead><tr><th></th><th></th>${r.map((x) => `<th>${x.label}</th>`).join("")}</tr></thead>` +
      `<tbody class="g-in"><tr class="r-inc"><td class="op">+</td><td class="lb"><i class="sw inc"></i>Receitas</td>${r.map((x) => cell(x.rec)).join("")}</tr></tbody>` +
      `<tbody class="g-out"><tr class="r-fix"><td class="op">−</td><td class="lb"><i class="sw fix"></i>Despesas fixas</td>${r.map((x) => cell(x.fixas)).join("")}</tr>` +
      `<tr class="r-var"><td class="op">−</td><td class="lb"><i class="sw var"></i>Despesas variáveis</td>${r.map((x) => cell(x.variaveis)).join("")}</tr></tbody>` +
      `<tbody class="g-res"><tr class="r-res"><td class="op">=</td><td class="lb">Resultado do mês</td>${r.map((x) => pill(x.res)).join("")}</tr>` +
      (temInvest
        ? `<tr class="invest"><td class="op">−</td><td class="lb">Investir</td>${r.map((x) => cell(x.invest)).join("")}</tr>` +
          `<tr class="r-res"><td class="op">=</td><td class="lb">Sobra</td>${r.map((x) => pill(x.sobra)).join("")}</tr>`
        : "") +
      `<tr class="saldo"><td class="op"></td><td class="lb">Saldo líquido no fim do mês</td>${r.map((x) => `<td class="n ${x.saldo < 0 ? "neg" : "pos"}">${brl(x.saldo)}</td>`).join("")}</tr></tbody>`;
    $("pl-start").textContent =
      `Começa do saldo líquido de hoje (R$ ${brl(data.hoje)})` + (data.gap ? ` menos R$ ${brl(data.gap)} estimados de compras deste mês ainda não importadas` : "") + ".";
    root.querySelectorAll(".base").forEach((el) => (el.textContent = data.base.join(", ")));
  }

  // ------------------------------------------------------------------ editores
  function renderRec() {
    $("pl-rec").innerHTML = data.receitas.filter((r) => r.previsto).map((r) =>
      `<span>${esc(r.name)}<b>R$ ${brl(r.previsto, true)}</b></span>`).join("");
  }

  // ------------------------------------------------------------------ orçamento do mês (50/30/20)
  const GRUPOS = [
    { k: "nec", nome: "Necessidades", ref: 50, cor: "var(--fix)", ex: "contas fixas, mercado, transporte, família, parcelas" },
    { k: "des", nome: "Desejos", ref: 30, cor: "var(--var)", ex: "restaurantes, lazer, compras, viagens" },
    { k: "gua", nome: "Guardar + sobra", ref: 20, cor: "var(--s3, #1baf7a)", ex: "meta de guardar e o que sobra" },
  ];
  function renderOrc() {
    const o = data.orc;
    if (!o) return;
    const rec = o.rec || 1;
    const val = { nec: o.nec, des: o.des, gua: Math.max(0, o.guardar + o.sobra) };
    $("orc-titulo").textContent = `Receita prevista · ${o.label}`;
    $("orc-rec").textContent = `R$ ${brl(o.rec)}`;
    const tot = Math.max(rec, val.nec + val.des + val.gua);
    $("orc-bar").innerHTML = GRUPOS.map((g) => `<i style="width:${(val[g.k] / tot) * 100}%;background:${g.cor}" data-tip="${g.nome} · R$ ${brl(val[g.k])} · ${Math.round((val[g.k] / rec) * 100)}% da receita"></i>`).join("");
    $("orc-bar").setAttribute("aria-label", GRUPOS.map((g) => `${g.nome} ${Math.round((val[g.k] / rec) * 100)}%`).join(", "));
    $("orc-rows").innerHTML = GRUPOS.map((g) => {
      const pc = Math.round((val[g.k] / rec) * 100);
      const ok = g.k === "gua" ? pc >= g.ref : pc <= g.ref;
      return `<div class="orc-row"><i class="dot" style="background:${g.cor}"></i><span>${g.nome}<small>${g.ex} · referência ${g.k === "gua" ? "pelo menos" : "até"} ${g.ref}%</small></span>
        <span class="r">R$ ${brl(val[g.k])}</span><span class="p ${ok ? "ok" : "off"}">${pc}%</span></div>`;
    }).join("");
    const so = o.sobra;
    $("orc-sobra").className = `orc-sobra ${so >= 0 ? "pos" : "neg"}`;
    $("orc-sobra").innerHTML = so >= 0
      ? `<span>Sobra prevista no mês${o.guardar ? `, além dos R$ ${brl(o.guardar)} guardados` : ""}</span><b>R$ ${brl(so)}</b>`
      : `<span>Falta no mês: o plano gasta mais do que entra</span><b>−R$ ${brl(-so)}</b>`;
  }

  function renderAum() {
    if (!$("pl-aum")) return;
    const fixos = data.receitas.filter((r) => (cfg.receitas[r.account] || {}).modo === "fixo");
    $("pl-aum").innerHTML = fixos.map((r) => {
      const rule = cfg.receitas[r.account];
      const aum = rule.aumentos || [];
      return `<div class="aum"><p class="hint" style="margin-top:14px"><b>${esc(r.name)}</b>: R$ ${brl(rule.valor, true)} hoje${aum.length ? "" : " · sem aumento previsto"}</p>
        ${aum.map((a, i) => `<div class="ctrl" style="justify-content:flex-start;margin-top:6px">a partir de <input type="month" data-aum="${esc(r.account)}" data-i="${i}" data-f="desde" value="${esc(a.desde || "")}"> passa a ser R$ <input type="number" step="0.01" data-aum="${esc(r.account)}" data-i="${i}" data-f="valor" value="${a.valor ?? ""}"><button type="button" class="x" data-delaum="${esc(r.account)}" data-i="${i}" aria-label="Remover aumento">×</button></div>`).join("")}
        <button class="btn ghost small" type="button" data-addaum="${esc(r.account)}" style="margin-top:8px">+ Aumento de ${esc(r.name)}</button></div>`;
    }).join("") || `<p class="hint" style="margin-top:12px">Para registrar um aumento, primeiro troque a fonte para "Valor fixo".</p>`;
  }

  function renderHx() {
    if (!$("pl-hx")) return;
    const nome = (a) => data.receitas.find((r) => r.account === a)?.name || a.split(":").pop();
    $("pl-hx").innerHTML = cfg.extras_receita.length
      ? `<thead><tr><th>Fonte</th><th>Recebe em</th><th class="n">Valor</th><th>Descrição</th><th></th></tr></thead><tbody>` +
        cfg.extras_receita.map((x, i) => `<tr>
          <td><select data-hx="${i}" data-f="fonte">${fontes().map((a) => `<option value="${esc(a)}"${a === x.fonte ? " selected" : ""}>${esc(nome(a))}</option>`).join("")}</select></td>
          <td><input type="month" data-hx="${i}" data-f="mes" value="${esc(x.mes || "")}"></td>
          <td class="n"><input type="number" step="0.01" data-hx="${i}" data-f="valor" value="${x.valor ?? 0}"></td>
          <td><input class="desc" data-hx="${i}" data-f="descricao" value="${esc(x.descricao || "")}" placeholder="ex.: 12h extras de setembro"></td>
          <td class="n"><button type="button" class="x" data-delhx="${i}" aria-label="Remover">×</button></td></tr>`).join("") + `</tbody>`
      : `<tbody><tr><td class="muted">Nenhuma hora extra ou bônus informado.</td></tr></tbody>`;
  }

  // ------------------------------------------------------------------ orçamento por categoria
  // Como nos apps de orçamento: você digita quanto quer gastar (em R$ ou em % da receita);
  // "Média", "−10%" e "−20%" são atalhos. O que sai sozinho (assinaturas, celular, DAS) não precisa de decisão.
  const PEQUENA = 0.02; // abaixo de 2% da receita a categoria vai para "Pequenas"
  const recMes = () => data.orc?.rec || 0;
  const pctDe = (v) => (recMes() ? (v / recMes()) * 100 : 0);
  const fmtPct = (v) => v.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
  const ehAuto = (c) => (c.modo === "assinaturas" || c.modo === "das") && !(cfg.categorias[c.account] || {}).modo;
  function modoTxt(c) {
    const r = cfg.categorias[c.account] || {};
    if (ehAuto(c)) return c.modo === "das" ? "valor da guia do DAS" : "soma das assinaturas ativas";
    return { ajuste: `média ${r.valor > 0 ? "+" : ""}${r.valor}%`, fixo: "valor que você definiu", pct: `${fmtPct(+r.valor || 0)}% da receita` }[r.modo] || "pela média";
  }
  function meter(c) {
    const max = Math.max(c.previsto, c.media, 1) * 1.15;
    const d = c.previsto - c.media;
    const cor = c.orc === "nec" ? "var(--fix)" : "var(--var)";
    return `<div class="meter" title="média R$ ${brl(c.media, true)}"><i style="width:${(c.previsto / max) * 100}%;background:${cor}"></i><b style="left:${(c.media / max) * 100}%"></b></div>` +
      `<span class="delta ${Math.abs(d) < 1 ? "" : d < 0 ? "down" : "up"}">${Math.abs(d) < 1 ? "igual à média" : `${d < 0 ? "−" : "+"}R$ ${brl(Math.abs(d))} vs média`}</span>`;
  }
  function linha(c) {
    const acc = esc(c.account);
    const r = cfg.categorias[c.account] || {};
    if (ehAuto(c)) {
      return `<div class="brow auto" data-row="${acc}"><div class="bn"><i class="dot ${c.orc}"></i><b>${esc(c.name)}</b><small>${modoTxt(c)}</small></div>
        <div class="bv"><b>R$ ${brl(c.previsto, true)}</b><small>${fmtPct(pctDe(c.previsto))}% da receita</small></div>
        <div class="bq"><a href="#pl-ass-card" data-ir="ass">${c.modo === "das" ? "muda em config/accounts.yaml" : "ver assinaturas"}</a></div><div></div></div>`;
    }
    const q = (k, t) => `<button type="button" data-quick="${k}" data-cat="${acc}" aria-pressed="${(k === "media" && !r.modo) || (r.modo === "ajuste" && String(r.valor) === k)}">${t}</button>`;
    return `<div class="brow" data-row="${acc}">
      <div class="bn"><i class="dot ${c.orc}" title="${c.orc === "nec" ? "necessidade" : "desejo"}"></i><b>${esc(c.name)}</b><small>média R$ ${brl(c.media)} · <span data-modo>${modoTxt(c)}</span></small></div>
      <div class="bin"><label class="unit rs"><em>R$</em><input type="number" inputmode="decimal" min="0" step="10" data-cat="${acc}" data-f="rs" value="${Math.round(c.previsto)}" aria-label="${esc(c.name)} em reais por mês"></label>
        <label class="unit"><input type="number" inputmode="decimal" min="0" step="0.5" data-cat="${acc}" data-f="pct" value="${fmtPct(pctDe(c.previsto)).replace(",", ".")}" aria-label="${esc(c.name)} em % da receita"><em>%</em></label></div>
      <div class="bq">${q("media", "Média")}${q("-10", "−10%")}${q("-20", "−20%")}</div>
      <div class="bm" data-meter>${meter(c)}</div></div>`;
  }
  function bloco(titulo, sub, cats, extra = "") {
    if (!cats.length) return "";
    const tot = cats.reduce((s, c) => s + c.previsto, 0);
    return `<div class="bgrp"><div class="bh"><div><h4>${titulo}</h4><span>${sub}</span></div><div class="bt"><b>R$ ${brl(tot)}</b><span>${fmtPct(pctDe(tot))}% da receita</span></div></div>
      ${cats.map(linha).join("")}${extra}</div>`;
  }
  let pequenasAberto = false;
  function renderCat() {
    const cats = [...data.categorias].sort((a, b) => b.previsto - a.previsto);
    const auto = cats.filter(ehAuto);
    const fixas = cats.filter((c) => !ehAuto(c) && c.grupo === "Fixas");
    const dia = cats.filter((c) => !ehAuto(c) && c.grupo !== "Fixas");
    const grandes = dia.filter((c) => Math.max(c.media, c.previsto) >= recMes() * PEQUENA);
    const peq = dia.filter((c) => !grandes.includes(c));
    const totPeq = peq.reduce((s, c) => s + c.previsto, 0);
    const pequenas = peq.length ? `<details class="bsmall"${pequenasAberto ? " open" : ""}><summary><span>Pequenas · ${peq.length} categorias (${peq.map((c) => c.name).join(", ")})</span><b>R$ ${brl(totPeq)}</b></summary>${peq.map(linha).join("")}</details>` : "";
    $("pl-cat").innerHTML =
      bloco("Dia a dia", "o que você controla: digite quanto quer gastar por mês", grandes, pequenas) +
      bloco("Contas fixas", "valores que mudam pouco; ajuste se souber o valor certo", fixas) +
      bloco("Automático", "sai sozinho, pelo valor exato", auto);
    $("pl-cat").querySelector(".bsmall")?.addEventListener("toggle", (e) => (pequenasAberto = e.target.open));
  }

  function renderList(id, list, kind) {
    const mesCol = kind === "extra" ? `<th>Mês</th>` : `<th>Início</th><th>Fim</th>`;
    $(id).innerHTML = list.length
      ? `<thead><tr><th>Descrição</th><th>Tipo</th><th>Categoria</th><th class="n">Valor${kind === "comp" ? "/mês" : ""}</th>${mesCol}<th></th></tr></thead><tbody>` +
        list.map((x, i) => {
          const tipo = x.tipo || "gasto";
          const meses = kind === "extra"
            ? `<td><input type="month" data-${kind}="${i}" data-f="mes" value="${esc(x.mes || "")}"></td>`
            : `<td><input type="month" data-${kind}="${i}" data-f="inicio" value="${esc(x.inicio || "")}"></td><td><input type="month" data-${kind}="${i}" data-f="fim" value="${esc(x.fim || "")}" title="Vazio = sem fim"></td>`;
          return `<tr><td><input class="desc" data-${kind}="${i}" data-f="descricao" value="${esc(x.descricao)}" placeholder="Descrição"></td>
            <td><select data-${kind}="${i}" data-f="tipo">${Object.entries(TIPOS).map(([k, v]) => `<option value="${k}"${k === tipo ? " selected" : ""}>${v}</option>`).join("")}</select></td>
            <td>${tipo === "investimento" ? '<span class="z">·</span>' : `<select data-${kind}="${i}" data-f="conta">${optConta(x.conta, tipo)}</select>`}</td>
            <td class="n"><input type="number" step="0.01" data-${kind}="${i}" data-f="valor" value="${x.valor ?? 0}"></td>
            ${meses}<td class="n"><button type="button" class="x" data-del="${kind}" data-i="${i}" aria-label="Remover">×</button></td></tr>`;
        }).join("") + `</tbody>`
      : `<tbody><tr><td class="muted">Nenhum item.</td></tr></tbody>`;
  }

  function renderSug() {
    const ja = new Set(cfg.compromissos.map((c) => c.descricao));
    $("pl-sug").innerHTML =
      `<button class="btn ghost small" type="button" data-add="comp">+ Adicionar compromisso</button>` +
      (data.sugestoes.some((s) => !ja.has(s.descricao)) ? `<span>Da planilha antiga:</span>` : "") +
      data.sugestoes.filter((s) => !ja.has(s.descricao)).map((s, i) =>
        `<button class="btn ghost small" type="button" data-sug="${i}">${esc(s.descricao)} · R$ ${brl(s.valor, true)}</button>`).join("");
  }

  function renderParc() {
    $("pl-parc").innerHTML = data.parcelas.length
      ? `<thead><tr><th>Mês</th><th>Compra</th><th>Parcela</th><th class="n">Valor</th></tr></thead><tbody>` +
        data.parcelas.map((p) => `<tr><td>${ymLabel(p.ym)}</td><td>${esc(p.desc)}</td><td class="muted">${esc(p.parcela)}</td><td class="n">R$ ${brl(p.valor, true)}</td></tr>`).join("") + `</tbody>`
      : `<tbody><tr><td class="muted">Nenhuma parcela futura.</td></tr></tbody>`;
  }

  function renderAss() {
    const subs = data.assinaturas || [];
    const dm = (d) => d ? `${d.slice(8, 10)}/${d.slice(5, 7)}` : "—";
    const ativas = subs.filter((a) => a.status === "ativa");
    const total = ativas.reduce((s, a) => s + a.valor, 0);
    $("pl-ass").innerHTML = subs.length
      ? `<thead><tr><th>Assinatura</th><th class="n">Valor</th><th>Dia</th><th>Última</th><th>Próxima</th><th>Situação</th><th></th></tr></thead><tbody>` +
        subs.map((a) => {
          const st = a.cobrou_depois ? ["alerta", `cobrou depois de cancelar (${dm(a.cancelada_em)})`]
            : a.status === "ativa" ? ["ativa", "ativa · prevista"]
            : a.status === "cancelada" ? ["", `cancelada em ${dm(a.cancelada_em)}`]
            : ["", "parada · sem cobrança há 2 meses"];
          const btn = a.status === "cancelada"
            ? `<button class="btn ghost small" type="button" data-ass="${esc(a.key)}" data-acao="reativar">Reativar</button>`
            : a.status === "ativa" ? `<button class="btn ghost small" type="button" data-ass="${esc(a.key)}" data-nome="${esc(a.nome)}" data-acao="cancelar">Cancelei</button>` : "";
          return `<tr class="${a.status !== "ativa" ? "off" : ""}"><td class="nm">${esc(a.nome)}<small>${esc(a.cat)} · ${a.cartao ? "cartão" : "Pix/débito"} · ${a.n} cobrança${a.n > 1 ? "s" : ""}</small></td>
            <td class="n">R$ ${brl(a.valor, true)}</td><td>dia ${a.dia}</td><td>${dm(a.ultima)}</td><td>${dm(a.proxima)}</td>
            <td><span class="ass-st ${st[0]}">${st[1]}</span></td><td class="n">${btn}</td></tr>`;
        }).join("") +
        `<tr class="grp"><td>Total por mês (ativas)</td><td class="n">R$ ${brl(total, true)}</td><td colspan="5"></td></tr></tbody>`
      : `<tbody><tr><td class="muted">Nenhuma assinatura encontrada nos extratos.</td></tr></tbody>`;
    $("pl-ass").querySelectorAll("[data-ass]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      b.textContent = "Salvando…";
      const res = await fetch("assinatura", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: b.dataset.ass, nome: b.dataset.nome, acao: b.dataset.acao }) });
      if (res.ok) location.reload();
      else { b.disabled = false; b.textContent = "Tente de novo"; }
    }));
  }

  function renderAll() {
    renderOrc();
    $("n-ass").textContent = (data.assinaturas || []).filter((a) => a.status === "ativa").length || "";
    $("n-parc").textContent = data.parcelas.length || "";
    $("n-comp").textContent = cfg.compromissos.length || "";
    $("n-extra").textContent = cfg.extras.length || "";
    renderAss();
    renderTable();
    renderRec();
    renderAum();
    renderHx();
    renderCat();
    renderList("pl-comp", cfg.compromissos, "comp");
    renderList("pl-extra", cfg.extras, "extra");
    renderSug();
    renderParc();
    $("m-investir").value = cfg.metas.investir ?? "";
    $("m-doar").value = cfg.metas.doar ?? "";
  }

  // ------------------------------------------------------------------ prévia e gravação
  let timer, seq = 0;
  function changed(rerenderEditors) {
    const dirty = JSON.stringify(cfg) !== saved;
    $("pl-status").textContent = dirty ? "Alterações não salvas" : "Tudo salvo";
    $("pl-status").classList.toggle("dirty", dirty);
    $("pl-save").disabled = $("pl-undo").disabled = !dirty;
    if (rerenderEditors) renderAll();
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const my = ++seq;
      try {
        const res = await fetch("simular", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cfg) });
        if (!res.ok) throw new Error(res.status);
        const next = await res.json();
        if (my !== seq) return;
        data = { ...data, rows: next.rows, receitas: next.receitas, categorias: next.categorias, gap: next.gap, hoje: next.hoje, orc: next.orc };
        const livre = !document.activeElement?.closest?.("#pl-cat input, .guardar");
        renderTable();
        renderOrc();
        if (livre) { renderRec(); renderCat(); } else updatePrev();
      } catch {
        $("pl-status").textContent = "Não consegui recalcular. O servidor do Finance está rodando?";
      }
    }, 250);
  }
  // atualiza os números das categorias sem recriar o campo em que você está digitando
  function updatePrev() {
    const foco = document.activeElement;
    data.categorias.forEach((c) => {
      const row = root.querySelector(`.brow[data-row="${CSS.escape(c.account)}"]`);
      if (!row) return;
      const rs = row.querySelector('[data-f="rs"]'), pc = row.querySelector('[data-f="pct"]');
      if (rs && rs !== foco) rs.value = Math.round(c.previsto);
      if (pc && pc !== foco) pc.value = fmtPct(pctDe(c.previsto)).replace(",", ".");
      const m = row.querySelector("[data-meter]"); if (m) m.innerHTML = meter(c);
      const t = row.querySelector("[data-modo]"); if (t) t.textContent = modoTxt(c);
    });
    root.querySelectorAll("#pl-cat .bgrp").forEach((g) => {
      const tot = [...g.querySelectorAll(".brow")].reduce((s, r) => s + (data.categorias.find((c) => c.account === r.dataset.row)?.previsto || 0), 0);
      const b = g.querySelector(".bt b"), sp = g.querySelector(".bt span");
      if (b) b.textContent = `R$ ${brl(tot)}`;
      if (sp) sp.textContent = `${fmtPct(pctDe(tot))}% da receita`;
    });
  }

  root.addEventListener("input", (e) => {
    const el = e.target;
    const f = el.dataset.f;
    const val = el.type === "number" ? (el.value === "" ? 0 : +el.value) : el.value;
    const structural = f === "modo" || f === "tipo";
    if (el.dataset.rec) {
      const r = (cfg.receitas[el.dataset.rec] ||= { modo: "media" });
      r[f] = val;
      if (f === "modo" && val === "fixo" && r.valor === undefined) r.valor = data.receitas.find((x) => x.account === el.dataset.rec)?.media || 0;
      if (r.modo === "media") delete cfg.receitas[el.dataset.rec];
    } else if (el.dataset.cat) {
      // digitou em R$ -> valor fixo; digitou em % -> % da receita
      if (el.value === "") return;
      cfg.categorias[el.dataset.cat] = f === "pct" ? { modo: "pct", valor: val } : { modo: "fixo", valor: val };
    } else if (el.dataset.comp !== undefined) {
      cfg.compromissos[+el.dataset.comp][f] = val || (f === "fim" ? null : val);
    } else if (el.dataset.extra !== undefined) {
      cfg.extras[+el.dataset.extra][f] = val;
    } else if (el.dataset.aum) {
      const a = cfg.receitas[el.dataset.aum].aumentos[+el.dataset.i];
      a[f] = val;
    } else if (el.dataset.hx !== undefined) {
      cfg.extras_receita[+el.dataset.hx][f] = val;
    } else if (el.id === "m-investir" || el.id === "m-doar") {
      const k = el.id.slice(2);
      if (el.value === "" || +el.value === 0) delete cfg.metas[k];
      else cfg.metas[k] = +el.value;
    } else return;
    changed(structural);
  });
  root.addEventListener("click", async (e) => {
    const ir = e.target.closest("[data-ir]");
    if (ir) { e.preventDefault(); abrir(ir.dataset.ir); $("pl-tabs").scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.quick) {
      if (b.dataset.quick === "media") delete cfg.categorias[b.dataset.cat];
      else cfg.categorias[b.dataset.cat] = { modo: "ajuste", valor: +b.dataset.quick };
    } else if (b.dataset.addaum) {
      const r = cfg.receitas[b.dataset.addaum];
      (r.aumentos ||= []).push({ desde: proxMes(), valor: r.valor });
    } else if (b.dataset.delaum) {
      cfg.receitas[b.dataset.delaum].aumentos.splice(+b.dataset.i, 1);
    } else if (b.dataset.add === "hx") {
      cfg.extras_receita.push({ fonte: fontes()[0], mes: proxMes(), valor: 0, descricao: "" });
    } else if (b.dataset.delhx !== undefined) {
      cfg.extras_receita.splice(+b.dataset.delhx, 1);
    } else if (b.dataset.add === "comp") cfg.compromissos.push({ descricao: "", tipo: "gasto", conta: "Expenses:Variaveis:Familia", valor: 0, inicio: proxMes(), fim: null });
    else if (b.dataset.add === "extra") cfg.extras.push({ descricao: "", tipo: "gasto", conta: "Expenses:Variaveis:Compras", valor: 0, mes: proxMes() });
    else if (b.dataset.sug !== undefined) {
      const ja = new Set(cfg.compromissos.map((c) => c.descricao));
      const s = data.sugestoes.filter((x) => !ja.has(x.descricao))[+b.dataset.sug];
      cfg.compromissos.push({ ...s, inicio: proxMes(), fim: null });
    } else if (b.dataset.del) {
      (b.dataset.del === "comp" ? cfg.compromissos : cfg.extras).splice(+b.dataset.i, 1);
    } else if (b.id === "pl-undo") {
      cfg = JSON.parse(saved);
    } else if (b.id === "pl-save") {
      b.disabled = true;
      $("pl-status").textContent = "Salvando…";
      try {
        const res = await fetch("salvar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cfg) });
        if (!res.ok) throw new Error(res.status);
        location.reload();
      } catch {
        $("pl-status").textContent = "Não consegui salvar. Tente de novo.";
        b.disabled = false;
      }
      return;
    } else return;
    changed(true);
  });

  // abas dos valores conhecidos (a escolhida fica lembrada neste navegador)
  const abrir = (k) => {
    root.querySelectorAll("#pl-tabs [data-tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === k)));
    root.querySelectorAll(".panel[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== k));
    try { localStorage.setItem("pl-aba", k); } catch { /* sem armazenamento */ }
  };
  $("pl-tabs").addEventListener("click", (e) => { const b = e.target.closest("[data-tab]"); if (b) abrir(b.dataset.tab); });
  try { const k = localStorage.getItem("pl-aba"); if (k && root.querySelector(`[data-panel="${k}"]`)) abrir(k); } catch { /* sem armazenamento */ }
  if (location.hash === "#pl-ass-card") abrir("ass");

  renderAll();
  simulador();
  // dica nas barras
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

  // ------------------------------------------------------------------ simulador de aumento
  function simulador() {
    const fontes = data.receitas.filter((r) => r.account.startsWith("Income:Trabalho:") && !r.account.endsWith(":Extra"));
    if (!fontes.length || !$("sim")) return;
    $("sim-fonte").innerHTML = fontes.map((f) => `<option value="${esc(f.account)}">${esc(f.name)} (hoje R$ ${brl(f.previsto, true)})</option>`).join("");
    $("sim-desde").value = proxMes();
    let simRows = null, t;
    const base = () => fontes.find((f) => f.account === $("sim-fonte").value);

    const media = (rows, k) => rows.reduce((s, r) => s + r[k], 0) / rows.length;
    const ano = data.mei.ano;
    const meiAno = (rows) => data.mei.realizado + rows.filter((r) => +r.ym.slice(0, 4) === ano).reduce((s, r) => s + r.rec, 0);

    function card(l, hoje, sim, fmt = (v) => `R$ ${brl(v)}`, extra = "", cls = "") {
      const d = sim - hoje;
      return `<div class="sim-k ${cls}"><div class="l">${l}</div><div class="v">${fmt(sim)}</div>
        <div class="d">hoje ${fmt(hoje)} · <b class="${d >= 0 ? "pos" : "neg"}">${d >= 0 ? "+" : "−"}${fmt(Math.abs(d)).replace("R$ ", "R$ ")}</b>${extra}</div></div>`;
    }
    function draw() {
      if (!simRows) {
        $("sim-out").innerHTML = `<p class="sim-hint">Digite o novo salário (ou o % de aumento) para ver o efeito na sobra, no saldo e no limite do MEI.</p>`;
        $("sim-aplicar").disabled = true;
        return;
      }
      const hojeR = data.rows, simR = simRows, ult = simR[simR.length - 1];
      const meiH = meiAno(hojeR), meiS = meiAno(simR), lim = data.mei.limite;
      const pct = (v) => `${Math.round((v / lim) * 100)}%`;
      const meiCls = meiS > lim ? "bad" : meiS > lim * 0.85 ? "warn" : "";
      $("sim-out").innerHTML =
        card("Sobra média por mês", media(hojeR, "sobra"), media(simR, "sobra")) +
        card(`Saldo líquido em ${ult.label}`, hojeR[hojeR.length - 1].saldo, ult.saldo) +
        card("Receita por mês", media(hojeR, "rec"), media(simR, "rec")) +
        card(`MEI ${ano} (limite R$ ${brl(lim)})`, meiH, meiS, (v) => `R$ ${brl(v)}`,
          meiS > lim ? " · <b class='neg'>passa do limite</b>" : ` · ${pct(meiS)} do limite`, meiCls) +
        (meiCls ? `<p class="sim-hint">${meiS > lim ? "Com esse aumento o faturamento do ano passa do limite do MEI: converse com um contador antes de aceitar (pode exigir mudar de enquadramento)." : "Fica perto do limite do MEI: horas extras e bônus podem fazer passar. Acompanhe na aba Receitas."}</p>` : "");
      $("sim-aplicar").disabled = false;
    }
    async function simular() {
      const f = base(), v = +$("sim-valor").value, desde = $("sim-desde").value;
      if (!v || !desde) { simRows = null; return draw(); }
      const c = JSON.parse(JSON.stringify(cfg));
      const r = (c.receitas[f.account] ||= { modo: "fixo", valor: f.previsto });
      if (r.modo !== "fixo") { r.modo = "fixo"; r.valor = f.previsto; }
      r.aumentos = [...(r.aumentos || []).filter((a) => a.desde < desde), { desde, valor: v }];
      const res = await fetch("simular", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c) });
      if (res.ok) { simRows = (await res.json()).rows; draw(); }
    }
    const agendar = () => { clearTimeout(t); t = setTimeout(simular, 250); };
    $("sim-valor").addEventListener("input", () => { const b = base().previsto; $("sim-pct").value = $("sim-valor").value ? Math.round((+$("sim-valor").value / b - 1) * 100) : ""; agendar(); });
    $("sim-pct").addEventListener("input", () => { const b = base().previsto; $("sim-valor").value = $("sim-pct").value ? Math.round(b * (1 + +$("sim-pct").value / 100)) : ""; agendar(); });
    ["sim-fonte", "sim-desde"].forEach((id) => $(id).addEventListener("change", agendar));
    $("sim-limpar").addEventListener("click", () => { $("sim-valor").value = $("sim-pct").value = ""; simRows = null; draw(); });
    $("sim-aplicar").addEventListener("click", async () => {
      const f = base(), v = +$("sim-valor").value, desde = $("sim-desde").value;
      const atual = cfg.receitas[f.account] || { modo: "fixo", valor: f.previsto };
      const fontesPayload = fontes.map((x) => {
        const r = JSON.parse(JSON.stringify(cfg.receitas[x.account] || { modo: "media" }));
        if (x.account === f.account) {
          if (r.modo !== "fixo") { r.modo = "fixo"; r.valor = atual.valor ?? f.previsto; }
          r.aumentos = [...(r.aumentos || []).filter((a) => a.desde !== desde), { desde, valor: v }];
        }
        return { account: x.account, ...r };
      });
      $("sim-aplicar").disabled = true;
      const res = await fetch("../Receitas/salvar_salario", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fontes: fontesPayload, extras: cfg.extras_receita || [] }) });
      if (res.ok) location.reload();
      else $("sim-aplicar").disabled = false;
    });
    draw();
  }
}

export default {
  onExtensionPageLoad() {
    start();
  },
};
