"""Extensão do Fava: página inicial "Resumo".

Estrutura esperada das contas (ver config/rules.yaml):
  Income:<Grupo>:<Fonte>                 -> Receitas
  Expenses:Fixas:<Categoria>[:<Sub>]     -> Despesas fixas
  Expenses:Variaveis:<Categoria>[:<Sub>] -> Despesas variáveis
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from beancount.core.data import Balance, Transaction
from fava.ext import FavaExtensionBase, extension_endpoint

from app.forecast import DOACOES as DOACOES_ACC
from app.forecast import forecast

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MESES_LONGOS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
                "Setembro", "Outubro", "Novembro", "Dezembro"]

# nomes das contas sem acento (exigência do Beancount) -> nome para exibir
NOMES = {
    "Trabalho": "Trabalho", "Outras": "Outras",
    "Educacao": "Educação", "Assinaturas": "Assinaturas", "Impostos": "Impostos (DAS)", "Moradia": "Moradia",
    "Faculdade": "Faculdade", "Cursos": "Cursos", "Ingles": "Inglês",
    "Mercado": "Mercado", "Restaurantes": "Restaurantes e bares", "Delivery": "Delivery",
    "Transporte": "Transporte", "Uber": "Uber", "Combustivel": "Combustível", "Pedagio": "Pedágio",
    "Estacionamento": "Estacionamento", "Lazer": "Lazer", "Compras": "Compras", "Vestuario": "Vestuário",
    "Eletronicos": "Eletrônicos", "Online": "Online", "Saude": "Saúde e cuidados", "Viagem": "Viagem",
    "Familia": "Família e doações", "Presentes": "Presentes", "Extra": "Hora extra / bônus", "Doacoes": "Doações (meta)", "Outros": "Outros", "Celular": "Celular", "Tarifas": "Tarifas e IOF", "A-Revisar": "A revisar", "Reembolso-sem-detalhe": "Reembolsos sem detalhe",
}

COV_NOMES = {
    "Assets:Inter:PF": "Conta Inter PF", "Assets:Cora:PJ": "Conta Cora PJ",
    "Liabilities:Cartao:Inter": "Cartão Inter", "Liabilities:Cartao:Nubank": "Cartão Nubank",
    "Assets:Fora-dos-Extratos": "Outra conta",
    "Assets:Nubank:Conta": "Conta Nubank PF",
}

SECTIONS = [
    ("fixas", "Despesas fixas", "Expenses:Fixas", "Repetem todo mês: faculdade, cursos, assinaturas, DAS"),
    ("variaveis", "Despesas variáveis", "Expenses:Variaveis", "Mudam mês a mês: mercado, restaurantes, transporte"),
]


_CONTAS_CFG: dict = {}


def contas_cfg() -> dict:
    """config/accounts.yaml (relido quando o arquivo muda)."""
    import yaml
    from app.paths import CONFIG
    f = CONFIG / "accounts.yaml"
    m = f.stat().st_mtime if f.exists() else 0
    if _CONTAS_CFG.get("m") != m:
        _CONTAS_CFG.update(m=m, cfg=(yaml.safe_load(f.read_text()) or {}) if m else {})
    return _CONTAS_CFG["cfg"]


def empresas() -> dict:
    """Quem paga você e pode reembolsar gastos: nome da conta (sem acento) -> nome para exibir."""
    return {str(k): str(v) for k, v in (contas_cfg().get("empresas") or {}).items()}


def contas_ordem() -> list:
    """Contas da config (accounts.yaml: sources + ofx_contas), agrupando conta e cartão do mesmo banco,
    mais uma "a receber" por empresa e a conta genérica."""
    cfg = contas_cfg()
    accs = [*(cfg.get("sources") or {}).values(),
            *(c["conta"] for c in (cfg.get("ofx_contas") or {}).values() if not c.get("ignorar"))]
    banco = lambda a: a.split(":")[-1] if a.startswith("Liabilities:") else a.split(":")[1]  # noqa: E731
    bancos = list(dict.fromkeys(banco(a) for a in accs))
    accs = sorted(dict.fromkeys(accs), key=lambda a: (bancos.index(banco(a)), a.startswith("Liabilities:")))
    return [*accs, *(f"Assets:Reembolsos:{k}" for k in empresas()), "Assets:Fora-dos-Extratos"]


def conta_tipo(a: str) -> str:
    return ("reembolso" if a.startswith("Assets:Reembolsos:") else "outra" if a == "Assets:Fora-dos-Extratos"
            else "cartao" if a.startswith("Liabilities:") else "conta")


def contas_nomes() -> dict:
    cfg = contas_cfg()
    ofx = {c["conta"]: c["nome"] for c in (cfg.get("ofx_contas") or {}).values() if c.get("nome")}
    return {**COV_NOMES, **ofx, **{f"Assets:Reembolsos:{k}": f"A receber · {n}" for k, n in empresas().items()}}


def label(account: str) -> str:
    if account.endswith(":Extra"):
        return f"{label(account.rsplit(':', 1)[0])} · hora extra/bônus"
    nome = account.split(":")[-1]
    return empresas().get(nome) or (contas_cfg().get("nomes") or {}).get(nome) or NOMES.get(nome, nome)


def brl(v, cents: bool = False) -> str:
    if v is None:
        return ""
    s = f"{abs(v):,.{2 if cents else 0}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if v < 0 else "") + s


def zeros():
    return [Decimal(0)] * 12


def add(a, b):
    return [x + y for x, y in zip(a, b)]


class _Comum:
    """O que toda aba expõe aos templates (window.FIN, em _style.html)."""

    def fin_js(self) -> dict:
        return {"empresas": empresas()}

    def fin_textos(self) -> dict:
        """Pedaços de texto que dependem da config (dias de pagamento, contas, fechamento dos cartões)."""
        cfg = contas_cfg()
        dias = sorted({int(v["dia"]) for v in (cfg.get("pagamentos") or {}).values() if v.get("dia")})
        contas = [a for a in contas_ordem() if conta_tipo(a) == "conta"]
        nomes = contas_nomes()
        fechas = sorted({int(c["fecha"]) for c in (cfg.get("card_cycles") or {}).values() if c.get("fecha")})
        dias_txt = (f"do dia {dias[0]}" if len(dias) == 1 else
                    f"dos dias {', '.join(map(str, dias[:-1]))} e {dias[-1]}" if dias else "")
        return {"dias": dias_txt, "contas": " + ".join(nomes.get(a, label(a)).replace("Conta ", "") for a in contas),
                "fecha": " e ".join(map(str, fechas))}


class Resumo(_Comum, FavaExtensionBase):
    report_title = "Resumo"
    has_js_module = True

    MESES = MESES

    def brl(self, v, cents=False):
        return brl(v, cents)

    def pct(self, part, whole):
        return float(part) / float(whole) * 100 if whole else 0.0

    # ------------------------------------------------------------------ dados
    def data(self, ano: str | None, mes: str | None):
        txns = [e for e in self.ledger.all_entries if isinstance(e, Transaction)]
        years = sorted({e.date.year for e in txns}) or [date.today().year]
        year = int(ano) if ano and ano.isdigit() and int(ano) in years else years[-1]

        per_account = defaultdict(zeros)
        revisar = 0
        cov = defaultdict(lambda: [0] * 12)
        for e in txns:
            if any(p.account.endswith("A-Revisar") for p in e.postings):
                revisar += 1
            if e.date.year != year:
                continue
            m = e.date.month - 1
            if e.meta.get("fonte"):
                cov[e.postings[0].account][m] += 1
            for p in e.postings:
                if p.account.startswith(("Income:", "Expenses:")):
                    per_account[p.account][m] += p.units.number

        today = date.today()
        fc = forecast(self.ledger.all_entries, today)
        fcm = {m - 1 for y, m in fc["months"] if y == year}
        prev = defaultdict(zeros)
        for acc, by_ym in fc["per_account"].items():
            for (y, m), v in by_ym.items():
                if y == year:
                    prev[acc][m - 1] += v
                    per_account[acc]  # garante a linha mesmo sem realizado no ano

        # ---- receitas: uma linha por fonte (Income:Grupo:Fonte)
        income = []
        for acc, months in per_account.items():
            if acc.startswith("Income:"):
                income.append(self._row(acc, [-v for v in months], [-v for v in prev[acc]], fcm))
        income = [r for r in income if r["total"] or any(r["show"])]
        income.sort(key=lambda r: -r["total"])

        # ---- despesas: seção -> categoria (nível 3) -> subcategoria (nível 4+)
        sections = []
        for key, title, prefix, hint in SECTIONS:
            cats = defaultdict(lambda: {"months": zeros(), "prev": zeros(), "subs": {}})
            for acc, months in per_account.items():
                if not acc.startswith(prefix + ":"):
                    continue
                cat = ":".join(acc.split(":")[:3])
                cats[cat]["months"] = add(cats[cat]["months"], months)
                cats[cat]["prev"] = add(cats[cat]["prev"], prev[acc])
                if acc != cat:
                    cats[cat]["subs"][acc] = (months, prev[acc])
            rows = []
            for cat, c in cats.items():
                r = self._row(cat, c["months"], c["prev"], fcm)
                r["subs"] = sorted((self._row(s, m, pv, fcm) for s, (m, pv) in c["subs"].items()),
                                   key=lambda x: -x["total"])
                r["review"] = cat.endswith("A-Revisar")
                rows.append(r)
            rows.sort(key=lambda r: (r["review"], -r["total"]))  # "A revisar" sempre por último
            months, pv = zeros(), zeros()
            for r in rows:
                months = add(months, r["months"])
                pv = add(pv, r["prev"])
            sections.append({"key": key, "title": title, "hint": hint, "rows": rows,
                             "total": self._row(prefix, months, pv, fcm)})

        rec, rec_show = zeros(), zeros()
        for r in income:
            rec = add(rec, r["months"])
            rec_show = add(rec_show, r["show"])
        fixas, variaveis = sections[0]["total"]["months"], sections[1]["total"]["months"]
        fixas_show, variaveis_show = sections[0]["total"]["show"], sections[1]["total"]["show"]
        desp = add(fixas, variaveis)
        res = [r - d for r, d in zip(rec, desp)]
        res_show = [r - f - v for r, f, v in zip(rec_show, fixas_show, variaveis_show)]
        has_data = [bool(rec[i] or desp[i]) for i in range(12)]
        is_fc = [i in fcm for i in range(12)]
        acumulado, acc = [], Decimal(0)
        for i in range(12):
            acc += res_show[i]
            acumulado.append(acc if (has_data[i] or is_fc[i]) else None)

        partial = today.month - 1 if today.year == year else None
        complete = [i for i in range(12) if has_data[i] and rec[i] and i != partial]
        if mes and mes.isdigit() and 1 <= int(mes) <= 12 and has_data[int(mes) - 1]:
            focus = int(mes) - 1
        else:
            focus = complete[-1] if complete else max((i for i in range(12) if has_data[i]), default=0)

        last = max((i for i in range(12) if has_data[i]), default=-1)
        missing_income = [MESES[i] for i in range(last + 1) if desp[i] and not rec[i]]
        # período comparável: meses com receita e já fechados (o mês atual ainda não tem todas as faturas)
        months_with_income = [i for i in range(12) if rec[i] and i != partial]

        comp_rec = sum(rec[i] for i in months_with_income)
        comp_desp = sum(desp[i] for i in months_with_income)
        comp_fix = sum(fixas[i] for i in months_with_income)
        comp_var = sum(variaveis[i] for i in months_with_income)

        # ranking de categorias no ano (todas as seções)
        ranking = sorted(
            ({"name": r["name"], "total": r["total"], "section": s["key"], "account": r["account"]}
             for s in sections for r in s["rows"] if r["total"] > 0 and not r["review"]),
            key=lambda x: -x["total"])[:8]
        rank_max = ranking[0]["total"] if ranking else 1

        saldo = self._saldo()
        proj, run = [], saldo["total"] + fc.get("a_receber_mes", 0) - fc["gap"]
        for t in fc["totals"][:4]:
            run += t["sobra"]
            proj.append({"mes": f"{MESES_LONGOS[t['ym'][1] - 1]}" + (f" de {t['ym'][0]}" if t["ym"][0] != today.year else ""),
                         "v": run, "invest": t["invest"]})
        parcelas = [dict(p, mes=p["ym"][1] - 1) for p in fc["parcelas"] if p["ym"][0] == year]
        previsao = {
            "months": sorted(fcm), "gap": fc["gap"], "a_receber": fc.get("a_receber_mes", 0), "hoje": saldo["total"],
            "proj": proj, "parcelas": parcelas,
            "extras": [], "base": " e ".join(", ".join(MESES[m - 1] for _, m in fc["base"]).rsplit(", ", 1)) if fc["base"] else "",
            "fim_ano": acumulado[11] if fcm else None,
            "parcelas_total": sum((p["valor"] for p in parcelas), Decimal(0)),
            "invest": any(t["invest"] for t in fc["totals"]),
        }

        return {
            "saldo": saldo, "previsao": previsao, "is_fc": is_fc,
            "rec_show": rec_show, "fixas_show": fixas_show, "variaveis_show": variaveis_show, "res_show": res_show,
            "year": year, "years": years, "income": income, "sections": sections,
            "rec": rec, "fixas": fixas, "variaveis": variaveis, "desp": desp, "res": res,
            "acumulado": acumulado, "partial": partial, "has_data": has_data,
            "missing_income": missing_income, "revisar": revisar,
            "focus": {
                "i": focus, "name": MESES_LONGOS[focus], "rec": rec[focus], "fixas": fixas[focus],
                "variaveis": variaveis[focus], "res": res[focus],
            },
            "periodo": {
                "n": len(months_with_income),
                "de": MESES[months_with_income[0]] if months_with_income else "",
                "ate": MESES[months_with_income[-1]] if months_with_income else "",
                "rec": comp_rec, "desp": comp_desp, "fixas": comp_fix, "variaveis": comp_var,
                "res": comp_rec - comp_desp,
                "media_res": (comp_rec - comp_desp) / len(months_with_income) if months_with_income else 0,
            },
            "ranking": ranking, "rank_max": rank_max,
            "coverage": [{"name": COV_NOMES.get(a, a), "months": m} for a, m in sorted(cov.items())],
            "chart": self._chart(fixas_show, variaveis_show, rec_show, has_data, partial, is_fc),
            "res_chart": self._res_chart(res_show, has_data, partial, is_fc),
        }

    # ------------------------------------------------------------------ mini gráfico do resultado (barras +/-)
    def _res_chart(self, res, has_data, partial, is_fc):
        W, H, pad_b = 600, 132, 18
        mid = (H - pad_b) / 2
        peak = max([abs(float(v)) for v in res] + [1])
        col = W / 12
        bw = min(26, col * 0.55)
        bars = []
        for i, v in enumerate(res):
            if not (has_data[i] or is_fc[i]):
                continue
            h = max(1.5, abs(float(v)) / peak * (mid - 6))
            x = col * i + (col - bw) / 2
            y = mid - h if v >= 0 else mid
            bars.append({"x": x, "y": y, "w": bw, "h": h, "pos": v >= 0, "partial": i == partial, "m": i + 1,
                         "fc": is_fc[i],
                         "tip": f"{MESES_LONGOS[i]} · {'previsto: ' if is_fc[i] else ''}{'sobra' if v >= 0 else 'falta'} R$ {brl(abs(v), True)}",
                         "label_y": (y - 5) if v >= 0 else (y + h + 12), "label": brl(v)})
        labels = [{"x": col * i + col / 2, "text": MESES[i], "dim": not (has_data[i] or is_fc[i])} for i in range(12)]
        return {"W": W, "H": H, "mid": mid, "bars": bars, "labels": labels}

    # ------------------------------------------------------------------ saldo de hoje
    def _saldo(self):
        """Dinheiro nas contas menos o que se deve nos cartões (só contas vindas de extrato)."""
        bal = defaultdict(Decimal)
        checked = {}
        last = {}
        vence = {}
        for e in self.ledger.all_entries:
            if isinstance(e, Transaction):
                for p in e.postings:
                    if p.account.startswith(("Assets:Inter", "Assets:Cora", "Assets:Nubank:Conta", "Liabilities:Cartao")):
                        bal[p.account] += p.units.number
                        if e.meta.get("fonte"):
                            last[p.account] = max(last.get(p.account, e.date), e.date)
                        if e.meta.get("vence"):
                            v = date.fromisoformat(e.meta["vence"])
                            vence[p.account] = max(vence.get(p.account, v), v)
            elif isinstance(e, Balance):
                checked[e.account] = e.date
        contas = [{"name": COV_NOMES.get(a, a), "v": v, "checked": checked.get(a), "ate": last.get(a)}
                  for a, v in sorted(bal.items()) if a.startswith("Assets:")]
        today = date.today()
        from app.cycles import faturas_abertas
        abertas = faturas_abertas(self.ledger.all_entries, today)
        cartoes = []
        for a, v in sorted(bal.items()):
            if not a.startswith("Liabilities:"):
                continue
            due, pendente = vence.get(a), False
            if due and due < today:
                # a última fatura importada já venceu: a próxima ainda não chegou (compras novas faltando)
                y, m = divmod(due.month, 12)
                due, pendente = due.replace(year=due.year + y, month=m + 1), True
            ab = abertas.get(a)
            if ab and ab["depois"] > 0 and ab["agora"] >= 0:  # separa a fatura que vence agora das compras da seguinte
                due, pendente = ab["due"], False
            cartoes.append({"name": COV_NOMES.get(a, a), "v": v, "a_pagar": -v, "vence": due, "pendente": pendente,
                            "agora": ab["agora"] if ab else -v, "depois": ab["depois"] if ab else Decimal(0)})
        total_contas = sum((c["v"] for c in contas), Decimal(0))
        total_cartoes = sum((c["v"] for c in cartoes), Decimal(0))
        return {"contas": contas, "cartoes": cartoes, "total_contas": total_contas,
                "total_cartoes": total_cartoes, "total": total_contas + total_cartoes,
                "checked": max(checked.values()) if checked else None,
                "ate": max((c["ate"] for c in contas if c["ate"]), default=None)}

    def _row(self, account, months, prev=None, fcm=frozenset()):
        """months = realizado; prev = previsão; show = realizado com os meses futuros preenchidos pela previsão."""
        prev = prev or zeros()
        total = sum(months)
        active = [v for v in months if v]
        peak = max((abs(v) for v in months), default=0) or 1
        return {"account": account, "name": label(account), "months": months, "prev": prev,
                "show": [prev[i] if i in fcm else months[i] for i in range(12)],
                "total": total, "avg": total / len(active) if active else Decimal(0),
                "heat": [round(float(abs(v) / peak) * 100) for v in months]}

    # ------------------------------------------------------------------ gráfico (SVG gerado no servidor)
    def _chart(self, fixas, variaveis, rec, has_data, partial, is_fc):
        W, H, pad_l, pad_r, pad_t, pad_b = 960, 280, 48, 8, 16, 28
        plot_h = H - pad_t - pad_b
        col_w = (W - pad_l - pad_r) / 12
        bar_w = min(34, col_w * 0.5)
        peak = max([float(fixas[i] + variaveis[i]) for i in range(12)] + [float(v) for v in rec] + [1])
        step = next(s for s in (500, 1000, 2000, 2500, 5000, 10000, 20000) if peak / s <= 5)
        top_v = step * (int(peak // step) + 1)

        def y(v):
            return pad_t + plot_h - float(v) / top_v * plot_h

        grid = [{"y": y(v), "label": brl(v)} for v in range(0, int(top_v) + 1, step)]
        bars, marks, cols = [], [], []
        for i in range(12):
            cx = pad_l + col_w * i
            x = cx + (col_w - bar_w) / 2
            cols.append({"x": cx, "w": col_w, "i": i + 1, "has": has_data[i]})
            segs = [("fix", "Fixas", fixas[i]), ("var", "Variáveis", variaveis[i])]
            segs = [s for s in segs if s[2] > 0]
            base = Decimal(0)
            for j, (cls, name, v) in enumerate(segs):
                y0, y1 = y(base), y(base + v)
                is_top = j == len(segs) - 1
                h = max(0.0, y0 - y1 - (0 if is_top else 2))  # 2px de respiro entre segmentos
                r = min(4.0, h / 2) if is_top else 0.0
                d = (f"M{x:.1f},{y1 + h:.1f}V{y1 + r:.1f}Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f}"
                     f"H{x + bar_w - r:.1f}Q{x + bar_w:.1f},{y1:.1f} {x + bar_w:.1f},{y1 + r:.1f}V{y1 + h:.1f}Z")
                bars.append({"d": d, "cls": cls, "partial": i == partial, "fc": is_fc[i],
                             "tip": f"{MESES_LONGOS[i]} · {'previsto · ' if is_fc[i] else ''}{name}: R$ {brl(v, True)}"})
                base += v
            if rec[i]:
                marks.append({"x1": x - 7, "x2": x + bar_w + 7, "y": y(rec[i]), "fc": is_fc[i],
                              "tip": f"{MESES_LONGOS[i]} · {'previsto · ' if is_fc[i] else ''}Receita: R$ {brl(rec[i], True)}"})
        labels = [{"x": pad_l + col_w * i + col_w / 2, "text": MESES[i], "dim": not (has_data[i] or is_fc[i])}
                  for i in range(12)]
        return {"W": W, "H": H, "grid": grid, "bars": bars, "marks": marks, "labels": labels,
                "cols": cols, "pad_l": pad_l, "right": W - pad_r, "base_y": y(0), "top": pad_t}


# ====================================================================== aba "Gastos"

MEIO_ORDEM = ["Crédito Inter", "Crédito Nubank", "Débito Inter", "Débito Nubank", "Pix", "Pix no crédito",
              "TED", "Boleto", "Pix PJ", "Transferência", "Outro"]


class Gastos(_Comum, FavaExtensionBase):
    """Todos os gastos com filtros por meio de pagamento, cartão, categoria e período."""

    report_title = "Gastos"
    has_js_module = True

    def _card_names(self) -> dict:
        from pathlib import Path

        import yaml

        cfg = Path(self.ledger.beancount_file_path).resolve().parent.parent / "config" / "accounts.yaml"
        try:
            return {str(k): v for k, v in (yaml.safe_load(cfg.read_text()).get("cards") or {}).items()}
        except Exception:
            return {}

    def rows(self) -> list[dict]:
        cards = self._card_names()
        out = []
        for e in self.ledger.all_entries:
            if not isinstance(e, Transaction):
                continue
            pay = next((p for p in e.postings if not p.account.startswith(("Expenses:", "Assets:Reembolsos"))), None)
            # identidade do lançamento importado (a mesma usada pelo build para marcar reembolsáveis)
            manual_p = str(Path(self.ledger.beancount_file_path).resolve().parent / "manual.beancount")
            if e.meta.get("filename") == manual_p:  # lançado à mão (inclusive provisórios): marca direto no arquivo
                key = f"manual:{e.meta.get('lineno')}"
            else:
                key = (f"{e.date}|{pay.account}|{pay.units.number:.2f}|{e.narration}"
                       if pay and e.meta.get("fonte") else "")
            for p in e.postings:
                reemb = ""
                if p.account.startswith("Assets:Reembolsos:") and p.units.number > 0:
                    reemb, acc = p.account.split(":")[-1], str(e.meta.get("categoria") or "Expenses:Variaveis:Outros")
                elif p.account.startswith("Expenses:"):
                    acc = p.account
                else:
                    continue
                parts = acc.split(":")
                grupo = {"Fixas": "Fixas", "Variaveis": "Variáveis"}.get(parts[1], parts[1]) if len(parts) > 1 else ""
                cartao = e.meta.get("cartao")
                out.append({
                    "d": e.date.isoformat(), "desc": e.narration, "g": grupo,
                    "c": label(":".join(parts[:3])), "s": label(acc) if len(parts) > 3 else "", "acc": acc,
                    "meio": e.meta.get("meio") or "Outro",
                    "cartao": cards.get(str(cartao), f"final {cartao}") if cartao else "",
                    "parc": e.meta.get("parcela", ""), "v": float(p.units.number),
                    "reemb": reemb, "key": key,
                })
        out.sort(key=lambda r: r["d"], reverse=True)
        return out

    def _reembolso_manual(self, lineno: int, fonte: str):
        """Marca/desmarca um lançamento de manual.beancount como reembolsável, editando o próprio bloco."""
        mp = Path(self.ledger.beancount_file_path).resolve().parent / "manual.beancount"
        lines = mp.read_text().split("\n")
        i = lineno - 1
        if not (0 <= i < len(lines)) or not re.match(r"^\d{4}-\d{2}-\d{2} ", lines[i]):
            return False, "Lançamento não encontrado. Recarregue a página."
        fim = i + 1
        while fim < len(lines) and lines[fim].strip():
            fim += 1
        bloco = lines[i:fim]
        cat = next((re.search(r'categoria: "([^"]+)"', l).group(1) for l in bloco if "categoria:" in l), None)
        # tira marcação antiga
        bloco = [l for l in bloco if not re.match(r'\s+(reembolso|categoria):', l)]
        idx = next((k for k, l in enumerate(bloco) if re.match(r"\s+(Expenses:|Assets:Reembolsos:)", l)), None)
        if idx is None:
            return False, "Só dá para marcar gastos."
        conta_atual = bloco[idx].split()[0]
        original = cat or conta_atual
        if fonte:
            bloco[idx] = bloco[idx].replace(conta_atual, f"Assets:Reembolsos:{fonte}", 1)
            bloco[1:1] = [f'  reembolso: "{fonte}"', f'  categoria: "{original}"']
        else:
            bloco[idx] = bloco[idx].replace(conta_atual, original, 1)
        lines[i:fim] = bloco
        mp.write_text("\n".join(lines))
        return True, ""

    @extension_endpoint("reembolso", ["POST"])
    def reembolso(self):
        """Marca/desmarca um gasto importado como reembolsável e reimporta."""
        from pathlib import Path

        import yaml
        from flask import jsonify, request

        from app.build import build, ler_reembolsos_cfg, salvar_reembolsos_cfg

        j = request.get_json(force=True)
        fonte = str(j.get("fonte") or "")
        keys = [str(k) for k in (j.get("keys") or [j.get("key")]) if k]
        if not keys and not j.get("periodo"):
            return jsonify({"ok": False, "erro": "Esse lançamento não pode ser marcado."}), 400
        for k in [k for k in keys if k.startswith("manual:")]:
            ok, erro = self._reembolso_manual(int(k.split(":")[1]), fonte)
            if not ok and len(keys) == 1:
                return jsonify({"ok": False, "erro": erro}), 400
        imp = {k for k in keys if not k.startswith("manual:")}
        head, cfg = ler_reembolsos_cfg()
        cfg["gastos"] = [g for g in (cfg.get("gastos") or []) if g.get("key") not in imp]
        cfg["nao"] = [k for k in (cfg.get("nao") or []) if k not in imp]
        if fonte:
            cfg["gastos"] += [{"key": k, "fonte": fonte} for k in keys if k in imp]
        else:  # "não é reembolsável": vale também contra um período de viagem lembrado
            cfg["nao"] += sorted(imp)
        per = j.get("periodo")
        if per and fonte:  # lembrar o período: o que chegar depois (fatura que ainda vai fechar) também entra
            de, ate = sorted([str(per["de"]), str(per["ate"])])
            cfg["periodos"] = [x for x in (cfg.get("periodos") or []) if not (str(x.get("de")) == de and str(x.get("ate")) == ate)]
            cfg["periodos"].append({"de": de, "ate": ate, "fonte": fonte, "nome": str(per.get("nome") or "Viagem")})
        salvar_reembolsos_cfg(head, cfg)
        build(verbose=False)
        self.ledger.load_file()  # recarrega já, para a próxima tela vir atualizada
        return jsonify({"ok": True, "n": len(keys)})

    @extension_endpoint("periodo_remover", ["POST"])
    def periodo_remover(self):
        """Esquece um período lembrado. Os gastos que ele marcou voltam a ser seus (os marcados um a um ficam)."""
        from flask import jsonify, request

        from app.build import build, ler_reembolsos_cfg, salvar_reembolsos_cfg
        j = request.get_json(force=True)
        head, cfg = ler_reembolsos_cfg()
        cfg["periodos"] = [x for x in (cfg.get("periodos") or [])
                           if not (str(x.get("de")) == str(j.get("de")) and str(x.get("ate")) == str(j.get("ate")))]
        salvar_reembolsos_cfg(head, cfg)
        build(verbose=False)
        self.ledger.load_file()
        return jsonify({"ok": True})

    def periodos_reembolso(self):
        from app.build import ler_reembolsos_cfg
        return [{**{k: str(v) for k, v in x.items()}} for x in ler_reembolsos_cfg()[1].get("periodos") or []]

    def meio_ordem(self):
        return MEIO_ORDEM

    def periodos(self):
        """Datas dos atalhos de período (hoje, ciclo atual) para a aba Gastos."""
        from app.cycles import _cfg, cycle_of
        hoje = date.today()
        ini, fim = cycle_of(hoje, _cfg()[1])
        return {"hoje": hoje.isoformat(), "ciclo_de": ini.isoformat(), "ciclo_ate": fim.isoformat()}


# ====================================================================== aba "Planejamento"

def _plain(v):
    """Decimal/tuplas/datas -> tipos JSON."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, tuple) and len(v) == 2 and all(isinstance(x, int) for x in v):
        return f"{v[0]}-{v[1]:02d}"
    if isinstance(v, dict):
        return {(_plain(k) if isinstance(k, tuple) else k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, date):
        return v.isoformat()
    return v


# sugestões de compromisso de 1 clique na aba Planejamento (accounts.yaml -> sugestoes substitui estas)
SUGESTOES = [
    {"descricao": "Aporte mensal", "tipo": "investimento", "conta": "", "valor": 500.00},
    {"descricao": "Ajuda para a família", "tipo": "gasto", "conta": "Expenses:Variaveis:Familia", "valor": 300.00},
    {"descricao": "Celular", "tipo": "gasto", "conta": "Expenses:Fixas:Celular", "valor": 50.00},
]


def _orc_grupo(account: str) -> str:
    """Necessidade (contas fixas e o essencial do dia a dia) ou desejo (restaurante, lazer, compras...), como no 50/30/20."""
    partes = account.split(":")
    return "nec" if (len(partes) > 1 and partes[1] == "Fixas") or (len(partes) > 2 and partes[2] in ESSENCIAIS) else "des"


class Planejamento(_Comum, FavaExtensionBase):
    """Editor da previsão: receitas, ajustes por categoria, compromissos, metas e extras."""

    report_title = "Planejamento"
    has_js_module = True

    def _payload(self, cfg=None):
        today = date.today()
        fc = forecast(self.ledger.all_entries, today, cfg=cfg)
        saldo = Resumo._saldo(self)
        start = saldo["total"] + fc.get("a_receber_mes", 0) - fc["gap"]
        run, rows = start, []
        for t in fc["totals"]:
            run += t["sobra"]
            rows.append({**t, "saldo": run, "label": f"{MESES[t['ym'][1] - 1]}/{str(t['ym'][0])[2:]}"})
        for c in fc["receitas"] + fc["categorias"]:
            c["name"] = label(c["account"])
        for c in fc["categorias"]:
            c["orc"] = _orc_grupo(c["account"])
        # orçamento do próximo mês no modelo 50/30/20: necessidades, desejos, guardar (com parcelas e compromissos)
        orc = None
        if fc["months"]:
            ym0 = fc["months"][0]
            nec = des = Decimal(0)
            for a, v in fc["per_account"].items():
                if a.startswith("Expenses:") and v.get(ym0):
                    if _orc_grupo(a) == "nec":
                        nec += v[ym0]
                    else:
                        des += v[ym0]
            t0 = fc["totals"][0]
            orc = {"label": f"{MESES_LONGOS[ym0[1] - 1]} de {ym0[0]}", "rec": t0["rec"], "nec": nec, "des": des,
                   "guardar": t0["invest"], "sobra": t0["sobra"]}
        contas = sorted({p.account for e in self.ledger.all_entries if isinstance(e, Transaction)
                         for p in e.postings if p.account.startswith(("Expenses:", "Income:"))} | {DOACOES_ACC})
        opcoes = sorted({":".join(a.split(":")[:3]) for a in contas}, key=lambda a: (a.split(":")[0] != "Expenses", a))
        return _plain({
            "rows": rows, "start": start, "hoje": saldo["total"], "gap": fc["gap"],
            "base": [f"{MESES[m - 1]}/{str(y)[2:]}" for y, m in fc["base"]],
            "receitas": fc["receitas"], "categorias": fc["categorias"], "parcelas": fc["parcelas"],
            "config": fc["config"], "contas": [{"account": a, "name": ("Receita · " if a.startswith("Income") else "")
                                                + (("Fixas · " if ":Fixas:" in a + ":" else "Variáveis · ") if a.startswith("Expenses") else "")
                                                + label(a)} for a in opcoes],
            "sugestoes": contas_cfg().get("sugestoes") or SUGESTOES, "orc": orc,
            "mei": self._mei(),
            "assinaturas": [{**{k: v for k, v in a.items() if k not in ("ultima", "proxima")},
                             "ultima": a["ultima"].isoformat(), "proxima": a["proxima"] and a["proxima"].isoformat(),
                             "cat": label(a["account"]), "cartao": a["pay"].startswith("Liabilities")}
                            for a in fc["assinaturas"]],
        })

    def _mei(self):
        import yaml
        cfg = yaml.safe_load((Path(self.ledger.beancount_file_path).resolve().parent.parent / "config" / "accounts.yaml").read_text())
        ano = date.today().year
        bruto = Decimal(0)
        for e in self.ledger.all_entries:
            if isinstance(e, Transaction) and e.date.year == ano:
                for p in e.postings:
                    if p.account.startswith("Income:Trabalho:"):
                        bruto -= p.units.number
                bruto += Decimal(str(e.meta.get("reembolso_recebido") or 0))
        return {"limite": (cfg.get("mei") or {}).get("limite_anual", 81000), "realizado": bruto, "ano": ano}

    def page_json(self):
        import json
        return json.dumps(self._payload(), ensure_ascii=False).replace("</", "<\\/")

    @extension_endpoint("simular", ["POST"])
    def simular(self):
        from flask import jsonify, request
        return jsonify(self._payload(request.get_json(force=True)))

    @extension_endpoint("assinatura", ["POST"])
    def assinatura(self):
        """Cancelei / Reativar uma assinatura (tira ou volta para a previsão)."""
        from flask import jsonify, request

        from app import assinaturas
        d = request.get_json(force=True)
        if d.get("acao") == "cancelar":
            assinaturas.cancelar(d["key"], d.get("nome", d["key"]), date.today())
        else:
            assinaturas.reativar(d["key"])
        return jsonify({"ok": True})

    @extension_endpoint("salvar", ["POST"])
    def salvar(self):
        from flask import jsonify, request

        from app.forecast import load_config, normalize, save_config
        cfg = normalize(request.get_json(force=True))
        atual = load_config()  # salário, aumentos e horas extras são editados na aba Receitas: preserva
        cfg["receitas"], cfg["extras_receita"] = atual["receitas"], atual["extras_receita"]
        save_config(cfg)
        return jsonify({"ok": True})


# ====================================================================== aba "Receitas"

class Receitas(_Comum, FavaExtensionBase):
    """Receitas por fonte: evolução, concentração, previsão e lista de recebimentos."""

    report_title = "Receitas"
    has_js_module = True

    def _salario(self):
        """Cadastro de salário/aumentos/horas extras (o mesmo plano usado pela previsão e pela conferência)."""
        from app.forecast import load_config
        cfg = load_config()
        fontes = sorted({p.account for e in self.ledger.all_entries if isinstance(e, Transaction)
                         for p in e.postings if p.account.startswith("Income:Trabalho:") and not p.account.endswith(":Extra")}
                        | set(a for a in cfg["receitas"] if a.startswith("Income:Trabalho:")))
        from statistics import median
        hoje = date.today()
        dias = defaultdict(list)
        for e in self.ledger.all_entries:
            if isinstance(e, Transaction) and e.date >= hoje - timedelta(days=150):
                for p in e.postings:
                    if p.account in fontes:
                        dias[p.account].append(e.date.day)

        import yaml

        from app.diasuteis import proximo_dia_util
        pag = (yaml.safe_load((Path(self.ledger.beancount_file_path).resolve().parent.parent / "config" / "accounts.yaml")
                              .read_text()) or {}).get("pagamentos") or {}

        def proximo(a):
            d = int((pag.get(a) or {}).get("dia") or (median(dias[a]) if dias[a] else 0))
            if not d:
                return None
            y, m = hoje.year, hoje.month
            cand = proximo_dia_util(date(y, m, min(d, 28)))
            if cand <= hoje:  # já passou este mês: próximo mês
                y, m = (y, m + 1) if m < 12 else (y + 1, 1)
                cand = proximo_dia_util(date(y, m, min(d, 28)))
            return cand.isoformat()

        return {"fontes": [{"account": a, "name": label(a), "proximo": proximo(a),
                            **(cfg["receitas"].get(a) or {"modo": "media"})} for a in fontes],
                "extras": cfg.get("extras_receita") or [], "hoje": hoje.isoformat()}

    @extension_endpoint("salvar_salario", ["POST"])
    def salvar_salario(self):
        from flask import jsonify, request

        from app.build import build
        from app.forecast import load_config, save_config
        j = request.get_json(force=True)
        cfg = load_config()
        for f in j.get("fontes") or []:
            acc = f.get("account", "")
            if not acc.startswith("Income:"):
                continue
            if f.get("modo") == "fixo":
                cfg["receitas"][acc] = {"modo": "fixo", "valor": float(f.get("valor") or 0),
                                        **({"aumentos": [{"desde": a["desde"], "valor": float(a["valor"])}
                                                         for a in f.get("aumentos") or [] if a.get("desde")]}
                                           if f.get("aumentos") else {})}
            else:
                cfg["receitas"].pop(acc, None)
        cfg["extras_receita"] = [{"fonte": x["fonte"], "mes": x["mes"], "valor": float(x.get("valor") or 0),
                                  "descricao": x.get("descricao", "")}
                                 for x in j.get("extras") or [] if x.get("fonte") and x.get("mes")]
        save_config(cfg)
        build(verbose=False)
        self.ledger.load_file()
        return jsonify({"ok": True})

    def _conferencia(self):
        """Cada pagamento de trabalho: esperado (salário vigente + extras informados) × recebido."""
        out = []
        for e in self.ledger.all_entries:
            if not isinstance(e, Transaction) or "esperado" not in e.meta:
                continue
            inc = [p for p in e.postings if p.account.startswith("Income:Trabalho:")]
            base_acc = min((p.account for p in inc), key=len)
            recebido = -sum((p.units.number for p in inc), Decimal(0))
            extra = -sum((p.units.number for p in inc if p.account.endswith(":Extra")), Decimal(0))
            reemb = Decimal(str(e.meta.get("reembolso_recebido") or 0))
            esperado = Decimal(str(e.meta["esperado"]))
            dif = recebido - esperado  # reembolso fica fora: é explicado à parte
            out.append({"d": e.date.isoformat(), "fonte": label(base_acc), "esperado": float(esperado),
                        "recebido": float(recebido + reemb), "extra": float(extra), "reemb": float(reemb),
                        "dif": float(dif)})
        return sorted(out, key=lambda r: r["d"], reverse=True)

    def _notas(self):
        """Notas fiscais emitidas × pagamentos recebidos (cada nota casa com o pagamento da mesma empresa)."""
        import yaml

        from app import nfse
        cfg = yaml.safe_load((Path(self.ledger.beancount_file_path).resolve().parent.parent / "config" / "accounts.yaml").read_text()) or {}
        tomadores = {str(k): v for k, v in (cfg.get("tomadores") or {}).items()}
        notas = nfse.todas()
        pags = []
        for e in self.ledger.all_entries:
            if not isinstance(e, Transaction) or "esperado" not in e.meta:
                continue
            inc = [p for p in e.postings if p.account.startswith("Income:Trabalho:")]
            fonte = min((p.account for p in inc), key=len)
            bruto = -sum((p.units.number for p in inc), Decimal(0)) + Decimal(str(e.meta.get("reembolso_recebido") or 0))
            pags.append({"d": e.date, "fonte": fonte, "valor": bruto, "usado": False})
        linhas = []
        for n in notas:
            t = tomadores.get(n["tomador_cnpj"]) or {}
            emi = date.fromisoformat(n["emissao"])
            cands = [p for p in pags if p["fonte"] == t.get("fonte") and not p["usado"] and abs((p["d"] - emi).days) <= 20]
            p = min(cands, key=lambda p: (abs(p["valor"] - Decimal(str(n["valor"]))) > Decimal("0.01"), abs((p["d"] - emi).days)), default=None)
            if p:
                p["usado"] = True
            dif = float(p["valor"]) - n["valor"] if p else None
            linhas.append({**n, "fonte": label(t["fonte"]) if t.get("fonte") else n["tomador"].title(),
                           "recebido": float(p["valor"]) if p else None, "recebido_em": p["d"].isoformat() if p else None,
                           "status": "aguardando" if not p else "ok" if abs(dif) < 0.01 else "diferente", "dif": dif})
        # pagamentos que deveriam ter nota e não têm (só a partir da primeira nota importada)
        exige = {v["fonte"] for v in tomadores.values() if v.get("exige_nota")}
        desde = date.fromisoformat(notas[0]["emissao"]) - timedelta(days=20) if notas else None
        for p in pags:
            if not p["usado"] and p["fonte"] in exige and desde and p["d"] >= desde:
                linhas.append({"numero": None, "fonte": label(p["fonte"]), "competencia": "", "emissao": "",
                               "valor": None, "recebido": float(p["valor"]), "recebido_em": p["d"].isoformat(),
                               "status": "sem_nota", "dif": None, "descricao": "", "pdf": False})
        linhas.sort(key=lambda l: l["recebido_em"] or l["emissao"], reverse=True)
        return {"linhas": linhas, "desde": notas[0]["emissao"] if notas else None,
                "total_ano": {str(y): sum(n["valor"] for n in notas if n["emissao"][:4] == str(y))
                              for y in {n["emissao"][:4] for n in notas}}}

    def _reembolsos(self):
        from pathlib import Path

        import yaml
        p = Path(self.ledger.beancount_file_path).resolve().parent.parent / "config" / "reembolsos.yaml"
        base = ((yaml.safe_load(p.read_text()) if p.exists() else {}) or {}).get("base") or {}
        return _reembolsos_de(self.ledger.all_entries, base)

    def page_json(self):
        import json

        rows = []
        for e in self.ledger.all_entries:
            if not isinstance(e, Transaction):
                continue
            inc = [p for p in e.postings if p.account.startswith("Income:")]
            if not inc:
                continue
            onde = [p.account for p in e.postings if not p.account.startswith("Income:")]
            for p in inc:
                rows.append({
                    "d": e.date.isoformat(), "acc": p.account,
                    "desc": re.sub(r"^(Transf Pix recebida|Pix recebido|TED recebida) - ", "", e.narration or e.payee or ""),
                    "fonte": label(p.account), "onde": COV_NOMES.get(onde[0], label(onde[0])) if onde else "",
                    "origem": "planilha antiga" if e.meta.get("fonte") == "planilha" else "extrato",
                    "v": float(-p.units.number), "reemb": float(e.meta.get("reembolso_recebido") or 0),
                })
        rows.sort(key=lambda r: r["d"], reverse=True)

        today = date.today()
        fc = forecast(self.ledger.all_entries, today)
        previsto = []
        for acc, by_ym in fc["per_account"].items():
            if acc.startswith("Income:"):
                for (y, m), v in by_ym.items():
                    previsto.append({"ym": f"{y}-{m:02d}", "acc": acc, "fonte": label(acc), "v": float(-v)})
        regras = {r["account"]: ("valor fixo" if r["modo"] == "fixo" else "média") for r in fc["receitas"]}
        from pathlib import Path

        import yaml
        cfg = yaml.safe_load((Path(self.ledger.beancount_file_path).resolve().parent.parent / "config" / "accounts.yaml").read_text())
        mei = cfg.get("mei") or {}
        return json.dumps({"rows": rows, "previsto": previsto, "regras": regras,
                           "mei": {"limite": mei.get("limite_anual", 81000)},
                           "reembolsos": self._reembolsos(),
                           "conferencia": self._conferencia(),
                           "notas": self._notas(),
                           "salario": self._salario(),
                           "hoje": today.isoformat()}, ensure_ascii=False).replace("</", "<\\/")


def _reembolsos_de(entries, base_cfg):
    """Pendências e histórico de reembolso por empresa."""
    pend, marcados, recebidos, acima = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal), []
    for e in entries:
        if not isinstance(e, Transaction):
            continue
        for p in e.postings:
            if p.account.startswith("Assets:Reembolsos:"):
                f = p.account.split(":")[-1]
                pend[f] += p.units.number
                if p.units.number > 0:
                    marcados[(f, e.date.year)] += p.units.number
                else:
                    recebidos[(f, e.date.year)] += -p.units.number
            elif p.account in base_cfg and -p.units.number > Decimal(str(base_cfg[p.account])) + 1 \
                    and not e.meta.get("reembolso_recebido"):
                # pagou acima do fixo e nenhum gasto reembolsável explica a diferença
                acima.append({"d": e.date.isoformat(), "fonte": label(p.account),
                              "extra": float(-p.units.number - Decimal(str(base_cfg[p.account])))})
    emp = empresas()
    return {"pendente": {emp.get(f, f): float(v) for f, v in pend.items()},
            "marcados": {f"{emp.get(f, f)}|{y}": float(v) for (f, y), v in marcados.items()},
            "recebidos": {f"{emp.get(f, f)}|{y}": float(v) for (f, y), v in recebidos.items()},
            "acima": sorted(acima, key=lambda a: a["d"], reverse=True)}


