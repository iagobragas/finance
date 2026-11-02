"""Onde fica cada coisa.

O código (este repositório) e os seus dados ficam separados: extratos, livro, configurações, comprovantes
e notas moram na pasta de dados, que nunca vai para o git. Ela é procurada em:

1. a variável FINANCE_DATA, se definida;
2. `dados/` ao lado do código (pode ser um link para uma pasta no iCloud Drive).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # código
DATA = Path(os.environ.get("FINANCE_DATA") or ROOT / "dados").expanduser().resolve()
CONFIG = DATA / "config"
