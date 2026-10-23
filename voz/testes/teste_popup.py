"""O aviso próprio do guardião (popup.py, 0.9.1), com a janela de verdade na tela por alguns segundos e sem som: aparece no canto de baixo,
por cima, sem roubar o foco e sem botão na barra de tarefas; acentos e aspas chegam inteiros; um aviso novo substitui o anterior; some sozinho.
Também: a rota /popup do servidor, o Iniciar do aviso só vale para a tarefa de agora, e o avisos.ps1 usa o aviso próprio com a notificação do
Windows só de reserva."""
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

import requests

import v2_base as B
from v2_base import confere, h, placar, v2

AQUI = os.path.dirname(os.path.abspath(__file__))
VOZ = os.path.dirname(AQUI)
POPUP = os.path.join(VOZ, "popup.py")
PYW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
PYW = PYW if os.path.exists(PYW) else sys.executable
user32 = ctypes.windll.user32
TITULO_JANELA = "Guardião · aviso"
os.environ["GUARDIAO_POPUP_MUDO"] = "1"

# A parte com a janela de verdade mostra avisos na tela de quem está usando o computador ("Segundo aviso", "Este substitui o primeiro"),
# e a pessoa não tem como saber que são de teste (caso de 15/10/2026). Ela só roda quando pedida: --janela ou GUARDIAO_TESTE_JANELA=1.
JANELA_DE_VERDADE = "--janela" in sys.argv or os.environ.get("GUARDIAO_TESTE_JANELA") == "1"

PORTA = 8799
tmp, relogio = B.preparar(PORTA, hora="09:50")
URL = f"http://localhost:{PORTA}"


def janelas():
    achadas = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def olhar(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value == TITULO_JANELA and user32.IsWindowVisible(hwnd):
            achadas.append(hwnd)
        return True

    user32.EnumWindows(olhar, 0)
    return achadas


PROCS = []


def pid_de(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def abrir(dados, segundos=6):
    arq = os.path.join(tempfile.gettempdir(), f"gv_teste_popup_{time.time_ns()}.json")
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    PROCS.append(subprocess.Popen([PYW, POPUP, "--json", arq, "--segundos", str(segundos)], cwd=VOZ))
    return arq


def esperar(cond, seg):
    fim = time.time() + seg
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.1)
    return cond()


# ---------------- pode mostrar agora? ----------------
r = subprocess.run([sys.executable, POPUP, "--checar"], cwd=VOZ)
confere("--checar responde rápido, 0 (pode mostrar) ou 3 (apresentação ou tela cheia)", r.returncode in (0, 3), r.returncode)
pode = r.returncode == 0

# ---------------- a janela de verdade (só quando pedida) ----------------
if not JANELA_DE_VERDADE:
    print("  (a parte com a janela de verdade foi pulada: ela aparece na tela de quem usa o computador. Para rodar: --janela)")
elif pode:
    arq = abrir({"titulo": "Teste: montar as campanhas da Clínica \"Vitta\"", "texto": "Comece por: revisar o público, ação e orçamento.", "kicker": "Agora", "tag": "até 10:30", "bloco": "b3"})
    confere("o aviso aparece na tela", esperar(lambda: len(janelas()) == 1, 8), janelas())
    time.sleep(0.8)
    hwnd = (janelas() or [0])[0]
    ex = user32.GetWindowLongW(hwnd, -20)
    # o foco pode mudar porque a pessoa está usando o computador; o que não pode é ele ir para o aviso
    confere("não rouba o foco de quem está digitando (janela que não se ativa)", ex & 0x08000000 and pid_de(user32.GetForegroundWindow()) != PROCS[-1].pid,
            (hex(ex), pid_de(user32.GetForegroundWindow()), PROCS[-1].pid))
    confere("sem botão na barra de tarefas e por cima das outras janelas", ex & 0x80 and ex & 0x8, hex(ex))
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    area = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)
    confere("fica no canto de baixo à direita, dentro da área útil (acima da barra de tarefas)",
            area.right - 80 <= r.right <= area.right and area.bottom - 80 <= r.bottom <= area.bottom and r.right - r.left > 300, (r.left, r.top, r.right, r.bottom, area.right, area.bottom))
    confere("o arquivo com o texto é apagado depois de lido", not os.path.exists(arq))
    abrir({"titulo": "Teste do guardião (pode ignorar)", "texto": "Este aviso de teste substitui o anterior."}, segundos=3)
    time.sleep(2.0)
    confere("um aviso novo substitui o anterior (fica um só na tela)", len(janelas()) == 1, janelas())
    confere("e some sozinho depois do tempo dele (mesmo com o ponteiro do mouse parado em cima de onde ele nasceu)", esperar(lambda: not janelas(), 15), janelas())
else:
    print("  (o Windows está em apresentação ou tela cheia: a parte da janela de verdade foi pulada)")

# ---------------- a rota do servidor e o Iniciar do aviso ----------------
pedidos = []
h.COMANDO_POPUP = lambda d: pedidos.append(d) or True
r = requests.post(URL + "/popup", json={"titulo": "Montar as campanhas", "texto": "Faltam 10 minutos.", "kicker": "Aviso de tempo", "tag": "faltam 10 min", "outra": "x"}, timeout=5)
confere("POST /popup abre o aviso com título, texto, etiqueta e kicker (e nada além disso)", r.status_code == 202 and r.json()["ok"] and pedidos and set(pedidos[-1]) == {"titulo", "texto", "kicker", "tag", "bloco"}, (r.status_code, pedidos))
confere("sem título, não abre nada", requests.post(URL + "/popup", json={"texto": "x"}, timeout=5).json()["ok"] is False)
confere("origem estranha é recusada", requests.post(URL + "/popup", json={"titulo": "x"}, headers={"Origin": "http://exemplo.com"}, timeout=5).status_code == 403)
r = v2.acao_execucao({"acao": "iniciar", "id": "b5"})
confere("Iniciar no aviso de uma tarefa que já não é a de agora não inicia nada", r["ok"] is False and not v2.estado_exec()["sessao"], r)
r = v2.acao_execucao({"acao": "iniciar", "id": "b3"})
confere("Iniciar no aviso da tarefa de agora inicia ela (e liga o modo execução)", r["ok"] and r["ativo"] and r["sessao"] and r["sessao"]["bloco"] == "b3", r)

# ---------------- o avisos.ps1 ----------------
raiz = os.path.dirname(VOZ)  # no repositório o avisos.ps1 fica em app\; numa instalação, na pasta do guardião
avisos = open(next(p for p in (os.path.join(raiz, "app", "avisos.ps1"), os.path.join(raiz, "avisos.ps1")) if os.path.exists(p)), encoding="utf-8-sig").read()
confere("avisos.ps1 usa o aviso próprio (popup.py), confere antes se pode mostrar e passa o texto por arquivo",
        "voz\\popup.py" in avisos and "'--checar'" in avisos and "'--json'" in avisos)
confere("a notificação comum do Windows fica só de reserva", "Mostrar-Notificacao" in avisos and avisos.count("Mostrar-Notificacao") == 2)
confere("o aviso do começo da tarefa leva o id dela (para o botão Iniciar)", "'Agora' (\"até {0}\" -f $b.fim) $b.id" in avisos)
fonte = open(os.path.join(VOZ, "hud2", "Main.dc.html"), encoding="utf-8").read()
confere("o painel escondido pede o aviso próprio, e não a notificação do navegador", "API.post('/popup'" in fonte and "new Notification(" not in fonte and "requestPermission" not in fonte)

sys.exit(0 if placar() else 1)