# ====================================================================== aba "Lançar"

PAGAMENTOS = {
    "despesa": [
        {"account": "Liabilities:Cartao:Inter", "label": "Crédito Inter", "meio": "Crédito Inter", "prov": True},
        {"account": "Liabilities:Cartao:Nubank", "label": "Crédito Nubank", "meio": "Crédito Nubank", "prov": True},
        {"account": "Assets:Inter:PF", "label": "Pix / débito Inter", "meio": "Pix", "prov": True},
        {"account": "Assets:Nubank:Conta", "label": "Pix Nubank", "meio": "Pix", "prov": True},
        {"account": "Assets:Dinheiro", "label": "Dinheiro", "meio": "Dinheiro", "prov": False},
        {"account": "Assets:Fora-dos-Extratos", "label": "Outra conta", "meio": "Outro", "prov": False},
    ],
    "receita": [
        {"account": "Assets:Cora:PJ", "label": "Conta PJ", "meio": "Pix PJ", "prov": True},
        {"account": "Assets:Inter:PF", "label": "Conta PF", "meio": "Pix", "prov": True},
        {"account": "Assets:Nubank:Conta", "label": "Nubank PF", "meio": "Pix", "prov": True},
        {"account": "Assets:Dinheiro", "label": "Dinheiro", "meio": "Dinheiro", "prov": False},
        {"account": "Assets:Fora-dos-Extratos", "label": "Outra conta", "meio": "Outro", "prov": False},
    ],
}


