"""Leitores de extratos. Cada parser recebe um arquivo e devolve uma lista de Txn.

Convenção de sinal: `amount` é o efeito na conta de origem (`account`).
  - Conta corrente: positivo = entrou dinheiro, negativo = saiu.
  - Cartão (passivo): negativo = compra (aumenta a dívida), positivo = pagamento/estorno.
"""

from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.paths import CONFIG as CONFIG_DIR


@dataclass
class Txn:
    date: date
    desc: str
    amount: Decimal
    account: str
    source: str  # nome do arquivo de origem
    meta: dict = field(default_factory=dict)


@dataclass
class Balance:
    date: date  # saldo no FIM deste dia
    account: str
    amount: Decimal


@dataclass
class Parsed:
    txns: list[Txn] = field(default_factory=list)
    balances: list[Balance] = field(default_factory=list)
    opening: list[Txn] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def br_decimal(s: str) -> Decimal:
    """'1.234,56' / '- 145,00' / '-2431.5' -> Decimal."""
    s = s.strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError(d)


# ---------------------------------------------------------------- Inter PF (conta corrente)

def is_inter_pf(path: Path) -> bool:
    if path.suffix.lower() != ".csv":
        return False
    head = path.read_text(encoding="utf-8-sig", errors="ignore")[:300]
    return "Extrato Conta Corrente" in head


def meio_inter(hist: str) -> str:
    """Histórico do extrato Inter -> meio de pagamento."""
    h = hist.lower()
    if "pix no cr" in h or "crédito liberado" in h:
        return "Pix no crédito"
    if "débito" in h or "debito" in h:
        return "Débito Inter"
    if "pix" in h:
        return "Pix"
    if "ted" in h or "doc" in h or "transfer" in h:
        return "TED"
    if "boleto" in h or "pagamento" in h:
        return "Boleto"
    return hist.strip()


def parse_inter_pf(path: Path, account: str) -> Parsed:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("Data Lançamento"))
    rows = []
    for r in csv.reader(lines[start + 1 :], delimiter=";"):
        if len(r) >= 5 and r[0].strip():  # formato antigo: Data;Histórico;Descrição;Valor;Saldo
            rows.append([r[0], r[1].strip(), r[2].strip(), r[3], r[4]])
        elif len(r) == 4 and r[0].strip():  # formato novo: Data;Descrição;Valor;Saldo, com 'Pix enviado: "Cp :123-NOME"'
            m = re.match(r'\s*([^:]+):\s*"?(?:Cp\s*:\s*\d+-)?([^"]*)"?\s*$', r[1])
            hist, desc = (m.group(1).strip(), m.group(2).strip()) if m else (r[1].strip(), "")
            if desc.isupper() or desc.islower():
                desc = desc.title()
            rows.append([r[0], hist, desc, r[2], r[3]])
    data = lambda r: datetime.strptime(r[0].strip(), "%d/%m/%Y").date()
    if rows and data(rows[0]) < data(rows[-1]):  # formato novo vem do mais antigo para o mais novo
        rows.reverse()
    out = Parsed()
    last_of_day: dict[date, Decimal] = {}
    for d, hist, desc, valor, saldo in rows:  # do mais novo para o mais antigo
        dt = datetime.strptime(d.strip(), "%d/%m/%Y").date()
        amount = br_decimal(valor)
        # identidade do lançamento independente do formato do arquivo: data + valor + saldo depois dele
        out.txns.append(Txn(dt, f"{hist} - {desc}" if desc else hist, amount, account, path.name,
                            {"meio": meio_inter(hist), "_id": f"saldo {br_decimal(saldo)}"}))
        last_of_day.setdefault(dt, br_decimal(saldo))  # primeira linha do dia = saldo final do dia
    for dt, s in last_of_day.items():
        out.balances.append(Balance(dt, account, s))
    # saldo antes do primeiro lançamento do arquivo
    oldest = rows[-1]
    before = br_decimal(oldest[4]) - br_decimal(oldest[3])
    first_day = datetime.strptime(oldest[0].strip(), "%d/%m/%Y").date()
    out.opening.append(Txn(first_day, "Saldo inicial", before, account, path.name))
    return out


# ---------------------------------------------------------------- Cora PJ (conta do MEI; CSV Data,Transação,Tipo Transação,...)

def is_cora_pj(path: Path) -> bool:
    if path.suffix.lower() != ".csv":
        return False
    head = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()[:1]
    return bool(head) and head[0].startswith("Data,Transação,Tipo Transação")


def parse_cora_pj(path: Path, account: str) -> Parsed:
    out = Parsed()
    with path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            dt = datetime.strptime(r["Data"].strip(), "%d/%m/%Y").date()
            desc = f"{r['Transação'].strip()} - {r['Identificação'].strip()}"
            out.txns.append(Txn(dt, desc, br_decimal(r["Valor"]), account, path.name,
                                {"meio": meio_inter(r["Transação"]) + " PJ"}))
    return out


