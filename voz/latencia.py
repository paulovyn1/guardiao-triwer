# Os tempos de cada resposta do guardião, do pedido até a última frase falada, em logs\latencia.jsonl (uma linha por resposta).
# Serve para achar onde o tempo vai quando "demora": o Claude, a geração da voz ou o computador ocupado. Nada aqui muda o comportamento.
import ctypes
import json
import os
import threading
import time

import hud_servidor as h

LIMITE_ARQUIVO = 1_000_000  # passou disso, o arquivo é cortado ao meio (fica o fim, que é o que importa)
_trava = threading.Lock()
ATUAL = None  # o medidor da resposta em andamento


class _FT(ctypes.Structure):
    _fields_ = [("baixo", ctypes.c_uint32), ("alto", ctypes.c_uint32)]


def _tempos_cpu():
    """(tempo ocioso, tempo total) de todos os núcleos desde que o Windows ligou; a diferença entre duas leituras dá o uso do computador."""
    try:
        ocioso, nucleo, usuario = _FT(), _FT(), _FT()
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(ocioso), ctypes.byref(nucleo), ctypes.byref(usuario))
        v = lambda f: (f.alto << 32) | f.baixo  # noqa: E731
        return v(ocioso), v(nucleo) + v(usuario)  # o tempo do núcleo já inclui o ocioso
    except Exception:
        return 0, 0


class Medidor:
    def __init__(self, modo, motivo=""):
        self.t0 = time.time()
        self.modo = modo
        self.motivo = motivo
        self.passos = []
        self.cpu0 = _tempos_cpu()

    def marca(self, nome, **dados):
        passo = [round(time.time() - self.t0, 2), nome]
        if dados:
            passo.append(dados)
        self.passos.append(passo)

    def fechar(self, **extra):
        global ATUAL
        ocioso1, total1 = _tempos_cpu()
        dt = total1 - self.cpu0[1]
        cpu = round(100 * (1 - (ocioso1 - self.cpu0[0]) / dt)) if dt > 0 else None
        linha = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "modo": self.modo, "motivo": self.motivo, "total": round(time.time() - self.t0, 2),
                 "cpu_pct": cpu, **extra, "passos": self.passos}
        if ATUAL is self:
            ATUAL = None
        _gravar(linha)


def _arquivo():
    return os.path.join(h.OPER, "logs", "latencia.jsonl")


def _gravar(linha):
    try:
        with _trava:
            caminho = _arquivo()
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            if os.path.exists(caminho) and os.path.getsize(caminho) > LIMITE_ARQUIVO:
                with open(caminho, "rb") as f:
                    f.seek(-LIMITE_ARQUIVO // 2, os.SEEK_END)
                    f.readline()  # descarta a linha cortada
                    resto = f.read()
                with open(caminho, "wb") as f:
                    f.write(resto)
            with open(caminho, "a", encoding="utf-8") as f:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except Exception:
        pass


def iniciar(modo, motivo=""):
    """Começa a medir uma resposta. As funções de leitura do Claude e de voz marcam os passos pelo marca() do módulo."""
    global ATUAL
    ATUAL = Medidor(modo, motivo)
    return ATUAL


def marca(nome, **dados):
    m = ATUAL
    if m:
        m.marca(nome, **dados)


def ler(n=200):
    """As últimas respostas medidas (para o diagnóstico)."""
    try:
        with open(_arquivo(), encoding="utf-8") as f:
            linhas = f.readlines()[-n:]
    except OSError:
        return []
    saida = []
    for linha in linhas:
        try:
            saida.append(json.loads(linha))
        except ValueError:
            pass
    return saida
