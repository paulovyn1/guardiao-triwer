# Gera, na pasta amostras, a mesma frase em várias vozes masculinas (e a feminina do Kokoro) para você comparar.
# Edge: grátis, precisa de internet. Kokoro: roda no seu PC, sem internet.
import asyncio
import os
import sys
import time
import wave

import numpy as np

import guardiao_voz as g

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FRASE = "Seu próximo bloco é revisar a skill do guardião, às quinze horas. Comece abrindo a tela e lendo o plano de hoje."
PASTA = os.path.join(g.BASE, "amostras")
os.makedirs(PASTA, exist_ok=True)

print("== Edge (neural, online) ==")
edge = [
    "pt-BR-AntonioNeural",
    "pt-PT-DuarteNeural",
    "en-US-AndrewMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "fr-FR-RemyMultilingualNeural",
    "de-DE-FlorianMultilingualNeural",
    "it-IT-GiuseppeMultilingualNeural",
]
for voz in edge:
    caminho = os.path.join(PASTA, "edge_" + voz + ".mp3")
    try:
        asyncio.run(g._salvar_edge(FRASE, voz, caminho))
        print("ok ", os.path.basename(caminho))
    except Exception as erro:
        print("falhou", voz, erro)

print("== Kokoro (local, offline) ==")
from kokoro_onnx import Kokoro  # noqa: E402

kok = Kokoro(os.path.join(g.BASE, "kokoro", "kokoro-v1.0.int8.onnx"), os.path.join(g.BASE, "kokoro", "voices-v1.0.bin"))
for voz in ("pm_alex", "pm_santa", "pf_dora"):
    t0 = time.time()
    amostras, taxa = kok.create(FRASE, voice=voz, speed=1.0, lang="pt-br")
    seg = time.time() - t0
    pcm = (np.clip(amostras, -1.0, 1.0) * 32767).astype(np.int16)
    caminho = os.path.join(PASTA, "kokoro_" + voz + ".wav")
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm.tobytes())
    dur = len(pcm) / taxa
    print(f"ok  kokoro_{voz}.wav  (gerou em {seg:.1f}s para {dur:.1f}s de fala)")
