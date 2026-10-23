"""Texto na tela (Edge sem janela): a resposta do Guardião com formatação (negrito, itálico, lista, número, título, código, citação, tabela, link) sem nunca virar HTML de
verdade, a mensagem da pessoa com várias linhas, e a caixa de escrever que cresce para cima até 10 linhas e depois rola por dentro (Enter envia, Shift+Enter quebra a linha).
Capturas em capturas\\v2_texto_*.png."""
import json
import queue
import time

import v2_base as B
from v2_base import confere, h

PORTA = 8801
tmp, relogio = B.preparar(PORTA, hora="09:50", prefs={"execucao_ao_abrir": False})
nav = B.Navegador(f"http://localhost:{PORTA}/v2/?semabertura=1", porta_cdp=9352)
js, espera = nav.js, nav.espera


def comandos():
    saida = []
    while True:
        try:
            saida.append(h.bus.comandos.get_nowait())
        except queue.Empty:
            return saida


def pausa(seg):
    time.sleep(seg)
    return True


def escrever(texto, enter=False, shift=False):
    return js("""(() => { const e = [...document.querySelectorAll('[data-tour="campo"]')].find((x) => !x.closest('[aria-hidden="true"]') && x.getBoundingClientRect().width > 0); if (!e) return false;
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(e, %s); e.dispatchEvent(new Event('input', { bubbles: true }));
      if (%s) e.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: %s, bubbles: true, cancelable: true })); return true; })()""" % (json.dumps(texto), "true" if enter else "false", "true" if shift else "false"))


def campo():
    return json.loads(js("""(() => { const e = [...document.querySelectorAll('[data-tour="campo"]')].find((x) => !x.closest('[aria-hidden="true"]') && x.getBoundingClientRect().width > 0);
      if (!e) return JSON.stringify({}); const r = e.getBoundingClientRect(), c = e.closest('.cmd').getBoundingClientRect(), cs = getComputedStyle(e);
      return JSON.stringify({ tag: e.tagName, h: Math.round(r.height), topo: Math.round(r.top), base: Math.round(r.bottom), cmdBase: Math.round(c.bottom), rola: cs.overflowY, valor: e.value, linhas: Math.round(e.scrollHeight / parseFloat(cs.lineHeight)) }); })()""") or "{}")


def md_visivel():
    return js("""(() => { const e = [...document.querySelectorAll('.m-g .md')].pop(); return e ? e.innerHTML : null; })()""") or ""


