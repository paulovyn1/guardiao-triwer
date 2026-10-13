"""Capturas da abertura, da janela compacta e do celular (painel novo)."""
import queue
import time

import v2_base as B
from v2_base import h

B.preparar(8778, hora="09:50")
nav = B.Navegador("http://localhost:8778/v2/?abertura=1", porta_cdp=9344)
try:
    for seg, nome in ((2.2, "abertura_1"), (2.3, "abertura_2"), (2.0, "abertura_3"), (1.6, "abertura_4"), (2.6, "abertura_5")):
        time.sleep(seg)
        print(nome, nav.foto(nome), nav.js("document.querySelector('.gd') && document.querySelector('.gd').className"))
    cmds = []
    while True:
        try:
            cmds.append(h.bus.comandos.get_nowait())
        except queue.Empty:
            break
    print("comandos:", cmds, "| portão da saudação liberado:", h.bus.portao_saudacao.is_set())
    print("sessão marcada (não repete):", B.v2.sessao()["abertura"] is False)
    for pagina, w, hh, nome in (("mini.html", 336, 440, "mini"), ("celular.html", 390, 844, "celular")):
        nav.cdp("Emulation.setDeviceMetricsOverride", {"width": w, "height": hh, "deviceScaleFactor": 2, "mobile": False})
        nav.abrir(f"http://localhost:8778/v2/{pagina}?semabertura=1")
        time.sleep(4.5)
        print(nome, nav.foto(nome), (nav.js("document.body.innerText") or "")[:160].replace("\n", " | "))
    print("erros:", nav.erros[:5])
finally:
    nav.fechar()
