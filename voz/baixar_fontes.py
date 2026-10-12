# Baixa as fontes da tela do guardião para a pasta hud\fontes, para ela funcionar sem internet.
import os
import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(BASE, "hud", "fontes")
os.makedirs(PASTA, exist_ok=True)

URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500"
    "&family=JetBrains+Mono:wght@400;500"
    "&family=Instrument+Sans:wght@400;500;600&display=swap"
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
css = requests.get(URL, headers={"User-Agent": UA}, timeout=30).text

saida = []
vistos = {}
for m in re.finditer(r"/\* (\S+) \*/\s*(@font-face \{.*?\})", css, re.S):
    subconjunto, bloco = m.group(1), m.group(2)
    if subconjunto != "latin":
        continue
    familia = re.search(r"font-family: '([^']+)'", bloco).group(1)
    estilo = re.search(r"font-style: (\w+)", bloco).group(1)
    peso = re.search(r"font-weight: (\d+)", bloco).group(1)
    url = re.search(r"url\((https://[^)]+)\)", bloco).group(1)
    nome = f"{familia.replace(' ', '')}-{estilo}-{peso}.woff2"
    if url not in vistos:
        dados = requests.get(url, headers={"User-Agent": UA}, timeout=60).content
        with open(os.path.join(PASTA, nome), "wb") as f:
            f.write(dados)
        vistos[url] = nome
        print("baixou", nome, len(dados) // 1024, "KB")
    saida.append(bloco.replace(url, "fontes/" + vistos[url]))

with open(os.path.join(BASE, "hud", "fontes.css"), "w", encoding="utf-8") as f:
    f.write("\n".join(saida) + "\n")
print("fontes.css com", len(saida), "faces")
