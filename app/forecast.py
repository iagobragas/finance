"""Previsão dos próximos meses a partir do histórico do livro + o plano editado na aba Planejamento.

O plano fica em config/forecast.yaml (a aba Planejamento lê e grava esse arquivo):
  receitas:     por fonte, "media" (padrão) ou "fixo" com valor
  categorias:   por categoria de gasto, "media" (padrão), "ajuste" em % sobre a média, "pct" em % da receita
                prevista do mês, ou "fixo" em R$/mês (os mesmos modelos do Actual Budget: média, % da receita, valor fixo)
  compromissos: itens com nome, valor mensal, início e fim (ex.: aporte mensal, ajuda para a família)
  metas:        % da receita para investir e para doar (como na planilha antiga: 30% e 10%)
  extras:       gastos ou receitas pontuais num mês
Parcelas de compras já feitas entram sempre pelo valor exato, tirado das faturas.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

import yaml
from beancount.core.data import Transaction

from app.paths import CONFIG as CONFIG_DIR

CONFIG = CONFIG_DIR / "forecast.yaml"
DOACOES = "Expenses:Variaveis:Doacoes"
CENT = Decimal("0.01")


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError(d)


def ym_add(ym: tuple[int, int], n: int) -> tuple[int, int]:
    y, m = divmod(ym[1] - 1 + n, 12)
    return ym[0] + y, m + 1


def parse_ym(s) -> tuple[int, int] | None:
    if not s:
        return None
    try:
        y, m = (int(x) for x in str(s).split("-")[:2])
        return y, m
    except ValueError:
        return None


def D(v) -> Decimal:
    return Decimal(str(v or 0))


def load_config() -> dict:
    try:
        cfg = yaml.safe_load(CONFIG.read_text()) or {}
    except FileNotFoundError:
        cfg = {}
    return normalize(cfg)


def normalize(cfg: dict) -> dict:
    cfg = dict(cfg or {})
    # formato antigo: receitas: {Empresa: 3000} / ajustes: {Restaurantes: -30}
    rec = cfg.get("receitas") or {}
    cfg["receitas"] = {k: (v if isinstance(v, dict) else {"modo": "fixo", "valor": v}) for k, v in rec.items()}
    cats = cfg.get("categorias") or {}
    for k, v in (cfg.pop("ajustes", None) or {}).items():
        cats.setdefault(k, {"modo": "ajuste", "valor": v})
    cfg["categorias"] = cats
    cfg.setdefault("compromissos", [])
    cfg.setdefault("extras", [])
    cfg.setdefault("extras_receita", [])
    cfg.setdefault("metas", {})
    return cfg


def save_config(cfg: dict) -> None:
    header = ("# Plano de previsão. Editado pela aba Planejamento do Finance.\n"
              "# Pode editar à mão também; a página recalcula ao recarregar.\n")
    CONFIG.write_text(header + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))


def valor_em(rule: dict, ym: tuple[int, int]) -> Decimal | None:
    """Valor fixo de uma receita num mês, considerando os aumentos (cada um vale a partir de `desde`)."""
    if not rule or rule.get("modo") != "fixo":
        return None
    valor = D(rule.get("valor"))
    for a in sorted(rule.get("aumentos") or [], key=lambda a: str(a.get("desde"))):
        desde = parse_ym(a.get("desde"))
        if desde and desde <= ym:
            valor = D(a.get("valor"))
    return valor


def extra_em(cfg: dict, account: str, ym: tuple[int, int]) -> Decimal:
    """Hora extra/bônus informados para uma fonte num mês."""
    return sum((D(x.get("valor")) for x in cfg.get("extras_receita") or []
                if x.get("fonte") == account and parse_ym(x.get("mes")) == ym), Decimal(0))


def _lookup(table: dict, account: str):
    """Aceita a chave pela conta completa ou pelo último nome (Empresa, Restaurantes)."""
    return table.get(account) or table.get(account.split(":")[-1]) or {}


def _pendentes_reembolso(txns) -> dict:
    pend = defaultdict(Decimal)
    for e in txns:
        for p in e.postings:
            if p.account.startswith("Assets:Reembolsos:"):
                pend[p.account] += p.units.number
    return pend


def forecast(entries, today: date, horizon: int | None = None, cfg: dict | None = None) -> dict:
    cfg = normalize(cfg) if cfg is not None else load_config()
    n_base = int(cfg.get("meses_base", 3))
    horizon = int(horizon or cfg.get("horizonte", 6))
    months = [ym_add((today.year, today.month), k) for k in range(1, horizon + 1)]
    txns = [e for e in entries if isinstance(e, Transaction)]

    # ---- base: meses fechados com receita e despesa
    monthly = defaultdict(lambda: defaultdict(Decimal))
    has_inc, has_exp = set(), set()
    for e in txns:
        ym = (e.date.year, e.date.month)
        if ym >= (today.year, today.month):
            continue
        parcela = bool(e.meta.get("parcela"))
        for p in e.postings:
            if p.account.startswith("Income:"):
                has_inc.add(ym)
                monthly[ym][p.account] += p.units.number
            elif p.account.startswith("Expenses:"):
                has_exp.add(ym)
                if not parcela and "Reembolso-sem-detalhe" not in p.account:  # devolução pontual: não se repete
                    cat = ":".join(p.account.split(":")[:3])
                    monthly[ym][cat] += p.units.number
    base = sorted(has_inc & has_exp)[-n_base:]
    avg = defaultdict(Decimal)
    for ym in base:
        for acc, v in monthly[ym].items():
            avg[acc] += v / len(base)

    per_account = defaultdict(lambda: defaultdict(Decimal))  # conta -> (ano, mes) -> valor (sinal do lançamento)
    invest = defaultdict(Decimal)

    # ---- receitas
    receitas = []
    for acc in sorted(a for a in avg if a.startswith("Income:") and not a.endswith("A-Revisar")):  # Pix sem categoria não se repete
        media = (-avg[acc]).quantize(CENT)
        rule = _lookup(cfg["receitas"], acc)
        modo = rule.get("modo", "media")
        for ym in months:
            per_account[acc][ym] -= valor_em(rule, ym) if modo == "fixo" else media
        receitas.append({"account": acc, "media": media, "modo": modo, "valor": D(rule.get("valor", media)),
                         "previsto": valor_em(rule, months[0]) if modo == "fixo" and months else media,
                         "aumentos": rule.get("aumentos") or []})

    # ---- hora extra / bônus informados (entram numa linha própria: <fonte>:Extra)
    for x in cfg.get("extras_receita") or []:
        ym = parse_ym(x.get("mes"))
        if ym in months and x.get("fonte"):
            per_account[f"{x['fonte']}:Extra"][ym] -= D(x.get("valor"))

    # ---- categorias de gasto
    # assinaturas: em vez da média, a soma das assinaturas ativas (continuam até você marcar "Cancelei")
    from app.assinaturas import detectar as _subs
    from app.assinaturas import mensal as _mensal
    subs = _subs(entries, today)
    por_assinatura = _mensal(subs)
    try:
        _mei = (yaml.safe_load((CONFIG_DIR / "accounts.yaml").read_text()) or {}).get("mei") or {}
    except FileNotFoundError:
        _mei = {}
    das_conta, das_valor = _mei.get("das_conta", "Expenses:Fixas:Impostos"), D(_mei["das_valor"]) if _mei.get("das_valor") else None
    categorias = []
    for acc in sorted({a for a in avg if a.startswith("Expenses:")} | set(por_assinatura)):
        media = avg[acc].quantize(CENT)
        rule = _lookup(cfg["categorias"], acc)
        modo = rule.get("modo", "media")
        if modo == "media" and acc.startswith(("Expenses:Fixas:Assinaturas", "Expenses:Fixas:Celular")):
            modo = "assinaturas"
            valor = por_assinatura.get(acc, Decimal(0)).quantize(CENT)
        elif modo == "media" and das_valor and acc.startswith(das_conta):  # DAS: valor da guia, sem as multas da média
            modo = "das"
            valor = das_valor
        elif modo == "fixo":
            valor = D(rule.get("valor"))
        elif modo == "ajuste":
            valor = (media * (1 + D(rule.get("valor")) / 100)).quantize(CENT)
        elif modo == "pct":  # % da receita prevista de cada mês (acompanha aumentos e extras)
            pct = D(rule.get("valor")) / 100
            rec_mes = {ym: -sum((v[ym] for a, v in per_account.items() if a.startswith("Income:")), Decimal(0)) for ym in months}
            for ym in months:
                per_account[acc][ym] += (rec_mes[ym] * pct).quantize(CENT)
            valor = (rec_mes[months[0]] * pct).quantize(CENT) if months else Decimal(0)
        else:
            valor = media
        for ym in months if modo != "pct" else ():
            per_account[acc][ym] += valor
        categorias.append({"account": acc, "media": media, "modo": modo, "valor": D(rule.get("valor", 0)),
                           "previsto": valor, "grupo": acc.split(":")[1]})

    # ---- parcelas futuras (valor exato)
    latest = {}
    for e in txns:
        par = e.meta.get("parcela")
        if not par or "/" not in str(par):
            continue
        n, total = (int(x) for x in str(par).split("/"))
        exp = [p for p in e.postings if p.account.startswith("Expenses:")]
        if not exp:
            continue
        desc = re.sub(r"\s*\(Parcela.*$", "", e.narration).strip()
        # a mesma compra vem com nomes diferentes no PDF e no CSV ("LOJA CENTRO SP 000183" / "LOJA CENTRO SP"):
        # identifica pela data da compra, nº de parcelas, conta e valor (arredondado: 110,01 / 109,99)
        key = (total, add_months(e.date, -(n - 1)), exp[0].account, round(abs(exp[0].units.number)))
        pay = next((p.account for p in e.postings if not p.account.startswith(("Expenses:", "Income:"))), "")
        if key not in latest or n > latest[key][0]:
            latest[key] = (n, e.date, exp[0].units.number, pay, desc)
    # último dia já importado de cada conta/cartão: parcelas depois dele ainda não estão no livro, mesmo que a
    # data já tenha passado (ex.: parcela de 11/10 que só vem na fatura importada em novembro)
    corte = {}
    for e in txns:
        if e.meta.get("fonte") and not e.meta.get("provisorio"):
            for p in e.postings:
                if p.account.startswith(("Assets:", "Liabilities:")):
                    corte[p.account] = max(corte.get(p.account, e.date), e.date)
    parcelas, futuras = [], []
    for (total, _, acc, _v), (n, d, valor, pay, desc) in latest.items():
        for k in range(n + 1, total + 1):
            dk = add_months(d, k - n)
            ym = (dk.year, dk.month)
            if ym in months:
                per_account[acc][ym] += valor
                parcelas.append({"desc": desc, "parcela": f"{k}/{total}", "ym": ym, "valor": valor, "account": acc})
            if dk > min(today, corte.get(pay, today)):  # todas as futuras, com data e cartão (o Ciclo usa para saber em que fatura caem)
                futuras.append({"desc": desc, "parcela": f"{k}/{total}", "date": dk, "valor": valor, "account": acc, "pay": pay})
    parcelas.sort(key=lambda p: (p["ym"], -p["valor"]))

    # ---- compromissos recorrentes com nome
    compromissos = []
    for c in cfg["compromissos"]:
        ini, fim = parse_ym(c.get("inicio")), parse_ym(c.get("fim"))
        valor, tipo = D(c.get("valor")), c.get("tipo", "gasto")
        for ym in months:
            if (ini and ym < ini) or (fim and ym > fim):
                continue
            if tipo == "investimento":
                invest[ym] += valor
            elif tipo == "receita":
                per_account[c.get("conta") or "Income:Outras:Outros"][ym] -= valor
            else:
                per_account[c.get("conta") or "Expenses:Variaveis:Outros"][ym] += valor
        compromissos.append(c)

    # ---- extras pontuais
    for x in cfg["extras"]:
        ym = parse_ym(x.get("mes"))
        if ym not in months:
            continue
        valor, tipo = D(x.get("valor")), x.get("tipo", "gasto")
        if tipo == "investimento":
            invest[ym] += valor
        elif tipo == "receita":
            per_account[x.get("conta") or "Income:Outras:Outros"][ym] -= valor
        else:
            per_account[x.get("conta") or "Expenses:Variaveis:Outros"][ym] += valor

    # ---- metas em % da receita prevista (a planilha antiga usava 30% investir, 10% doar)
    metas = {k: D(v) for k, v in (cfg.get("metas") or {}).items()}
    for ym in months:
        receita = -sum((v[ym] for a, v in per_account.items() if a.startswith("Income:")), Decimal(0))
        if metas.get("investir"):
            invest[ym] += (receita * metas["investir"] / 100).quantize(CENT)
        if metas.get("doar"):
            per_account[DOACOES][ym] += (receita * metas["doar"] / 100).quantize(CENT)

    # ---- quanto do mês atual ainda não foi importado (ex.: fatura do cartão que só fecha depois)
    esperado = sum((v for a, v in avg.items() if a.startswith("Expenses:")), Decimal(0))
    realizado = sum((p.units.number for e in txns
                     if (e.date.year, e.date.month) == (today.year, today.month) and not e.meta.get("parcela")
                     for p in e.postings if p.account.startswith("Expenses:")), Decimal(0))
    gap = max(Decimal(0), esperado - realizado)

    # ---- o que ainda entra no mês atual: salário fixo (+ extras) que não caiu e reembolsos a receber
    cur = (today.year, today.month)
    a_receber = Decimal(0)
    for r in receitas:
        if r["modo"] != "fixo":
            continue
        rule = _lookup(cfg["receitas"], r["account"])
        esperado_mes = valor_em(rule, cur) + extra_em(cfg, r["account"], cur)
        recebido = -sum((p.units.number for e in txns if (e.date.year, e.date.month) == cur
                         for p in e.postings if p.account.startswith(r["account"])), Decimal(0))
        a_receber += max(Decimal(0), esperado_mes - recebido)
    a_receber += sum((max(Decimal(0), v) for v in _pendentes_reembolso(txns).values()), Decimal(0))

    # ---- totais por mês
    totals = []
    for ym in months:
        rec = -sum((v[ym] for a, v in per_account.items() if a.startswith("Income:")), Decimal(0))
        fix = sum((v[ym] for a, v in per_account.items() if a.startswith("Expenses:Fixas")), Decimal(0))
        var = sum((v[ym] for a, v in per_account.items() if a.startswith("Expenses:") and not a.startswith("Expenses:Fixas")), Decimal(0))
        totals.append({"ym": ym, "rec": rec, "fixas": fix, "variaveis": var, "res": rec - fix - var,
                       "invest": invest[ym], "sobra": rec - fix - var - invest[ym]})

    return {"months": months, "per_account": {a: dict(v) for a, v in per_account.items()}, "invest": dict(invest),
            "totals": totals, "a_receber_mes": a_receber, "parcelas": parcelas, "parcelas_futuras": futuras, "corte": corte, "assinaturas": subs, "base": base, "gap": gap, "receitas": receitas,
            "categorias": categorias, "compromissos": compromissos, "extras": cfg["extras"],
            "metas": {k: float(v) for k, v in metas.items()}, "config": cfg}