class Lancar(_Comum, FavaExtensionBase):
    """Lançamento manual rápido de receitas e despesas (grava em ledger/manual.beancount)."""

    report_title = "Lançar"
    has_js_module = True

    @property
    def manual_path(self):
        from pathlib import Path
        return Path(self.ledger.beancount_file_path).resolve().parent / "manual.beancount"

    def page_json(self):
        import json
        from pathlib import Path

        import yaml

        txns = [e for e in self.ledger.all_entries if isinstance(e, Transaction)]
        used = {p.account for e in txns for p in e.postings}
        cats = sorted({a for a in used if a.startswith(("Expenses:", "Income:")) and not a.endswith("A-Revisar")}
                      | {"Expenses:Variaveis:Outros", "Income:Outras:Outros"})

        def cat_label(a):
            parts = a.split(":")
            grupo = {"Fixas": "Fixas", "Variaveis": "Variáveis"}.get(parts[1], "") if a.startswith("Expenses") else ""
            nomes = " · ".join(label(":".join(parts[:i])) for i in range(3, len(parts) + 1))
            return (grupo + " · " if grupo else "") + nomes

        # histórico: descrição -> conta, para sugerir a categoria enquanto digita
        hist = []
        for e in reversed(txns[-1500:]):
            for p in e.postings:
                if p.account.startswith(("Expenses:", "Income:")) and not p.account.endswith("A-Revisar"):
                    hist.append([re.sub(r"^(Compra no débito|Pix enviado|Pix recebido|Transf Pix recebida) - ", "",
                                        e.narration or "").lower()[:40], p.account])
        rules_file = Path(self.ledger.beancount_file_path).resolve().parent.parent / "config" / "rules.yaml"
        try:
            rules = [{"match": r["match"], "account": r["account"]}
                     for r in yaml.safe_load(rules_file.read_text())["rules"]
                     if r["account"].startswith(("Expenses:", "Income:"))]
        except Exception:
            rules = []

        # lançamentos manuais existentes
        manual = []
        mp = str(self.manual_path)
        for e in txns:
            if e.meta.get("filename") != mp:
                continue
            cat = next((p for p in e.postings if p.account.startswith(("Expenses:", "Income:", "Assets:Reembolsos:"))), None)
            pay = next((p for p in e.postings if not p.account.startswith(("Expenses:", "Income:", "Assets:Reembolsos:"))), None)
            if not cat:
                continue
            pay_label = next((o["label"] for opts in PAGAMENTOS.values() for o in opts if pay and o["account"] == pay.account),
                             label(pay.account) if pay else "")
            nome_cat = (f"Reembolsável · {label(str(e.meta.get('categoria', '')))} ({label(cat.account)})"
                        if cat.account.startswith("Assets:Reembolsos:") else cat_label(cat.account))
            devol = cat.account.startswith("Expenses:") and cat.units.number < 0
            if devol:
                nome_cat = "Devolução · " + cat_label(cat.account).split(" · ", 1)[-1]
            manual.append({"d": e.date.isoformat(), "desc": e.narration, "cat": nome_cat,
                           "pay": pay_label, "v": float(abs(cat.units.number)), "receita": cat.account.startswith("Income") or devol,
                           "prov": bool(e.meta.get("provisorio")), "line": e.meta.get("lineno")})
        manual.sort(key=lambda r: (r["d"], r["line"] or 0), reverse=True)

        return json.dumps({
            "cats": [{"account": a, "label": cat_label(a), "tipo": "receita" if a.startswith("Income") else "despesa"} for a in cats]
                    # alguém te devolveu parte de um gasto (rateio com amigo): entra abatendo a categoria do gasto
                    + [{"account": a, "label": "Devolução · " + cat_label(a).split(" · ", 1)[-1], "tipo": "receita"}
                       for a in cats if a.startswith("Expenses:") and len(a.split(":")) == 3 and not a.endswith(("Mae", "A-Revisar"))],
            "pag": PAGAMENTOS, "hist": hist, "rules": rules, "manual": manual, "hoje": date.today().isoformat(),
        }, ensure_ascii=False).replace("</", "<\\/")

    def _last_balance(self, account):
        dates = [e.date for e in self.ledger.all_entries if isinstance(e, Balance) and e.account == account]
        return max(dates) if dates else None

    @extension_endpoint("lancar", ["POST"])
    def lancar(self):
        from flask import jsonify, request

        from app.forecast import add_months
        j = request.get_json(force=True)
        try:
            tipo = j["tipo"]
            valor = Decimal(str(j["valor"]).replace(",", ".")).quantize(Decimal("0.01"))
            d = date.fromisoformat(j["data"])
            cat, pay = j["categoria"], j["pagamento"]
            desc = (j.get("descricao") or "").strip() or label(cat)
            parcelas = max(1, int(j.get("parcelas") or 1))
            reemb = str(j.get("reembolso") or "") if j.get("tipo") == "despesa" else ""
        except (KeyError, ValueError, ArithmeticError):
            return jsonify({"ok": False, "erro": "Preencha valor, data e categoria."}), 400
        if valor <= 0:
            return jsonify({"ok": False, "erro": "O valor precisa ser maior que zero."}), 400
        opt = next((o for o in PAGAMENTOS.get(tipo, []) if o["account"] == pay), None)
        if not opt:
            return jsonify({"ok": False, "erro": "Escolha como foi pago."}), 400
        last = self._last_balance(pay)
        if last and d < last:
            return jsonify({"ok": False, "erro": f"O extrato de {opt['label']} já foi importado até {last - timedelta(days=1):%d/%m}. "
                                                 "Se o gasto não aparece lá, confira a data."}), 400

        q = lambda s: s.replace('"', "'").replace("\\", "/")
        blocks = []
        parte = (valor / parcelas).quantize(Decimal("0.01"))
        for k in range(parcelas):
            v = parte if k < parcelas - 1 else valor - parte * (parcelas - 1)
            dk = add_months(d, k)
            nome = f"{desc} (Parcela {k + 1:02d} de {parcelas:02d})" if parcelas > 1 else desc
            meta = [f'  meio: "{opt["meio"]}"', '  manual: TRUE']
            if opt["prov"]:
                meta.append("  provisorio: TRUE")
            if parcelas > 1:
                meta.append(f'  parcela: "{k + 1}/{parcelas}"')
            if reemb:
                meta += [f'  reembolso: "{reemb}"', f'  categoria: "{cat}"']
            if tipo == "despesa":
                posts = [f"  {f'Assets:Reembolsos:{reemb}' if reemb else cat}  {v} BRL", f"  {pay}  {-v} BRL"]
            else:
                posts = [f"  {pay}  {v} BRL", f"  {cat}  {-v} BRL"]
            blocks.append("\n".join([f'{dk} * "{q(nome)}"', *meta, *posts]))
        text = self.manual_path.read_text() if self.manual_path.exists() else ""
        self.manual_path.write_text(text.rstrip("\n") + "\n\n" + "\n\n".join(blocks) + "\n")
        return jsonify({"ok": True})

    @extension_endpoint("remover", ["POST"])
    def remover(self):
        from flask import jsonify, request
        line = int(request.get_json(force=True).get("line", 0))
        lines = self.manual_path.read_text().split("\n")
        if not (0 < line <= len(lines)) or not re.match(r"^\d{4}-\d{2}-\d{2} ", lines[line - 1]):
            return jsonify({"ok": False, "erro": "Lançamento não encontrado. Recarregue a página."}), 400
        end = line - 1
        while end < len(lines) and lines[end].strip():
            end += 1
        del lines[line - 1:end + 1 if end < len(lines) else end]
        self.manual_path.write_text("\n".join(lines))
        return jsonify({"ok": True})


    @extension_endpoint("editar", ["POST"])
    def editar(self):
        """Corrige data, valor e/ou descrição de um lançamento de manual.beancount (todas as pernas juntas)."""
        from flask import jsonify, request
        j = request.get_json(force=True)
        line = int(j.get("line", 0))
        lines = self.manual_path.read_text().split("\n")
        if not (0 < line <= len(lines)) or not re.match(r"^\d{4}-\d{2}-\d{2} ", lines[line - 1]):
            return jsonify({"ok": False, "erro": "Lançamento não encontrado. Recarregue a página."}), 400
        end = line - 1
        while end < len(lines) and lines[end].strip():
            end += 1
        bloco = lines[line - 1:end]
        try:
            if j.get("data"):
                nova = date.fromisoformat(j["data"])
                bloco[0] = re.sub(r"^\d{4}-\d{2}-\d{2}", nova.isoformat(), bloco[0])
            if j.get("descricao") is not None and str(j["descricao"]).strip():
                d = str(j["descricao"]).strip().replace('"', "'").replace("\\", "/")
                bloco[0] = re.sub(r'"[^"]*"\s*$', f'"{d}"', bloco[0])
            if j.get("valor"):
                v = Decimal(str(j["valor"]).replace(",", ".")).quantize(Decimal("0.01"))
                if v <= 0:
                    raise ValueError
                for k, l in enumerate(bloco):
                    m = re.match(r"^(\s+\S+\s+)(-?)[\d.]+( BRL.*)$", l)
                    if m:
                        bloco[k] = f"{m.group(1)}{m.group(2)}{v}{m.group(3)}"
        except (ValueError, ArithmeticError):
            return jsonify({"ok": False, "erro": "Data ou valor inválido."}), 400
        lines[line - 1:end] = bloco
        self.manual_path.write_text("\n".join(lines))
        return jsonify({"ok": True})