# ---------------------------------------------------------------- Nubank cartão (CSV)

def is_nubank_card(path: Path) -> bool:
    if path.suffix.lower() != ".csv":
        return False
    head = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()[:1]
    return bool(head) and head[0].strip() == "date,title,amount"


def parse_nubank_card(path: Path, account: str) -> Parsed:
    out = Parsed()
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    vence = m.group(1) if m else ""
    with path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            dt = date.fromisoformat(r["date"].strip())
            # CSV do Nubank: positivo = compra, negativo = pagamento/estorno
            out.txns.append(Txn(dt, r["title"].strip(), -br_decimal(r["amount"]), account, path.name,
                                {"meio": "Crédito Nubank", **({"vence": vence} if vence else {})}))
    return out


# ---------------------------------------------------------------- Inter fatura (PDF)

MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
LINE_RE = re.compile(
    r"^\s*(\d{2}) de (\w{3})\. (\d{4})\s+(.+?)\s{2,}.*?(\+?)\s?R\$ ([\d.,]+)\s*$")
PARCELA_RE = re.compile(r"\(Parcela (\d+) de (\d+)\)")
CARD_RE = re.compile(r"^\s*CARTÃO \d{4}\*{4}(\d{4})\s*$")


def pdf_text(path: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(path), "-"],
                          capture_output=True, text=True, check=True).stdout


def is_inter_card(path: Path) -> bool:
    if path.suffix.lower() != ".pdf":
        return False
    try:
        t = pdf_text(path)
    except Exception:
        return False
    return "Despesas da fatura" in t and "CARTÃO" in t


def parse_inter_card(path: Path, account: str) -> Parsed:
    t = pdf_text(path)
    venc = re.search(r"(\d\d/\d\d/\d{4})", t[t.find("Data de Vencimento"):]).group(1)
    due = datetime.strptime(venc, "%d/%m/%Y").date()
    next_cut = re.search(r"Data de corte:\s*(\d\d/\d\d/\d{4})", t)
    cut = add_months(datetime.strptime(next_cut.group(1), "%d/%m/%Y").date(), -1) if next_cut else None
    fatura = f"{due:%Y-%m}"

    out = Parsed()
    section = t[t.find("Despesas da fatura"):]
    card = None
    for line in section.splitlines():
        c = CARD_RE.search(line)
        if c:
            card = c.group(1)
            continue
        found = LINE_RE.match(line)
        if not found:
            continue
        d, m, y, desc, plus, valor = found.groups()
        desc = re.sub(r"\s{2,}.*$", "", desc.strip())
        dt = date(int(y), MESES[m.lower()], int(d))
        amount = br_decimal(valor)
        amount = amount if plus else -amount
        meta = {"fatura": fatura, "vence": due.isoformat(), "meio": "Crédito Inter"}
        if card:
            meta["cartao"] = card
        p = PARCELA_RE.search(desc)
        if p:
            n, total = int(p.group(1)), int(p.group(2))
            # a fatura mostra a data da compra original; cada parcela vai para o mês correspondente
            dt = add_months(dt, n - 1)
            meta["parcela"] = f"{n}/{total}"
        out.txns.append(Txn(dt, desc, amount, account, path.name, meta))
    out.meta = {"due": due, "cut": cut}
    return out


# ---------------------------------------------------------------- OFX (qualquer banco)
# Qual conta do livro corresponde a cada número de conta vem de config/accounts.yaml -> ofx_contas.

def is_ofx(path: Path) -> bool:
    if path.suffix.lower() not in (".ofx", ".qfx"):
        return False
    head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    return "<OFX>" in head.upper() or "OFXHEADER" in head.upper()


def _ofx_tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, re.I)
    return m.group(1).strip() if m else ""


def _ofx_date(s: str) -> date:
    return datetime.strptime(s[:8], "%Y%m%d").date()


def _ofx_brt(s: str) -> date:
    """Data no horário de Brasília (o Cora e o Nubank exportam DTSERVER em GMT: 01:53 GMT = 22:53 da véspera)."""
    from datetime import timedelta
    m = re.match(r"(\d{8})(\d{6})?(?:\.\d+)?(?:\[([+-]?\d+)(?::\w+)?\])?", s.strip())
    if not m:
        return _ofx_date(s)
    dt = datetime.strptime(m.group(1) + (m.group(2) or "120000"), "%Y%m%d%H%M%S")
    if m.group(3) is not None and m.group(2):
        dt = dt - timedelta(hours=int(m.group(3))) - timedelta(hours=3)
    return dt.date()


