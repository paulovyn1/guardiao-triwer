# Quem manda na fala em andamento. Quando a pessoa fecha a janela no meio da resposta, o guardião para de falar:
# o som, a geração das próximas frases e o Claude que ainda escreve o resto. (Fechar a janela não desliga o programa:
# ele segue ouvindo "Ei guardião" em segundo plano. Só a fala em curso para.)
import threading
import time

import sounddevice as sd

from hud_servidor import bus

PARAR = threading.Event()    # a fala em andamento deve parar: o que falta dizer não é mais dito
FALANDO = threading.Event()  # há alguma coisa sendo falada agora
GRACA_JANELA = 2.0           # recarregar a página derruba a conexão por um instante: só vale como "fechou" se ela não voltar logo
_trava = threading.Lock()
_ativas = 0                  # falas aninhadas (uma pergunta de permissão no meio de uma resposta, por exemplo)
_processos = set()           # Claude do modo rápido em andamento


def comecar():
    global _ativas
    with _trava:
        if _ativas == 0:
            PARAR.clear()
        _ativas += 1
        FALANDO.set()


def terminar():
    global _ativas
    with _trava:
        _ativas = max(0, _ativas - 1)
        if _ativas == 0:
            FALANDO.clear()


def registrar_processo(proc):
    with _trava:
        _processos.add(proc)


def esquecer_processo(proc):
    with _trava:
        _processos.discard(proc)


def parar(motivo=""):
    """Para tudo que está sendo dito agora. A conversa continua: a próxima fala da pessoa começa do zero."""
    PARAR.set()
    try:
        sd.stop()
    except Exception:
        pass
    try:  # a sessão do Claude Code para de escrever e o que ainda chegar desse turno é descartado
        import guardiao_sessao
        guardiao_sessao.interromper()
    except Exception:
        pass
    with _trava:
        procs = list(_processos)
    for p in procs:
        try:
            p.terminate()
        except OSError:
            pass
    try:
        import latencia
        latencia.marca("parada", motivo=motivo)
    except Exception:
        pass
    bus.emitir("estado", v="aguardando")


def _janela_fechou():
    """A última janela do painel fechou. Se o guardião está falando, para (a pessoa fechou porque quer silêncio)."""
    def espera():
        time.sleep(GRACA_JANELA)
        if FALANDO.is_set() and not bus.assinantes:
            parar("a janela do painel foi fechada")
    threading.Thread(target=espera, daemon=True).start()


bus.ao_ficar_sem_janela = _janela_fechou
