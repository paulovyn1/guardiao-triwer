# Confere a instalação de verdade, sem microfone e sem tocar som: carrega o modelo de escuta, faz a voz gerar uma frase
# e olha se o painel está na pasta. Usado no fim do instalador. Sai com 0 se tudo funcionou.
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import nativo  # noqa: E402

falhas = 0


def passo(nome, funcao):
    global falhas
    inicio = time.time()
    try:
        detalhe = funcao() or ""
        print(f"OK    {nome}{' (' + detalhe + ')' if detalhe else ''}, {time.time() - inicio:.1f} s")
    except Exception as erro:
        falhas += 1
        print(f"FALHA {nome}: {erro}")


def bibliotecas():
    import edge_tts  # noqa: F401
    import numpy  # noqa: F401
    import onnxruntime  # noqa: F401
    import requests  # noqa: F401
    import sounddevice  # noqa: F401


def escuta():
    from vosk import KaldiRecognizer, SetLogLevel

    SetLogLevel(-1)
    rec = KaldiRecognizer(nativo.carregar_escuta(BASE), 16000, '["ei guardião", "[unk]"]')
    rec.AcceptWaveform(b"\x00" * 3200)


def voz():
    k = nativo.carregar_voz(BASE)
    amostras, taxa = k.create("Tudo certo por aqui.", voice="pm_santa", speed=1.0, lang="pt-br")
    if len(amostras) < taxa // 2:
        raise RuntimeError("a voz gerou um áudio curto demais")
    return f"{len(amostras) / taxa:.1f} s de fala"


def programa():
    # importar o programa inteiro pega biblioteca que falte: foi assim que uma instalação nova já ficou sem ligar
    import fala  # noqa: F401
    import guardiao_atualizacao  # noqa: F401
    import guardiao_janela  # noqa: F401
    import guardiao_sessao  # noqa: F401
    import guardiao_v2  # noqa: F401
    import guardiao_voz  # noqa: F401
    import hud_servidor  # noqa: F401


def painel():
    for arquivo in ("index.html", "Main.dc.html", "Orb3D.dc.html", "support.js"):
        if not os.path.isfile(os.path.join(BASE, "hud2", arquivo)):
            raise RuntimeError(f"falta hud2\\{arquivo}")


def microfone():
    import sounddevice as sd

    entradas = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    if not entradas:
        return "nenhum microfone encontrado: o painel funciona por texto"
    return f"{len(entradas)} entrada(s) de áudio"


passo("bibliotecas do Python", bibliotecas)
passo("modelo de escuta", escuta)
passo("voz do guardião", voz)
passo("programa do guardião", programa)
passo("arquivos do painel", painel)
passo("microfone", microfone)
sys.exit(1 if falhas else 0)
