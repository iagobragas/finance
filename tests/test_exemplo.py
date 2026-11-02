"""O livro de exemplo/ importa, valida e todas as abas do painel abrem."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

import pytest

ROOT = Path(__file__).resolve().parent.parent
ABAS = ["Resumo", "Ciclo", "Planejamento", "Gastos", "Receitas", "Contas",
        "Lancar", "Pendencias", "Simulador", "Buscar", "Importar"]


def test_usa_dados_de_teste(data_dir):
    from app.paths import DATA

    assert DATA == data_dir.resolve(), "os testes nunca podem tocar a pasta de dados real"


def test_build_gera_imported(ledger):
    assert (ledger.parent / "imported.beancount").exists()


def test_livro_valido(ledger):
    from beancount import loader

    _, errors, _ = loader.load_file(str(ledger))
    assert not errors, "\n".join(str(e) for e in errors[:5])


@pytest.fixture(scope="module")
def client(ledger):
    from fava.application import create_app

    sys.path.insert(0, str(ROOT))  # para o Fava achar a extensão app.fava_resumo
    app = create_app([ledger])
    app.testing = True
    return app.test_client()


@pytest.fixture(scope="module")
def base(client):
    r = client.get("/")
    assert r.status_code == 302
    return r.headers["Location"].split("/extension/")[0]


@pytest.mark.parametrize("aba", ABAS)
def test_aba_abre(client, base, aba):
    r = client.get(f"{base}/extension/{aba}/")
    assert r.status_code == 200, f"{aba}: HTTP {r.status_code}"
    assert b"Traceback" not in r.data


@pytest.mark.parametrize("aba", ABAS)
def test_js_da_aba(client, base, aba):
    r = client.get(f"{base}/extension_js_module/{aba}.js")
    assert r.status_code == 200


def test_previa_do_planejamento(client, base):
    r = client.post(f"{base}/extension/Planejamento/simular", json={})
    assert r.status_code == 200


DEMO_CHECK = f"""
import os, shutil, sys
sys.path.insert(0, {str(ROOT)!r})
shutil.rmtree("/tmp/finance-demo", ignore_errors=True)  # começa limpo, como uma instância nova da Vercel
import demo
c = demo.app.test_client()
b = "/" + {quote("finanças-exemplo")!r}
assert c.post(b + "/extension/Lancar/lancar", json={{}}).status_code == 403
assert c.post(b + "/extension/Planejamento/salvar", json={{}}).status_code == 403
assert c.post(b + "/extension/Planejamento/simular", json={{}}).status_code == 200
r = c.get(b + "/extension/Resumo/")
assert r.status_code == 200 and "Demonstração".encode() in r.data
"""


def test_demo_somente_leitura():
    # demo.py (entrada da Vercel) define o próprio FINANCE_DATA, então roda em outro processo
    import os
    import subprocess

    env = {k: v for k, v in os.environ.items() if k != "FINANCE_DATA"}
    r = subprocess.run([sys.executable, "-c", DEMO_CHECK], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
