# Toca a mesma frase nas três vozes do guardião, uma depois da outra, para a pessoa escolher.
# A escolhida vai no campo agente.voz do config.json (pm_santa, pm_alex ou pf_dora).
import os
import sys

import sounddevice as sd

import nativo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
FRASE = "Bom dia. O seu próximo bloco começa às nove horas. Quer revisar o plano de hoje comigo?"
VOZES = [("1", "pm_santa", "voz masculina, mais grave"), ("2", "pm_alex", "voz masculina, mais leve"), ("3", "pf_dora", "voz feminina")]

so = [v for v in VOZES if v[0] in sys.argv[1:] or v[1] in sys.argv[1:]] or VOZES
k = nativo.carregar_voz(BASE)
for numero, voz, descricao in so:
    print(f"{numero}) {voz}: {descricao}")
    amostras, taxa = k.create(FRASE, voice=voz, speed=1.0, lang="pt-br")
    sd.play(amostras, taxa)
    sd.wait()
print("Pronto. Diga ao Claude o número da voz que você preferiu.")
