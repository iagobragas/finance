// Aba "Ciclo": só o tooltip (o resto é gerado no servidor).
// Números principais "sobem" até o valor ao abrir a página (uma vez; respeita "reduzir movimento").
function contar(els) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  els.forEach((el) => {
    const txt = el.textContent.trim();
    const m = txt.match(/^([^\d−-]*)([−-]?)([\d.]+)(,(\d+))?(.*)$/);
    if (!m || el.dataset.contou) return;
    el.dataset.contou = "1";
    const casas = m[5] ? m[5].length : 0;
    const alvo = parseFloat(m[3].replace(/\./g, "") + (casas ? "." + m[5] : ""));
    if (!alvo) return;
    const fmt = (v) => m[1] + m[2] + v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }) + m[6];
    const t0 = performance.now(), dur = 700;
    const passo = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = k < 1 ? fmt(alvo * e) : txt;
      if (k < 1) requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  });
}

export default {
  onExtensionPageLoad() {
    contar(document.querySelectorAll(".livre .big"));
    const root = document.querySelector(".cy");
    if (!root) return;
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
    // linha do tempo no celular: rola até "hoje"
    const tl = root.querySelector(".tl-scroll");
    const hoje = tl?.querySelector(".today line");
    if (tl && hoje && tl.scrollWidth > tl.clientWidth) {
      const svg = tl.querySelector("svg");
      const x = (Number(hoje.getAttribute("x1")) / svg.viewBox.baseVal.width) * svg.clientWidth;
      tl.scrollLeft = Math.max(0, x - tl.clientWidth * 0.6);
    }
    // prévia dos próximos ciclos: como contar os gastos novos (média / planejamento / nenhum), lembrado neste navegador
    const seg = root.querySelector("#px-modo");
    if (seg) {
      const set = (modo) => {
        root.classList.remove("modo-media", "modo-plano", "modo-nada");
        root.classList.add(`modo-${modo}`);
        seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.modo === modo)));
        try { localStorage.setItem("ciclo-modo", modo); } catch { /* sem armazenamento */ }
      };
      let modo = "media";
      try {
        const v = localStorage.getItem("ciclo-modo") ?? (localStorage.getItem("ciclo-ritmo") === "0" ? "nada" : null);
        if (["media", "plano", "nada"].includes(v)) modo = v;
      } catch { /* sem armazenamento */ }
      set(modo);
      seg.addEventListener("click", (e) => { const b = e.target.closest("button[data-modo]"); if (b) set(b.dataset.modo); });
    }
    // "Ciclo a ciclo": abrir/fechar subcategorias
    root.querySelectorAll("tr.cat.has-subs").forEach((tr) =>
      tr.querySelector("td").addEventListener("click", () => {
        const open = tr.classList.toggle("open");
        root.querySelectorAll(`tr.sub[data-parent="${tr.dataset.group}"]`).forEach((s) => s.classList.toggle("show", open));
      }),
    );
    // abrir/fechar as categorias da tabela "Resultado por ciclo"
    root.querySelectorAll("[data-toggle]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const open = btn.getAttribute("aria-expanded") !== "true";
        btn.setAttribute("aria-expanded", String(open));
        root.querySelectorAll(`tr[data-parent="${btn.dataset.toggle}"]`).forEach((tr) => tr.classList.toggle("show", open));
      }),
    );
  },
};
