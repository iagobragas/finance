"""Demo pública na Vercel: o Fava com os dados fictícios de exemplo/, somente leitura.

A Vercel só deixa escrever em /tmp, então exemplo/ é copiado para lá a cada instância nova
e o build gera o imported.beancount ali. Nada do que a demo faz toca o repositório ou dados reais.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, unquote_to_bytes

ROOT = Path(__file__).resolve().parent
DEMO_DATA = Path("/tmp/finance-demo")

# FINANCE_DATA precisa estar definido antes de importar app.* (app/paths.py lê na importação)
if not (DEMO_DATA / "ledger" / "main.beancount").exists():
    shutil.copytree(ROOT / "exemplo", DEMO_DATA, dirs_exist_ok=True)
os.environ["FINANCE_DATA"] = str(DEMO_DATA)
sys.path.insert(0, str(ROOT))  # para o Fava achar a extensão app.fava_resumo

from fava.application import create_app  # noqa: E402
from flask import request, send_file  # noqa: E402

from app.build import build  # noqa: E402

build(verbose=False)

app = create_app([DEMO_DATA / "ledger" / "main.beancount"])

# Somente leitura: bloqueia tudo que não é GET, menos rotas que só calculam (prévia do Planejamento).
SO_CALCULA = ("/extension/Planejamento/simular",)


@app.before_request
def _somente_leitura():
    if request.method != "GET" and not request.path.endswith(SO_CALCULA):
        return {"success": False, "error": "Demo somente leitura: rode localmente para editar."}, 403


def _decodifica_path(wsgi_app):
    # a Vercel entrega PATH_INFO ainda com %XX; o slug do livro tem acento ("finanças-exemplo")
    def wrapper(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if "%" in path:
            environ["PATH_INFO"] = unquote_to_bytes(path).decode("latin-1")  # WSGI: bytes como latin-1
        return wsgi_app(environ, start_response)

    return wrapper


app.wsgi_app = _decodifica_path(app.wsgi_app)

BANNER = (
    '<div style="position:fixed;left:0;right:0;bottom:0;z-index:9999;padding:6px 12px;text-align:center;'
    'font:13px/1.4 system-ui,sans-serif;background:#fff3cd;color:#664d03;border-top:1px solid #ffe69c">'
    "Demonstração com dados fictícios, somente leitura. "
    '<a href="https://github.com/iagobragas/finance" style="color:inherit;font-weight:600">'
    "Código no GitHub</a>, rode localmente para usar com os seus extratos.</div>"
)


# Pré-visualização ao compartilhar o link (WhatsApp, Slack, LinkedIn…): Open Graph + Twitter card
SITE = "https://finance-demo.iagobragas.com.br"
TITULO = "finance: controle financeiro pessoal e de MEI"
DESCRICAO = ("Quanto sobra até o fim do mês, para onde foi o dinheiro e como ficam os próximos meses. "
             "Beancount + Fava, roda no seu Mac. Demo com dados fictícios.")
OG = (
    f'<meta property="og:type" content="website">'
    f'<meta property="og:site_name" content="finance">'
    f'<meta property="og:locale" content="pt_BR">'
    f'<meta property="og:title" content="{TITULO}">'
    f'<meta property="og:description" content="{DESCRICAO}">'
    f'<meta property="og:image" content="{SITE}/og.jpg">'
    f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
    f'<meta property="og:image:alt" content="Aba Ciclo: quanto sobra até o fim do ciclo">'
    f'<meta name="twitter:card" content="summary_large_image">'
    f'<meta name="description" content="{DESCRICAO}">'
)


@app.route("/og.jpg")
def _og_imagem():
    return send_file(ROOT / "demo_assets" / "og.jpg", mimetype="image/jpeg", max_age=86400)


@app.after_request
def _aviso_demo(resp):
    if resp.mimetype == "text/html" and not resp.direct_passthrough:
        html = resp.get_data(as_text=True)
        if "<head" in html:
            i = html.index(">", html.index("<head")) + 1
            url = f'<meta property="og:url" content="{SITE}{quote(request.path)}">'
            html = html[:i] + OG + url + html[i:]
        if "<body" in html:
            i = html.index(">", html.index("<body")) + 1
            html = html[:i] + BANNER + html[i:]
        resp.set_data(html)
    return resp