# ====================================================================== aba "Ciclo"

class Ciclo(_Comum, FavaExtensionBase):
    """Visão do ciclo (16 -> 15): quanto tem, quanto entra, quanto vence e quanto está livre para gastar."""

    report_title = "Ciclo"
    has_js_module = True

    MESES = MESES

    def brl(self, v, cents=False):
        return brl(v, cents)

    def pct(self, part, whole):
        return float(part) / float(whole) * 100 if whole else 0.0

    def data(self, c: str | None):
        from app.cycles import _add_month, current, cycle_by_end, cycle_of, events, summarize

        today = date.today()
        _, inicio = __import__("app.cycles", fromlist=["_cfg"])._cfg()
        cur_start, cur_end = cycle_of(today, inicio)
        if c and re.match(r"^\d{4}-\d{2}$", c):
            y, m = (int(x) for x in c.split("-"))
            start, end = cycle_by_end(y, m, inicio)
        else:
            start, end = cur_start, cur_end
        is_current = start == cur_start
        is_next = start > cur_end  # prévia de um ciclo futuro (até o da última parcela)

        evs = events(self.ledger.all_entries)
        first = min((x["date"] for x in evs), default=today)
        ciclos = []
        y, m = end.year, end.month
        s0, _ = cycle_of(first, inicio)
        cy, cm = cur_end.year, cur_end.month
        while True:
            s, e = cycle_by_end(cy, cm, inicio)
            if e < s0:
                break
            r = summarize(evs, s, e)
            if r["entradas"] or r["saidas"]:
                ciclos.append({"start": s, "end": e, "key": f"{e.year}-{e.month:02d}", **r,
                               "res": r["entradas"] - r["saidas"], "atual": s == cur_start})
            cy, cm = _add_month(cy, cm, -1)

        sel = summarize(evs, start, end)
        # gasto no ciclo por categoria e por meio (data da compra)
        por_cat, por_meio = defaultdict(Decimal), defaultdict(Decimal)
        for x in sel["cons_list"]:
            por_cat[":".join(x["acc"].split(":")[:3])] += x["v"]
            por_meio[x["meio"] or "Outro"] += x["v"]
        cats = sorted(({"acc": a, "name": label(a), "v": v, "fixa": ":Fixas:" in a + ":"} for a, v in por_cat.items() if v > 0),
                      key=lambda r: -r["v"])
        meios = sorted(({"name": k, "v": v} for k, v in por_meio.items() if v > 0), key=lambda r: -r["v"])

        cur = prox = None
        if is_current or is_next:
            fc = forecast(self.ledger.all_entries, today)
            cur = current(self.ledger.all_entries, today, Resumo._saldo(self)["total_contas"], fc)
            for r in cur["receber"]:
                r["name"] = ("Reembolso " + label(r["acc"].split()[-1]) if r.get("reembolso")
                             else f"{label(r['acc'])}{' · ' + r['desc'] if r.get('desc') else ''}" if r.get("extra")
                             else label(r["acc"]))
            for f in cur["faturas"]:
                f["name"] = COV_NOMES.get(f["card"], label(f["card"]))
            for f in cur["fixas_fora"]:
                f["name"] = label(f["acc"])
        if is_next:
            from app.cycles import futuros
            fut = futuros(self.ledger.all_entries, today, fc, cur)
            idx = next((i for i, x in enumerate(fut) if x["start"] == start), len(fut) - 1 if start > fut[-1]["start"] else 0)
            prox = fut[idx]
            for r in prox["receber"]:
                r["name"] = label(r["acc"])
            for f in prox["faturas"]:
                f["name"] = COV_NOMES.get(f["card"], label(f["card"]))
                for i in f["itens"]:
                    i["cat"] = label(i["acc"])
            for f in prox["fixas_fora"]:
                f["name"] = label(f["acc"])
            for c in prox["plano_cats"]:
                c["name"] = label(c["acc"])
            linha = [{"key": x["key"], "nome": f"{MESES[x['end'].month - 1]}/{str(x['end'].year)[2:]}", "certo": x["certo"],
                      "com_ritmo": x["com_ritmo"], "com_plano": x["com_plano"], "sel": i == idx, "parcelas": x["a_parcelas"]} for i, x in enumerate(fut)]
            return {"start": prox["start"], "end": prox["end"], "is_current": False, "is_next": True, "prox": prox, "cur": None,
                    "today": today, "cur_end": cur_end, "fut": linha, "n_fut": len(fut),
                    "prev_end": fut[idx - 1]["end"] if idx else cur_end,
                    "prev_key": fut[idx - 1]["key"] if idx else f"{cur_end.year}-{cur_end.month:02d}",
                    "next_key": fut[idx + 1]["key"] if idx + 1 < len(fut) else None}
        prev_key = f"{_add_month(end.year, end.month, -1)[0]}-{_add_month(end.year, end.month, -1)[1]:02d}"
        next_key = f"{_add_month(end.year, end.month)[0]}-{_add_month(end.year, end.month)[1]:02d}"
        return {
            "start": start, "end": end, "is_current": is_current, "sel": sel, "cats": cats, "meios": meios,
            "cat_max": cats[0]["v"] if cats else 1, "ciclos": ciclos, "cur": cur, "today": today,
            "prev_key": prev_key if any(c["key"] == prev_key for c in ciclos) else None,
            "next_key": next_key if end <= cur_end else None,
            "timeline": self._timeline(start, end, today, evs, cur),
            "hist": self._hist(ciclos, first),
            "matriz": (mx := self._matriz(evs, ciclos, cur)),
            "saldos": self._saldos(mx, cur, today),
            "diario": self._diario(sel, start, end, today, cur) if cur else None,
            "proximos": self._proximos(today, cur) if cur else [],
            "saldo_ate": Resumo._saldo(self)["ate"] if cur else None,
        }

    def _saldos(self, mx, cur, today):
        """Saldo real no fim de cada ciclo: contas (Inter PF, Nubank PF, Cora PJ) e dívida nos cartões.
        No ciclo em andamento, a projeção para o fim dele se você não gastar mais nada no Pix/débito."""
        contas = {"Assets:Inter:PF": "Inter PF", "Assets:Nubank:Conta": "Nubank PF", "Assets:Cora:PJ": "Cora PJ"}
        movs, inicio = [], {}
        for e in self.ledger.all_entries:
            if not isinstance(e, Transaction):
                continue
            for p in e.postings:
                if p.account in contas or p.account.startswith("Liabilities:Cartao"):
                    movs.append((e.date, p.account, p.units.number))
                    if p.account in contas and (e.meta.get("fonte") or e.flag == "P") and not str(e.meta.get("fonte", "")).startswith("planilha"):
                        inicio[p.account] = min(inicio.get(p.account, e.date), e.date)
        out = []
        for c in mx["cols"]:
            fim = min(c["end"], today)
            conta = sum((v for d, a, v in movs if a in contas and d <= fim), Decimal(0))
            divida = -sum((v for d, a, v in movs if a.startswith("Liabilities") and d <= fim), Decimal(0))
            faltam = [n for a, n in contas.items() if not inicio.get(a) or inicio[a] > c["start"]]
            prev = False
            if c["atual"] and cur:
                conta = cur["saldo"] + cur["a_receber"] - cur["a_pagar"] - cur["fixas"] - cur.get("a_assinar", 0) - cur.get("a_parcelas", 0)
                divida = cur["comprometido"]  # compras já feitas que só vencem no próximo ciclo
                prev = True
            out.append({"contas": conta, "divida": divida, "liquido": conta - divida, "prev": prev,
                        "faltam": faltam, "nota": ("sem extrato de " + ", ".join(faltam)) if faltam else ""})
        return out

    def _matriz(self, evs, ciclos, cur, n=12):
        """Receitas − fixas − variáveis por ciclo (pelo caixa). No ciclo atual, soma o que ainda vai entrar/sair
        com certeza ou quase: receitas previstas, assinaturas, parcelas e fixas pagas por Pix (hachurados)."""
        cols = list(reversed(ciclos[:n]))  # mais antigo -> mais novo
        z = lambda: [Decimal(0)] * len(cols)
        rec, prev_rec = defaultdict(z), defaultdict(z)
        cats = {"Fixas": defaultdict(z), "Variaveis": defaultdict(z)}
        prev = {"Fixas": defaultdict(z), "Variaveis": defaultdict(z)}

        def grupo_de(acc):
            parts = acc.split(":")
            return parts[1] if len(parts) > 1 and parts[1] in cats else "Variaveis"

        for j, c in enumerate(cols):
            for x in evs:
                if not (c["start"] <= x["cash"] <= c["end"]):
                    continue
                if x["kind"] == "receita":
                    rec[x["acc"]][j] += x["v"]
                else:
                    cats[grupo_de(x["acc"])][x["acc"]][j] += x["v"]
            if c["atual"] and cur:
                for r in cur["receber"]:
                    if not r.get("reembolso"):
                        prev_rec[r["acc"]][j] += r["v"]
                for x in cur.get("assinaturas", []) + cur.get("parcelas", []) + cur.get("fixas_fora", []):
                    prev[grupo_de(x["acc"])][x["acc"]][j] += x["v"]

        fechados = [j for j, c in enumerate(cols) if not c["atual"]]

        def row(acc, vals, pv=None, subs=None, nome=None):
            pv = pv or z()
            show = [v + p for v, p in zip(vals, pv)]
            peak = max([abs(v) for v in show] + [Decimal(1)])
            media = sum((show[j] for j in fechados), Decimal(0)) / (len(fechados) or 1)
            return {"account": acc, "name": nome or label(acc), "show": show, "prev": [bool(p) for p in pv],
                    "total": sum(show, Decimal(0)), "avg": media, "subs": subs or [],
                    "heat": [round(float(abs(v) / peak) * 100) for v in show]}

        receitas = sorted((row(a, rec[a], prev_rec.get(a)) for a in set(rec) | set(prev_rec)), key=lambda r: -r["total"])
        tot = lambda rows: [sum((r["show"][j] for r in rows), Decimal(0)) for j in range(len(cols))]
        grupos = []
        for g, titulo, hint in (("Fixas", "Despesas fixas", "Faculdade, escola, assinaturas, celular, DAS"),
                                ("Variaveis", "Despesas variáveis", "Mercado, restaurantes, transporte, compras")):
            # categoria (3 níveis) com as subcategorias dentro
            por_cat = defaultdict(list)
            for acc in set(cats[g]) | set(prev[g]):
                por_cat[":".join(acc.split(":")[:3])].append(acc)
            rows = []
            for cat, accs in por_cat.items():
                soma, soma_p = z(), z()
                subs = []
                for acc in accs:
                    v, p = cats[g].get(acc, z()), prev[g].get(acc, z())
                    soma = [a + b for a, b in zip(soma, v)]
                    soma_p = [a + b for a, b in zip(soma_p, p)]
                    if acc != cat:
                        subs.append(row(acc, v, p, nome=" · ".join(label(":".join(acc.split(":")[:i])) for i in range(4, len(acc.split(":")) + 1))))
                if not any(soma) and not any(soma_p):
                    continue
                subs.sort(key=lambda r: -r["total"])
                if subs and cat in accs:  # lançamentos direto na categoria, ao lado das subcategorias
                    subs.append(row(cat, cats[g].get(cat, z()), prev[g].get(cat, z()), nome="Outros"))
                rows.append(row(cat, soma, soma_p, subs if len(subs) > 1 or (subs and subs[0]["account"] != cat) else []))
            rows.sort(key=lambda r: (r["account"].endswith("A-Revisar"), -r["total"]))
            t = tot(rows)
            grupos.append({"key": g, "title": titulo, "hint": hint, "rows": rows, "tot": t,
                           "total": sum(t, Decimal(0)), "avg": sum((t[j] for j in fechados), Decimal(0)) / (len(fechados) or 1),
                           "prev": [any(r["prev"][j] for r in rows) for j in range(len(cols))]})
        r_tot = tot(receitas)
        res = [r - grupos[0]["tot"][j] - grupos[1]["tot"][j] for j, r in enumerate(r_tot)]
        acum, a = [], Decimal(0)
        for v in res:
            a += v
            acum.append(a)
        return {"cols": [{"key": c["key"], "nome": f"{MESES[c['end'].month - 1]}/{str(c['end'].year)[2:]}",
                          "start": c["start"], "end": c["end"], "atual": c["atual"]} for c in cols],
                "receitas": receitas, "rec_tot": r_tot, "rec_prev": [any(r["prev"][j] for r in receitas) for j in range(len(cols))],
                "rec_total": sum(r_tot, Decimal(0)), "rec_avg": sum((r_tot[j] for j in fechados), Decimal(0)) / (len(fechados) or 1),
                "grupos": grupos, "res": res, "acum": acum}

    def _diario(self, sel, start, end, today, cur):
        """Gasto por dia no ciclo (data da compra) contra o valor diário que cabe no ciclo."""
        dias = (end - start).days + 1
        por_dia = defaultdict(Decimal)
        for x in sel["cons_list"]:
            por_dia[(x["date"] - start).days] += x["v"]
        orc = (cur["gasto"] + max(cur["livre"], Decimal(0))) / dias  # quanto cabe por dia no ciclo inteiro
        W, H, pb = 420, 110, 16
        peak = max([float(v) for v in por_dia.values()] + [float(orc) * 1.3, 1])
        col = W / dias
        y = lambda v: (H - pb) - float(v) / peak * (H - pb - 6)
        hoje_i = (today - start).days
        bars = []
        for i in range(dias):
            v = por_dia.get(i, Decimal(0))
            if i > hoje_i:
                continue
            d = start + timedelta(days=i)
            bars.append({"x": col * i + 1, "w": max(col - 2, 1), "y": y(v), "h": (H - pb) - y(v),
                         "over": v > orc, "tip": f"{d:%d/%m} · R$ {brl(v, True)}"})
        return {"W": W, "H": H, "bars": bars, "orc_y": y(orc), "orc": orc, "base": H - pb,
                "hoje_x": col * hoje_i + col / 2, "ini": f"{start:%d/%m}", "fim": f"{end:%d/%m}",
                "estourou": sum(1 for b in bars if b["over"])}

    def _proximos(self, today, cur, n=4):
        """Próximos eventos do ciclo com valor: receitas, fechamentos, vencimentos."""
        out = []
        for r in cur["receber"]:
            out.append({"d": r["date"], "t": r["name"], "v": r["v"], "k": "in"})
        for f in cur["faturas"]:
            if f["fecha"] >= today:
                out.append({"d": f["fecha"], "t": f"fecha {f['name'].replace('Cartão ', '')}", "v": None, "k": "close"})
            out.append({"d": f["due"], "t": f"vence {f['name'].replace('Cartão ', '')}", "v": f["v"], "k": "due"})
        out.sort(key=lambda e: (e["d"], e["k"] != "in"))
        # junta vários eventos iguais no mesmo dia (ex.: salário + hora extra da mesma empresa)
        agrup = []
        for e in out:
            ult = agrup[-1] if agrup else None
            if ult and ult["d"] == e["d"] and ult["k"] == e["k"] == "in" and e["t"].split(" ·")[0] in ult["t"]:
                ult["v"] += e["v"]
                ult["t"] = ult["t"].split(" ·")[0].replace(" (com extras)", "") + " (com extras)"
            elif ult and ult["d"] == e["d"] and ult["k"] == e["k"] == "close":
                ult["t"] += " + " + e["t"].replace("fecha ", "")
            else:
                agrup.append(dict(e))
        return [e for e in agrup if e["d"] >= today][:n]

    def _hist(self, ciclos, first):
        """Histórico dos ciclos com diferenças para o anterior, médias e gráfico de resultado."""
        from app.cycles import cycle_of
        _, inicio = __import__("app.cycles", fromlist=["_cfg"])._cfg()
        pf_ini = min((e.date for e in self.ledger.all_entries if isinstance(e, Transaction)
                      and any(p.account == "Assets:Inter:PF" for p in e.postings)), default=first)
        rows = []
        chron = list(reversed(ciclos))  # do mais antigo para o mais novo
        for i, c in enumerate(chron):
            prev = chron[i - 1] if i > 0 else None
            nome = MESES_LONGOS[c["end"].month - 1]
            parcial = c["atual"]
            incompleto = c["start"] < pf_ini  # antes do extrato PF: faltam Pix e débito
            rows.append({
                **{k: c[k] for k in ("start", "end", "key", "entradas", "saidas", "saidas_cartao", "saidas_outras", "consumo", "res", "atual")},
                "nome": f"{nome[:3]}/{str(c['end'].year)[2:]}", "nome_longo": f"{nome} de {c['end'].year}",
                "sobra_pct": float(c["res"] / c["entradas"] * 100) if c["entradas"] else None,
                "d_res": (c["res"] - prev["res"]) if prev and not parcial and prev["start"] >= pf_ini else None,
                "d_cons_pct": float((c["consumo"] - prev["consumo"]) / prev["consumo"] * 100)
                              if prev and prev["consumo"] and not parcial and prev["start"] >= pf_ini else None,
                "cartao_pct": float(c["saidas_cartao"] / c["saidas"] * 100) if c["saidas"] else 0.0,
                "parcial": parcial, "incompleto": incompleto,
            })
        completos = [r for r in rows if not r["parcial"] and not r["incompleto"]][-3:]
        media = None
        if completos:
            n = len(completos)
            media = {"n": n, "entradas": sum(r["entradas"] for r in completos) / n,
                     "saidas": sum(r["saidas"] for r in completos) / n,
                     "res": sum(r["res"] for r in completos) / n,
                     "consumo": sum(r["consumo"] for r in completos) / n}
            media["sobra_pct"] = float(media["res"] / media["entradas"] * 100) if media["entradas"] else None
        # gráfico: barras do resultado por ciclo (mais antigo à esquerda)
        W, H, pad = 900, 170, 22
        peak = max([abs(float(r["res"])) for r in rows] + [1])
        col = W / max(len(rows), 1)
        bw = min(34, col * .6)
        mid = (H - pad) / 2
        bars = []
        for i, r in enumerate(rows):
            h = max(2.0, abs(float(r["res"])) / peak * (mid - 14))
            x = col * i + (col - bw) / 2
            y = mid - h if r["res"] >= 0 else mid
            bars.append({"x": x, "y": y, "w": bw, "h": h, "pos": r["res"] >= 0, "key": r["key"], "nome": r["nome"],
                         "parcial": r["parcial"], "incompleto": r["incompleto"], "lx": x + bw / 2,
                         "ly": (y - 5) if r["res"] >= 0 else (y + h + 12), "label": brl(r["res"]),
                         "tip": f"{r['nome_longo']}: {'sobrou' if r['res'] >= 0 else 'faltou'} R$ {brl(abs(r['res']), True)}"
                                + (" (parcial)" if r["parcial"] else " (dados incompletos)" if r["incompleto"] else "")})
        return {"rows": list(reversed(rows)), "media": media,
                "chart": {"W": W, "H": H, "mid": mid, "bars": bars, "pad": pad},
                "melhor": max((r for r in rows if not r["parcial"] and not r["incompleto"]), key=lambda r: r["res"], default=None),
                "pior": min((r for r in rows if not r["parcial"] and not r["incompleto"]), key=lambda r: r["res"], default=None)}

    def _timeline(self, start, end, today, evs, cur):
        """Marcos do ciclo numa linha: receitas, fechamentos, vencimentos e hoje."""
        from app.cycles import _cfg, _safe
        cards, _ = _cfg()
        W, total = 1000, (end - start).days or 1
        x = lambda d: 20 + (d - start).days / total * (W - 40)
        marks = []
        recebidas = [r for r in evs if r["kind"] == "receita" and start <= r["date"] <= end]
        for r in recebidas:
            marks.append({"x": x(r["date"]), "d": r["date"], "t": f"{label(r['acc'])} +{brl(r['v'])}", "k": "in", "ok": True})
        for r in (cur or {}).get("receber", []):
            marks.append({"x": x(r["date"]), "d": r["date"], "t": f"{r.get('name') or label(r['acc'])} ~{brl(r['v'])}", "k": "in", "ok": False})
        for card, c in cards.items():
            nome = COV_NOMES.get(card, label(card)).replace("Cartão ", "")
            for d in {_safe(start.year, start.month, int(c["fecha"])), _safe(end.year, end.month, int(c["fecha"])),
                      _safe(start.year, start.month, int(c["vence"])), _safe(end.year, end.month, int(c["vence"]))}:
                if not (start <= d <= end):
                    continue
                vence = d.day == int(c["vence"])
                if vence:  # vencimento em fim de semana/feriado passa para o próximo dia útil
                    from app.diasuteis import proximo_dia_util
                    d = proximo_dia_util(d)
                    if d > end:
                        continue
                marks.append({"x": x(d), "d": d, "t": f"{'vence' if vence else 'fecha'} {nome}", "k": "due" if vence else "close",
                              "ok": d < today})
        try:
            import yaml
            from pathlib import Path
            mei = (yaml.safe_load((Path(self.ledger.beancount_file_path).resolve().parent.parent / "config" / "accounts.yaml").read_text()) or {}).get("mei") or {}
        except Exception:
            mei = {}
        if mei.get("das_dia"):
            for d in {_safe(start.year, start.month, int(mei["das_dia"])), _safe(end.year, end.month, int(mei["das_dia"]))}:
                if start <= d <= end:
                    pago = any(x["kind"] == "gasto" and x["acc"].startswith(mei.get("das_conta", "Expenses:Fixas:Impostos"))
                               and abs((x["date"] - d).days) <= 25 and x["date"] <= d + timedelta(days=5) for x in evs)
                    marks.append({"x": x(d), "d": d, "t": "DAS" + (" ✓" if pago else ""), "k": "due", "ok": d < today})
        # dias de importar: um dia depois dos fechamentos (faturas + extratos)
        # e um dia depois da última receita do mês (extratos, para confirmar o que entrou)
        from datetime import timedelta as _td
        from app.organize import STATEMENTS
        def ultimo(pasta):
            ds = []
            for f in (STATEMENTS / pasta).glob("*") if (STATEMENTS / pasta).exists() else []:
                m = re.findall(r"(\d{4}-\d{2}-\d{2})", f.name)
                if m:
                    # o período do OFX pode ir até o fim do mês; o extrato só cobre até o dia em que foi baixado
                    ds.append(min(date.fromisoformat(m[-1]), date.fromtimestamp(f.stat().st_mtime)))
                elif re.search(r"fatura_(\d{4})-(\d{2})", f.name):
                    y, mm = (int(v) for v in re.search(r"fatura_(\d{4})-(\d{2})", f.name).groups())
                    ds.append(date(y, mm, 1))
            return max(ds) if ds else None
        fecha_dia = max((int(c["fecha"]) for c in cards.values()), default=7) + 1
        dias_receita = [x["date"].day for x in evs if x["kind"] == "receita" and x["acc"].startswith("Income:Trabalho")
                        and x["date"] >= today - _td(days=120)]
        rec_dia = (max(dias_receita) + 1) if dias_receita else 11
        if cur and cur.get("receber"):
            ult = max(r["date"] for r in cur["receber"])
            rec_dia = (ult + _td(days=1)).day
        contas = ["cora-pj", "nubank-conta", "inter-pf"]  # o caminho do salário: Cora -> Nubank -> Inter
        checklist = []
        for dia, oque, pastas in ((fecha_dia, "importar tudo", ["inter-cartao", "nubank-cartao", *contas]),
                                  (rec_dia, "importar extratos", contas)):
            for d in {_safe(start.year, start.month, dia), _safe(end.year, end.month, dia)}:
                if not (start <= d <= end):
                    continue
                itens = []
                for p in pastas:
                    u = ultimo(p)
                    nome, como, _ = FONTE_NOMES[p]
                    ok = bool(u and u >= (d.replace(day=1) if "cartao" in p else d - _td(days=1)))
                    itens.append({"nome": nome, "formato": FORMATOS[p], "como": como, "ok": ok,
                                  "ate": (f"fatura {u:%m/%Y}" if "cartao" in p else f"até {u:%d/%m}") if u else "nunca"})
                feito = all(i["ok"] for i in itens)
                dica = " · ".join(f"{'✓' if i['ok'] else '○'} {i['nome']} ({i['formato']})" for i in itens)
                marks.append({"x": x(d), "d": d, "t": ("✓ " if feito else "") + oque, "k": "imp", "tip": dica,
                              "ok": feito, "late": d <= today and not feito})
                checklist.append({"d": d, "oque": oque, "itens": itens, "feito": feito, "late": d <= today and not feito,
                                  "motivo": "faturas fecharam ontem" if "tudo" in oque else "confirmar as receitas que entraram"})
        checklist.sort(key=lambda c: c["d"])
        # fechamentos no mesmo dia viram um marco só
        fechos = defaultdict(list)
        for m in [m for m in marks if m["k"] == "close"]:
            fechos[m["d"]].append(m)
        for d, ms in fechos.items():
            if len(ms) > 1:
                for m in ms[1:]:
                    marks.remove(m)
                ms[0]["t"] = "fecha " + " + ".join(m["t"].replace("fecha ", "") for m in ms)
        marks.sort(key=lambda m: (m["d"], m["k"] != "close"))
        # vencimentos de cartão com até 2 dias de diferença viram um marco só ("vence Nubank 14 + Inter 15")
        juntos = []
        for m in marks:
            ant = next((j for j in reversed(juntos) if j["k"] == "due" and j["t"].startswith("vence")
                        and (m["d"] - j["d"]).days <= 2), None)
            if ant and m["k"] == "due" and m["t"].startswith("vence"):
                if "+" not in ant["t"]:
                    ant["t"] = f"{ant['t']} {ant['d'].day}"
                ant["t"] += f" + {m['t'].replace('vence ', '')} {m['d'].day}"
                # o marco fica entre as datas, para não esconder atrás de outro ícone do mesmo dia
                ant["x"] = (x(ant["d"]) + m["x"]) / 2
                ant["dl"] = f"{ant['d']:%d}–{m['d']:%d/%m}"
                ant["ok"] = ant["ok"] and m["ok"]
                continue
            juntos.append(m)
        marks = juntos
        # etiquetas em 4 faixas (2 acima, 2 abaixo): cada uma vai para a primeira faixa livre
        faixas = {"u1": -1e9, "d1": -1e9, "u2": -1e9, "d2": -1e9}
        for m in marks:
            largura = 7.2 * max(len(m["t"]), 5) + 16
            # perto das bordas o texto alinha para dentro, para não ser cortado
            if m["x"] + largura / 2 > W:
                m["anchor"] = "end"
            elif m["x"] - largura / 2 < 0:
                m["anchor"] = "start"
            esq, dir_ = {"end": (m["x"] - largura, m["x"]), "start": (m["x"], m["x"] + largura)}.get(
                m.get("anchor"), (m["x"] - largura / 2, m["x"] + largura / 2))
            livre = next((f for f in ("u1", "d1", "u2", "d2") if esq > faixas[f]),
                         min(faixas, key=faixas.get))  # sem faixa livre: a que termina mais cedo
            faixas[livre] = dir_
            m["lane"] = livre
        # mostra a importação que importa agora: a primeira atrasada, senão a próxima, senão a última
        foco = (next((c for c in checklist if c["late"]), None) or next((c for c in checklist if c["d"] > today), None)
                or (checklist[-1] if checklist else None))
        return {"W": W, "marks": marks, "today": x(today) if start <= today <= end else None, "checklist": foco}


