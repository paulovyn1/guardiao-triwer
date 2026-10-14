# Quem manda na fala em andamento. Quando a pessoa fecha a janela no meio da resposta, o guardião para de falar:
# o som, a geração das próximas frases e o Claude que ainda escreve o resto. (Fechar a janela não desliga o programa:
# ele segue ouvindo "Ei guardião" em segundo plano. Só a fala em curso para.)
#
# Esc em camadas (pedido de 14/10/2026), uma camada por toque, da mais de fora para a mais de dentro:
#   1. lendo o plano da abertura: pula a leitura e vai direto ao pedido de ok;
#   2. falando: corta a voz, o resto da resposta aparece em texto e a voz fica desligada até a pessoa religar;
#   3. pensando ou escrevendo a resposta: cancela o resto da resposta (e o Claude, inclusive os subagentes da sessão);
#   4. nada em primeiro plano: cancela o trabalho em segundo plano (o guardião completo montando um plano).
import threading
import time

try:
    import sounddevice as sd
except Exception:  # testes sem placa de som
    sd = None

from hud_servidor import bus

PARAR = threading.Event()          # a fala em andamento deve parar: o que falta dizer não é mais dito
FALANDO = threading.Event()        # há alguma coisa sendo falada agora
SO_TEXTO = threading.Event()       # Esc com a voz tocando: o resto da resposta vai em texto
LEITURA = threading.Event()        # o guardião está lendo o plano da abertura, tarefa a tarefa
PULAR_LEITURA = threading.Event()  # Esc durante essa leitura
GRACA_JANELA = 2.0                 # recarregar a página derruba a conexão por um instante: só vale como "fechou" se ela não voltar logo
TOCANDO = None                     # o Tocador com a voz tocando agora (tocador.py), ou None
_trava = threading.Lock()
_ativas = 0                        # falas aninhadas (uma pergunta de permissão no meio de uma resposta, por exemplo)
_processos = set()                 # Claude do modo rápido em andamento
_fundo = set()                     # trabalho em segundo plano (o guardião completo)
FUNDO_CANCELADO = threading.Event()


def comecar():
    global _ativas
    with _trava:
        if _ativas == 0:
            PARAR.clear()
            SO_TEXTO.clear()
        _ativas += 1
        FALANDO.set()


def terminar():
    global _ativas
    with _trava:
        _ativas = max(0, _ativas - 1)
        if _ativas == 0:
            FALANDO.clear()


def tocando(t):
    """O programa de voz avisa qual Tocador está com o som agora (None quando acaba)."""
    global TOCANDO
    TOCANDO = t


def registrar_processo(proc):
    with _trava:
        _processos.add(proc)


def esquecer_processo(proc):
    with _trava:
        _processos.discard(proc)


def registrar_fundo(proc):
    with _trava:
        _fundo.add(proc)


def esquecer_fundo(proc):
    with _trava:
        _fundo.discard(proc)


def _parar_som():
    t = TOCANDO
    if t is not None:
        t.parar()
    try:
        if sd is not None:
            sd.stop()
    except Exception:
        pass


def parar(motivo=""):
    """Para tudo que está sendo dito agora. A conversa continua: a próxima fala da pessoa começa do zero."""
    PARAR.set()
    _parar_som()
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


def cancelar_fundo():
    """Para o trabalho em segundo plano. Devolve True se havia algo rodando."""
    with _trava:
        procs = list(_fundo)
    if not procs:
        return False
    FUNDO_CANCELADO.set()
    for p in procs:
        try:
            p.terminate()
        except OSError:
            pass
    return True


def esc():
    """Um toque no Esc do painel. Tira uma camada por vez e devolve qual foi: 'leitura', 'voz', 'resposta', 'segundo_plano' ou 'nada'."""
    if LEITURA.is_set() and not PULAR_LEITURA.is_set():
        PULAR_LEITURA.set()
        _parar_som()
        return "leitura"
    if FALANDO.is_set() and TOCANDO is not None and not SO_TEXTO.is_set() and not PARAR.is_set():
        SO_TEXTO.set()
        _parar_som()
        try:  # daqui em diante ele escreve: a voz fica desligada até a pessoa religar
            import hud_servidor
            hud_servidor.salvar_preferencias({"voz_guardiao": False})
        except Exception:
            pass
        return "voz"
    if FALANDO.is_set() and not PARAR.is_set():
        parar("esc")
        return "resposta"
    if cancelar_fundo():
        return "segundo_plano"
    return "nada"


def _janela_fechou():
    """A última janela do painel fechou. Se o guardião está falando, para (a pessoa fechou porque quer silêncio)."""
    def espera():
        time.sleep(GRACA_JANELA)
        if FALANDO.is_set() and not bus.assinantes:
            parar("a janela do painel foi fechada")
    threading.Thread(target=espera, daemon=True).start()


bus.ao_ficar_sem_janela = _janela_fechou
