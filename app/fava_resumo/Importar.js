// Aba "Importar": arrastar e soltar extratos -> POST enviar -> mostra o que aconteceu com cada arquivo.

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const FONTE = { "inter-pf": "Conta Inter PF", "cora-pj": "Conta Cora PJ", "inter-cartao": "Cartão Inter", "nubank-cartao": "Cartão Nubank", "nubank-conta": "Conta Nubank PF" };

function start() {
  const root = document.getElementById("im");
  const src = document.getElementById("im-data");
  if (!root || !src) return;
  const $ = (id) => document.getElementById(id);
  const data = JSON.parse(src.textContent);

  function renderFontes() {
    $("im-fontes").innerHTML = data.fontes.map((f) => {
      const d = f.ultimo;
      const quando = !d ? "nenhum arquivo ainda"
        : f.cartao ? `fatura mais recente: ${MESES[+d.slice(5, 7) - 1]}/${d.slice(2, 4)}`
        : `extrato até ${d.slice(8, 10)}/${d.slice(5, 7)} · ${f.dias === 0 ? "hoje" : f.dias === 1 ? "ontem" : `há ${f.dias} dias`}`;
      const st = f.atrasado ? `<span class="st late">baixar</span>` : `<span class="st ok">em dia</span>`;
      return `<section class="card fonte"><h3>${esc(f.nome)} ${st}</h3>
        <p class="como">${esc(quando)}<br>Onde baixar: ${esc(f.como)}</p>
        <ul>${f.arquivos.map((a) => `<li><span>${esc(a.nome)}</span><span>${a.kb < 1 ? "<1" : a.kb} KB</span></li>`).join("") || "<li>—</li>"}</ul></section>`;
    }).join("");
    const pend = data.pendentes;
    $("im-pend").hidden = !pend.length;
    $("im-pend-list").innerHTML = pend.map((n) => `<div class="it"><span class="bad">?</span><span><b>${esc(n)}</b><small>Formato não reconhecido. Se for um extrato de outro banco, me mande um exemplo para criar o leitor.</small></span><button type="button" class="x" data-drop="${esc(n)}">descartar</button></div>`).join("");
  }

  async function enviar(files) {
    if (!files.length) return;
    const drop = $("im-drop");
    drop.classList.add("busy");
    $("im-status").textContent = `Importando ${files.length} arquivo${files.length > 1 ? "s" : ""}…`;
    const fd = new FormData();
    [...files].forEach((f) => fd.append("files", f, f.name));
    try {
      const res = await fetch("enviar", { method: "POST", body: fd });
      const j = await res.json().catch(() => ({}));
      if (!res.ok || !j.ok) throw new Error(j.erro || "Não consegui importar.");
      const nomeFonte = (p) => FONTE[p.split("/")[1]] || "";
      const itens = [
        ...j.movidos.map((m) => `<div class="it"><span class="ok">✓</span><span><b>${esc(m.de)}</b><small>${esc(nomeFonte(m.para))} → ${esc(m.para)}</small></span><span></span></div>`),
        ...j.repetidos.map((m) => `<div class="it"><span class="dup">=</span><span><b>${esc(m.de)}</b><small>Já estava importado (${esc(m.para)}). Descartado.</small></span><span></span></div>`),
        ...j.desconhecidos.map((n) => `<div class="it"><span class="bad">?</span><span><b>${esc(n)}</b><small>Formato não reconhecido. Ficou na inbox.</small></span><button type="button" class="x" data-drop="${esc(n)}">descartar</button></div>`),
      ];
      const resumo = j.movidos.length
        ? `<b>${j.novos} lançamento${j.novos === 1 ? "" : "s"} novo${j.novos === 1 ? "" : "s"}</b> importado${j.novos === 1 ? "" : "s"}${j.revisar ? ` · ${j.revisar} sem categoria (veja "A revisar")` : ""}. As outras abas já estão atualizadas.`
        : "Nada novo para importar.";
      const pend = j.pendencias ? ` <a href="../Pendencias/"><b>${j.pendencias} pendência${j.pendencias > 1 ? "s" : ""} para resolver</b></a>` : " Nenhuma pendência.";
      $("im-list").innerHTML = `<div class="sum">${resumo}${pend}</div>` + itens.join("");
      $("im-res").hidden = false;
      $("im-status").textContent = "";
      // atualiza a lista de arquivos por fonte
      const html = await (await fetch(location.href)).text();
      const m = html.match(/<script type="application\/json" id="im-data">([\s\S]*?)<\/script>/);
      if (m) { Object.assign(data, JSON.parse(m[1])); renderFontes(); }
    } catch (err) {
      $("im-status").textContent = err.message;
    } finally {
      drop.classList.remove("busy");
      $("im-file").value = "";
    }
  }

  const drop = $("im-drop");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => enviar(e.dataTransfer.files));
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("im-file").click(); } });
  $("im-file").addEventListener("change", (e) => enviar(e.target.files));
  // soltar em qualquer lugar da página também funciona
  root.addEventListener("dragover", (e) => e.preventDefault());
  root.addEventListener("drop", (e) => { if (!e.target.closest("#im-drop")) { e.preventDefault(); enviar(e.dataTransfer.files); } });

  root.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-drop]");
    if (!b) return;
    e.preventDefault();
    await fetch("descartar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome: b.dataset.drop }) });
    b.closest(".it").remove();
    data.pendentes = data.pendentes.filter((n) => n !== b.dataset.drop);
    if (!data.pendentes.length) $("im-pend").hidden = true;
  });

  renderFontes();
}

export default { onExtensionPageLoad() { start(); } };
