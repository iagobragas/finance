// Aba "Simulador": cenário de receita, gasto por categoria, assinaturas e meta de guardar.
// Tudo é recalculado no navegador a cada movimento; só "Usar como plano" grava alguma coisa.

const brl = (v, c = false) => (v < 0 ? "−" : "") + Math.abs(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: c ? 2 : 0, maximumFractionDigits: c ? 2 : 0 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const LONGOS = { Jan: "janeiro", Fev: "fevereiro", Mar: "março", Abr: "abril", Mai: "maio", Jun: "junho", Jul: "julho", Ago: "agosto", Set: "setembro", Out: "outubro", Nov: "novembro", Dez: "dezembro" };
const longo = (m) => `${LONGOS[m.slice(0, 3)]} de 20${m.slice(4)}`;

function load(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }
function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* sem armazenamento */ } }

function start() {
  const root = document.getElementById("sm");
  const src = document.getElementById("sm-data");
  if (!root || !src) return;
  const D = JSON.parse(src.textContent);
  const $ = (id) => document.getElementById(id);
  const n = D.meses.length;
  const cats = D.categorias;
  let tip = document.getElementById("rs-tip");
  if (!tip) { tip = document.createElement("div"); tip.id = "rs-tip"; document.body.appendChild(tip); }
  const prevTot = cats.reduce((s, c) => s + c.previsto, 0);

  // estado: valor por categoria, assinaturas ligadas, aumento e meta
  const padrao = () => ({ v: Object.fromEntries(cats.map((c) => [c.account, Math.round(c.media)])), off: [], aum: 0, aumM: 0, meta: D.meta || 0, p: "atual" });
  let st = Object.assign(padrao(), load("sim-cenario", {}));
  st.v = Object.assign(padrao().v, st.v || {});
  const subsOn = () => D.assinaturas.filter((s) => !st.off.includes(s.key));

  // valor efetivo de uma categoria (assinaturas: soma das que estão ligadas)
  const valor = (c) => {
    if (!c.auto) return st.v[c.account] ?? 0;
    return subsOn().filter((s) => s.account === c.account).reduce((a, s) => a + s.valor, 0);
  };

  function simular(cenario) {
    const delta = cenario ? cats.reduce((s, c) => s + valor(c) - c.previsto, 0) : 0;
    const meta = cenario ? st.meta : D.meta || 0;
    const gastoCats = cenario ? cats.reduce((s, c) => s + valor(c), 0) : prevTot;
    const gap = prevTot ? D.gap * (gastoCats / prevTot) : D.gap; // o resto deste mês acompanha o ritmo
    let saldo = D.hoje + D.a_receber - gap;
    const out = [];
    for (let i = 0; i < n; i++) {
      const rec = D.rec[i] + (cenario && i >= st.aumM ? +st.aum || 0 : 0);
      const gasto = D.gasto[i] + delta;
      const guarda = cenario ? (rec * meta) / 100 : D.invest[i];
      const sobra = rec - gasto - guarda;
      saldo += sobra;
      out.push({ rec, gasto, guarda, sobra, saldo });
    }
    return out;
  }

  // ------------------------------------------------------------------ desenho
  function catsHtml() {
    let html = "";
    for (const [g, titulo] of [["Fixas", "Fixas"], ["Variaveis", "Variáveis"]]) {
      const cs = cats.filter((c) => c.grupo === g);
      if (!cs.length) continue;
      html += `<div class="grp"><span>${titulo}</span><span id="sm-tot-${g}"></span></div>`;
      html += cs.map((c) => {
        const max = Math.max(300, Math.ceil((c.media * 2.2) / 50) * 50);
        const pos = Math.min(100, (c.media / max) * 100);
        return `<div class="cat${c.auto ? " auto" : ""}" data-acc="${esc(c.account)}">
          <div class="nm">${esc(c.name)}<small data-dif></small></div>
          <div class="rng"><input type="range" min="0" max="${max}" step="10" aria-label="${esc(c.name)}" ${c.auto ? "disabled" : ""}><span class="avg" style="left:calc(${pos}% - 1px)" title="média R$ ${brl(c.media)}"></span></div>
          <div class="val">R$ <input type="number" min="0" step="10" ${c.auto ? "disabled" : ""} aria-label="${esc(c.name)} em reais"></div></div>`;
      }).join("");
    }
    html += `<div class="tot"><span>Total por mês</span><span id="sm-tot"></span></div>`;
    $("sm-cats").innerHTML = html;
  }

  function subsHtml() {
    $("sm-subs").innerHTML = D.assinaturas.length
      ? D.assinaturas.map((s) => `<div class="subrow${st.off.includes(s.key) ? " off" : ""}"><span>${esc(s.nome)} · R$ ${brl(s.valor, true)}</span>
          <button type="button" class="tg" data-sub="${esc(s.key)}" aria-pressed="${!st.off.includes(s.key)}" aria-label="${esc(s.nome)}"></button></div>`).join("")
      : `<p class="hint">Nenhuma assinatura ativa.</p>`;
  }

  function chart(base, sim) {
    const W = 960, H = 240, pl = 8, pr = 70, pt = 18, pb = 26;
    const vals = [...base.map((x) => x.saldo), ...sim.map((x) => x.saldo), 0];
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.12 || 500; lo -= pad; hi += pad;
    const x = (i) => pl + (i * (W - pl - pr)) / (n - 1);
    const y = (v) => pt + ((hi - v) / (hi - lo)) * (H - pt - pb);
    const path = (arr) => arr.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.saldo).toFixed(1)}`).join("");
    const passoGrade = [500, 1000, 2000, 5000, 10000, 20000, 50000].find((p) => (hi - lo) / p <= 5) || 100000;
    // rótulos do fim da linha (cenário e ritmo atual); diferença de poucos reais não ganha rótulo próprio
    const ls = sim[n - 1].saldo, lb = base[n - 1].saldo, doisRotulos = Math.abs(ls - lb) >= 10;
    let ys = y(ls) + 4, yb = y(lb) + 4;
    if (doisRotulos && Math.abs(ys - yb) < 14) { if (ls >= lb) { ys -= 7; yb += 7; } else { ys += 7; yb -= 7; } } // não se encostam
    const livre = (yy) => Math.abs(yy - ys) > 13 && (!doisRotulos || Math.abs(yy - yb) > 13); // marca do eixo não fica sob o rótulo
    let g = "";
    for (let v = Math.ceil(lo / passoGrade) * passoGrade; v <= hi; v += passoGrade) {
      if (v === 0) continue;
      g += `<line class="grid" x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}"/>` + (livre(y(v) + 4) ? `<text x="${W - pr + 6}" y="${y(v) + 4}">${v / 1000}k</text>` : "");
    }
    g += `<line class="zero" x1="${pl}" x2="${W - pr}" y1="${y(0)}" y2="${y(0)}"/>` + (livre(y(0) + 4) ? `<text x="${W - pr + 6}" y="${y(0) + 4}">R$ 0</text>` : "");
    g += D.meses.map((m, i) => `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${m.slice(0, 3)}</text>`).join("");
    g += `<path class="area" d="${path(sim)}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z"/>`;
    g += `<path class="base" d="${path(base)}"/><path class="sim" d="${path(sim)}"/>`;
    g += sim.map((p, i) => `<circle class="sim" cx="${x(i)}" cy="${y(p.saldo)}" r="3.5"><title>${D.meses[i]} · cenário R$ ${brl(p.saldo)} · ritmo atual R$ ${brl(base[i].saldo)}</title></circle>`).join("");
    g += `<text class="v" x="${x(n - 1) + 8}" y="${ys}">R$ ${brl(ls)}</text>`;
    if (doisRotulos) g += `<text class="vb" x="${x(n - 1) + 8}" y="${yb}">R$ ${brl(lb)}</text>`;
    g += `<line class="cross" x1="0" x2="0" y1="${pt}" y2="${H - pb}"/><circle class="hl b" r="5"/><circle class="hl s" r="5"/>`;
    const passo = (W - pl - pr) / (n - 1);
    g += D.meses.map((m, i) => `<rect class="hit" data-i="${i}" x="${x(i) - passo / 2}" y="${pt}" width="${passo}" height="${H - pt - pb}"/>`).join("");
    const svg = $("sm-chart");
    svg.innerHTML = g;
    svg.onmousemove = (e) => {
      const r = e.target.closest?.(".hit");
      if (!r) return;
      const i = +r.dataset.i, cx = x(i);
      const cross = svg.querySelector(".cross"), hs = svg.querySelector(".hl.s"), hb = svg.querySelector(".hl.b");
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.style.opacity = ".35";
      hs.setAttribute("cx", cx); hs.setAttribute("cy", y(sim[i].saldo)); hs.style.opacity = "1";
      hb.setAttribute("cx", cx); hb.setAttribute("cy", y(base[i].saldo)); hb.style.opacity = "1";
      const d = sim[i].saldo - base[i].saldo;
      tip.innerHTML = `<b>${longo(D.meses[i])}</b><br>Seu cenário: R$ ${brl(sim[i].saldo)}<br>Ritmo atual: R$ ${brl(base[i].saldo)}` +
        (Math.abs(d) >= 1 ? `<br>${d > 0 ? "+" : "−"}R$ ${brl(Math.abs(d))} · sobra no mês R$ ${brl(sim[i].sobra)}` : `<br>sobra no mês R$ ${brl(sim[i].sobra)}`);
      tip.style.whiteSpace = "normal";
      tip.style.left = `${Math.min(e.clientX + 14, innerWidth - 230)}px`;
      tip.style.top = `${e.clientY + 16}px`;
      tip.style.opacity = "1";
    };
    svg.onmouseleave = () => {
      tip.style.opacity = "0";
      svg.querySelectorAll(".cross,.hl").forEach((el) => (el.style.opacity = "0"));
    };
  }

  function stack(s0) {
    const c = cats.reduce((a, k) => {
      const v = valor(k);
      if (k.compromisso) a.comp += v; else if (k.essencial) a.ess += v; else a.esc += v;
      return a;
    }, { comp: D.parcelas[0] || 0, ess: 0, esc: 0 });
    const partes = [
      ["Compromissos (parcelas, assinaturas, DAS)", c.comp, "var(--fix)"],
      ["Essenciais (mercado, transporte, escola…)", c.ess, "var(--var)"],
      ["Escolhas (restaurantes, lazer, compras…)", c.esc, "var(--s3)"],
      ["Guardar", s0.guarda, "var(--s4)"],
      ["Sobra", Math.max(0, s0.sobra), "var(--line-2)"],
    ];
    const total = Math.max(s0.rec, partes.reduce((a, p) => a + p[1], 0));
    $("sm-stack-h").textContent = `${D.meses[0]}: receita de R$ ${brl(s0.rec)}${s0.sobra < 0 ? ` · falta R$ ${brl(-s0.sobra)}` : ""}`;
    $("sm-stack").innerHTML = partes.filter((p) => p[1] > 0).map((p) => `<i style="width:${(p[1] / total) * 100}%;background:${p[2]}" data-tip="${p[0]} · R$ ${brl(p[1])} · ${Math.round((p[1] / (s0.rec || 1)) * 100)}% da receita"></i>`).join("");
    $("sm-stack-l").innerHTML = partes.map((p) => `<div><span class="dot" style="background:${p[2]}"></span><span>${p[0]}</span><b>R$ ${brl(p[1])} · ${Math.round((p[1] / (s0.rec || 1)) * 100)}%</b></div>`).join("");
  }

  function render() {
    const base = simular(false), sim = simular(true);
    // categorias
    root.querySelectorAll(".cat").forEach((el) => {
      const c = cats.find((k) => k.account === el.dataset.acc);
      const v = valor(c);
      el.querySelector("input[type=range]").value = v;
      const num = el.querySelector("input[type=number]");
      if (document.activeElement !== num) num.value = Math.round(v);
      const d = v - c.media, small = el.querySelector("[data-dif]");
      if (c.auto) {
        small.className = "";
        small.textContent = "soma das assinaturas ligadas ao lado";
        return;
      }
      small.className = Math.abs(d) < 5 ? "" : d > 0 ? "up" : "down";
      small.textContent = Math.abs(d) < 5 ? `média R$ ${brl(c.media)}` : `${d > 0 ? "+" : "−"}R$ ${brl(Math.abs(d))} vs média`;
    });
    for (const g of ["Fixas", "Variaveis"]) {
      const el = $(`sm-tot-${g}`);
      if (el) el.textContent = `R$ ${brl(cats.filter((c) => c.grupo === g).reduce((s, c) => s + valor(c), 0))}`;
    }
    $("sm-tot").textContent = `R$ ${brl(cats.reduce((s, c) => s + valor(c), 0))} + parcelas`;
    // números do topo (média dos 6 primeiros meses)
    const k = Math.min(6, n);
    const media = (arr) => arr.slice(0, k).reduce((s, x) => s + x.sobra, 0) / k;
    const ms = media(sim), mb = media(base);
    $("k-sobra").textContent = `R$ ${brl(ms)}`;
    $("k-sobra").className = `v ${ms >= 0 ? "pos" : "neg"}`;
    $("k-sobra-d").innerHTML = `média dos próximos ${k} meses · ritmo atual R$ ${brl(mb)}${Math.abs(ms - mb) >= 10 ? ` (<b class="${ms > mb ? "pos" : "neg"}">${ms > mb ? "+" : "−"}R$ ${brl(Math.abs(ms - mb))}</b>)` : ""}`;
    const fim = sim[n - 1].saldo, fimB = base[n - 1].saldo;
    $("k-fim-l").textContent = `Saldo em ${longo(D.meses[n - 1])}`;
    $("k-fim").textContent = `R$ ${brl(fim)}`;
    $("k-fim").className = `v ${fim >= 0 ? "pos" : "neg"}`;
    $("k-fim-d").innerHTML = `ritmo atual: R$ ${brl(fimB)}${Math.abs(fim - fimB) >= 10 ? ` (<b class="${fim > fimB ? "pos" : "neg"}">${fim > fimB ? "+" : "−"}R$ ${brl(Math.abs(fim - fimB))}</b>)` : ""}`;
    const iS = sim.findIndex((p, i) => p.saldo >= 0 && sim.slice(i).every((q) => q.saldo >= 0));
    const iB = base.findIndex((p, i) => p.saldo >= 0 && base.slice(i).every((q) => q.saldo >= 0));
    $("k-pos").textContent = iS < 0 ? "Não em 12 meses" : iS === 0 ? "Já está" : longo(D.meses[iS]).replace(/ de 20\d\d/, "");
    $("k-pos").className = `v ${iS < 0 ? "neg" : "pos"}`;
    $("k-pos-d").textContent = iB < 0 ? "no ritmo atual: não em 12 meses" : iS >= 0 && iS !== iB
      ? `ritmo atual: ${longo(D.meses[iB])} · ${Math.abs(iB - iS)} ${Math.abs(iB - iS) === 1 ? "mês" : "meses"} ${iS < iB ? "antes" : "depois"}`
      : `ritmo atual: ${longo(D.meses[iB])}`;
    chart(base, sim);
    stack(sim[0]);
    $("sm-meta").value = st.meta;
    $("sm-meta-o").textContent = `${st.meta}%`;
    root.querySelectorAll("#sm-presets button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.p === st.p)));
    const mudou = cats.some((c) => !c.auto && Math.round(valor(c)) !== Math.round(c.previsto)) || st.meta !== (D.meta || 0);
    $("sm-usar").disabled = !mudou;
    save("sim-cenario", st);
  }

  // ------------------------------------------------------------------ cenários prontos
  function preset(p) {
    st.p = p;
    for (const c of cats) {
      if (c.auto) continue;
      const nome = c.account.split(":").pop();
      st.v[c.account] = Math.round(
        p === "corte" ? (c.grupo === "Variaveis" ? c.media * 0.8 : c.media)
          : p === "essencial" ? (c.essencial ? c.media : 0)
          : p === "compromisso" ? (c.compromisso ? c.media : 0)
          : c.media);
      if (nome === "A-Revisar" && p !== "atual") st.v[c.account] = 0;
    }
    render();
  }

  // ------------------------------------------------------------------ o que já está certo (não depende de escolha)
  function certosHtml() {
    const C = D.certos;
    if (!C) return;
    const cor = { fatura: "var(--s4)", parcela: "var(--fix)", assinatura: "var(--var)", das: "var(--s3)" };
    const dm = (d) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;
    const mx = Math.max(...C.meses.map((m) => m.total), 1);
    const ult = C.ultima ? `${["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"][+C.ultima.slice(5, 7) - 1]}/${C.ultima.slice(2, 4)}` : "";
    $("sm-certos").innerHTML = `
      <div class="head2"><div><h3>O que você já vai pagar com certeza</h3>
        <p>Faturas com o que você já gastou, parcelas de compras feitas, assinaturas e DAS, no mês em que saem do bolso. Não muda com o cenário: é dinheiro que já tem dono.</p></div>
        <div class="sumr"><b>R$ ${brl(C.parcelas_total, true)}</b><span>em ${C.parcelas_n} parcelas que faltam${ult ? ` · a última vence em ${ult}` : ""}</span></div></div>
      <div class="meses">${C.meses.map((m) => `
        <div class="mes"><div class="mh"><span>${esc(m.mes)}</span><b>R$ ${brl(m.total)}</b></div>
          <div class="mbar" title="faturas R$ ${brl(m.faturas)} · parcelas R$ ${brl(m.parcelas)} · assinaturas R$ ${brl(m.assinaturas)} · DAS R$ ${brl(m.das)}">
            ${[["fatura", m.faturas], ["parcela", m.parcelas], ["assinatura", m.assinaturas], ["das", m.das]].filter((x) => x[1] > 0).map(([t, v]) => `<i style="width:${(v / (m.total || 1)) * 100}%;background:${cor[t]}"></i>`).join("")}</div>
          ${m.itens.length ? `<ul>${m.itens.map((i) => `<li title="${esc(i.nome)}${i.parcela ? ` · parcela ${i.parcela}` : ""} · ${esc(i.onde || "")} · ${dm(i.quando)}"><span class="dot" style="background:${cor[i.tipo]}"></span>
            <span class="nm">${esc(i.nome)} ${i.parcela ? `<small>${i.parcela}${i.faltam === 0 ? " · última" : ""}</small>` : `<small>${dm(i.quando)}${i.tipo === "fatura" && i.onde ? " · " + esc(i.onde) : ""}</small>`}</span><b>${brl(i.valor, true)}</b></li>`).join("")}</ul>`
          : `<p class="vazio">Nada certo neste mês.</p>`}
        </div>`).join("")}</div>
      <div class="leg"><span><i style="background:var(--s4)"></i>Faturas (já gasto)</span><span><i style="background:var(--fix)"></i>Parcelas</span><span><i style="background:var(--var)"></i>Assinaturas</span><span><i style="background:var(--s3)"></i>DAS</span></div>`;
  }

  // ------------------------------------------------------------------ eventos
  certosHtml();
  catsHtml();
  subsHtml();
  $("sm-rec-base").textContent = `Hoje: ${D.receitas.map((r) => `${r.name} R$ ${brl(r.previsto)}`).join(" + ")} = R$ ${brl(D.receitas.reduce((s, r) => s + r.previsto, 0))} por mês.`;
  $("sm-aum-m").innerHTML = D.meses.map((m, i) => `<option value="${i}">${m}</option>`).join("");
  $("sm-aum").value = st.aum || 0;
  $("sm-aum-m").value = st.aumM || 0;

  root.addEventListener("input", (e) => {
    const cat = e.target.closest(".cat");
    if (cat && !e.target.disabled) {
      st.v[cat.dataset.acc] = Math.max(0, +e.target.value || 0);
      st.p = "";
      return render();
    }
    if (e.target.id === "sm-meta") { st.meta = +e.target.value; return render(); }
    if (e.target.id === "sm-aum") { st.aum = +e.target.value || 0; return render(); }
  });
  $("sm-aum-m").addEventListener("change", (e) => { st.aumM = +e.target.value; render(); });
  root.addEventListener("click", (e) => {
    const sub = e.target.closest("[data-sub]");
    if (sub) {
      const k = sub.dataset.sub;
      st.off = st.off.includes(k) ? st.off.filter((x) => x !== k) : [...st.off, k];
      subsHtml();
      return render();
    }
    const p = e.target.closest("[data-p]");
    if (p) preset(p.dataset.p);
  });
  $("sm-reset").addEventListener("click", () => { st = padrao(); $("sm-aum").value = 0; $("sm-aum-m").value = 0; subsHtml(); render(); });
  $("sm-usar").addEventListener("click", async () => {
    const b = $("sm-usar");
    b.disabled = true;
    $("sm-status").textContent = "Salvando…";
    const body = {
      meta: st.meta,
      categorias: cats.map((c) => ({ account: c.account, auto: c.auto, valor: valor(c), igual_media: Math.round(valor(c)) === Math.round(c.media) })),
    };
    const res = await fetch("usar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("sm-status").innerHTML = res.ok
      ? `Plano salvo. <a href="../Planejamento/">Ver no Planejamento</a>${st.off.length ? " · para tirar assinaturas da previsão, use “Cancelei” lá" : ""}${st.aum ? " · aumento de salário se registra na aba Receitas" : ""}`
      : "Não consegui salvar.";
    b.disabled = false;
  });

  $("sm-stack").addEventListener("mousemove", (e) => {
    const el = e.target.closest("[data-tip]");
    if (!el) return;
    tip.textContent = el.dataset.tip; tip.style.whiteSpace = "nowrap";
    tip.style.left = `${Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8)}px`;
    tip.style.top = `${e.clientY + 16}px`; tip.style.opacity = "1";
  });
  $("sm-stack").addEventListener("mouseleave", () => (tip.style.opacity = "0"));

  render();
}

export default { onExtensionPageLoad() { start(); } };
