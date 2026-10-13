"""Sonda rápida: o runtime do design roda servido de /v2/ ? (abre uma página, espera e fotografa)"""
import sys
import time

import v2_base as B

pagina = sys.argv[1] if len(sys.argv) > 1 else "_prototipo.dc.html"
espera = float(sys.argv[2]) if len(sys.argv) > 2 else 11
nome = sys.argv[3] if len(sys.argv) > 3 else "sonda"
B.preparar(8769)
nav = B.Navegador(f"http://localhost:8769/v2/{pagina}")
try:
    time.sleep(espera)
    print("titulo:", nav.js("document.title"))
    print("raiz .gd:", nav.js("!!document.querySelector('.gd')"), "| canvases:", nav.js("document.querySelectorAll('canvas').length"))
    print("texto:", (nav.js("document.body.innerText") or "")[:400].replace("\n", " | "))
    print("foto:", nav.foto(nome))
    print("erros:", nav.erros[:8])
finally:
    nav.fechar()