try:
    confere("o painel abre", espera("document.querySelector('.gd .hd')", 20))
    pausa(1.5)

    # ---------- a resposta com formatação ----------
    RESPOSTA = ("Esta é a proposta de hoje:\n- **11h às 12h30:** revisar os vídeos do *Carlos*.\n- **15h às 17h:** as seis tarefas com prazo de hoje.\n  - o bug da Central\n  - os fluxos do `ManyChat`\n\n"
                "1. Primeiro passo\n2. Segundo passo\n\n## Atenção\n> Confira o prazo antes de aprovar.\n\n| Dia | Horas |\n|---|---|\n| Sábado | 3 |\n| Domingo | 3 |\n\n"
                "Veja [o portal](https://exemplo.com/portal?a=1&b=2) e https://exemplo.com/outro. Posso rodar a conferência?")
    h.bus.emitir("guardiao_texto", texto=RESPOSTA)
    h.bus.emitir("guardiao_fim", texto=RESPOSTA)
    confere("a resposta chega com a formatação desenhada", espera("document.querySelector('.m-g .md strong')", 6), md_visivel()[:300])
    pausa(1.0)
    html = md_visivel()
    confere("negrito e itálico de verdade, sem os asteriscos à mostra", "<strong>11h às 12h30:</strong>" in html and "<em>Carlos</em>" in html and "**" not in html, html[:300])
    confere("a lista vira lista (com sublista), e o número vira lista numerada", "<ul><li><strong>11h" in html and "<ul><li>o bug da Central</li>" in html and "<ol><li>Primeiro passo</li><li>Segundo passo</li></ol>" in html, html[:500])
    confere("título, citação, código e tabela", '<p class="mdh">Atenção</p>' in html and "<blockquote>Confira o prazo antes de aprovar.</blockquote>" in html and "<code>ManyChat</code>" in html
            and "<th>Dia</th>" in html and "<td>Sábado</td>" in html, html[-500:])
    confere("link com texto e endereço solto viram links que abrem em outra aba, sem acesso à janela de origem",
            'href="https://exemplo.com/portal?a=1&amp;b=2" target="_blank" rel="noopener noreferrer">o portal</a>' in html and '>https://exemplo.com/outro</a>' in html, html[-400:])
    confere("a conversa não mostra o caractere da marca de quebra nem asteriscos soltos", "" not in (js("document.querySelector('.gd').textContent") or "") and "**" not in (js("document.querySelector('.gd .gc-log').innerText") or ""))
    confere("terminada a resposta, o cursor piscando some", js("!document.querySelector('.m-g .md .caret')"))
    confere("a legenda da Home (o texto no centro da tela) também desenha a formatação", js("!!document.querySelector('.gl-g .md strong') && !document.querySelector('.gl-g .md').textContent.includes('**')"))
    nav.foto("texto_formatado")

    # ---------- nada vira HTML de verdade ----------
    MAU = "<img src=x onerror=\"window.__xss=1\"> <script>window.__xss=2</script> **ok** [clique](javascript:window.__xss=3) <b>negrito html</b>"
    h.bus.emitir("guardiao_texto", texto=MAU)
    h.bus.emitir("guardiao_fim", texto=MAU)
    espera("[...document.querySelectorAll('.m-g .md')].some((e) => e.innerHTML.includes('&lt;img'))", 6)
    pausa(0.6)
    confere("HTML escrito na resposta aparece como texto e não executa nada", js("window.__xss === undefined") and js("!document.querySelector('.m-g .md img, .m-g .md script, .m-g .md b')"), js("window.__xss"))
    confere("link com javascript: não vira link", js("![...document.querySelectorAll('.m-g .md a')].some((a) => (a.getAttribute('href') || '').startsWith('javascript'))"))

    # ---------- resposta chegando aos poucos: o cursor acompanha o texto ----------
    h.bus.emitir("guardiao_texto", texto="Vou listar:\n- primeiro **item")
    confere("durante a resposta o cursor fica no fim do último item", espera("document.querySelector('.m-g .md li .caret')", 5) or espera("document.querySelector('.m-g .md .caret')", 3), md_visivel()[-200:])
    h.bus.emitir("guardiao_fim", texto="Vou listar:\n- primeiro **item** fechado.\n- segundo")
    espera("!document.querySelector('.m-g .md .caret')", 6)

    # ---------- a mensagem da pessoa ----------
    h.bus.emitir("voce", texto="primeira linha\nsegunda linha\n\nterceira depois de uma linha em branco")
    confere("a mensagem de várias linhas mantém as quebras", espera("[...document.querySelectorAll('.m-u p')].some((p) => p.innerText.includes('segunda linha'))", 6)
            and js("getComputedStyle([...document.querySelectorAll('.m-u p')].pop()).whiteSpace") == "pre-wrap")

    # ---------- a caixa de escrever ----------
    c0 = campo()
    confere("o campo de escrever é uma caixa de texto de uma linha", c0.get("tag") == "TEXTAREA" and 44 <= c0.get("h", 0) <= 56, c0)
    escrever("uma linha só")
    pausa(0.4)
    c1 = campo()
    confere("texto curto não aumenta a caixa", abs(c1["h"] - c0["h"]) <= 1, c1)
    escrever("linha 1\nlinha 2\nlinha 3")
    pausa(0.4)
    c3 = campo()
    confere("três linhas: a caixa cresce para cima e a base fica no mesmo lugar", c3["h"] > c0["h"] + 30 and c3["topo"] < c0["topo"] - 30 and abs(c3["base"] - c0["base"]) <= 2 and c3["rola"] == "hidden", (c0, c3))
    nav.foto("texto_caixa_3_linhas")
    escrever("\n".join(f"linha {i}" for i in range(1, 16)))
    pausa(0.5)
    c15 = campo()
    confere("quinze linhas: para em 10 linhas e passa a rolar por dentro", 240 <= c15["h"] <= 262 and c15["rola"] == "auto" and abs(c15["base"] - c0["base"]) <= 2, c15)
    nav.foto("texto_caixa_10_linhas")
    comandos()
    escrever("", enter=False)
    escrever("a\nb", enter=True, shift=True)
    pausa(0.3)
    confere("Shift+Enter quebra a linha e não envia", not any(c[0] == "perguntar" for c in comandos()) and campo()["valor"] == "a\nb")
    escrever("pergunta com\nduas linhas", enter=True)
    pausa(0.6)
    enviados = comandos()
    confere("Enter envia o texto com as quebras de linha", ("perguntar", "pergunta com\nduas linhas") in enviados, enviados)
    c_fim = campo()
    confere("depois de enviar, a caixa volta ao tamanho de uma linha e fica vazia", c_fim["valor"] == "" and abs(c_fim["h"] - c0["h"]) <= 1, c_fim)
finally:
    erros = nav.erros
    nav.fechar()

confere("sem erro de JavaScript na tela", not erros, erros[:3])
ok = B.placar()
raise SystemExit(0 if ok else 1)
