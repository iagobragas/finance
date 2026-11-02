"""Notas fiscais de serviço (NFS-e padrão nacional, XML) emitidas pelo MEI.

Ficam em notas/AAAA-MM_nota-N_tomador.xml (+ o PDF/DANFSe com o mesmo nome). A aba Receitas confere cada
nota com o pagamento recebido da empresa (config/accounts.yaml -> tomadores: CNPJ -> fonte de receita).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from app.paths import DATA

NOTAS = DATA / "notas"
NS = "{http://www.sped.fazenda.gov.br/nfse}"


def is_nfse(path: Path) -> bool:
    if path.suffix.lower() != ".xml":
        return False
    head = path.read_text(encoding="utf-8", errors="ignore")[:600]
    return "<NFSe" in head and "sped.fazenda.gov.br/nfse" in head


def chave_pdf(path: Path) -> str | None:
    """DANFSe (PDF da nota): a chave de 50 dígitos costuma ser o nome do arquivo."""
    if path.suffix.lower() != ".pdf":
        return None
    m = re.fullmatch(r"(\d{44,50})", path.stem)
    return m.group(1) if m else None


def parse(path: Path) -> dict:
    root = ET.parse(path).getroot()
    inf = root.find(f"{NS}infNFSe")

    def txt(node, *tags):
        for t in tags:
            el = node.find(f".//{NS}{t}") if node is not None else None
            if el is not None and el.text:
                return el.text.strip()
        return ""

    toma = root.find(f".//{NS}toma")
    emissao = txt(root, "dhEmi", "dhProc")
    return {
        "chave": (inf.get("Id") or "").removeprefix("NFS") if inf is not None else path.stem,
        "numero": int(txt(inf, "nNFSe") or 0),
        "competencia": txt(root, "dCompet"),
        "emissao": emissao[:10],
        "valor": float(Decimal(txt(root, "vServ") or "0")),
        "liquido": float(Decimal(txt(inf, "vLiq") or txt(root, "vServ") or "0")),
        "tomador_cnpj": re.sub(r"\D", "", txt(toma, "CNPJ", "CPF")),
        "tomador": txt(toma, "xNome"),
        "descricao": txt(root, "xDescServ"),
        "arquivo": path.name,
    }


def nome_arquivo(n: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", n["tomador"].lower()).strip("-")[:30] or "tomador"
    return f"{n['competencia'][:7]}_nota-{n['numero']}_{slug}"


def todas() -> list[dict]:
    if not NOTAS.exists():
        return []
    out = []
    for p in sorted(NOTAS.glob("*.xml")):
        try:
            n = parse(p)
        except ET.ParseError:
            continue
        n["pdf"] = p.with_suffix(".pdf").exists()
        out.append(n)
    return sorted(out, key=lambda n: (n["emissao"], n["numero"]))
