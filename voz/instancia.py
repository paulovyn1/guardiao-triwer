"""Um guardião só por pessoa no computador.

Caso real de 15/10/2026: no logon, a tarefa agendada "voz" e a tarefa "tela" ligaram o programa ao mesmo tempo. Os dois carregaram tudo,
os dois abriram o microfone, e o painel passou a falar com um enquanto o Esc e o texto digitado iam para o outro (a escuta ficou presa).
A trava é um mutex do Windows com nome: o primeiro processo fica com ela até fechar (o Windows solta sozinho se ele morrer), e quem chegar
depois sabe na hora que já existe um guardião, antes de carregar qualquer coisa. O abrir_guardiao_v2.ps1 olha a mesma trava para esperar
o guardião que está ligando, em vez de ligar outro.
A trava é por porta do painel (um guardião por painel): um guardião de teste, ou de outra instalação, que usa outra porta não é barrado
pelo guardião de verdade, e dois na mesma porta nunca ligam juntos."""
import ctypes
import sys

PREFIXO = "Local\\GuardiaoTriwerVoz-"


def nome_da_trava(porta):
    """O nome da trava do guardião que serve o painel nesta porta (o abrir_guardiao_v2.ps1 monta o mesmo nome)."""
    return f"{PREFIXO}{int(porta)}"


NOME = nome_da_trava(8767)
_JA_EXISTE = 183  # ERROR_ALREADY_EXISTS
_SINCRONIZAR = 0x00100000  # SYNCHRONIZE: basta para saber se a trava existe
_trava = None


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = ctypes.c_void_p
    k.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    k.OpenMutexW.restype = ctypes.c_void_p
    k.OpenMutexW.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
    k.CloseHandle.argtypes = (ctypes.c_void_p,)
    return k


def tomar(nome=NOME):
    """Tenta ser o guardião deste usuário. True: este processo é o único (e fica com a trava até fechar). False: já existe outro.
    Fora do Windows, ou se o Windows recusar a trava (raro), devolve True: a porta exclusiva do painel ainda impede dois painéis."""
    global _trava
    if sys.platform != "win32":
        return True
    k = _kernel32()
    trava = k.CreateMutexW(None, False, nome)
    if not trava:
        return True
    if ctypes.get_last_error() == _JA_EXISTE:
        k.CloseHandle(trava)
        return False
    _trava = trava
    return True


def existe(nome=NOME):
    """Algum processo está com a trava (um guardião ligado ou ligando)?"""
    if sys.platform != "win32":
        return False
    k = _kernel32()
    trava = k.OpenMutexW(_SINCRONIZAR, False, nome)
    if trava:
        k.CloseHandle(trava)
        return True
    return False


def soltar():
    """Solta a trava (os testes usam; o programa de verdade só solta ao fechar)."""
    global _trava
    if _trava:
        _kernel32().CloseHandle(_trava)
        _trava = None
