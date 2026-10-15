"""Roda um script do PowerShell sem janela nenhuma. As tarefas agendadas e o atalho do guardião chamam este arquivo pelo pythonw.

Por que existe: "powershell -WindowStyle Hidden" primeiro abre a janela do terminal e só depois a esconde. No logon, com o computador ainda
lento, cada tarefa deixava uma janela preta vazia na tela por alguns segundos (caso de 15/10/2026: quatro janelas ao ligar o computador,
que para quem não conhece parece vírus). O pythonw não tem janela, e o PowerShell aberto daqui com CREATE_NO_WINDOW também não.
Se o script falhar, o motivo fica em logs\\tarefas.log, com data e hora.

Uso: pythonw sem_janela.py <script.ps1> [argumentos do script]"""
import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(os.path.dirname(AQUI), "logs", "tarefas.log")
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def comando(script, extra=()):
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script, *extra]


def decodificar(dados):
    """O PowerShell 5.1 escreve a saída redirecionada na página de código do console (cp850 no Brasil), não em UTF-8."""
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        try:
            import ctypes
            return dados.decode(f"cp{ctypes.windll.kernel32.GetOEMCP()}", "replace")
        except (LookupError, OSError, AttributeError):
            return dados.decode("latin-1", "replace")


def anotar(texto):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {texto}\n")
    except OSError:
        pass


def rodar(script, extra=()):
    """Roda o script e espera ele terminar. Devolve o código de saída (1 se nem deu para começar)."""
    script = os.path.abspath(script)
    if not os.path.exists(script):
        anotar(f"{script}: o arquivo não existe")
        return 1
    try:
        r = subprocess.run(comando(script, extra), creationflags=SEM_JANELA, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE)
    except OSError as erro:
        anotar(f"{script}: não consegui abrir o PowerShell ({erro})")
        return 1
    if r.returncode:
        detalhe = decodificar(r.stderr or b"").strip().splitlines()[:2]  # as primeiras linhas trazem o erro; as de baixo são o detalhe técnico
        anotar(f"{os.path.basename(script)} terminou com código {r.returncode}" + (": " + " | ".join(detalhe) if detalhe else ""))
    return r.returncode


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(2)
    sys.exit(rodar(sys.argv[1], sys.argv[2:]))
