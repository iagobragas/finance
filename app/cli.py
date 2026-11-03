"""./finance            -> importa os extratos, abre o Fava e reimporta sozinho quando algo mudar
./finance build      -> só importa (gera ledger/imported.beancount) e valida
./finance check      -> valida o livro (saldos batem? lançamentos fecham?)
./finance init       -> cria a pasta de dados a partir de exemplo/ (configurações, sem os lançamentos fictícios)
./finance exemplo    -> abre o Fava com os dados fictícios de exemplo/

Os dados ficam em dados/ (ou em $FINANCE_DATA). Veja o README.
Navegador: o padrão do sistema, ou o comando em $FINANCE_BROWSER ({url} é trocado pelo endereço).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from app.build import CONFIG, STATEMENTS, build
from app.paths import DATA, ROOT

LEDGER = DATA / "ledger" / "main.beancount"
BIN = Path(sys.executable).parent
PORT = 5050


def check() -> bool:
    r = subprocess.run([BIN / "bean-check", LEDGER], capture_output=True, text=True)
    if r.returncode == 0:
        print("✓ livro válido: todos os saldos conferem com os extratos")
        return True
    print("✗ problemas no livro:\n" + (r.stdout + r.stderr).strip())
    return False


def snapshot() -> dict:
    files = [*STATEMENTS.rglob("*"), *(DATA / "inbox").glob("*"), *CONFIG.glob("*.yaml")]
    return {p: p.stat().st_mtime for p in files if p.is_file()}


def watch():
    last = snapshot()
    while True:
        time.sleep(2)
        now = snapshot()
        if now != last:
            last = now
            print("\n↻ mudança em inbox/, statements/ ou config/, reimportando…")
            # roda num processo novo para sempre usar a versão atual do código e das regras
            subprocess.run([sys.executable, "-m", "app.cli", "build"], cwd=ROOT)


def already_running() -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def abrir(url: str):
    """Abre o painel no navegador padrão, ou com o comando de $FINANCE_BROWSER.

    Ex.: export FINANCE_BROWSER='open -na "Google Chrome" --args --incognito {url}'
    """
    cmd = os.environ.get("FINANCE_BROWSER")
    if not cmd:
        webbrowser.open(url)
        return
    import shlex
    subprocess.Popen([a.replace("{url}", url) for a in shlex.split(cmd)] + ([] if "{url}" in cmd else [url]))


def serve():
    url = f"http://localhost:{PORT}"
    if already_running():
        print(f"→ Fava já está rodando, abrindo {url}")
        abrir(url)
        return
    build()
    check()
    threading.Thread(target=watch, daemon=True).start()
    print(f"\n→ Fava em {url}  (Ctrl+C para sair)\n")
    threading.Timer(1.5, abrir, [url]).start()
    env = {**os.environ, "PYTHONPATH": str(ROOT)}  # para o Fava achar a extensão app.fava_resumo
    subprocess.run([BIN / "fava", "--host", "127.0.0.1", "--port", str(PORT), LEDGER], env=env)


def init():
    """Cria a pasta de dados com as configurações de exemplo e um livro vazio."""
    import shutil
    if (DATA / "ledger" / "main.beancount").exists():
        print(f"✓ a pasta de dados já existe: {DATA}")
        return
    ex = ROOT / "exemplo"
    for sub in ("config", "statements", "inbox", "comprovantes", "notas", "ledger"):
        (DATA / sub).mkdir(parents=True, exist_ok=True)
    for f in (ex / "config").glob("*.yaml"):
        shutil.copy(f, DATA / "config" / f.name)
    main_ = (ex / "ledger" / "main.beancount").read_text().replace("Finanças - Exemplo", "Finanças")
    (DATA / "ledger" / "main.beancount").write_text(main_)
    (DATA / "ledger" / "manual.beancount").write_text(
        ";; Lançamentos manuais: o que não aparece em nenhum extrato (dinheiro vivo, empréstimos...).\n")
    print(f"✓ pasta de dados criada em {DATA}\n  Agora ajuste config/accounts.yaml e config/rules.yaml e rode ./finance")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "init":
        init()
        return
    if cmd == "exemplo":
        os.environ["FINANCE_DATA"] = str(ROOT / "exemplo")
        sys.exit(subprocess.run([sys.executable, "-m", "app.cli", *sys.argv[2:]], env=os.environ).returncode)
    if cmd in ("build", "check", "serve") and not LEDGER.exists():
        print(f"✗ pasta de dados não encontrada: {DATA}\n"
              "  Primeira vez? Rode ./finance init (ou ./finance exemplo para ver com dados fictícios).\n"
              "  Dados no iCloud? Veja \"Usar em mais de um Mac\" no README.")
        sys.exit(1)
    if cmd == "build":
        build()
        sys.exit(0 if check() else 1)
    elif cmd == "check":
        # imported.beancount é gerado pelo build; num clone novo (ou em exemplo/) ele ainda não existe
        if not (LEDGER.parent / "imported.beancount").exists():
            build(verbose=False)
        sys.exit(0 if check() else 1)
    elif cmd == "serve":
        try:
            serve()
        except KeyboardInterrupt:
            pass
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
