"""Os testes rodam sobre uma cópia de exemplo/ em uma pasta temporária, nunca sobre os seus dados.

FINANCE_DATA precisa estar definido antes de importar app.* (app/paths.py lê na importação),
por isso a cópia é feita aqui, no carregamento do conftest.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(tempfile.mkdtemp(prefix="finance-test-"))
shutil.copytree(ROOT / "exemplo", DATA, dirs_exist_ok=True)
os.environ["FINANCE_DATA"] = str(DATA)


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA


@pytest.fixture(scope="session")
def ledger(data_dir: Path) -> Path:
    from app.build import build

    build(verbose=False)
    return data_dir / "ledger" / "main.beancount"


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(DATA, ignore_errors=True)
