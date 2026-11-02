"""Lê todos os extratos de statements/, categoriza e reescreve ledger/imported.beancount.

O arquivo gerado é sempre refeito do zero a partir dos extratos: nunca edite ele à mão.
Lançamentos manuais vão em ledger/manual.beancount.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import yaml

from app.parsers import Txn, detect
from app.paths import DATA

STATEMENTS = DATA / "statements"
CONFIG = DATA / "config"
OUTPUT = DATA / "ledger" / "imported.beancount"
MANUAL = DATA / "ledger" / "manual.beancount"
REEMBOLSO_PREFIX = "Assets:Reembolsos"
CENTAVOS = Decimal("0.05")  # diferença máxima aceita ao casar os dois lados de uma transferência
FEES = "Expenses:Variaveis:Tarifas"


def load_config():
    accounts = yaml.safe_load((CONFIG / "accounts.yaml").read_text())
    # regras criadas na aba Pendências vêm primeiro (são as mais específicas)
    user = CONFIG / "rules_user.yaml"
    rules = ((yaml.safe_load(user.read_text()) or {}).get("rules") or [] if user.exists() else []) + \
        yaml.safe_load((CONFIG / "rules.yaml").read_text())["rules"]
    for r in rules:
        r["_re"] = re.compile(r["match"], re.I)
    return accounts, rules


def txn_key(t: Txn) -> str:
    """Identidade estável de um lançamento importado (usada para marcar reembolsáveis)."""
    return f"{t.date}|{t.account}|{t.amount:.2f}|{q(t.desc)}"


def ler_reembolsos_cfg() -> tuple[str, dict]:
    """(cabeçalho de comentários, conteúdo) de config/reembolsos.yaml."""
    p = CONFIG / "reembolsos.yaml"
    txt = p.read_text() if p.exists() else ""
    head = txt.split("base:")[0] if "base:" in txt else "# Reembolsos (editado pelas abas Gastos, Buscar e Lançar)\n"
    return head, yaml.safe_load(txt) or {}


def salvar_reembolsos_cfg(head: str, cfg: dict) -> None:
    """Grava mantendo todas as seções (base, gastos, periodos, nao)."""
    out = {"base": cfg.get("base") or {}, "gastos": cfg.get("gastos") or []}
    if cfg.get("periodos"):
        out["periodos"] = cfg["periodos"]
    if cfg.get("nao"):
        out["nao"] = sorted(set(cfg["nao"]))
    for k, v in cfg.items():  # qualquer outra seção (ex.: sem_detalhe) é mantida
        if k not in out and k not in ("periodos", "nao") and v:
            out[k] = v
    (CONFIG / "reembolsos.yaml").write_text(head + yaml.safe_dump(out, allow_unicode=True, sort_keys=False))


# Num período de viagem, o que quase nunca é da empresa fica de fora (dá para marcar à mão depois)
FORA_DO_PERIODO = re.compile(r"Familia|Saude|Tarifas|^Expenses:Fixas")
CARTAO_FAMILIA = "Liabilities:Cartao:Nubank"


def load_reembolsos():
    _, cfg = ler_reembolsos_cfg()
    base = {k: Decimal(str(v)) for k, v in (cfg.get("base") or {}).items()}
    marcados = {g["key"]: g["fonte"] for g in (cfg.get("gastos") or []) if g.get("key") and g.get("fonte")}
    return base, marcados


def periodo_de(cfg: dict, t, other: str) -> str | None:
    """Empresa que reembolsa este gasto por estar dentro de um período lembrado (viagem), se houver."""
    if t.amount >= 0 or not other.startswith("Expenses:") or FORA_DO_PERIODO.search(other) or t.account == CARTAO_FAMILIA:
        return None
    par = str(t.meta.get("parcela") or "")
    if par and not par.startswith("1/"):
        return None
    if txn_key(t) in set(cfg.get("nao") or []):
        return None
    for per in cfg.get("periodos") or []:
        if str(per.get("de")) <= t.date.isoformat() <= str(per.get("ate")):
            return per.get("fonte")
    return None


def manual_reembolsos():
    """(data, fonte, valor) dos gastos reembolsáveis lançados à mão em manual.beancount."""
    if not MANUAL.exists():
        return []
    from beancount.parser import parser
    out = []
    for e in parser.parse_file(str(MANUAL))[0]:
        for p in getattr(e, "postings", []):
            if p.account.startswith(REEMBOLSO_PREFIX + ":") and isinstance(getattr(p.units, "number", None), Decimal) \
                    and p.units.number > 0:
                out.append((e.date, p.account.split(":")[-1], p.units.number))
    return out


def categorize(t: Txn, kind: str, rules, unmatched) -> tuple[str, bool]:
    sign = "in" if t.amount > 0 else "out"
    for r in rules:
        if r.get("source") and r["source"] != kind:
            continue
        if r.get("sign") and r["sign"] != sign:
            continue
        if r["_re"].search(t.desc):
            return r["account"], True
    return (unmatched["inflow"] if sign == "in" else unmatched["outflow"]), False


def q(s: str) -> str:
    return re.sub(r"\s+", " ", s).replace("\\", "/").replace('"', "'").strip()


def fmt(amount: Decimal) -> str:
    return f"{amount:.2f} BRL"


SEM_DETALHE = "Expenses:Variaveis:Reembolso-sem-detalhe"
LAG_REEMBOLSO = 5  # dias mínimos entre o gasto e o pagamento que o reembolsa


def pix_credito(a: Txn, b: Txn) -> bool:
    """Pix no crédito: a conta recebe o valor (ex.: +80) e o cartão cobra valor + juros (-85,71), até 45 dias
    depois. Casa os dois; a diferença vira tarifa."""
    conta, cart = (a, b) if a.account.startswith("Assets") else (b, a)
    if not (conta.account.startswith("Assets") and cart.account.startswith("Liabilities:Cartao")):
        return False
    if not re.search(r"Pix no cr|PIX CRED|Valor adicionado na conta por cart", conta.desc + " " + cart.desc, re.I):
        return False
    return (conta.amount > 0 and -cart.amount >= conta.amount and -cart.amount <= conta.amount * Decimal("1.15")
            and 0 <= (cart.date - conta.date).days <= 45)


def build(verbose: bool = True) -> dict:
    accounts, rules = load_config()
    sources, transfer, unmatched = accounts["sources"], accounts["transfer_account"], accounts["unmatched"]

    # 0. organizar o que chegou na inbox
    from app.organize import organize
    organize(sources, verbose=verbose)

    # 1. ler arquivos (statements/<fonte>/...)
    per_file: list[tuple[str, Path, object]] = []
    ignored = []
    for path in sorted(p for p in STATEMENTS.rglob("*") if p.is_file() and not p.name.startswith(".")):
        kind, parse = detect(path)
        if not kind:
            ignored.append(path.name)
            continue
        parsed = parse(path, sources.get(kind))
        per_file.append((parsed.meta.get("kind", kind), path, parsed))

    # 1b. faturas de cartão: uma única fonte por fatura (a mesma fatura pode chegar em PDF, CSV e OFX, com
    #     descrições diferentes, e aí a deduplicação abaixo não pegaria). Preferência: OFX > PDF > CSV;
    #     no mesmo formato, o arquivo mais novo (uma fatura aberta exportada de novo substitui a anterior).
    prio = {".ofx": 3, ".pdf": 2, ".csv": 1}
    escolhido: dict[tuple, tuple] = {}
    for idx, (kind, path, parsed) in enumerate(per_file):
        m = re.match(r"fatura_(\d{4}-\d{2})", path.name)
        if not m or not parsed.txns:
            continue
        chave = (parsed.txns[0].account, m.group(1))
        nota = (prio.get(path.suffix.lower(), 0), path.stat().st_mtime, path.name)
        if chave not in escolhido or nota > escolhido[chave][0]:
            escolhido[chave] = (nota, idx)
    usar = {idx for _, idx in escolhido.values()}
    descartados = [path.relative_to(STATEMENTS) for idx, (kind, path, parsed) in enumerate(per_file)
                   if re.match(r"fatura_", path.name) and parsed.txns and idx not in usar]
    per_file = [x for idx, x in enumerate(per_file) if idx in usar or not (re.match(r"fatura_", x[1].name) and x[2].txns)]
    if verbose and descartados:
        print(f"  = {len(descartados)} fatura(s) repetida(s) em outro formato, ignorada(s): {', '.join(map(str, descartados))}")

    # 2. deduplicar: extratos com períodos sobrepostos não podem duplicar lançamentos.
    #    Para cada lançamento idêntico (conta, data, valor, descrição) fica a maior contagem vista num único arquivo.
    best: dict[tuple, int] = {}
    first_seen: dict[tuple, tuple[str, Txn]] = {}
    for kind, path, parsed in per_file:
        c = Counter()
        for t in parsed.txns:
            # extratos que trazem um identificador próprio (Inter: saldo após o lançamento) deduplicam por ele,
            # mesmo que a descrição mude entre formatos; o primeiro arquivo (mais antigo) dá a descrição
            key = (t.account, t.date, t.amount, t.meta.get("_id") or t.desc)
            c[key] += 1
            first_seen.setdefault(key, (kind, t))
        for key, n in c.items():
            best[key] = max(best.get(key, 0), n)
    txns = [(first_seen[k][0], first_seen[k][1]) for k, n in best.items() for _ in range(n)]
    txns.sort(key=lambda kt: (kt[1].date, kt[1].account, kt[1].desc))

    # 3. saldos (assertions) e saldo inicial
    balances = {}
    openings = {}
    pads = {}  # contas OFX: saldo antes do 1º arquivo, via pad (a conta pode ter lançamentos manuais antes)
    for kind, path, parsed in per_file:
        if "saldo_inicial" in parsed.meta:
            d, v = parsed.meta["saldo_inicial"]
            acc = parsed.txns[0].account if parsed.txns else parsed.balances[0].account
            if acc not in pads or d < pads[acc][0]:
                pads[acc] = (d, v)
        for b in parsed.balances:
            balances[(b.account, b.date)] = b
        for o in parsed.opening:
            if o.account not in openings or o.date < openings[o.account].date:
                openings[o.account] = o
    # cartões: a primeira fatura traz o pagamento da fatura anterior (que não temos) -> vira dívida inicial
    cards = defaultdict(list)
    for kind, path, parsed in per_file:
        if "due" in parsed.meta:
            cards[parsed.txns[0].account if parsed.txns else None].append(parsed)
    for acc, faturas in cards.items():
        first = min(faturas, key=lambda p: p.meta["due"])
        paid = sum((t.amount for t in first.txns
                    if t.amount > 0 and categorize(t, "inter_card", rules, unmatched)[0] == transfer), Decimal(0))
        if paid:
            d = min(t.date for t in first.txns if not t.meta.get("parcela"))
            openings[acc] = Txn(d, "Fatura anterior ao primeiro extrato", -paid, acc, "")

    # 4. escrever (saldos iniciais)
    lines = [
        ";; GERADO AUTOMATICAMENTE por app/build.py a partir de statements/ - NÃO EDITE.",
        ";; Para mudar categorias edite config/rules.yaml; lançamentos manuais em manual.beancount.",
        "",
    ]
    for acc, o in sorted(openings.items()):
        lines += [
            f'{o.date - timedelta(days=1)} * "Saldo inicial" "{q(o.desc)}"',
            f"  {acc}  {fmt(o.amount)}",
            "  Equity:Abertura",
            "",
        ]

    for acc, (d, v) in sorted(pads.items()):
        lines += [f"{d - timedelta(days=1)} pad {acc} Equity:Abertura", f"{d} balance {acc}  {fmt(v)}", ""]

    # 5. casar transferências: o mesmo dinheiro aparece nos dois extratos (Pix PJ -> PF, pagamento de
    #    fatura na conta e no cartão). Vira um lançamento só, direto entre as duas contas.
    from app.parsers import ofx_config
    own = set(sources.values()) | {c["conta"] for c in ofx_config().values()}
    items = [(kind, t, *categorize(t, kind, rules, unmatched)) for kind, t in txns]
    # decisões lançamento a lançamento tomadas na aba Pendências
    ov_file = CONFIG / "overrides.yaml"
    overrides = ((yaml.safe_load(ov_file.read_text()) or {}).get("lancamentos") or {}) if ov_file.exists() else {}
    if overrides:
        # valor = conta, ou {conta: ..., parcela: "n/t"} quando o lançamento é parcela de algo (sai da média da previsão)
        for n, (k, t, o, ok) in enumerate(items):
            v = overrides.get(txn_key(t))
            if isinstance(v, dict):
                t.meta.update({m: str(x) for m, x in v.items() if m != "conta"})
                v = v.get("conta")
            if v:
                items[n] = (k, t, v, True)
    movable = [i for i, (_, t, other, _) in enumerate(items) if other == transfer or other in own]
    paired: dict[int, int] = {}
    for i in movable:
        if i in paired:
            continue
        _, a, a_other, _ = items[i]
        best_j, best_gap = None, None
        for j in movable:
            if j == i or j in paired:
                continue
            _, b, b_other, _ = items[j]
            if b.account == a.account:
                continue
            if a_other not in (transfer, b.account) or b_other not in (transfer, a.account):
                continue
            if not pix_credito(a, b) and (abs(b.amount + a.amount) > CENTAVOS or abs((b.date - a.date).days) > 5):
                continue
            # prefere: valor exato, depois o dia mais próximo, depois a descrição que cita o banco da outra conta
            # (ex.: Cora -> Nubank -> Inter no mesmo dia e mesmo valor)
            cita = lambda x, y: y.account.split(":")[1].lower() in x.desc.lower()
            gap = (abs(b.amount + a.amount), abs((b.date - a.date).days), not (cita(a, b) or cita(b, a)))
            if best_gap is None or gap < best_gap:
                best_j, best_gap = j, gap
        if best_j is not None:
            paired[i], paired[best_j] = best_j, i

    base, marcados = load_reembolsos()
    reemb_cfg = ler_reembolsos_cfg()[1]
    from app.forecast import _lookup, extra_em, load_config as load_plano, valor_em
    plano = load_plano()

    def base_em(acc, d):
        """Salário vigente na data (plano com aumentos) ou a parte fixa de reembolsos.yaml."""
        v = valor_em(_lookup(plano["receitas"], acc), (d.year, d.month))
        return v if v is not None else base.get(acc)
    # fonte -> [data do gasto, quanto ainda falta receber], na ordem dos gastos. Um pagamento só quita gastos
    # feitos pelo menos LAG_REEMBOLSO dias antes (a empresa precisa receber a prestação de contas).
    pendente = defaultdict(list)
    splits = {}  # índice do item -> (valor da receita, valor do reembolso)
    manuais = manual_reembolsos()
    order = sorted([("i", items[i][1].date, i) for i in range(len(items))] + [("m", d, (f, v)) for d, f, v in manuais],
                   key=lambda x: (x[1], x[0] == "i"))
    for tipo, _, ref in order:  # noqa: B007 (_ = data, usada nos reembolsos manuais)
        if tipo == "m":
            pendente[ref[0]].append([_, ref[1]])
            continue
        i = ref
        kind, t, other, ok = items[i]
        fonte = marcados.get(txn_key(t)) or periodo_de(reemb_cfg, t, other)
        if fonte and other.startswith("Expenses:"):
            items[i] = (kind, t, f"{REEMBOLSO_PREFIX}:{fonte}", ok)
            t.meta["categoria"] = other
            t.meta["reembolso"] = fonte
            pendente[fonte].append([t.date, -t.amount])
        elif other.startswith("Income:Trabalho:") and base_em(other, t.date) is not None:
            b = base_em(other, t.date)
            extra_decl = extra_em(plano, other, (t.date.year, t.date.month))
            t.meta["esperado"] = f"{b + extra_decl:.2f}"
            if t.amount > b:
                fonte = other.split(":")[-1]
                excesso = t.amount - b
                extra = min(excesso, extra_decl)          # primeiro: hora extra/bônus informados
                elegiveis = [g for g in pendente[fonte] if g[1] > 0 and (t.date - g[0]).days >= LAG_REEMBOLSO]
                quita = max(Decimal(0), min(excesso - extra, sum((g[1] for g in elegiveis), Decimal(0))))  # depois: reembolsos
                # reembolso sem detalhe: a empresa devolveu gastos que você não sabe mais quais eram
                sem_det = {str(x.get("key")): Decimal(str(x.get("valor") or 0)) for x in reemb_cfg.get("sem_detalhe") or []}
                sem = min(excesso - extra - quita, sem_det.get(txn_key(t), Decimal(0)))
                if extra or quita or sem:
                    resto = quita
                    for g in elegiveis:  # baixa dos mais antigos primeiro
                        baixa = min(g[1], resto)
                        g[1] -= baixa
                        resto -= baixa
                    splits[i] = (t.amount - quita - extra - sem, extra, quita, sem)

    review = []
    n_pairs = 0
    for i, (kind, t, other, ok) in enumerate(items):
        if i in paired:
            j = paired[i]
            if j < i:
                continue  # já escrito junto com o par
            b = items[j][1]
            n_pairs += 1
            vence = t.meta.get("vence") or b.meta.get("vence")  # lado do cartão: em que fatura cai
            lines += [f'{min(t.date, b.date)} * "Transferência" "{q(t.desc)} ↔ {q(b.desc)}"',
                      f'  fonte: "{q(t.source)} + {q(b.source)}"', '  meio: "Transferência"',
                      *([f'  vence: "{vence}"'] if vence else []),
                      f"  {t.account}  {fmt(t.amount)}", f"  {b.account}  {fmt(b.amount)}"]
            if t.amount + b.amount:  # diferença de centavos entre os dois lados
                lines.append(f"  {FEES}  {fmt(-(t.amount + b.amount))}")
            lines.append("")
            continue
        if not ok:
            review.append(t)
        flag = "*" if ok else "!"
        meta = [f'  fonte: "{q(t.source)}"'] + [f'  {k}: "{v}"' for k, v in t.meta.items() if not k.startswith("_")]
        if i in splits:  # pagamento = salário + hora extra informada + reembolso de gastos marcados
            receita, extra, reemb, sem = splits[i]
            lines += [f'{t.date} {flag} "{q(t.desc)}"', *meta]
            if reemb or sem:
                lines.append(f'  reembolso_recebido: "{reemb + sem:.2f}"')
            if extra:
                lines.append(f'  extra_recebido: "{extra:.2f}"')
            lines += [f"  {t.account}  {fmt(t.amount)}", f"  {other}  {fmt(-receita)}"]
            if extra:
                lines.append(f"  {other}:Extra  {fmt(-extra)}")
            if reemb:
                lines.append(f"  {REEMBOLSO_PREFIX}:{other.split(':')[-1]}  {fmt(-reemb)}")
            if sem:  # abate as despesas: devolveu gastos que estavam contados como seus
                lines.append(f"  {SEM_DETALHE}  {fmt(-sem)}")
            lines.append("")
            continue
        lines += [f'{t.date} {flag} "{q(t.desc)}"', *meta,
                  f"  {t.account}  {fmt(t.amount)}", f"  {other}", ""]

    lines.append(";; ---------------------------------------------------------------- saldos conferidos com o banco")
    for (acc, d), b in sorted(balances.items(), key=lambda kv: kv[0][1]):
        lines.append(f"{d + timedelta(days=1)} balance {acc}  {fmt(b.amount)}")

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n")
    replaced = drop_provisional([t for _, t in txns])
    if replaced >= 1000:  # marcações de reembolso foram repassadas: reimporta para aplicar
        replaced -= 1000
        build(verbose=False)

    stats = {"files": len(per_file), "txns": len(txns), "review": review, "ignored": ignored}
    if verbose:
        print(f"✓ {len(per_file)} extratos lidos, {len(txns)} lançamentos ({n_pairs} transferências casadas) → {OUTPUT.relative_to(DATA)}")
        if ignored:
            print(f"  ⚠ arquivos não reconhecidos: {', '.join(ignored)}")
        if review:
            print(f"  ! {len(review)} lançamentos sem categoria (veja Expenses:A-Revisar no Fava)")
        if replaced:
            print(f"  ↺ {replaced} lançamento(s) manual(is) provisório(s) substituído(s) pelo extrato")
    return stats


def drop_provisional(imported: list[Txn]) -> int:
    """Remove de manual.beancount os lançamentos provisórios que já chegaram por extrato.

    Um lançamento manual feito numa conta que vem de extrato (Inter PF, cartões) é marcado com
    `provisorio: TRUE`. Quando o extrato traz o mesmo valor na mesma conta em até 5 dias, o manual sai.
    """
    if not MANUAL.exists():
        return 0
    from beancount.parser import parser

    entries, _, _ = parser.parse_file(str(MANUAL))
    used, remove, carry, carry_cat = set(), [], [], []
    for e in entries:
        if not getattr(e, "meta", {}).get("provisorio") or not hasattr(e, "postings"):
            continue
        known = [p.units.number for p in e.postings if isinstance(getattr(p.units, "number", None), Decimal)]
        for p in e.postings:
            num = getattr(p.units, "number", None)
            if not isinstance(num, Decimal):  # valor em branco: é o que falta para fechar o lançamento
                num = -sum(known, Decimal(0))
            match = next((i for i, t in enumerate(imported) if i not in used and t.account == p.account
                          and t.amount == num and abs((t.date - e.date).days) <= 5), None)
            if match is not None:
                used.add(match)
                remove.append(e.meta["lineno"])
                if e.meta.get("reembolso"):
                    carry.append((txn_key(imported[match]), str(e.meta["reembolso"])))
                else:  # a categoria escolhida à mão vale para o lançamento do extrato
                    cat = next((q.account for q in e.postings if q.account.startswith(("Expenses:", "Income:"))), None)
                    if cat and not cat.endswith((":Outros", ":A-Revisar")):
                        carry_cat.append((txn_key(imported[match]), cat))
                break
    if not remove:
        return 0
    lines = MANUAL.read_text().split("\n")
    for lineno in sorted(remove, reverse=True):
        start = lineno - 1
        end = start
        while end < len(lines) and lines[end].strip():
            end += 1
        del lines[start:end + 1 if end < len(lines) else end]
    MANUAL.write_text("\n".join(lines))
    if carry:  # guarda a marcação de reembolso no lançamento que veio do extrato
        head, cfg = ler_reembolsos_cfg()
        cfg["gastos"] = (cfg.get("gastos") or []) + [{"key": k, "fonte": f} for k, f in carry]
        salvar_reembolsos_cfg(head, cfg)
    if carry_cat:  # só grava se não houver decisão anterior para o mesmo lançamento
        p = CONFIG / "overrides.yaml"
        txt = p.read_text() if p.exists() else ""
        cfg = yaml.safe_load(txt) or {}
        lanc = cfg.get("lancamentos") or {}
        novos = {k: c for k, c in carry_cat if k not in lanc}
        if novos:
            add = "".join(f"  {k}: {c}\n" for k, c in novos.items())
            if "lancamentos:" in txt:
                txt = re.sub(r"(lancamentos:[^\n]*\n)", lambda m: m.group(1).replace(" {}", "") + add, txt, count=1)
            else:
                txt += "lancamentos:\n" + add
            p.write_text(txt)
        else:
            carry_cat = []
    return len(remove) + (1000 if carry or carry_cat else 0)


if __name__ == "__main__":
    build()
