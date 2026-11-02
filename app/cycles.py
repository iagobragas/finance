"""Visão por ciclo: do dia 16 de um mês ao dia 15 do seguinte (configurável em config/accounts.yaml).

Tudo é visto pelo CAIXA, isto é, pelo dia em que o dinheiro sai ou entra:
  - receitas: na data em que entram;
  - compras no cartão: no vencimento da fatura em que caem (fecha/vence de cada cartão);
  - Pix, débito, dinheiro: na data da compra.
Assim o "resultado do ciclo" responde: o que entrou no ciclo pagou o que venceu no ciclo?
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median

import yaml
from beancount.core.data import Transaction
from app.paths import CONFIG as CONFIG_DIR

CONFIG = CONFIG_DIR / "accounts.yaml"
ZERO = Decimal(0)


def _cfg():
    try:
        c = yaml.safe_load(CONFIG.read_text()) or {}
    except FileNotFoundError:
        c = {}
    return c.get("card_cycles") or {}, int((c.get("ciclo") or {}).get("inicio", 16))


def _das():
    """(conta, valor) do DAS do MEI em config/accounts.yaml; o Ciclo usa esse valor em vez da média (que inclui multas)."""
    try:
        mei = (yaml.safe_load(CONFIG.read_text()) or {}).get("mei") or {}
    except FileNotFoundError:
        mei = {}
    v = mei.get("das_valor")
    return mei.get("das_conta", "Expenses:Fixas:Impostos"), (Decimal(str(v)) if v else None)


def _safe(y, m, d):
    while True:
        try:
            return date(y, m, d)
        except ValueError:
            d -= 1


def _add_month(y, m, n=1):
    y2, m2 = divmod(m - 1 + n, 12)
    return y + y2, m2 + 1


def desde_extrato(fc: dict, today: date) -> date:
    """Primeiro dia ainda não importado nos cartões: cobranças previstas a partir dele (não de hoje)."""
    cards, _ = _cfg()
    cortes = [d for a, d in (fc.get("corte") or {}).items() if a in cards]
    return min([today] + cortes) + timedelta(days=1)


def faturas_abertas(entries, today: date) -> dict:
    """Por cartão: a próxima fatura a vencer e quanto dela já está lançado, e o que fica para as seguintes.
    {cartão: {"due": data, "agora": valor dessa fatura, "depois": compras que vencem depois}}"""
    cards, _ = _cfg()
    evs = [x for x in events(entries) if x["kind"] == "gasto" and x["pay"] in cards]
    saldo = defaultdict(Decimal)
    outros = []  # lançamentos do cartão que não são gasto, com vencimento próprio (Pix no crédito)
    for e in entries:
        if not isinstance(e, Transaction):
            continue
        pagador = next((q.account for q in e.postings if not q.account.startswith(("Expenses:", "Income:"))), "")
        for p in e.postings:
            if p.account in cards:
                saldo[p.account] += p.units.number
                if e.meta.get("vence") and pagador != p.account:
                    outros.append((p.account, date.fromisoformat(str(e.meta["vence"])), -p.units.number))
    out = {}
    for card, c in cards.items():
        due = min([x["cash"] for x in evs if x["pay"] == card and x["cash"] >= today]
                  + [card_due(today, int(c["fecha"]), int(c["vence"]))])
        depois = sum((x["v"] for x in evs if x["pay"] == card and x["cash"] > due), ZERO) + \
            sum((v for a, d, v in outros if a == card and d > due), ZERO)
        total = -saldo[card]
        out[card] = {"due": due, "agora": total - depois, "depois": depois}
    return out


def card_due(d: date, fecha: int, vence: int) -> date:
    """Vencimento da fatura em que cai uma compra feita no dia d."""
    y, m = (d.year, d.month) if d.day <= fecha else _add_month(d.year, d.month)
    if vence <= fecha:  # vence no mês seguinte ao fechamento
        y, m = _add_month(y, m)
    return _safe(y, m, vence)


def cycle_of(d: date, inicio: int) -> tuple[date, date]:
    """(início, fim) do ciclo que contém o dia d. O ciclo é nomeado pelo mês em que termina."""
    if d.day >= inicio:
        start = _safe(d.year, d.month, inicio)
    else:
        y, m = _add_month(d.year, d.month, -1)
        start = _safe(y, m, inicio)
    ey, em = _add_month(start.year, start.month)
    return start, _safe(ey, em, inicio) - timedelta(days=1)


def cycle_by_end(y: int, m: int, inicio: int) -> tuple[date, date]:
    sy, sm = _add_month(y, m, -1)
    return _safe(sy, sm, inicio), _safe(y, m, inicio) - timedelta(days=1)


def events(entries):
    """Cada gasto/receita com a data de caixa, data de compra, conta de pagamento e categoria."""
    cards, _ = _cfg()
    out = []
    for e in entries:
        if not isinstance(e, Transaction):
            continue
        others = [p for p in e.postings if not p.account.startswith(("Expenses:", "Income:"))]
        pay = others[0].account if others else ""
        for p in e.postings:
            if p.account.startswith("Expenses:"):
                c = cards.get(pay)
                if c and e.meta.get("vence"):  # veio de uma fatura: usa o vencimento real dela
                    cash = date.fromisoformat(str(e.meta["vence"]))
                elif c:
                    cash = card_due(e.date, int(c["fecha"]), int(c["vence"]))
                else:
                    cash = e.date
                out.append({"kind": "gasto", "date": e.date, "cash": cash, "v": p.units.number, "acc": p.account,
                            "pay": pay, "card": bool(c), "desc": e.narration, "meio": e.meta.get("meio", "")})
            elif p.account.startswith("Income:"):
                out.append({"kind": "receita", "date": e.date, "cash": e.date, "v": -p.units.number,
                            "acc": p.account, "pay": pay, "card": False, "desc": e.narration, "meio": e.meta.get("meio", "")})
    return out


def summarize(evs, start: date, end: date):
    ent = [x for x in evs if x["kind"] == "receita" and start <= x["cash"] <= end]
    sai = [x for x in evs if x["kind"] == "gasto" and start <= x["cash"] <= end]
    cons = [x for x in evs if x["kind"] == "gasto" and start <= x["date"] <= end]
    return {
        "entradas": sum((x["v"] for x in ent), ZERO),
        "saidas": sum((x["v"] for x in sai), ZERO),
        "saidas_cartao": sum((x["v"] for x in sai if x["card"]), ZERO),
        "saidas_outras": sum((x["v"] for x in sai if not x["card"]), ZERO),
        "consumo": sum((x["v"] for x in cons), ZERO),
        "ent_list": ent, "sai_list": sai, "cons_list": cons,
    }


def current(entries, today: date, saldo_contas: Decimal, fc: dict):
    """Números do ciclo atual: quanto tem, quanto entra, quanto vence e quanto sobra livre."""
    cards, inicio = _cfg()
    evs = events(entries)
    start, end = cycle_of(today, inicio)

    # ---- receitas que ainda vão entrar neste ciclo (dia típico de cada fonte)
    from app.diasuteis import proximo_dia_util
    try:
        pagamentos = (yaml.safe_load(CONFIG.read_text()) or {}).get("pagamentos") or {}
    except FileNotFoundError:
        pagamentos = {}
    previsto_por_fonte = {r["account"]: r["previsto"] for r in fc.get("receitas", [])}
    receber = []
    for acc, valor in previsto_por_fonte.items():
        dias = [x["date"].day for x in evs if x["kind"] == "receita" and x["acc"] == acc and x["date"] >= today - timedelta(days=150)]
        dia = int((pagamentos.get(acc) or {}).get("dia") or (median(dias) if dias else 0))
        if not dia or not valor:
            continue
        quando = _safe(start.year, start.month, dia) if dia >= inicio else _safe(end.year, end.month, dia)
        quando = proximo_dia_util(quando)  # fim de semana/feriado: paga no próximo dia útil
        ja = [x for x in evs if x["kind"] == "receita" and x["acc"] == acc and start <= x["date"] <= today]
        if ja or quando < today or quando > end:
            continue
        receber.append({"acc": acc, "date": quando, "v": valor})
    # hora extra / bônus informados: entram junto com o pagamento da fonte, no mês informado
    for x in (fc.get("config") or {}).get("extras_receita") or []:
        base = next((r for r in receber if r["acc"] == x.get("fonte")), None)
        if not base or str(x.get("mes")) != f"{base['date']:%Y-%m}":
            continue
        receber.append({"acc": f"{x['fonte']}:Extra", "date": base["date"], "v": Decimal(str(x.get("valor") or 0)),
                        "extra": True, "desc": x.get("descricao", "")})

    # reembolsos pendentes: entram junto com o próximo pagamento da empresa
    pend = defaultdict(Decimal)
    for e in entries:
        if isinstance(e, Transaction):
            for p in e.postings:
                if p.account.startswith("Assets:Reembolsos:"):
                    pend[p.account.split(":")[-1]] += p.units.number
    for fonte, v in pend.items():
        if v <= 0:
            continue
        prox = next((r for r in receber if r["acc"].endswith(":" + fonte)), None)
        if prox:
            receber.append({"acc": f"Reembolso {fonte}", "date": prox["date"], "v": v, "reembolso": True})
    receber.sort(key=lambda r: r["date"])

    # ---- faturas que vencem até o fim do ciclo
    # valor = saldo devedor do cartão hoje menos o que só vence depois do ciclo (inclui resíduos e estornos)
    saldo_cartao = defaultdict(Decimal)
    for e in entries:
        if isinstance(e, Transaction):
            for p in e.postings:
                if p.account in cards:
                    saldo_cartao[p.account] += p.units.number
    faturas = []
    for card, c in cards.items():
        depois = sum((x["v"] for x in evs if x["pay"] == card and x["kind"] == "gasto" and x["cash"] > end), ZERO)
        # Pix no crédito e outros lançamentos do cartão que não são gasto, mas caem numa fatura posterior
        depois += sum((-p.units.number for e in entries if isinstance(e, Transaction) and e.meta.get("vence")
                       and str(e.meta["vence"]) > end.isoformat()
                       # se o cartão é o "pagador" do lançamento, o gasto já foi contado acima pelos eventos
                       and next((q.account for q in e.postings if not q.account.startswith(("Expenses:", "Income:"))), "") != card
                       for p in e.postings if p.account == card), ZERO)
        total = -saldo_cartao[card] - depois
        itens = [x for x in evs if x["pay"] == card and x["kind"] == "gasto" and today < x["cash"] <= end]
        due = min((x["cash"] for x in itens), default=None) or card_due(today, int(c["fecha"]), int(c["vence"]))
        if due > end or total <= 0:
            continue
        fecha_em = _safe(due.year, due.month, int(c["fecha"])) if int(c["vence"]) > int(c["fecha"]) else \
            _safe(*_add_month(due.year, due.month, -1), int(c["fecha"]))
        faturas.append({"card": card, "due": proximo_dia_util(due), "due_nominal": due, "fecha": fecha_em,
                        "v": total, "aberta": fecha_em >= today, "n": len(itens)})
    faturas.sort(key=lambda f: f["due"])

    # ---- assinaturas e parcelas que ainda vão cobrar e caem neste ciclo (no cartão: pela fatura em que entram)
    def cai_no_ciclo(d, pay):
        c = cards.get(pay)
        cash = card_due(d, int(c["fecha"]), int(c["vence"])) if c else d
        return start <= cash <= end

    from app.assinaturas import cobrancas
    assinaturas = [{"nome": x["nome"], "date": x["date"], "v": x["valor"], "acc": x["account"], "card": x["pay"] in cards}
                   for x in cobrancas(fc.get("assinaturas") or [], desde_extrato(fc, today), end + timedelta(days=45))
                   if cai_no_ciclo(x["date"], x["pay"])]
    parcelas = [{"nome": p["desc"], "parcela": p["parcela"], "date": p["date"], "v": p["valor"], "acc": p["account"],
                 "card": p["pay"] in cards}
                for p in fc.get("parcelas_futuras") or [] if cai_no_ciclo(p["date"], p["pay"])]

    # ---- contas fixas pagas fora do cartão (ex.: DAS por Pix) que ainda não saíram neste ciclo
    fixas_fora = []
    prev = [cycle_by_end(*_add_month(end.year, end.month, -k), inicio) for k in (1, 2, 3)]
    cats = defaultdict(list)
    for s, e_ in prev:
        tot = defaultdict(Decimal)
        for x in evs:
            if x["kind"] == "gasto" and not x["card"] and x["acc"].startswith("Expenses:Fixas") and s <= x["date"] <= e_:
                tot[":".join(x["acc"].split(":")[:3])] += x["v"]
        for k, v in tot.items():
            cats[k].append(v)
    das_conta, das_valor = _das()
    if das_valor:
        cats.setdefault(das_conta, [das_valor, das_valor])
    for cat, vals in cats.items():
        if len(vals) < 2:
            continue
        esperado = das_valor if das_valor and cat == das_conta else sum(vals, ZERO) / len(vals)
        pago = sum((x["v"] for x in evs if x["kind"] == "gasto" and not x["card"] and x["acc"].startswith(cat)
                    and start <= x["date"] <= today), ZERO)
        if esperado - pago > 1:
            fixas_fora.append({"acc": cat, "v": (esperado - pago).quantize(Decimal("0.01")), "fixo": bool(das_valor) and cat == das_conta})

    # ---- guardar: meta % da receita do ciclo (salário + extras; reembolso só devolve o que já foi gasto) + investimentos
    receita_ciclo = sum((x["v"] for x in evs if x["kind"] == "receita" and start <= x["date"] <= today), ZERO) + \
        sum((r["v"] for r in receber if not r.get("reembolso")), ZERO)
    metas = (fc.get("config") or {}).get("metas") or {}
    guardar = (receita_ciclo * Decimal(str(metas.get("investir", 0))) / 100).quantize(Decimal("0.01"))
    for c in (fc.get("config") or {}).get("compromissos") or []:
        if c.get("tipo") == "investimento":
            guardar += Decimal(str(c.get("valor") or 0))

    a_receber = sum((r["v"] for r in receber), ZERO)
    a_pagar = sum((f["v"] for f in faturas), ZERO)
    fixas = sum((f["v"] for f in fixas_fora), ZERO)
    a_assinar = sum((x["v"] for x in assinaturas), ZERO)
    a_parcelas = sum((x["v"] for x in parcelas), ZERO)
    livre = saldo_contas + a_receber - a_pagar - fixas - a_assinar - a_parcelas - guardar

    # compras já feitas que só vencem no próximo ciclo
    comprometido = sum((x["v"] for x in evs if x["kind"] == "gasto" and x["card"] and x["date"] <= today and x["cash"] > end), ZERO)
    gasto_ate_agora = sum((x["v"] for x in evs if x["kind"] == "gasto" and start <= x["date"] <= today), ZERO)
    dias = (end - today).days + 1

    return {
        "start": start, "end": end, "today": today, "dias": dias,
        "saldo": saldo_contas, "receber": receber, "a_receber": a_receber,
        "faturas": faturas, "a_pagar": a_pagar, "fixas_fora": fixas_fora, "fixas": fixas,
        "assinaturas": assinaturas, "a_assinar": a_assinar, "parcelas": parcelas, "a_parcelas": a_parcelas,
        "guardar": guardar, "meta_pct": metas.get("investir", 0), "livre": livre,
        "por_dia": livre / dias if dias > 0 and livre > 0 else ZERO,
        "comprometido": comprometido, "gasto": gasto_ate_agora,
        "progresso": float(gasto_ate_agora / (gasto_ate_agora + max(livre, ZERO)) * 100) if gasto_ate_agora + max(livre, ZERO) else 0.0,
        "tempo": float(((today - start).days + 1) / ((end - start).days + 1) * 100),
        "cards": cards, "inicio": inicio,
    }


def proximo(entries, today: date, fc: dict, cur: dict, k: int = 1, prev: dict | None = None, evs=None):
    """Prévia do k-ésimo ciclo depois do atual: parte da sobra prevista do ciclo anterior (`prev`, ou o atual),
    soma as receitas previstas e tira as faturas que vencem nele (com as compras já feitas no cartão), assinaturas,
    parcelas e fixas por Pix. Por último, uma estimativa dos gastos novos no seu ritmo médio.
    Duas correntes de saldo: `certo` (sem gastos novos em nenhum ciclo) e `com_ritmo` (gastando a média em todos)."""
    from app.assinaturas import cobrancas
    from app.diasuteis import proximo_dia_util
    from app.forecast import _lookup, extra_em, valor_em

    cards, inicio = _cfg()
    evs = evs if evs is not None else events(entries)
    cy, cm = _add_month(cur["end"].year, cur["end"].month, k)
    start, end = cycle_by_end(cy, cm, inicio)
    cfg = fc.get("config") or {}
    try:
        pagamentos = (yaml.safe_load(CONFIG.read_text()) or {}).get("pagamentos") or {}
    except FileNotFoundError:
        pagamentos = {}

    # ---- receitas previstas no ciclo (dia de pagamento de cada fonte, com aumentos e extras do mês)
    receber = []
    for r in fc.get("receitas", []):
        acc = r["account"]
        dias = [x["date"].day for x in evs if x["kind"] == "receita" and x["acc"] == acc and x["date"] >= today - timedelta(days=150)]
        dia = int((pagamentos.get(acc) or {}).get("dia") or (median(dias) if dias else 0))
        if not dia:
            continue
        quando = proximo_dia_util(_safe(start.year, start.month, dia) if dia >= inicio else _safe(end.year, end.month, dia))
        ym = (quando.year, quando.month)
        v = valor_em(_lookup(cfg.get("receitas") or {}, acc), ym)
        v = (v if v is not None else r["previsto"]) + extra_em(cfg, acc, ym)
        if v > 0 and start <= quando <= end:
            receber.append({"acc": acc, "date": quando, "v": v})
    receber.sort(key=lambda r: r["date"])

    # ---- faturas que vencem no ciclo: compras já lançadas + Pix no crédito etc.
    faturas = []
    for card, c in cards.items():
        itens = sorted((x for x in evs if x["pay"] == card and x["kind"] == "gasto" and start <= x["cash"] <= end),
                       key=lambda x: x["date"])
        outros = sum((-p.units.number for e in entries if isinstance(e, Transaction) and e.meta.get("vence")
                      and start.isoformat() <= str(e.meta["vence"]) <= end.isoformat()
                      and next((q.account for q in e.postings if not q.account.startswith(("Expenses:", "Income:"))), "") != card
                      for p in e.postings if p.account == card), ZERO)
        total = sum((x["v"] for x in itens), ZERO) + outros
        due = card_due(_safe(start.year, start.month, int(c["fecha"])) if int(c["fecha"]) >= inicio
                       else _safe(end.year, end.month, int(c["fecha"])), int(c["fecha"]), int(c["vence"]))
        if not (start <= due <= end):
            due = min((x["cash"] for x in itens), default=None)
        if due is None:
            continue
        fecha_em = _safe(due.year, due.month, int(c["fecha"])) if int(c["vence"]) > int(c["fecha"]) else \
            _safe(*_add_month(due.year, due.month, -1), int(c["fecha"]))
        faturas.append({"card": card, "due": proximo_dia_util(due), "fecha": fecha_em, "v": total, "outros": outros,
                        "itens": [{"date": x["date"], "desc": x["desc"], "v": x["v"], "acc": x["acc"]} for x in itens]})
    faturas.sort(key=lambda f: f["due"])

    def cai(d, pay):
        c = cards.get(pay)
        cash = card_due(d, int(c["fecha"]), int(c["vence"])) if c else d
        return start <= cash <= end

    assinaturas = [{"nome": x["nome"], "date": x["date"], "v": x["valor"], "acc": x["account"], "card": x["pay"] in cards}
                   for x in cobrancas(fc.get("assinaturas") or [], desde_extrato(fc, today), end + timedelta(days=45))
                   if cai(x["date"], x["pay"])]
    parcelas = [{"nome": p["desc"], "parcela": p["parcela"], "date": p["date"], "v": p["valor"], "acc": p["account"]}
                for p in fc.get("parcelas_futuras") or [] if cai(p["date"], p["pay"])]

    # ---- fixas pagas fora do cartão (DAS, escola...): média dos 3 ciclos anteriores ao atual
    cats = defaultdict(list)
    for atras in (1, 2, 3):
        s, e_ = cycle_by_end(*_add_month(cur["end"].year, cur["end"].month, -atras), inicio)
        tot = defaultdict(Decimal)
        for x in evs:
            if x["kind"] == "gasto" and not x["card"] and x["acc"].startswith("Expenses:Fixas") and s <= x["date"] <= e_:
                tot[":".join(x["acc"].split(":")[:3])] += x["v"]
        for c_, v in tot.items():
            cats[c_].append(v)
    das_conta, das_valor = _das()
    if das_valor:
        cats[das_conta] = [das_valor, das_valor]  # valor da guia, sem as multas que entraram na média
    fixas_fora = [{"acc": c_, "v": (sum(v, ZERO) / len(v)).quantize(Decimal("0.01")), "fixo": c_ == das_conta and bool(das_valor)}
                  for c_, v in cats.items() if len(v) >= 2]
    fixas_fora = [f for f in fixas_fora if f["v"] > 1]

    a_receber = sum((r["v"] for r in receber), ZERO)
    a_pagar = sum((f["v"] for f in faturas), ZERO)
    a_assinar = sum((x["v"] for x in assinaturas), ZERO)
    a_parcelas = sum((x["v"] for x in parcelas), ZERO)
    fixas = sum((f["v"] for f in fixas_fora), ZERO)
    ini_certo = prev["certo"] if prev else cur["livre"]
    ini_ritmo = prev["com_ritmo"] if prev else cur["livre"]
    ini_plano = prev["com_plano"] if prev else cur["livre"]
    mov = a_receber - a_pagar - a_assinar - a_parcelas - fixas
    certo = ini_certo + mov
    ja_var = sum((i["v"] for f in faturas for i in f["itens"] if not i["acc"].startswith("Expenses:Fixas")), ZERO)
    var = [c_ for c_ in fc.get("categorias", []) if c_["grupo"] == "Variaveis"]

    # fixas sem valor certo (Educação...): as assinaturas, o celular e o DAS já entram acima pelo valor exato
    das_conta, _ = _das()
    fix = [c_ for c_ in fc.get("categorias", []) if c_["grupo"] == "Fixas" and c_["modo"] != "assinaturas"
           and not c_["account"].startswith(das_conta)]
    contas_fix = tuple(c_["account"] for c_ in fix)
    ja_fix = sum((i["v"] for f in faturas for i in f["itens"] if contas_fix and i["acc"].startswith(contas_fix)), ZERO)

    # ---- gastos novos no ritmo médio: média dos últimos meses (sem o Planejamento) menos o que já está no cartão
    media_var = sum((c_["media"] for c_ in var), ZERO)
    media_fix = sum((c_["media"] for c_ in fix), ZERO)
    ritmo = (max(ZERO, media_var - ja_var) + max(ZERO, media_fix - ja_fix)).quantize(Decimal("0.01"))

    # ---- gastos novos pelo Planejamento: categorias como você definiu (valor fixo / ajuste em %),
    #      mais compromissos, extras e o quanto guardar no mês em que o ciclo termina
    ym = (end.year, end.month)
    plano_var = sum((c_["previsto"] for c_ in var), ZERO)
    plano_fix = sum((c_["previsto"] for c_ in fix), ZERO)
    plano_cats = [{"acc": c_["account"], "media": c_["media"], "previsto": c_["previsto"], "modo": c_["modo"]}
                  for c_ in var + fix if c_["modo"] != "media"]
    plano_itens = []
    for c_ in (cfg.get("compromissos") or []):
        ini, fim_ = str(c_.get("inicio") or ""), str(c_.get("fim") or "")
        mes = f"{ym[0]}-{ym[1]:02d}"
        if c_.get("tipo", "gasto") == "gasto" and (not ini or ini[:7] <= mes) and (not fim_ or mes <= fim_[:7]):
            plano_itens.append({"nome": c_.get("nome") or c_.get("descricao") or "Compromisso", "v": Decimal(str(c_.get("valor") or 0))})
    for x in (cfg.get("extras") or []):
        if x.get("tipo", "gasto") == "gasto" and str(x.get("mes"))[:7] == f"{ym[0]}-{ym[1]:02d}":
            plano_itens.append({"nome": x.get("descricao") or "Extra", "v": Decimal(str(x.get("valor") or 0))})
    guardar = Decimal(str((fc.get("invest") or {}).get(ym, 0)))
    if guardar:
        plano_itens.append({"nome": "Guardar (meta + investimentos)", "v": guardar})
    plano = (max(ZERO, plano_var - ja_var) + max(ZERO, plano_fix - ja_fix)
             + sum((i["v"] for i in plano_itens), ZERO)).quantize(Decimal("0.01"))

    return {"start": start, "end": end, "key": f"{end.year}-{end.month:02d}", "k": k,
            "ini_certo": ini_certo, "ini_ritmo": ini_ritmo, "ini_plano": ini_plano,
            "antes_ritmo": ini_ritmo + mov, "antes_plano": ini_plano + mov,
            "receber": receber, "a_receber": a_receber, "faturas": faturas, "a_pagar": a_pagar,
            "assinaturas": assinaturas, "a_assinar": a_assinar, "parcelas": parcelas, "a_parcelas": a_parcelas,
            "fixas_fora": fixas_fora, "fixas": fixas, "certo": certo, "ja_var": ja_var,
            "media_var": media_var, "media_fix": media_fix, "plano_fix": plano_fix, "ja_fix": ja_fix,
            "fix_nomes": [c_["account"].split(":")[-1] for c_ in fix], "ritmo": ritmo, "com_ritmo": ini_ritmo + mov - ritmo,
            "plano_var": plano_var, "plano_cats": plano_cats, "plano_itens": plano_itens, "plano": plano,
            "com_plano": ini_plano + mov - plano}


def futuros(entries, today: date, fc: dict, cur: dict, minimo: int = 1, maximo: int = 24) -> list[dict]:
    """Prévias encadeadas do próximo ciclo até o último em que ainda cai uma parcela já comprada."""
    cards, inicio = _cfg()
    ultimo = cur["end"]
    for p in fc.get("parcelas_futuras") or []:
        c = cards.get(p["pay"])
        ultimo = max(ultimo, card_due(p["date"], int(c["fecha"]), int(c["vence"])) if c else p["date"])
    n = 0
    while n < maximo:
        _, e = cycle_by_end(*_add_month(cur["end"].year, cur["end"].month, n), inicio)
        if e >= ultimo:
            break
        n += 1
    evs = events(entries)
    out, prev = [], None
    for k in range(1, max(minimo, n) + 1):
        prev = proximo(entries, today, fc, cur, k, prev, evs)
        out.append(prev)
    return out
