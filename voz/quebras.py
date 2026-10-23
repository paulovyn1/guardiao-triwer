# Quebras de linha da resposta do Claude no caminho até a tela. O texto passa por muitas etapas que juntam tudo numa linha só (corte em frases, voz,
# acúmulo do que já foi dito), e com isso a lista e o parágrafo da resposta se perdiam: o painel mostrava "- **a** - **b**" tudo emendado.
# Aqui a quebra vira um caractere especial (que não é espaço, então ninguém o come) e volta a ser "\n" só na hora de ir para a tela e para a memória.
# O recuo da linha (para sublistas) vira um caractere por nível. A voz ignora todos.
import re

QUEBRA = ""      # uma quebra de linha
PARAGRAFO = ""   # uma linha em branco
RECUO = ""       # um nível de recuo (2 espaços) no começo da linha
MAX_RECUO = 4


def _recuo(espacos):
    return RECUO * min(MAX_RECUO, len(str(espacos).expandtabs(4)) // 2)


def marca_de(espacos):
    """A marca que corresponde a um trecho de espaços e quebras: duas quebras ou mais é parágrafo, uma é quebra, nenhuma é nada. Leva junto o recuo da última linha."""
    espacos = str(espacos)
    n = espacos.count("\n")
    if not n:
        return ""
    return (PARAGRAFO if n >= 2 else QUEBRA) + _recuo(espacos.rsplit("\n", 1)[-1])


def marcar(texto):
    """Troca as quebras de linha do texto pelas marcas e junta os espaços que sobram."""
    t = re.sub(r"[ \t\r]*\n(?:[ \t\r]*\n)+([ \t]*)", lambda m: PARAGRAFO + _recuo(m.group(1)), str(texto))
    t = re.sub(r"[ \t\r]*\n([ \t]*)", lambda m: QUEBRA + _recuo(m.group(1)), t)
    return re.sub(r"[ \t]+", " ", t)


def para_tela(texto):
    """As marcas voltam a ser quebras de linha, com o recuo (para a tela, a memória e o que o guardião lembra)."""
    t = re.sub(RECUO + "+", lambda m: "  " * len(m.group(0)), str(texto))
    t = t.replace(PARAGRAFO, "\n\n").replace(QUEBRA, "\n")
    return re.sub(r" +\n", "\n", t).strip()


def sem_marcas(texto):
    """Para a voz: as marcas viram espaço."""
    return re.sub(r"[-]", " ", str(texto))
