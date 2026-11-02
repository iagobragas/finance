"""Comprovantes (fotos/PDFs de notas e recibos) ligados aos gastos.

Arquivos em comprovantes/AAAA-MM/AAAA-MM-DD_loja_valor.ext; a lista em config/comprovantes.yaml.
A ligação com o lançamento é feita pela data (até 3 dias de diferença) e pelo valor cobrado, não por um
identificador fixo: assim continua valendo quando um lançamento provisório é trocado pelo do extrato.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml
from beancount.core.data import Transaction

from app.paths import DATA

PASTA = DATA / "comprovantes"
CONFIG = DATA / "config" / "comprovantes.yaml"
TIPOS = {".png", ".jpg", ".jpeg", ".heic", ".webp", ".pdf"}


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "gasto"


def load() -> list[dict]:
    try:
        return (yaml.safe_load(CONFIG.read_text()) or {}).get("comprovantes") or []
    except FileNotFoundError:
        return []


def save(itens: list[dict]) -> None:
    CONFIG.write_text("# Comprovantes ligados aos gastos (por data e valor cobrado). Editado pela aba Contas.\n"
                      + yaml.safe_dump({"comprovantes": itens}, allow_unicode=True, sort_keys=False))


def guardar(origem: Path, d: date, valor: Decimal, loja: str, extra: str = "", mover: bool = False) -> dict:
    """Copia (ou move) o arquivo para comprovantes/AAAA-MM/ com um nome legível e registra."""
    ext = origem.suffix.lower()
    if ext not in TIPOS:
        raise ValueError(f"tipo de arquivo não aceito: {ext}")
    pasta = PASTA / f"{d:%Y-%m}"
    pasta.mkdir(parents=True, exist_ok=True)
    base = f"{d}_{_slug(loja)}_{valor:.2f}".replace(".", ",") + (f"_{extra}" if extra else "")
    dest, n = pasta / f"{base}{ext}", 2
    while dest.exists():
        dest, n = pasta / f"{base}_{n}{ext}", n + 1
    (shutil.move if mover else shutil.copy2)(str(origem), dest)
    item = {"arquivo": str(dest.relative_to(PASTA)), "data": d.isoformat(), "valor": float(valor), "loja": loja}
    itens = load()
    itens.append(item)
    save(itens)
    return item


def caminho(arquivo: str) -> Path | None:
    """Caminho seguro dentro de comprovantes/ (nunca fora dela)."""
    p = (PASTA / arquivo).resolve()
    return p if PASTA.resolve() in p.parents and p.is_file() else None


def ligar(entries) -> dict[int, list[dict]]:
    """id(lançamento) -> comprovantes. Casa pelo valor cobrado e pela data mais próxima (até 3 dias)."""
    itens = load()
    if not itens:
        return {}
    txns = [e for e in entries if isinstance(e, Transaction)]
    por_valor: dict[Decimal, list] = {}
    for e in txns:
        vals = {abs(p.units.number) for p in e.postings
                if p.account.startswith(("Liabilities:", "Assets:Inter", "Assets:Cora", "Assets:Nubank", "Assets:Dinheiro",
                                         "Assets:Fora"))}
        for v in vals:
            por_valor.setdefault(v.quantize(Decimal("0.01")), []).append(e)
    out: dict[int, list[dict]] = {}
    for c in itens:
        v = Decimal(str(c["valor"])).quantize(Decimal("0.01"))
        d = date.fromisoformat(str(c["data"]))
        cands = [e for e in por_valor.get(v, []) if abs((e.date - d).days) <= 3]
        if not cands:
            continue
        e = min(cands, key=lambda e: (abs((e.date - d).days), id(e) in out))
        out.setdefault(id(e), []).append(c)
    return out
