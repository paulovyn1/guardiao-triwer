"""O registro do programa em segundo plano (logs\\voz.log), com data, hora e número do processo em cada linha.

Sem a hora não dava para saber quando algo aconteceu, e sem o número do processo não dava para ver que dois guardiões escreviam no mesmo
arquivo (caso de 15/10/2026, que só apareceu olhando os processos). O arquivo passa para voz.log.1 quando cresce, em vez de ser apagado:
o registro do problema de ontem continua lá."""
import os
import time

LIMITE = 2_000_000


class ComHora:
    """Arquivo de texto que põe 'AAAA-MM-DD HH:MM:SS [pid] ' no começo de cada linha. Aceita print com end='' e com '\\r'."""

    def __init__(self, arquivo):
        self.arquivo = arquivo
        self.inicio_de_linha = True
        self.pid = os.getpid()

    def write(self, texto):
        if not texto:
            return 0
        saida = []
        for pedaco in texto.splitlines(keepends=True):
            if self.inicio_de_linha:
                saida.append(time.strftime("%Y-%m-%d %H:%M:%S") + f" [{self.pid}] ")
            saida.append(pedaco)
            self.inicio_de_linha = pedaco.endswith("\n")
        self.arquivo.write("".join(saida))
        return len(texto)

    def flush(self):
        self.arquivo.flush()

    def reconfigure(self, **_):
        pass  # o arquivo já nasce em UTF-8, com erros substituídos

    def isatty(self):
        return False

    def __getattr__(self, nome):
        return getattr(self.arquivo, nome)


def abrir(pasta_logs, nome="voz.log"):
    """Abre o registro para acrescentar (girando para .1 quando passa do limite) e devolve o arquivo com hora."""
    os.makedirs(pasta_logs, exist_ok=True)
    caminho = os.path.join(pasta_logs, nome)
    try:
        if os.path.getsize(caminho) > LIMITE:
            os.replace(caminho, caminho + ".1")
    except OSError:
        pass  # não existe ainda, ou outro processo está com ele aberto: segue acrescentando
    return ComHora(open(caminho, "a", encoding="utf-8", errors="replace", buffering=1))