# ====================================================================== aba "Importar"

FORMATOS = {"inter-pf": "CSV", "cora-pj": "OFX", "inter-cartao": "CSV", "nubank-cartao": "OFX", "nubank-conta": "OFX"}
FONTE_NOMES = {
    "inter-pf": ("Conta Inter PF", "App Inter → Extrato → Exportar → CSV", 7),
    "cora-pj": ("Conta Cora PJ", "App/Web Cora → Extrato → Exportar OFX", 7),
    "inter-cartao": ("Cartão Inter", "App Inter → Cartão → Fatura → Exportar CSV (dá para baixar a fatura aberta)", 35),
    "nubank-cartao": ("Cartão Nubank", "App Nubank → Fatura → Exportar OFX (a qualquer hora, inclusive a aberta)", 35),
    "nubank-conta": ("Conta Nubank PF", "App Nubank → Conta → Extrato → Exportar OFX (mês a mês)", 31),
}


class Importar(_Comum, FavaExtensionBase):
    """Arraste extratos e faturas: o sistema reconhece, organiza em statements/ e reimporta."""

    report_title = "Importar"
    has_js_module = True

    def page_json(self):
        import json

        from app.organize import INBOX, STATEMENTS
        from app.parsers import detect

        fontes = []
        for pasta, (nome, como, prazo) in FONTE_NOMES.items():
            arquivos = sorted((STATEMENTS / pasta).glob("*")) if (STATEMENTS / pasta).exists() else []
            arquivos = [a for a in arquivos if a.is_file() and not a.name.startswith(".")]
            ult = None
            for a in arquivos:
                m = re.findall(r"(\d{4}-\d{2}-\d{2})", a.name)
                if m:
                    d = min(date.fromisoformat(m[-1]), date.fromtimestamp(a.stat().st_mtime))  # OFX pode declarar o mês inteiro
                elif re.search(r"fatura_(\d{4})-(\d{2})", a.name):
                    y, mm = (int(x) for x in re.search(r"fatura_(\d{4})-(\d{2})", a.name).groups())
                    d = date(y, mm, 15)
                else:
                    continue
                ult = max(ult, d) if ult else d
            hoje = date.today()
            if pasta.endswith("cartao"):
                # fatura esperada: Inter só depois do fechamento (dia 7); Nubank a aberta (pode baixar a qualquer hora)
                y, mm = hoje.year, hoje.month
                if pasta.startswith("inter") and hoje.day <= 7:
                    y, mm = (y, mm - 1) if mm > 1 else (y - 1, 12)
                if pasta.startswith("nubank") and hoje.day > 7:
                    y, mm = (y, mm + 1) if mm < 12 else (y + 1, 1)
                atrasado = not ult or (ult.year, ult.month) < (y, mm)
                dias = None
            else:
                dias = (hoje - ult).days if ult else None
                atrasado = dias is None or dias > prazo
            fontes.append({"pasta": pasta, "nome": nome, "como": como, "ultimo": ult.isoformat() if ult else "",
                           "dias": dias, "atrasado": atrasado, "prazo": prazo, "cartao": pasta.endswith("cartao"),
                           "arquivos": [{"nome": a.name, "kb": round(a.stat().st_size / 1024)} for a in reversed(arquivos)]})
        pendentes = [p.name for p in INBOX.glob("*") if p.is_file() and not p.name.startswith(".")] if INBOX.exists() else []
        return json.dumps({"fontes": fontes, "pendentes": pendentes}, ensure_ascii=False).replace("</", "<\\/")

    @extension_endpoint("enviar", ["POST"])
    def enviar(self):
        from flask import jsonify, request

        import yaml
        from app.build import CONFIG as CFG_DIR
        from app.build import OUTPUT, build
        from app.organize import INBOX, organize

        INBOX.mkdir(exist_ok=True)
        salvos = []
        for f in request.files.getlist("files"):
            nome = re.sub(r"[^\w.\- ()]", "_", Path(f.filename or "arquivo").name)[:120] or "arquivo"
            dest = INBOX / nome
            n = 2
            while dest.exists():
                dest = INBOX / f"{Path(nome).stem}_{n}{Path(nome).suffix}"
                n += 1
            f.save(dest)
            salvos.append(dest)
        if not salvos:
            return jsonify({"ok": False, "erro": "Nenhum arquivo recebido."}), 400
        antes = OUTPUT.read_text().count("\n20") if OUTPUT.exists() else 0
        sources = yaml.safe_load((CFG_DIR / "accounts.yaml").read_text())["sources"]
        rep = organize(sources, paths=salvos, verbose=False)
        stats = build(verbose=False)
        self.ledger.load_file()
        depois = OUTPUT.read_text().count("\n20") if OUTPUT.exists() else 0
        return jsonify({
            "ok": True,
            "movidos": [{"de": a, "para": str(b)} for a, b in rep["moved"]],
            "repetidos": [{"de": a, "para": str(b)} for a, b in rep["dup"]],
            "desconhecidos": rep["unknown"],
            "novos": max(0, depois - antes), "revisar": len(stats["review"]),
            "pendencias": Pendencias.contar(self),
        })

    @extension_endpoint("descartar", ["POST"])
    def descartar(self):
        from flask import jsonify, request

        from app.organize import INBOX
        nome = Path(str(request.get_json(force=True).get("nome", ""))).name
        alvo = INBOX / nome
        if nome and alvo.exists():
            alvo.unlink()
        return jsonify({"ok": True})


