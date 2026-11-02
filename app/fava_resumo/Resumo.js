// Tema global do Fava (cabeçalho, menu, fontes) + interações da página Resumo.

const THEME = `
@import url("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500..800&family=Geist:wght@400..700&display=swap");
:root {
  --font-ui: "Geist", "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-display: "Bricolage Grotesque", "Geist", system-ui, sans-serif;
  --font-family: var(--font-ui);
  --font-family-monospaced: ui-monospace, "SF Mono", Menlo, monospace;
  --background: #f3f5f8;
  --background-darker: #eef1f6;
  --sidebar-background: #f3f5f8;
  --sidebar-border: #e1e5ec;
  --sidebar-color: #475467;
  --sidebar-hover-color: #101828;
  --header-background: #101828;
  --header-color: #ffffff;
  --header-placeholder-background: #1d2939;
  --header-placeholder-color: #98a2b3;
  --link-color: #3b4bd8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --background: #0c111a;
    --background-darker: #131a25;
    --sidebar-background: #0c111a;
    --sidebar-border: #243044;
    --sidebar-color: #a8b3c4;
    --sidebar-hover-color: #eef2f7;
    --header-background: #0c111a;
    --header-placeholder-background: #1a2230;
    --header-placeholder-color: #8b97ab;
    --link-color: #8f9bff;
  }
}
body { font-family: var(--font-ui); -webkit-font-smoothing: antialiased; }
header { border-bottom: 1px solid var(--sidebar-border); }
header h1, header h1 a { font-family: var(--font-display); font-weight: 700; letter-spacing: -.01em; }
/* o "Importar" nativo do Fava é técnico; a aba Importar do Finance substitui */
aside li:has(a[href$="/import/"]), aside a[href$="/import/"] { display: none !important; }
aside a { border-radius: 8px; font-weight: 500; transition: background .15s, color .15s; }
aside a.selected, aside li.selected > a { font-weight: 650; }
`;

function installTheme() {
  if (document.getElementById("rs-theme")) return;
  const style = document.createElement("style");
  style.id = "rs-theme";
  style.textContent = THEME;
  document.head.appendChild(style);
}

function tooltip(root) {
  let tip = document.getElementById("rs-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "rs-tip";
    tip.setAttribute("role", "tooltip");
    document.body.appendChild(tip);
  }
  root.addEventListener("mousemove", (e) => {
    const el = e.target.closest("[data-tip]");
    if (!el) {
      tip.style.opacity = "0";
      return;
    }
    tip.textContent = el.dataset.tip;
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = `${x}px`;
    tip.style.top = `${e.clientY + 16}px`;
    tip.style.opacity = "1";
  });
  root.addEventListener("mouseleave", () => (tip.style.opacity = "0"));
}

function toggles(root) {
  root.querySelectorAll("[data-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      root.querySelectorAll(`tr[data-parent="${btn.dataset.toggle}"]`).forEach((tr) => tr.classList.toggle("show", open));
    });
  });
}

function expanders(root) {
  root.querySelectorAll("tr.cat.has-subs").forEach((tr) => {
    tr.firstElementChild.addEventListener("click", () => {
      const open = tr.classList.toggle("open");
      root
        .querySelectorAll(`tr.sub[data-parent="${tr.dataset.group}"]`)
        .forEach((s) => s.classList.toggle("show", open));
    });
  });
}

// menu lateral só com as abas do Finance, na ordem de uso. As páginas nativas do Fava continuam
// acessíveis pelo endereço (ex.: /journal/); só saem do menu.
const ORDEM = ["Ciclo", "Resumo", "Contas", "Gastos", "Receitas", "Buscar", "Planejamento", "Simulador", "Lancar", "Importar", "Pendencias"];

function tidySidebar() {
  const aside = document.querySelector("aside");
  if (!aside) return;
  aside.querySelectorAll("li").forEach((li) => {
    const link = li.querySelector('a[href*="/extension/"]');
    if (!link) {
      li.style.display = "none";
      return;
    }
    const nome = (link.getAttribute("href").match(/\/extension\/([^/]+)\//) || [])[1];
    const i = ORDEM.indexOf(nome);
    li.style.order = String(i < 0 ? 99 : i);
  });
  aside.querySelectorAll("ul").forEach((ul) => {
    const visivel = [...ul.children].some((li) => li.style.display !== "none");
    ul.style.display = visivel ? "flex" : "none";
    ul.style.flexDirection = "column";
  });
  pintarBadge(); // o Fava redesenha o menu às vezes: recoloca o contador
  // os filtros do topo (data, conta, tag) valem só para as páginas nativas do Fava
  document.querySelectorAll("header form:not(.fin-search), header input:not(.fin-search input)").forEach((el) => {
    if (el.closest(".fin-search")) return;
    // sobe até o filho direto do <header> que contém o campo e esconde o bloco inteiro
    let n = el;
    while (n.parentElement && n.parentElement.tagName !== "HEADER") n = n.parentElement;
    if (!n.querySelector("h1, a[href$='/']:only-child")) n.style.display = "none";
  });
}

// campo de busca no topo de todas as páginas: Enter abre a aba Buscar
function headerSearch() {
  const header = document.querySelector("header");
  if (!header || header.querySelector(".fin-search")) return;
  const f = document.createElement("form");
  f.className = "fin-search";
  f.style.cssText = "margin-left:auto;margin-right:12px;display:flex";
  f.innerHTML = '<input type="search" placeholder="Buscar gasto: uber, 33,96, mercado set…" aria-label="Buscar" style="width:280px;font:13px var(--font-ui);padding:7px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.08);color:#fff;outline:none">';
  f.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = f.querySelector("input").value.trim();
    const base = "/" + location.pathname.split("/")[1];
    location.href = `${base}/extension/Buscar/?q=${encodeURIComponent(q)}`;
  });
  header.appendChild(f);
}

function watchSidebar() {
  headerSearch();
  tidySidebar();
  const aside = document.querySelector("aside");
  if (aside && !aside.dataset.tidy) {
    aside.dataset.tidy = "1";
    new MutationObserver(() => tidySidebar()).observe(aside, { childList: true, subtree: true });
  }
}

// contador de pendências ao lado do item "Pendências" no menu lateral
let contagem = null;

function pintarBadge() {
  const link = document.querySelector('aside a[href*="/extension/Pendencias/"]');
  if (!link || contagem === null) return;
  let b = link.querySelector(".pd-badge");
  if (!b) {
    b = document.createElement("span");
    b.className = "pd-badge";
    b.style.cssText = "margin-left:8px;font:600 11px var(--font-ui);padding:1px 7px;border-radius:999px;background:#b54708;color:#fff";
    link.appendChild(b);
  }
  if (b.textContent !== String(contagem)) b.textContent = contagem;
  b.hidden = !contagem;
}

async function badge() {
  const link = document.querySelector('aside a[href*="/extension/Pendencias/"]');
  if (!link) return;
  try {
    const base = "/" + location.pathname.split("/")[1];
    const { n } = await (await fetch(`${base}/extension/Pendencias/contagem`)).json();
    contagem = n;
    pintarBadge();
  } catch {
    /* sem contador: tudo bem */
  }
}

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
  init() {
    installTheme();
    watchSidebar();
    badge();
  },
  onPageLoad() {
    watchSidebar();
    badge();
  },
  onExtensionPageLoad() {
    contar(document.querySelectorAll(".result .big"));
    const root = document.querySelector(".rs:not(.gs)");
    if (!root) return;
    tooltip(root);
    expanders(root);
    toggles(root);
  },
};