BANCOS = {"CORA": "Cora", "BANCO INTER": "Inter", "WOOVI": "Woovi", "NU PAGAMENTOS": "Nubank", "C6": "C6",
          "IFOOD": "iFood", "ITAU": "Itaú", "BRADESCO": "Bradesco", "SANTANDER": "Santander", "CAIXA": "Caixa",
          "BANCO DO BRASIL": "BB", "MERCADO PAGO": "Mercado Pago", "PICPAY": "PicPay"}


def _banco(memo: str) -> str:
    up = memo.upper()
    # o banco vem depois do CPF/CNPJ: "... - •••.650.119-•• - BANCO INTER (0077) Agência..."
    m = re.search(r"(?:-••|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\s+-\s+(.+?\(\d{3,4}\))", up)
    alvo = m.group(1) if m else ""
    return next((v for k, v in BANCOS.items() if k in alvo), alvo.split(" (")[0].title() if alvo else "")


def _ofx_desc(memo: str) -> tuple[str, str]:
    """Descrição curta como nos outros extratos: 'Pix recebido - Fulano · Banco'."""
    banco = _banco(memo)
    suf = f" · {banco}" if banco else ""
    m = re.match(r"Transfer[êe]ncia (recebida|enviada) pelo Pix - (.+?)\s+-\s", memo, re.I)
    if m:
        return f"Pix {'recebido' if m.group(1).lower() == 'recebida' else 'enviado'} - {m.group(2).strip()}{suf}", "Pix"
    m = re.match(r"Transfer[êe]ncia (recebida|enviada) - (.+?)(\s+-\s|$)", memo, re.I)
    if m:
        return f"Transferência {m.group(1).lower()} - {m.group(2).strip()}{suf}", "Transferência"
    if re.search(r"d[ée]bito", memo, re.I):
        return memo, "Débito"
    if re.search(r"boleto|pagamento de fatura", memo, re.I):
        return memo, "Boleto"
    if re.search(r"\bpix\b", memo, re.I):  # "Pgto QR Code Pix - MINISTERIO DA FAZENDA"
        return memo, "Pix"
    return memo, "Outro"


def ofx_config() -> dict:
    import yaml
    cfg = CONFIG_DIR / "accounts.yaml"
    return (yaml.safe_load(cfg.read_text()) or {}).get("ofx_contas") or {}


def parse_ofx(path: Path, account: str | None = None) -> Parsed:
    t = path.read_text(encoding="utf-8", errors="ignore")
    acct = _ofx_tag(t, "ACCTID")
    conf = ofx_config().get(acct) or ofx_config().get(acct.replace("-", ""))
    if not conf:
        raise ValueError(f"conta OFX {acct} ({_ofx_tag(t, 'ORG')}) não configurada em config/accounts.yaml -> ofx_contas")
    account = conf["conta"]
    out = Parsed()
    out.meta = {"kind": conf.get("tipo", "ofx"), "pasta": conf.get("pasta", f"ofx-{acct}"),
                "inicio": _ofx_date(_ofx_tag(t, "DTSTART")), "fim": _ofx_date(_ofx_tag(t, "DTEND"))}
    if conf.get("ignorar"):  # conta que vem por outro formato (ex.: Inter PF em CSV, com saldo diário)
        out.meta["ignorado"] = True
        return out
    cartao = bool(conf.get("cartao"))
    if cartao:  # fatura de cartão: o vencimento vem do nome (Nubank_2026-10-14.ofx) ou do fechamento + 7 dias
        from datetime import timedelta
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", path.name)
        vence = date(*map(int, m.groups())) if m else out.meta["fim"] + timedelta(days=7)
        out.meta["fatura_vence"] = vence
    desde = date.fromisoformat(str(conf["desde"])) if conf.get("desde") else None
    total = Decimal(0)
    for bloco in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", t, re.S | re.I):
        memo = _ofx_tag(bloco, "MEMO") or _ofx_tag(bloco, "NAME")
        desc, meio = _ofx_desc(memo)
        valor = Decimal(_ofx_tag(bloco, "TRNAMT"))
        dt = _ofx_date(_ofx_tag(bloco, "DTPOSTED"))
        total += valor
        if desde and dt < desde:  # antes disso a conta vem de outro formato: não duplica
            continue
        if account.startswith("Assets:Cora") and meio != "Outro":
            meio += " PJ"  # como no CSV do Cora: "Pix PJ", "Boleto PJ"
        meta = {"meio": conf.get("meio") or meio, "fitid": _ofx_tag(bloco, "FITID")}
        if cartao:
            meta.update({"vence": vence.isoformat(), "fatura": f"{vence:%Y-%m}"})
            desc = memo
        out.txns.append(Txn(dt, desc, valor, account, path.name, meta))
    bal = re.search(r"<LEDGERBAL>(.*?)</LEDGERBAL>", t, re.S | re.I)
    if bal and not cartao:
        asof = _ofx_date(_ofx_tag(bal.group(1), "DTASOF"))
        valor_fim = Decimal(_ofx_tag(bal.group(1), "BALAMT"))
        srv = _ofx_tag(t, "DTSERVER")
        if srv and asof >= _ofx_brt(srv):
            # o Cora data o saldo no fim do mês pedido (31/10) mesmo exportando no dia 08: confere só até a véspera
            # da exportação, para um arquivo mais novo do mesmo mês não contradizer este
            from datetime import timedelta
            exp = _ofx_brt(srv)
            depois = sum((tx.amount for tx in out.txns if tx.date >= exp), Decimal(0))
            out.balances.append(Balance(exp - timedelta(days=1), account, valor_fim - depois))
        else:
            out.balances.append(Balance(asof, account, valor_fim))
        if not desde:
            out.meta["saldo_inicial"] = (out.meta["inicio"], valor_fim - total)  # saldo antes do 1º dia do arquivo
    return out