# ====================================================================== aba "Pendências"

PREFIXOS = re.compile(r"^(Pix enviado devolvido|Pix recebido devolvido|Pix enviado|Pix recebido|Pix Automático enviado|"
                      r"Compra no débito|Transf Pix enviada|Transf Pix recebida|Devolução Pix enviada) - ", re.I)
DESTINOS_TRANSF = [
    ("Assets:Transferencias", "Transferência entre contas minhas (está certo)"),
    ("Assets:Nubank:Conta", "Foi para a conta Nubank"),
    ("Assets:Investimentos:Bitcoin", "Investimento · Bitcoin"),
    ("Assets:Investimentos:Outros", "Investimento · outro"),
    ("Expenses:Variaveis:Familia:Mae", "Família · Mãe"),
    ("Expenses:Variaveis:Outros", "Gasto · outros"),
]


def _nome_grupo(narr: str) -> str:
    n = PREFIXOS.sub("", narr or "")
    n = re.sub(r"\s*\(Parcela.*$", "", n)
    n = re.sub(r"\s{2,}.*$", "", n)  # "Churrascaria           Saopaulobra" -> "Churrascaria"
    return n.strip() or (narr or "").strip()


class Pendencias(_Comum, FavaExtensionBase):
    """O que precisa da sua decisão: sem categoria, pagamentos a identificar, transferências sem destino…"""

    report_title = "Pendências"
    has_js_module = True

    def _cfg_dir(self):
        return Path(self.ledger.beancount_file_path).resolve().parent.parent / "config"

    def _ignoradas(self):
        import yaml
        p = self._cfg_dir() / "overrides.yaml"
        return set(((yaml.safe_load(p.read_text()) if p.exists() else {}) or {}).get("ignoradas") or [])

    def _marco(self):
        """Data do "marco zero": pendências anteriores ficam arquivadas (não somem, só saem da lista principal)."""
        import yaml
        p = self._cfg_dir() / "overrides.yaml"
        m = ((yaml.safe_load(p.read_text()) if p.exists() else {}) or {}).get("marco_zero")
        return date.fromisoformat(str(m)) if m else None

    def _key(self, e):
        pay = next((p for p in e.postings if not p.account.startswith(("Expenses:", "Income:", "Assets:Reembolsos",
                                                                       "Assets:Transferencias"))), None)
        return f"{e.date}|{pay.account}|{pay.units.number:.2f}|{e.narration}" if pay else ""

    def itens(self):
        ign = self._ignoradas()
        txns = [e for e in self.ledger.all_entries if isinstance(e, Transaction)]
        hoje = date.today()

        # 1. sem categoria, agrupado por pessoa/loja
        grupos = {}
        for e in txns:
            for p in e.postings:
                if not p.account.endswith("A-Revisar"):
                    continue
                entrada = p.account.startswith("Income")
                nome = _nome_grupo(e.narration)
                g = grupos.setdefault((nome.lower(), entrada), {"nome": nome, "entrada": entrada, "itens": [], "total": 0.0})
                g["itens"].append({"d": e.date.isoformat(), "desc": e.narration, "v": float(abs(p.units.number)),
                                   "key": self._key(e), "meio": e.meta.get("meio", "")})
                g["total"] += float(abs(p.units.number))
        sem_cat = sorted(grupos.values(), key=lambda g: -g["total"])
        for g in sem_cat:
            g["regra"] = re.escape(g["nome"])
            g["id"] = f"cat|{g['nome'].lower()}|{g['entrada']}"
            g["itens"].sort(key=lambda i: i["d"], reverse=True)

        # 2. pagamentos acima/abaixo do esperado
        conf = []
        for c in Receitas._conferencia(self):
            cid = f"conf|{c['d']}|{c['fonte']}"
            if abs(c["dif"]) >= 1 and cid not in ign:
                conf.append({**c, "id": cid})

        # 3. transferências sem par (dinheiro que foi/veio de uma conta que não é importada)
        pf_ini = min((e.date for e in txns if any(p.account == "Assets:Inter:PF" for p in e.postings)), default=hoje)
        transf = []
        for e in txns:
            tp = [p for p in e.postings if p.account == "Assets:Transferencias"]
            if not tp or len(e.postings) != 2 or not e.meta.get("fonte"):
                continue
            v = tp[0].units.number
            key = self._key(e)
            if abs(v) < 50 or f"tr|{key}" in ign or e.date < pf_ini or "Pix No Cr" in (e.narration or ""):
                continue  # centavos, antes do extrato PF, ou Pix no crédito (se resolve com a próxima fatura)
            transf.append({"d": e.date.isoformat(), "desc": e.narration, "v": float(-v), "key": key, "id": f"tr|{key}"})
        transf.sort(key=lambda t: t["d"], reverse=True)

        # 4. extratos atrasados e arquivos parados na inbox
        imp = __import__("json").loads(Importar.page_json(self))
        atrasados = [f for f in imp["fontes"] if f["atrasado"]]

        # 5. provisórios antigos (lançados à mão e ainda não confirmados por extrato)
        prov = [{"d": e.date.isoformat(), "desc": e.narration,
                 "v": float(max((abs(p.units.number) for p in e.postings), default=0))}
                for e in txns if e.meta.get("provisorio") and (hoje - e.date).days > 45]

        cats = sorted({p.account for e in txns for p in e.postings
                       if p.account.startswith(("Expenses:", "Income:")) and not p.account.endswith("A-Revisar")}
                      | {"Expenses:Variaveis:Outros", "Income:Outras:Outros", "Income:Outras:Presentes",
                         "Expenses:Variaveis:Familia:Mae", "Expenses:Variaveis:Presentes"})

        def nome_cat(a):
            parts = a.split(":")
            grupo = {"Fixas": "Fixas", "Variaveis": "Variáveis", "Trabalho": "Receita", "Outras": "Receita"}.get(parts[1], "")
            return f"{grupo} · " + " · ".join(label(":".join(parts[:i])) for i in range(3, len(parts) + 1))

        return {
            "sem_cat": sem_cat, "conf": conf, "transf": transf, "atrasados": atrasados, "inbox": imp["pendentes"],
            "prov": prov,
            "cats_out": [{"a": a, "n": nome_cat(a)} for a in cats if a.startswith("Expenses")]
                        + [{"a": a, "n": f"Transferência · {n}"} for a, n in DESTINOS_TRANSF if a.startswith("Assets")],
            "cats_in": [{"a": a, "n": nome_cat(a)} for a in cats if a.startswith("Income")]
                       + [{"a": "Assets:Transferencias", "n": "Transferência · de uma conta minha"},
                          {"a": "Expenses:Variaveis:Familia:Mae", "n": "Família · Mãe (devolveu)"}]
                       # alguém te devolveu parte de um gasto (rateio com amigo): abate a categoria do gasto
                       + [{"a": a, "n": "Devolução · " + nome_cat(a).split(" · ", 1)[-1]}
                          for a in cats if a.startswith("Expenses") and len(a.split(":")) == 3 and not a.endswith("Mae")],
            "destinos": [{"a": a, "n": n} for a, n in DESTINOS_TRANSF],
        }

    def separar(self, it):
        """Divide em ativas (a partir do marco zero) e arquivadas (antes dele)."""
        marco = self._marco()
        if not marco:
            return it, None
        m = marco.isoformat()
        arq = {"sem_cat": [], "conf": [c for c in it["conf"] if c["d"] < m], "transf": [t for t in it["transf"] if t["d"] < m]}
        ativos = []
        for g in it["sem_cat"]:
            novos = [x for x in g["itens"] if x["d"] >= m]
            velhos = [x for x in g["itens"] if x["d"] < m]
            if novos:
                ativos.append({**g, "itens": novos, "total": sum(x["v"] for x in novos)})
            if velhos:
                arq["sem_cat"].append({**g, "itens": velhos, "total": sum(x["v"] for x in velhos)})
        ativas = {**it, "sem_cat": ativos, "conf": [c for c in it["conf"] if c["d"] >= m],
                  "transf": [t for t in it["transf"] if t["d"] >= m]}
        arq["n"] = sum(len(g["itens"]) for g in arq["sem_cat"]) + len(arq["conf"]) + len(arq["transf"])
        return ativas, arq

    def contar(self, it=None):
        it = it or self.itens()
        it, _ = self.separar(it) if "arquivadas" not in it else (it, None)
        return (sum(len(g["itens"]) for g in it["sem_cat"]) + len(it["conf"]) + len(it["transf"])
                + len(it["atrasados"]) + len(it["inbox"]) + len(it["prov"]))

    def page_json(self):
        import json

        from app.cycles import _cfg, cycle_of
        it, arq = self.separar(self.itens())
        it["arquivadas"] = arq
        it["total"] = self.contar(it)
        marco = self._marco()
        it["marco"] = marco.isoformat() if marco else ""
        it["ciclo_ini"] = cycle_of(date.today(), _cfg()[1])[0].isoformat()
        return json.dumps(_plain(it), ensure_ascii=False).replace("</", "<\\/")

    @extension_endpoint("contagem")
    def contagem(self):
        from flask import jsonify
        return jsonify({"n": self.contar()})

    @extension_endpoint("resolver", ["POST"])
    def resolver(self):
        import yaml
        from flask import jsonify, request

        from app.build import build
        j = request.get_json(force=True)
        tipo = j.get("tipo")
        cfg = self._cfg_dir()
        ov_p = cfg / "overrides.yaml"
        ov_txt = ov_p.read_text() if ov_p.exists() else ""
        ov = yaml.safe_load(ov_txt) or {}
        ov.setdefault("lancamentos", {})
        ov.setdefault("ignoradas", [])
        head = "".join(l + "\n" for l in ov_txt.splitlines() if l.startswith("#"))

        if tipo == "categoria":
            conta = str(j.get("conta") or "")
            if not re.match(r"^(Expenses|Income|Assets):[\w:-]+$", conta):
                return jsonify({"ok": False, "erro": "Escolha uma categoria."}), 400
            if j.get("regra") and j.get("padrao"):
                up = cfg / "rules_user.yaml"
                txt = up.read_text() if up.exists() else "rules: []\n"
                data = yaml.safe_load(txt) or {}
                regras = [r for r in (data.get("rules") or []) if r.get("match") != j["padrao"]]
                regras.insert(0, {"match": j["padrao"], "account": conta})
                uh = "".join(l + "\n" for l in txt.splitlines() if l.startswith("#"))
                up.write_text(uh + yaml.safe_dump({"rules": regras}, allow_unicode=True, sort_keys=False))
            else:
                for k in j.get("keys") or []:
                    if k:
                        ov["lancamentos"][k] = conta
        elif tipo == "ignorar":
            if j.get("id") and j["id"] not in ov["ignoradas"]:
                ov["ignoradas"].append(j["id"])
        elif tipo == "marco":
            if j.get("data"):
                ov["marco_zero"] = str(date.fromisoformat(j["data"]))
            else:
                ov.pop("marco_zero", None)
        elif tipo == "hora_extra":
            from app.forecast import CONFIG as FC, load_config, save_config
            plano = load_config()
            fontes = {label(a): a for a in plano["receitas"]} | {n: f"Income:Trabalho:{k}" for k, n in empresas().items()}
            plano["extras_receita"].append({"fonte": fontes.get(j.get("fonte"), j.get("fonte")), "mes": j["d"][:7],
                                            "valor": float(j["valor"]), "descricao": "informado na aba Pendências"})
            save_config(plano)
        else:
            return jsonify({"ok": False, "erro": "Ação desconhecida."}), 400
        ov_p.write_text(head + yaml.safe_dump(ov, allow_unicode=True, sort_keys=False))
        build(verbose=False)
        self.ledger.load_file()  # recarrega já, para a próxima tela vir atualizada
        return jsonify({"ok": True})


