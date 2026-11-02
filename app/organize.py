"""Organiza os extratos: tudo que cair em inbox/ é reconhecido, renomeado e guardado em statements/<fonte>/.

Nome pelo conteúdo (não pelo nome do arquivo baixado):
  extratos de conta  -> statements/<fonte>/<primeiro-dia>_a_<ultimo-dia>.<ext>
  faturas de cartão  -> statements/<fonte>/fatura_<AAAA-MM do vencimento>.<ext>
Arquivo idêntico a um já guardado é descartado. Arquivo não reconhecido fica na inbox.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from datetime import date
from pathlib import Path

from app.parsers import detect
from app.paths import DATA

INBOX = DATA / "inbox"
STATEMENTS = DATA / "statements"

# tipo de extrato -> pasta
FOLDERS = {
    "inter_pf": "inter-pf",
    "cora_pj": "cora-pj",
    "inter_card": "inter-cartao",
    "nubank_card": "nubank-cartao",
}
CARDS = {"inter_card", "nubank_card"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def target_name(path: Path, kind: str, parsed) -> str:
    ext = path.suffix.lower()
    if parsed.meta.get("fatura_vence"):  # faturas em OFX/CSV: o vencimento vem do próprio arquivo
        return f"fatura_{parsed.meta['fatura_vence']:%Y-%m}{ext}"
    if parsed.meta.get("inicio"):  # OFX: o período vem no próprio arquivo
        return f"{parsed.meta['inicio']}_a_{parsed.meta['fim']}{ext}"
    if kind in CARDS:
        due = parsed.meta.get("due")
        if not due:  # Nubank: o vencimento vem no nome do arquivo baixado (Nubank_AAAA-MM-DD.csv)
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", path.name)
            due = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
        if not due:
            dates = [t.date for t in parsed.txns] or [date.today()]
            due = max(dates)
        return f"fatura_{due:%Y-%m}{ext}"
    dates = [t.date for t in parsed.txns] + [b.date for b in parsed.balances]
    if kind == "inter_pf":  # o cabeçalho traz o período pedido, que pode ir além do último lançamento
        m = re.search(r"Período ;(\d\d)/(\d\d)/(\d{4}) a (\d\d)/(\d\d)/(\d{4})", path.read_text(encoding="utf-8-sig", errors="ignore"))
        if m:
            d1, m1, y1, d2, m2, y2 = (int(x) for x in m.groups())
            return f"{date(y1, m1, d1)}_a_{date(y2, m2, d2)}{ext}"
    m = re.search(r"_(\d{2})(\d{2})(\d{4})_a_(\d{2})(\d{2})(\d{4})_", path.name)  # Cora: _01032026_a_26092026_
    if m:
        d1, m1, y1, d2, m2, y2 = (int(x) for x in m.groups())
        return f"{date(y1, m1, d1)}_a_{date(y2, m2, d2)}{ext}"
    if not dates:
        return f"{date.today()}{ext}"
    return f"{min(dates)}_a_{max(dates)}{ext}"


PRIORIDADE = {".ofx": 3, ".pdf": 2, ".csv": 1}  # mesma fatura em formatos diferentes: qual fica


def _conteudo(path: Path, sources: dict):
    """Multiconjunto dos lançamentos de um arquivo (para saber se um contém o outro)."""
    from collections import Counter
    kind, parse = detect(path)
    try:
        parsed = parse(path, sources.get(kind)) if kind else None
    except ValueError:
        return None
    return Counter((t.date, t.amount, t.desc) for t in parsed.txns) if parsed else None


def _podar_faturas(verbose: bool) -> list:
    """Uma fatura por mês em cada pasta de cartão: fica o melhor formato e, nele, o arquivo mais novo."""
    apagados = []
    for pasta in [p for p in STATEMENTS.iterdir() if p.is_dir() and p.name.endswith("cartao")]:
        grupos = {}
        for f in pasta.glob("fatura_*"):
            m = re.match(r"fatura_(\d{4}-\d{2})", f.name)
            if m and f.is_file():
                grupos.setdefault(m.group(1), []).append(f)
        for mes, fs in grupos.items():
            if len(fs) < 2:
                continue
            fs.sort(key=lambda f: (PRIORIDADE.get(f.suffix.lower(), 0), f.stat().st_mtime), reverse=True)
            for f in fs[1:]:
                apagados.append((f.relative_to(DATA), fs[0].relative_to(DATA)))
                f.unlink()
            limpo = pasta / f"fatura_{mes}{fs[0].suffix.lower()}"
            if fs[0] != limpo and not limpo.exists():  # tira o "_v2" do que ficou
                fs[0].rename(limpo)
    return apagados


def _periodo(nome: str):
    m = re.match(r"(\d{4}-\d{2}-\d{2})_a_(\d{4}-\d{2}-\d{2})", nome)
    return (m.group(1), m.group(2)) if m else None


def _podar_extratos(sources: dict, novo: Path) -> list:
    """Extratos de conta na mesma pasta e formato: um período inteiro dentro do outro, com os mesmos
    lançamentos, sobra. Fica o mais completo."""
    apagados = []
    pn = _periodo(novo.name)
    if not pn:
        return apagados
    cn = None
    for f in sorted(novo.parent.iterdir()):
        po = _periodo(f.name)
        if f == novo or not po or f.suffix.lower() != novo.suffix.lower():
            continue
        if pn[0] <= po[0] and po[1] <= pn[1]:  # o antigo cabe no novo
            cn = cn if cn is not None else _conteudo(novo, sources)
            co = _conteudo(f, sources)
            if cn is not None and co is not None and not (co - cn):
                apagados.append((f.relative_to(DATA), f"contido em {novo.name}"))
                f.unlink()
    return apagados


def organize(sources: dict, paths: list[Path] | None = None, verbose: bool = True) -> dict:
    """Move os arquivos da inbox (ou os `paths` dados) para statements/<fonte>/<nome>.

    Apaga o que não acrescenta nada: cópia idêntica, OFX de conta que vem em outro formato, fatura futura
    (só parcelas, que a previsão já conta), extrato do mesmo período contido em outro e fatura repetida
    em formato pior ou versão mais antiga.
    """
    INBOX.mkdir(exist_ok=True)
    STATEMENTS.mkdir(exist_ok=True)
    known = {sha(p): p for p in STATEMENTS.rglob("*") if p.is_file() and not p.name.startswith(".")}
    todo = paths if paths is not None else sorted(p for p in INBOX.iterdir() if p.is_file() and not p.name.startswith("."))
    report = {"moved": [], "dup": [], "unknown": [], "apagado": []}
    # notas fiscais (NFS-e): XML primeiro, depois o PDF com a mesma chave vai junto
    from app import nfse
    nfse.NOTAS.mkdir(exist_ok=True)
    chaves = {}
    for path in [p for p in todo if nfse.is_nfse(p)] + [p for p in todo if nfse.chave_pdf(p)]:
        if path.suffix.lower() == ".xml":
            n = nfse.parse(path)
            chaves[n["chave"]] = nome = nfse.nome_arquivo(n)
        else:
            ch = nfse.chave_pdf(path)
            ja = next((f.stem for f in nfse.NOTAS.glob("*.xml") if nfse.parse(f)["chave"] == ch), None)
            nome = chaves.get(ch) or ja
            if not nome:
                continue  # PDF qualquer com nome numérico: segue o fluxo normal
        dest = nfse.NOTAS / f"{nome}{path.suffix.lower()}"
        if dest.exists():
            report["dup"].append((path.name, dest.relative_to(DATA)))
            path.unlink()
        else:
            shutil.move(str(path), dest)
            report["moved"].append((path.name, dest.relative_to(DATA)))
        todo = [p for p in todo if p != path]
    for path in todo:
        h = sha(path)
        if h in known and known[h] != path:
            report["dup"].append((path.name, known[h].relative_to(DATA)))
            path.unlink()
            continue
        kind, parse = detect(path)
        try:
            parsed = parse(path, sources.get(kind)) if kind else None
        except ValueError as e:  # ex.: OFX de uma conta ainda não configurada
            print(f"  ? {path.name}: {e}")
            parsed = None
        if parsed and (parsed.meta.get("ignorado") or parsed.meta.get("futura")):
            motivo = ("essa conta vem por outro formato" if parsed.meta.get("ignorado")
                      else "fatura futura, só parcelas que a previsão já conta")
            report["apagado"].append((path.name, motivo))
            path.unlink()
            continue
        pasta = parsed and (parsed.meta.get("pasta") or FOLDERS.get(kind))
        if not pasta:
            report["unknown"].append(path.name)
            continue
        kind = parsed.meta.get("kind", kind)
        folder = STATEMENTS / pasta
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / target_name(path, kind, parsed)
        if dest.resolve() == path.resolve():
            continue
        fatura = dest.name.startswith("fatura_")
        if dest.exists() and not fatura and dest.suffix.lower() == path.suffix.lower():
            # mesmo período e formato: se um contém o outro, fica só o mais completo
            novo, velho = _conteudo(path, sources), _conteudo(dest, sources)
            if novo is not None and velho is not None:
                if not (novo - velho):  # nada novo
                    report["apagado"].append((path.name, f"mesmos lançamentos de {dest.relative_to(DATA)}"))
                    path.unlink()
                    continue
                if not (velho - novo):  # o novo tem tudo do antigo e mais: substitui
                    report["apagado"].append((dest.name, f"substituído por {path.name}, mais completo"))
                    dest.unlink()
        n = 2
        stem = dest.stem
        while dest.exists():  # mesmo nome, conteúdo diferente: guarda os dois
            dest = folder / f"{stem}_v{n}{dest.suffix}"
            n += 1
        shutil.move(str(path), dest)
        known[h] = dest
        report["moved"].append((path.name, dest.relative_to(DATA)))
        if not fatura:
            report["apagado"] += [(str(a), m) for a, m in _podar_extratos(sources, dest)]
    report["apagado"] += [(str(a), f"mesma fatura, fica {b}") for a, b in _podar_faturas(verbose)]

    if verbose:
        for src, dst in report["moved"]:
            print(f"  → {src}  ⟶  {dst}")
        for src, dst in report["dup"]:
            print(f"  = {src} já estava guardado em {dst} (apagado)")
        for src, motivo in report["apagado"]:
            print(f"  ✗ {src} apagado: {motivo}")
        for src in report["unknown"]:
            print(f"  ? {src}: formato não reconhecido, ficou em inbox/")
    return report
