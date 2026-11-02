"""Demo pública na Vercel: o Fava com os dados fictícios de exemplo/, somente leitura.

A Vercel só deixa escrever em /tmp, então exemplo/ é copiado para lá a cada instância nova
e o build gera o imported.beancount ali. Nada do que a demo faz toca o repositório ou dados reais.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DATA = Path("/tmp/finance-demo")

# FINANCE_DATA precisa estar definido antes de importar app.* (app/paths.py lê na importação)
if not (DEMO_DATA / "ledger" / "main.beancount").exists():
    shutil.copytree(ROOT / "exemplo", DEMO_DATA, dirs_exist_ok=True)
os.environ["FINANCE_DATA"] = str(DEMO_DATA)
sys.path.insert(0, str(ROOT))  # para o Fava achar a extensão app.fava_resumo

from fava.application import create_app  # noqa: E402

from app.build import build  # noqa: E402

build(verbose=False)

app = create_app([DEMO_DATA / "ledger" / "main.beancount"], read_only=True)

BANNER = (
    '<div style="position:sticky;top:0;z-index:9999;padding:6px 12px;text-align:center;'
    'font:13px/1.4 system-ui,sans-serif;background:#fff3cd;color:#664d03;border-bottom:1px solid #ffe69c">'
    "Demonstração com dados fictícios, somente leitura. "
    '<a href="https://github.com/iagobragas/finance" style="color:inherit;font-weight:600">'
    "Código no GitHub</a>, rode localmente para usar com os seus extratos.</div>"
)


@app.errorhandler(401)
def _somente_leitura(_):
    # o modo read_only do Fava recusa tudo que não é GET (lançar, editar, importar…)
    return {"success": False, "error": "Demo somente leitura: rode localmente para editar."}, 403


@app.after_request
def _aviso_demo(resp):
    if resp.mimetype == "text/html" and not resp.direct_passthrough:
        html = resp.get_data(as_text=True)
        if "<body" in html:
            i = html.index(">", html.index("<body")) + 1
            resp.set_data(html[:i] + BANNER + html[i:])
    return resp