# ====================================================================== aba "Buscar"

class Buscar(_Comum, FavaExtensionBase):
    """Busca em todos os lançamentos (gastos, receitas, transferências, manuais) por texto, valor e data."""

    report_title = "Buscar"
    has_js_module = True

    def page_json(self):
        import json
        mp = str(Path(self.ledger.beancount_file_path).resolve().parent / "manual.beancount")
        cards = Gastos._card_names(self)
        out = []
        for e in self.ledger.all_entries:
            if not isinstance(e, Transaction):
                continue
            exp = [p for p in e.postings if p.account.startswith("Expenses:") or
                   (p.account.startswith("Assets:Reembolsos:") and p.units.number > 0)]
            inc = [p for p in e.postings if p.account.startswith("Income:")]
            if exp:
                tipo, principal = "gasto", exp[0]
                valor = sum((p.units.number for p in exp), Decimal(0))
                conta = str(e.meta.get("categoria") or principal.account) if principal.account.startswith("Assets:Reembolsos") else principal.account
            elif inc:
                tipo, principal = "receita", inc[0]
                valor = -sum((p.units.number for p in inc), Decimal(0))
                conta = min((p.account for p in inc), key=len)
            else:
                tipo = "transferência"
                pos = [p for p in e.postings if p.units.number > 0]
                valor = sum((p.units.number for p in pos), Decimal(0))
                conta = pos[0].account if pos else e.postings[0].account
            parts = conta.split(":")
            grupo = {"Fixas": "Fixa", "Variaveis": "Variável"}.get(parts[1], "") if conta.startswith("Expenses") and len(parts) > 1 else ""
            cartao = e.meta.get("cartao")
            pay = next((p for p in e.postings if not p.account.startswith(("Expenses:", "Income:", "Assets:Reembolsos"))), None)
            if e.meta.get("filename") == mp:
                key = f"manual:{e.meta.get('lineno')}"
            else:
                key = f"{e.date}|{pay.account}|{pay.units.number:.2f}|{e.narration}" if pay and e.meta.get("fonte") else ""
            out.append({
                "key": key if tipo == "gasto" else "",
                "d": e.date.isoformat(), "desc": e.narration or e.payee or "", "tipo": tipo, "v": float(valor),
                "cat": " · ".join(label(":".join(parts[:i])) for i in range(3, len(parts) + 1)) if len(parts) > 2 else label(conta),
                "conta": conta, "grupo": grupo, "meio": e.meta.get("meio", ""),
                "cartao": cards.get(str(cartao), f"final {cartao}") if cartao else "",
                "parc": e.meta.get("parcela", ""), "reemb": e.meta.get("reembolso", ""),
                "prov": bool(e.meta.get("provisorio")), "manual": e.meta.get("filename") == mp,
                "arquivo": e.meta.get("fonte", ""), "fatura": e.meta.get("fatura", "") or e.meta.get("vence", ""),
                "postings": [{"a": p.account, "n": label(p.account) if not p.account.startswith(("Assets:Inter", "Assets:Cora", "Assets:Nubank:Conta", "Liabilities"))
                              else COV_NOMES.get(p.account, p.account), "v": float(p.units.number)} for p in e.postings],
            })
        out.sort(key=lambda r: r["d"], reverse=True)
        return json.dumps({"rows": out, "hoje": date.today().isoformat()}, ensure_ascii=False).replace("</", "<\\/")


# ====================================================================== aba "Contas"