# ---------------------------------------------------------------- Inter fatura (CSV do app)
# "Data","Lançamento","Categoria","Tipo","Valor" · Tipo = "Compra à vista" ou "Parcela n/t" (data da compra original)

def is_inter_card_csv(path: Path) -> bool:
    if path.suffix.lower() != ".csv":
        return False
    head = path.read_text(encoding="utf-8-sig", errors="ignore")[:200]
    return head.startswith('"Data","Lançamento","Categoria","Tipo","Valor"')


def parse_inter_card_csv(path: Path, account: str | None = None) -> Parsed:
    import yaml
    cfg = yaml.safe_load((CONFIG_DIR / "accounts.yaml").read_text()) or {}
    account = account or cfg["sources"]["inter_card"]
    dia_venc = int(((cfg.get("card_cycles") or {}).get(account) or {}).get("vence", 15))
    m = re.search(r"(\d{4})-(\d{2})", path.name)
    out = Parsed()
    with path.open(encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f))
    if m:
        vence = date(int(m.group(1)), int(m.group(2)), dia_venc)
    else:  # sem o mês no nome: a última compra à vista + 1 mês
        ult = max(datetime.strptime(r["Data"], "%d/%m/%Y").date() for r in linhas if not r["Tipo"].startswith("Parcela"))
        vence = add_months(ult.replace(day=dia_venc), 1)
    a_vista = [r for r in linhas if not r["Tipo"].startswith("Parcela")]
    out.meta = {"kind": "inter_card", "pasta": "inter-cartao" if a_vista else "inter-cartao/futuras", "fatura_vence": vence}
    if not a_vista:  # fatura futura: só parcelas que ainda vão ser cobradas (a previsão já conta com elas)
        out.meta["futura"] = True
        return out
    for r in linhas:
        dt = datetime.strptime(r["Data"], "%d/%m/%Y").date()
        v = r["Valor"].replace("\xa0", " ").strip()
        neg = v.startswith("-")
        valor = br_decimal(re.sub(r"[^\d.,]", "", v))
        amount = valor if neg else -valor  # compra aumenta a dívida; pagamento/estorno ("-R$") diminui
        bruto = r["Lançamento"].strip()
        desc = re.sub(r"\s{2,}.*$", "", bruto)
        if len(desc) <= 3 and len(bruto) > 22:  # "DL           UberRides Sao Paulo": o nome ocupa as 22 primeiras colunas
            desc = re.sub(r"\s+", " ", bruto[:22]).strip()
        meta = {"fatura": f"{vence:%Y-%m}", "vence": vence.isoformat(), "meio": "Crédito Inter",
                "categoria_banco": r["Categoria"].strip().title()}
        p = re.match(r"Parcela (\d+)/(\d+)", r["Tipo"])
        if p:
            n, total = int(p.group(1)), int(p.group(2))
            dt = add_months(dt, n - 1)  # a data é da compra original: cada parcela vai para o seu mês
            meta["parcela"] = f"{n}/{total}"
        out.txns.append(Txn(dt, desc, amount, account, path.name, meta))
    return out


PARSERS = [
    ("inter_pf", is_inter_pf, parse_inter_pf),
    ("cora_pj", is_cora_pj, parse_cora_pj),
    ("nubank_card", is_nubank_card, parse_nubank_card),
    ("inter_card", is_inter_card, parse_inter_card),
    ("ofx", is_ofx, parse_ofx),
    ("inter_card_csv", is_inter_card_csv, parse_inter_card_csv),
]


def detect(path: Path):
    for name, check, parse in PARSERS:
        if check(path):
            return name, parse
    return None, None
