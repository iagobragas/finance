"""Assinaturas: cobranças mensais nas categorias de assinatura (Apple, Claude, celular...).

Cada assinatura vista nos extratos é prevista para continuar todo mês, no mesmo dia e com o último valor,
até ser marcada como cancelada (aba Planejamento -> "Cancelei"). As canceladas ficam em config/assinaturas.yaml.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal

import yaml
from beancount.core.data import Transaction

from app.paths import CONFIG as CONFIG_DIR

CONFIG = CONFIG_DIR / "assinaturas.yaml"
CATEGORIAS = ("Expenses:Fixas:Assinaturas", "Expenses:Fixas:Celular")
SUMIU_DIAS = 62  # sem cobrança há mais que isso: provavelmente já foi cancelada


def _sem(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()


def nome(desc: str) -> str:
    """'PG *DRY COMPANY B' -> 'Dry Company', 'APPLE.COM/BILL' -> 'Apple', 'ANTHROPIC* CLAUDE SUB' -> 'Anthropic Claude'."""
    d = re.sub(r"\(.*?\)", " ", desc)
    d = re.sub(r"^(PG|PAG|IFD|MP|EBN|DL|HTM)\s*\*?\s+", "", d, flags=re.I)
    d = re.sub(r"\bCOM\s+BILL\b", "", d, flags=re.I)
    d = re.sub(r"\.COM(/BILL)?|\bSUB\b|\bB$|\*|\d+", " ", d, flags=re.I)
    d = re.sub(r"\s+", " ", d).strip(" -·")
    return d.title() if d.isupper() or d.islower() else d


RUIDO = {"pg", "pag", "com", "bill", "sub", "ifd", "dl", "mp", "ebn", "htm", "www", "br", "ltda", "sa"}


def chave(desc: str) -> str:
    """A marca, igual em qualquer formato de extrato: 'APPLE.COM/BILL', 'APPLE COM BILL' -> 'apple';
    'ANTHROPIC* CLAUDE SUB', 'ANTHROPIC' -> 'anthropic'; 'PG *DRY COMPANY B', 'PG DRY COMPANY B' -> 'dry'."""
    toks = [t for t in re.split(r"[^a-z0-9]+", _sem(desc)) if t and t not in RUIDO and len(t) > 1 and not t.isdigit()]
    return toks[0] if toks else re.sub(r"[^a-z]", "", _sem(desc))[:24]


def _add_month(d: date, k: int = 1) -> date:
    y, m = divmod(d.month - 1 + k, 12)
    y, m = d.year + y, m + 1
    while True:
        try:
            return date(y, m, d.day)
        except ValueError:
            d = d.replace(day=d.day - 1)


def load() -> dict:
    try:
        return yaml.safe_load(CONFIG.read_text()) or {}
    except FileNotFoundError:
        return {}


def save(cfg: dict) -> None:
    CONFIG.write_text("# Assinaturas marcadas como canceladas (não entram mais na previsão). Editado pela aba Planejamento.\n"
                      + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True))


def cancelar(k: str, nome_: str, desde: date) -> None:
    cfg = load()
    cfg.setdefault("canceladas", {})[k] = {"nome": nome_, "desde": desde.isoformat()}
    save(cfg)


def reativar(k: str) -> None:
    cfg = load()
    (cfg.get("canceladas") or {}).pop(k, None)
    save(cfg)


def detectar(entries, today: date) -> list[dict]:
    """Todas as assinaturas vistas, com a situação (ativa / cancelada / parada) e a próxima cobrança prevista."""
    canceladas = load().get("canceladas") or {}
    grupos = defaultdict(list)
    for e in entries:
        if not isinstance(e, Transaction) or e.meta.get("parcela"):
            continue
        for p in e.postings:
            if p.account.startswith(CATEGORIAS) and p.units.number > 0:
                pay = next((q.account for q in e.postings if not q.account.startswith(("Expenses:", "Income:"))), "")
                grupos[chave(e.narration)].append((e.date, p.units.number, p.account, pay, e.narration))
    out = []
    for k, cobr in grupos.items():
        cobr.sort()
        ult_d, ult_v, acc, pay, desc = cobr[-1]
        canc = canceladas.get(k)
        prox = _add_month(ult_d)
        while prox <= today:
            prox = _add_month(prox)
        if canc:
            status = "cancelada"
        elif (today - ult_d).days > SUMIU_DIAS:
            status = "parada"  # não cobra há 2 meses: não prevê, mas não precisa cancelar
        else:
            status = "ativa"
        cobrou_depois = bool(canc and ult_d > date.fromisoformat(canc["desde"]))
        out.append({"key": k, "nome": nome(desc), "desc": desc, "valor": ult_v, "account": acc, "pay": pay,
                    "dia": ult_d.day, "ultima": ult_d, "proxima": prox if status == "ativa" else None,
                    "status": status, "n": len(cobr), "cancelada_em": canc and canc["desde"],
                    "cobrou_depois": cobrou_depois,
                    "historico": [{"d": d.isoformat(), "v": float(v)} for d, v, *_ in cobr[-6:]]})
    out.sort(key=lambda s: ({"ativa": 0, "parada": 1, "cancelada": 2}[s["status"]], -s["valor"]))
    return out


def cobrancas(subs: list[dict], de: date, ate: date) -> list[dict]:
    """Cobranças previstas das assinaturas ativas entre `de` e `ate` (inclusive)."""
    out = []
    for s in subs:
        if s["status"] != "ativa":
            continue
        d = s["ultima"]
        while d <= ate:
            d = _add_month(d)
            if de <= d <= ate:
                out.append({**s, "date": d})
    return out


def mensal(subs: list[dict]) -> dict:
    """Valor mensal previsto por categoria (só as ativas)."""
    tot = defaultdict(Decimal)
    for s in subs:
        if s["status"] == "ativa":
            tot[s["account"]] += s["valor"]
    return dict(tot)
