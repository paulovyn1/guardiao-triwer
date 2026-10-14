"""A abertura do app, no Edge sem janela. Desde a 0.9 a animação roda em toda abertura (Esc pula) e a primeira abertura do dia é a que monta e revisa o
plano; as outras vão para a execução. O que continua de antes (0.7.0): sem ninguém olhando (janela que abriu sozinha, por tarefa agendada), a animação e a
abertura do dia esperam o primeiro olhar, e o carimbo "a primeira abertura do dia já foi vista" só é gravado quando a animação termina ou é pulada."""
import os
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


def sessao():
    return requests.get(f"{URL}/sessao", timeout=5).json()


def tocando():
    return js("(() => { const g = document.querySelector('.gd'); return !!g && g.classList.contains('is-intro'); })()")


def comandos():
    return list(h.bus.comandos.queue)


def pedidos_de_abertura():
    return [c[1] for c in comandos() if c[0] == "abertura"]


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
    s = sessao()
    confere("dia novo: o servidor pede a animação e diz que é a primeira abertura do dia", s["abertura"] is True and s["primeira_do_dia"] is True, s)
    nav.abrir(f"{URL}/v2/")
    espera("document.querySelector('.gd')", 10)
    time.sleep(2.2)
    confere("janela aberta sem ninguém olhando: a animação NÃO toca", tocando() is False)
    confere("a primeira abertura do dia continua pendente (não foi gasta)", sessao()["primeira_do_dia"] is True)
    confere("e a abertura do dia (plano) também espera o primeiro olhar (nada foi pedido ao guardião)", not pedidos_de_abertura(), comandos())
    confere("a tela principal aparece normalmente enquanto espera", espera("document.querySelector('.gd') && !document.querySelector('.gd').classList.contains('is-prep')", 5))

    # ---- o primeiro olhar ----
    js("window.__focado = true; window.dispatchEvent(new Event('focus'))")
    confere("quando a pessoa olha pela primeira vez (a janela ganha foco), a animação toca", espera("document.querySelector('.gd').classList.contains('is-intro')", 5))
    time.sleep(0.5)
    confere("e a abertura do dia é pedida nesse momento, como a primeira do dia", pedidos_de_abertura() == [{"primeira": True}], comandos())
    confere("enquanto a animação roda, a primeira abertura do dia ainda não está gasta (se a janela fechar no meio, ela volta)", sessao()["primeira_do_dia"] is True)
    pular()
    confere("Esc pula a animação", espera("!document.querySelector('.gd').classList.contains('is-intro')", 5))
    time.sleep(0.6)
    confere("ao terminar, a primeira abertura do dia fica registrada como vista", sessao()["primeira_do_dia"] is False and os.path.exists(CARIMBO))
    confere("e a fala do guardião é liberada (o portão abre no fim da animação)", h.bus.portao_saudacao.is_set())

    # ---- reabrir logo depois: a animação roda de novo, mas não é mais a primeira do dia ----
    esvaziar()
    nav.abrir(f"{URL}/v2/?olhando=1")
    confere("reaberta em seguida, com foco: a animação roda de novo (toda abertura tem animação)", espera("document.querySelector('.gd') && document.querySelector('.gd').classList.contains('is-intro')", 6))
    time.sleep(0.4)
    confere("e a abertura pedida ao guardião já não é a primeira do dia (vai para a execução)", pedidos_de_abertura() == [{"primeira": False}], comandos())
    pular()
    time.sleep(1.0)

    # ---- janela aberta com a pessoa olhando, num dia novo: toca de cara; o carimbo só no fim ----
    apagar_carimbo()
    esvaziar()
    nav.abrir(f"{URL}/v2/?olhando=1")
    confere("janela aberta com a pessoa olhando: a animação toca logo", espera("document.querySelector('.gd') && document.querySelector('.gd').classList.contains('is-intro')", 6))
    time.sleep(0.4)
    confere("com a animação no meio, o carimbo ainda não foi gravado", sessao()["primeira_do_dia"] is True and not os.path.exists(CARIMBO))
    pular()
    time.sleep(1.2)
    confere("pulada com Esc, a primeira abertura do dia conta como vista", sessao()["primeira_do_dia"] is False)
    confere("com o plano aprovado, depois da abertura o painel vai direto para a execução", espera("document.querySelector('.gd').classList.contains('is-exec')", 5))

    # ---- ?abertura=1 sempre toca ----
    nav.abrir(f"{URL}/v2/?abertura=1")
    confere("?abertura=1 toca mesmo sem ninguém olhando", espera("document.querySelector('.gd') && document.querySelector('.gd').classList.contains('is-intro')", 6))
    pular()
    time.sleep(1.0)

    fonte = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hud2", "Main.dc.html"), encoding="utf-8").read()
    confere("o carimbo é gravado no fim da abertura (afterIntro), não ao carregar a página", fonte.count("API.get('/sessao?marcar=1')") == 1 and "if (this.abriu) API.get('/sessao?marcar=1')" in fonte)
    confere("as preferências não têm mais animação de abertura, saudação ao abrir nem vidro", all(x not in fonte for x in ("'Animação de abertura'", "'Saudação ao abrir'", "'Vidro com desfoque'")))
    confere("sem erros no console da página", not nav.erros, nav.erros[:3])
finally:
    nav.fechar()

placar()
