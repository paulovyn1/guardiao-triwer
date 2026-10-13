"""A abertura animada só é gasta quando a pessoa a vê (0.7.0), no Edge sem janela. Antes, o carimbo "a abertura do dia já foi vista" era gravado ao carregar
a página: a janela que abria sozinha (tarefa agendada) ou durante a instalação consumia a animação, e a pessoa nunca a via. Agora: sem ninguém olhando, a abertura
e a saudação esperam o primeiro olhar; o carimbo só é gravado quando a animação termina (ou é pulada por clique); e "?abertura=1" sempre toca."""
import json
import os
import sys
import time

import requests

import v2_base as B
from v2_base import confere, h, placar

PORTA = 8797
tmp, relogio = B.preparar(PORTA, hora="09:50")
URL = f"http://localhost:{PORTA}"
CARIMBO = os.path.join(tmp, "logs", "abertura.json")

nav = B.Navegador(f"{URL}/v2/?semabertura=1", porta_cdp=9350)
js, espera = nav.js, nav.espera
# o Edge sem janela não diz de verdade se a janela está em foco: aqui o foco é do teste (?olhando=1 abre com foco; window.__focado = true dá o primeiro olhar depois)
nav.cdp("Page.addScriptToEvaluateOnNewDocument", {"source": "window.__focado = /[?&]olhando=1/.test(location.search); Document.prototype.hasFocus = function () { return window.__focado === true; };"})


def abertura_do_servidor():
    return requests.get(f"{URL}/sessao", timeout=5).json()["abertura"]


def tocando():
    return js("(() => { const g = document.querySelector('.gd'); return !!g && g.classList.contains('is-intro'); })()")


def comandos():
    return [c[0] for c in list(h.bus.comandos.queue)]


def esvaziar():
    while not h.bus.comandos.empty():
        h.bus.comandos.get_nowait()


def apagar_carimbo():
    if os.path.exists(CARIMBO):
        os.remove(CARIMBO)


def pular():
    js("document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")


try:
    # ---- janela que abre sozinha, ninguém olhando ----
    apagar_carimbo()
    esvaziar()
    confere("instalação nova: o servidor diz que a abertura está pendente", abertura_do_servidor() is True)
    nav.abrir(f"{URL}/v2/")
    espera("document.querySelector('.gd')", 10)
    time.sleep(2.2)
    confere("janela aberta sem ninguém olhando: a animação NÃO toca", tocando() is False)
    confere("a abertura do dia continua pendente (não foi gasta)", abertura_do_servidor() is True)
    confere("e a saudação também espera o primeiro olhar (nada foi pedido ao guardião)", "saudacao" not in comandos(), comandos())
    confere("a tela principal aparece normalmente enquanto espera", espera("document.querySelector('.gd') && !document.querySelector('.gd').classList.contains('is-prep')", 5))

    # ---- o primeiro olhar ----
    js("window.__focado = true; window.dispatchEvent(new Event('focus'))")
    confere("quando a pessoa olha pela primeira vez (a janela ganha foco), a abertura toca", espera("document.querySelector('.gd').classList.contains('is-intro')", 5))
    time.sleep(0.5)
    confere("e a saudação é pedida nesse momento", "saudacao" in comandos(), comandos())
    confere("enquanto a animação roda, a abertura do dia ainda não está gasta (se a janela fechar no meio, toca de novo)", abertura_do_servidor() is True)
    pular()
    confere("clicar ou apertar Esc pula a animação", espera("!document.querySelector('.gd').classList.contains('is-intro')", 5))
    time.sleep(0.6)
    confere("ao terminar, a abertura do dia fica registrada como vista", abertura_do_servidor() is False and os.path.exists(CARIMBO))

    # ---- reabrir logo depois: não repete ----
    esvaziar()
    nav.abrir(f"{URL}/v2/?olhando=1")
    espera("document.querySelector('.gd')", 10)
    time.sleep(1.5)
    confere("reaberta em seguida (já vista), mesmo com foco, a animação não toca de novo", tocando() is False)

    # ---- janela aberta com a pessoa olhando: toca de cara; o carimbo só no fim ----
    apagar_carimbo()
    esvaziar()
    nav.abrir(f"{URL}/v2/?olhando=1")
    confere("janela aberta com a pessoa olhando: a abertura toca logo", espera("document.querySelector('.gd') && document.querySelector('.gd').classList.contains('is-intro')", 6))
    time.sleep(0.4)
    confere("com a animação no meio, o carimbo ainda não foi gravado", abertura_do_servidor() is True and not os.path.exists(CARIMBO))
    pular()
    time.sleep(1.2)
    confere("pulada por clique, a abertura conta como vista", abertura_do_servidor() is False)

    # ---- ?abertura=1 sempre toca, e é o que o botão "Rever a abertura" usa ----
    nav.abrir(f"{URL}/v2/?abertura=1")
    confere("?abertura=1 toca mesmo com a abertura do dia já vista e sem ninguém olhando", espera("document.querySelector('.gd') && document.querySelector('.gd').classList.contains('is-intro')", 6))
    pular()
    time.sleep(1.0)

    # ---- o botão no painel de Preferências ----
    fonte = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hud2", "Main.dc.html"), encoding="utf-8").read()
    confere("Preferências, Comportamento: botão 'Rever a abertura' que recarrega o painel pedindo a abertura completa", "Rever a abertura" in fonte and "verAbertura()" in fonte and "location.search = '?abertura=1'" in fonte)
    confere("o carimbo é gravado no fim da abertura (afterIntro), não ao carregar a página", fonte.count("API.get('/sessao?marcar=1')") == 1 and "if (this.abriu) API.get('/sessao?marcar=1')" in fonte)
    confere("sem erros no console da página", not nav.erros, nav.erros[:3])
finally:
    nav.fechar()

placar()