class Contas(_Comum, FavaExtensionBase):
    """Cada conta e cartão como um extrato: escolhe um e vê a movimentação por data, com saldo."""

    report_title = "Contas"
    has_js_module = True

    ORDEM = property(lambda self: contas_ordem())
    TIPOS = property(lambda self: {a: conta_tipo(a) for a in contas_ordem()})
    NOMES = property(lambda self: contas_nomes())

    def _outro(self, acc):
        if acc in self.NOMES:
            return self.NOMES[acc]
        if acc == "Assets:Transferencias":
            return "Transferência (sem par)"
        parts = acc.split(":")
        if acc.startswith(("Expenses:", "Income:")) and len(parts) > 2:
            return " · ".join(label(":".join(parts[:i])) for i in range(3, len(parts) + 1))
        return label(acc)

    @extension_endpoint("comprovante")
    def comprovante(self):
        """Abre um comprovante (só arquivos de dentro de comprovantes/)."""
        from flask import abort, request, send_file

        from app import comprovantes
        p = comprovantes.caminho(request.args.get("f", ""))
        if not p:
            abort(404)
        return send_file(p)

    @extension_endpoint("anexar", ["POST"])
    def anexar(self):
        """Recebe a foto/PDF de um comprovante e liga ao gasto (data + valor cobrado)."""
        import tempfile

        from flask import jsonify, request

        from app import comprovantes
        f = request.files.get("arquivo")
        try:
            d = date.fromisoformat(request.form["data"])
            valor = abs(Decimal(request.form["valor"]))
        except (KeyError, ValueError, ArithmeticError):
            return jsonify({"ok": False, "erro": "Gasto inválido."}), 400
        if not f or not f.filename:
            return jsonify({"ok": False, "erro": "Escolha um arquivo."}), 400
        ext = Path(f.filename).suffix.lower()
        if ext not in comprovantes.TIPOS:
            return jsonify({"ok": False, "erro": "Use foto (JPG, PNG, HEIC) ou PDF."}), 400
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / f"upload{ext}"
            f.save(t)
            item = comprovantes.guardar(t, d, valor, request.form.get("loja") or "gasto", mover=True)
        return jsonify({"ok": True, "arquivo": item["arquivo"]})

    def page_json(self):
        import json
        mp = str(Path(self.ledger.beancount_file_path).resolve().parent / "manual.beancount")
        cards = Gastos._card_names(self)
        hoje = date.today()
        rows = defaultdict(list)
        checks = defaultdict(list)
        from app import comprovantes
        comp = comprovantes.ligar(self.ledger.all_entries)
        for e in self.ledger.all_entries:
            if isinstance(e, Balance) and e.account in self.TIPOS:
                checks[e.account].append({"d": (e.date - timedelta(days=1)).isoformat(), "v": float(e.amount.number)})
            if not isinstance(e, Transaction):
                continue
            lados = (e.narration or "").split(" ↔ ")  # transferência casada: "lado do 1º posting ↔ lado do 2º"
            for idx, p in enumerate(e.postings):
                if p.account not in self.TIPOS:
                    continue
                outros = [q for q in e.postings if q is not p and q.account != p.account]
                cartao = e.meta.get("cartao")
                reemb = self.TIPOS[p.account] == "reembolso"
                rows[p.account].append({
                    "d": e.date.isoformat(), "v": float(p.units.number),
                    "desc": "Ajuste para o saldo do primeiro extrato" if e.flag == "P" else lados[idx] if len(lados) == 2 and idx < 2 else (e.narration or e.payee or ""),
                    "outro": " + ".join(dict.fromkeys(self._outro(q.account) for q in outros)) or "—",
                    "tipo": ("reembolso" if reemb and p.units.number > 0 else "recebido" if reemb else
                             "transf" if outros and all(q.account in self.TIPOS or q.account == "Assets:Transferencias" for q in outros)
                             else "receita" if any(q.account.startswith("Income") for q in outros) else "gasto"),
                    "revisar": any(q.account.endswith("A-Revisar") for q in outros),
                    "categoria": label(str(e.meta.get("categoria"))) if reemb and e.meta.get("categoria") else "",
                    "line": e.meta.get("lineno") if e.meta.get("filename") == mp else None,
                    "meio": e.meta.get("meio", ""), "cartao": cards.get(str(cartao), f"final {cartao}") if cartao else "",
                    "parc": e.meta.get("parcela", ""), "fatura": e.meta.get("vence", "") or e.meta.get("fatura", ""),
                    "arquivo": e.meta.get("fonte", ""), "manual": e.meta.get("filename") == mp,
                    "prov": bool(e.meta.get("provisorio")), "futuro": e.date > hoje, "pad": e.flag == "P",
                    "comp": [{"arquivo": c["arquivo"], "loja": c.get("loja", "")} for c in comp.get(id(e), [])],
                })
        contas = []
        for acc in self.ORDEM:
            rs = rows.get(acc)
            if not rs:
                continue
            rs.sort(key=lambda r: r["d"])
            saldo = 0.0
            for r in rs:
                saldo = round(saldo + r["v"], 2)
                r["saldo"] = saldo
            atual = next((r["saldo"] for r in reversed(rs) if not r["futuro"]), 0.0)
            ck = sorted(checks.get(acc, []), key=lambda c: c["d"])
            contas.append({"acc": acc, "nome": self.NOMES.get(acc, label(acc)), "tipo": self.TIPOS[acc],
                           "saldo": atual, "n": len(rs), "ultimo": next((r["d"] for r in reversed(rs) if not r["futuro"]), ""),
                           "conferido": ck[-1] if ck else None, "checks": ck,
                           "cartoes": sorted({r["cartao"] for r in rs if r["cartao"]}),
                           "rows": list(reversed(rs))})
            # cartão com vários plásticos (físico, virtual, adicional): cada um vira um cartão próprio.
            # A fatura é uma só, então o valor de cada um é o quanto ele soma na fatura em aberto.
            if self.TIPOS[acc] == "cartao" and len(contas[-1]["cartoes"]) > 1:
                from app.cycles import _cfg, card_due
                cyc = _cfg()[0].get(acc) or {"fecha": 7, "vence": 15}
                def vence(r):
                    v = r["fatura"]
                    if len(v) == 10:
                        return date.fromisoformat(v)
                    return card_due(date.fromisoformat(r["d"]), int(cyc["fecha"]), int(cyc["vence"]))
                aberta = card_due(hoje, int(cyc["fecha"]), int(cyc["vence"]))
                pai = contas[-1]
                for nome in pai["cartoes"]:
                    sub = [dict(r, saldo=None) for r in pai["rows"] if r["cartao"] == nome]
                    # a fatura em aberto só sabe o cartão quando o PDF chega; até lá, mostra a última com compras dele
                    fatura = max((vence(r) for r in sub if vence(r) <= aberta), default=aberta)
                    na_fatura = sum(r["v"] for r in sub if vence(r) == fatura)
                    contas.append({"acc": f"{acc}#{nome}", "pai": acc, "nome": "Cartão " + nome, "tipo": "cartao",
                                   "sub": True, "saldo": round(na_fatura, 2), "vence": fatura.isoformat(), "aberta": fatura == aberta,
                                   "n": len(sub), "ultimo": next((r["d"] for r in sub if not r["futuro"]), ""),
                                   "conferido": None, "checks": [], "cartoes": [], "rows": sub})
        # para o formulário "novo a receber" (cards de reembolso)
        usadas = sorted({p.account for e in self.ledger.all_entries if isinstance(e, Transaction) for p in e.postings
                         if p.account.startswith("Expenses:") and not p.account.endswith(("A-Revisar", ":Mae"))})
        cats = [{"account": a, "label": " · ".join(label(":".join(a.split(":")[:i])) for i in range(3, len(a.split(":")) + 1))}
                for a in usadas]
        return json.dumps({"contas": contas, "hoje": hoje.isoformat(), "cats": cats,
                           "pag": PAGAMENTOS["despesa"]}, ensure_ascii=False).replace("</", "<\\/")


# ====================================================================== aba "Simulador"

ESSENCIAIS = ("Mercado", "Transporte", "Saude", "Impostos", "Educacao", "Assinaturas", "Celular", "Tarifas", "Familia")
COMPROMISSO = ("Impostos", "Assinaturas", "Celular")  # o que sai de qualquer jeito (as parcelas entram à parte)


class Simulador(_Comum, FavaExtensionBase):
    """Brincar com receita, gasto por categoria, assinaturas e meta de guardar, vendo o saldo dos próximos meses."""

    report_title = "Simulador"
    has_js_module = True

    def page_json(self):
        import json
        today = date.today()
        fc = forecast(self.ledger.all_entries, today, horizon=12)
        saldo = Resumo._saldo(self)
        meses = fc["months"]
        rec = [-sum((v.get(ym, 0) for a, v in fc["per_account"].items() if a.startswith("Income:")), Decimal(0)) for ym in meses]
        tot = {t["ym"]: t for t in fc["totals"]}
        gasto = [tot[ym]["fixas"] + tot[ym]["variaveis"] for ym in meses]
        parcelas = defaultdict(Decimal)
        for p in fc["parcelas"]:
            parcelas[p["ym"]] += p["valor"]
        cats = []
        for c in fc["categorias"]:
            nome = c["account"].split(":")[-1]
            cats.append({"account": c["account"], "name": label(c["account"]), "grupo": c["grupo"],
                         "media": c["media"], "previsto": c["previsto"], "auto": c["modo"] == "assinaturas",
                         "essencial": nome in ESSENCIAIS, "compromisso": nome in COMPROMISSO})
        cats.sort(key=lambda c: (c["grupo"] != "Fixas", -float(c["previsto"])))
        subs = [{"key": s["key"], "nome": s["nome"], "valor": s["valor"], "account": s["account"]}
                for s in fc["assinaturas"] if s["status"] == "ativa"]
        certos = self._certos(fc, today)
        return json.dumps(_plain({
            "hoje": saldo["total"], "a_receber": fc.get("a_receber_mes", 0), "gap": fc["gap"],
            "meses": [f"{MESES[m - 1]}/{str(y)[2:]}" for y, m in meses], "rec": rec, "gasto": gasto,
            "invest": [tot[ym]["invest"] for ym in meses], "parcelas": [parcelas.get(ym, Decimal(0)) for ym in meses],
            "categorias": cats, "assinaturas": subs, "meta": (fc["config"].get("metas") or {}).get("investir", 0),
            "receitas": [{"name": label(r["account"]), "previsto": r["previsto"]} for r in fc["receitas"]],
            "certos": certos,
        }), ensure_ascii=False).replace("</", "<\\/")

    def _certos(self, fc, today, n=6):
        """O que já vai sair com certeza, por mês de PAGAMENTO (vencimento da fatura): parcelas de compras
        feitas, assinaturas ativas e DAS."""
        from app.assinaturas import cobrancas, nome as nome_limpo
        from app.cycles import _cfg, card_due
        from app.diasuteis import proximo_dia_util
        cards = _cfg()[0]
        venc = lambda d, pay: card_due(d, int(cards[pay]["fecha"]), int(cards[pay]["vence"])) if pay in cards else d
        meses = []
        y, m = today.year, today.month
        for _ in range(n):
            meses.append((y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        itens = defaultdict(list)
        for p in fc["parcelas_futuras"]:
            d = venc(p["date"], p["pay"])
            n_, t_ = (int(x) for x in p["parcela"].split("/"))
            itens[(d.year, d.month)].append({"tipo": "parcela", "nome": nome_limpo(re.sub(r"^\d+", "", p["desc"])),
                                             "parcela": p["parcela"], "faltam": t_ - n_, "valor": p["valor"],
                                             "quando": d, "cat": label(p["account"]),
                                             "onde": COV_NOMES.get(p["pay"], label(p["pay"]))})
        fim = date(meses[-1][0], meses[-1][1], 28) + timedelta(days=10)
        from app.cycles import desde_extrato
        for c in cobrancas(fc["assinaturas"], desde_extrato(fc, today), fim):
            d = venc(c["date"], c["pay"])
            itens[(d.year, d.month)].append({"tipo": "assinatura", "nome": c["nome"], "valor": c["valor"], "quando": d,
                                             "onde": COV_NOMES.get(c["pay"], label(c["pay"]))})
        # faturas: o que já foi gasto no cartão (compras feitas até hoje), no mês em que vence
        from app.cycles import current, events
        cur = current(self.ledger.all_entries, today, Decimal(0), fc)
        ja = {(f["card"], (f["due"].year, f["due"].month)) for f in cur["faturas"]}
        for f in cur["faturas"]:  # faturas que vencem neste ciclo (fechadas ou quase)
            itens[(f["due"].year, f["due"].month)].append({"tipo": "fatura", "nome": f"Fatura {f['card'].split(':')[-1]}",
                                                         "valor": f["v"], "quando": f["due"], "onde": "fechada" if not f["aberta"] else "aberta"})
        futuras = defaultdict(Decimal)
        for x in events(self.ledger.all_entries):  # compras já feitas que vencem em faturas seguintes
            if x["kind"] == "gasto" and x["card"] and x["date"] <= today and (x["pay"], (x["cash"].year, x["cash"].month)) not in ja \
                    and x["cash"] > today:
                futuras[(x["pay"], x["cash"])] += x["v"]
        for e in self.ledger.all_entries:  # Pix no crédito e afins (não são gasto, mas estão na fatura)
            if isinstance(e, Transaction) and e.meta.get("vence") and not any(q.account.startswith("Expenses:") and q.units.number > 0 and q.account != "Expenses:Variaveis:Tarifas" for q in e.postings):
                v = date.fromisoformat(str(e.meta["vence"]))
                for q in e.postings:
                    if q.account in cards and v > today and (q.account, (v.year, v.month)) not in ja \
                            and next((r.account for r in e.postings if not r.account.startswith(("Expenses:", "Income:"))), "") != q.account:
                        futuras[(q.account, v)] += -q.units.number
        for (card, d), v in futuras.items():
            if v > 0:
                itens[(d.year, d.month)].append({"tipo": "fatura", "nome": f"Fatura {card.split(':')[-1]}: já gasto",
                                                 "valor": v, "quando": proximo_dia_util(d), "onde": "fatura aberta"})
        das = next((c["previsto"] for c in fc["categorias"] if c["account"].endswith(":Impostos")), Decimal(0))
        for ym in meses:
            d = proximo_dia_util(date(ym[0], ym[1], 20))
            if d > today and das:
                itens[ym].append({"tipo": "das", "nome": "DAS (MEI)", "valor": das, "quando": d, "onde": "Conta Cora PJ"})
        out = []
        for ym in meses:
            its = sorted(itens.get(ym, []), key=lambda i: ({"fatura": 0, "parcela": 1, "assinatura": 2, "das": 3}[i["tipo"]], -i["valor"]))
            tot = lambda t: sum((i["valor"] for i in its if i["tipo"] == t), Decimal(0))
            out.append({"mes": f"{MESES[ym[1] - 1]}/{str(ym[0])[2:]}", "itens": its, "total": sum((i["valor"] for i in its), Decimal(0)),
                        "faturas": tot("fatura"), "parcelas": tot("parcela"), "assinaturas": tot("assinatura"), "das": tot("das")})
        restantes = [p for p in fc["parcelas_futuras"]]
        ultima = max((venc(p["date"], p["pay"]) for p in restantes), default=None)
        return {"meses": out, "parcelas_total": sum((p["valor"] for p in restantes), Decimal(0)),
                "parcelas_n": len(restantes), "ultima": ultima}

    @extension_endpoint("usar", ["POST"])
    def usar(self):
        """Grava o cenário no plano: categorias que mudaram viram valor fixo; meta de guardar."""
        from flask import jsonify, request

        from app.forecast import load_config, save_config
        j = request.get_json(force=True)
        cfg = load_config()
        for c in j.get("categorias") or []:
            acc, v = c.get("account"), float(c.get("valor") or 0)
            if not acc or c.get("auto"):
                continue  # assinaturas seguem automáticas: cancele pelo Planejamento
            if c.get("igual_media"):
                cfg["categorias"].pop(acc, None)
            else:
                cfg["categorias"][acc] = {"modo": "fixo", "valor": round(v, 2)}
        cfg.setdefault("metas", {})["investir"] = float(j.get("meta") or 0)
        save_config(cfg)
        return jsonify({"ok": True})
