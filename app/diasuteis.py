"""Dias úteis no Brasil: fins de semana + feriados nacionais (incluindo os bancários de Carnaval).

Feriados extras (estaduais/municipais) podem ser listados em config/accounts.yaml -> feriados_extras.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from app.paths import CONFIG as CONFIG_DIR

CONFIG = CONFIG_DIR / "accounts.yaml"
FIXOS = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


@lru_cache(maxsize=32)
def feriados(ano: int) -> dict:
    p = pascoa(ano)
    out = {date(ano, m, d): "feriado" for m, d in FIXOS}
    out[p - timedelta(days=48)] = "Carnaval"
    out[p - timedelta(days=47)] = "Carnaval"
    out[p - timedelta(days=2)] = "Sexta-feira Santa"
    out[p + timedelta(days=60)] = "Corpus Christi"
    try:
        extras = (yaml.safe_load(CONFIG.read_text()) or {}).get("feriados_extras") or []
    except FileNotFoundError:
        extras = []
    for x in extras:
        try:
            d = date.fromisoformat(str(x)) if len(str(x)) == 10 else date(ano, *map(int, str(x).split("-")))
            if d.year == ano:
                out[d] = "feriado local"
        except ValueError:
            pass
    return out


def dia_util(d: date) -> bool:
    return d.weekday() < 5 and d not in feriados(d.year)


def proximo_dia_util(d: date) -> date:
    """O próprio dia, se for útil; senão o próximo dia útil."""
    while not dia_util(d):
        d += timedelta(days=1)
    return d
