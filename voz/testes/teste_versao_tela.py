"""Versão 0.3.0 na tela (Edge sem janela): botão discreto de versão nova, cartão com as notas e atualizar, grupo Versão nas preferências,
"Esc cancela" na escuta, clique no microfone cancelando, aviso do guardião completo e a janela compacta pedindo para ficar por cima."""
import json
import os
import sys
import time

import v2_base as B
from v2_base import confere, h

import guardiao_atualizacao as at
import guardiao_janela as jan

PORTA = 8794
tmp, relogio = B.preparar(PORTA, hora="09:50")
with open(os.path.join(tmp, "VERSION"), "w", encoding="utf-8") as f:
    f.write("0.3.0\n")
at.CARREGADA = "0.3.0"
at.INICIO = time.time() + 5
fonte = os.path.join(tmp, "fonte")
os.makedirs(fonte)
with open(os.path.join(fonte, "VERSION"), "w", encoding="utf-8") as f:
    f.write("0.3.0\n")
with open(os.path.join(fonte, "CHANGELOG.md"), "w", encoding="utf-8") as f:
    f.write("# Changelog\n\n## 0.3.1 - 2026-10-20\n- **A escuta ficou mais paciente com pausas longas.** Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. \n- **Correção no cartão de detalhes.** Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. \n- **Mais tempo pela voz.** Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. \n- **Quarta mudança.** Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. Texto técnico comprido que o aluno não precisa ler, com nomes de arquivo, medidas e testes, repetido para encher o cartão. \n- **Quinta mudança que não aparece.** x\n- Testado: tudo, com detalhes internos.\n\n## 0.3.0 - 2026-10-12\n- Versão instalada.\n")


def config(**extra):
    caminho = os.path.join(tmp, "config.json")
    with open(caminho, encoding="utf-8") as f:
        c = json.load(f)
    c.update(extra)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)


config(atualizacao={"origem": fonte, "pasta": ""})
pedidos_janela = []
jan.rota = lambda dados: (pedidos_janela.append(dados), {"ok": True, "por_cima": True})[1]
chamados = []
at.COMANDO_ATUALIZAR = chamados.append
with open(os.path.join(tmp, "atualizar.ps1"), "w", encoding="utf-8") as f:
    f.write("# de mentira")

nav = B.Navegador(f"http://localhost:{PORTA}/v2/?semabertura=1", porta_cdp=9347)
js, espera, clicar = nav.js, nav.espera, nav.clicar_texto
# guarda a ligação de eventos da página, para o teste simular a queda e a volta do guardião
nav.cdp("Page.addScriptToEvaluateOnNewDocument", {"source": "(() => { const E = window.EventSource; window.EventSource = function (u) { const e = new E(u); window.__es = e; return e; }; })()"})
# conta as notas que o painel toca (cada nota é um oscilador), para conferir os sons sem ouvir
nav.cdp("Page.addScriptToEvaluateOnNewDocument", {"source": "(() => { window.__notas = []; const C = window.AudioContext || window.webkitAudioContext; if (!C) return; const o = C.prototype.createOscillator; "
        "C.prototype.createOscillator = function () { const n = o.call(this); const f = n.frequency.setValueAtTime.bind(n.frequency); n.frequency.setValueAtTime = (v, t) => { window.__notas.push(Math.round(v)); return f(v, t); }; return n; }; })()"})
nav.abrir(f"http://localhost:{PORTA}/v2/?semabertura=1")


def texto(seletor):
    return js("(() => { const e = document.querySelector(%s); return e ? e.innerText : null; })()" % json.dumps(seletor)) or ""


def pausa(seg):
    time.sleep(seg)
    return True


try:
    confere("o painel abre", espera("document.querySelector('.gd .hd')", 20))
    pausa(1.5)
    confere("na primeira abertura do dia o guardião confere a versão sozinho", espera("true", 1) and (at._estado().get("verificado_em") or "")[:10] == time.strftime("%Y-%m-%d"), at._estado())
    confere("em dia: nenhum botão de versão no topo", js("!document.querySelector('.hd .upd')"))
    js("document.querySelector('.ibtn[aria-label=\"Preferências\"]').click()")
    confere("as preferências abrem e a seção Versão resume o estado, mesmo fechada", espera("document.querySelector('.prefs.open')", 3)
            and "0.3.0 · em dia" in js("[...document.querySelectorAll('.prefs .pg')].find(e => e.textContent.includes('Versão')).querySelector('.pg-s').textContent"))
    js("[...document.querySelectorAll('.prefs .pg-h')].find(e => e.textContent.includes('Versão')).click()")
    pausa(0.7)
    confere("preferências mostram a versão instalada", espera("document.querySelector('.prefs.open')", 3) and "Guardião 0.3.0" in texto(".prefs") and "EM DIA" in texto(".prefs").upper(), texto(".prefs")[-400:])
    confere("a versão aparece logo no alto das preferências", "VERSÃO 0.3.0" in texto(".prefs .pver").upper(), texto(".prefs .pver"))
    confere("e o botão de conferir, com a data da última conferência", "CONFERIR" in texto(".prefs").upper() and "Conferido em" in texto(".prefs"), texto(".prefs")[-500:])

    with open(os.path.join(fonte, "VERSION"), "w", encoding="utf-8") as f:
        f.write("0.3.1\n")
    clicar("Conferir", ".prefs button")
    confere("conferir agora acha a versão nova e a linha vira 'disponível'", espera("document.querySelector('.prefs').innerText.includes('Versão 0.3.1 disponível')", 8), texto(".prefs")[-400:])
    confere("o botão discreto aparece no topo", espera("document.querySelector('.hd .upd')", 8) and "NOVA VERSÃO" in texto(".hd .upd").upper(), texto(".hd-r"))
    nav.foto("versao_preferencias")
    js("document.querySelector('.prefs .dt-x').click()")
    pausa(0.6)
    nav.foto("versao_botao")
    js("document.querySelector('.hd .upd').click()")
    confere("o clique abre o cartão com o que muda", espera("document.querySelector('.scene.open')", 3) and "Há uma versão nova" in texto(".scene") and "mais paciente" in texto(".scene"), texto(".scene"))
    confere("os botões já estão visíveis, sem esperar o texto terminar", js("getComputedStyle(document.querySelector('.scene .dt-acts')).display !== 'none'") and "ATUALIZAR AGORA" in texto(".scene").upper())
    confere("o cartão mostra só o título de cada mudança (sem o texto técnico, sem asterisco e no máximo 4)",
            "Texto técnico" not in texto(".scene") and "**" not in texto(".scene") and "Quarta mudança" in texto(".scene") and "Quinta mudança" not in texto(".scene") and "Testado" not in texto(".scene"), texto(".scene"))
    confere("o botão Atualizar agora fica dentro da tela, mesmo com notas longas",
            js("(() => { const b = [...document.querySelectorAll('.scene button')].find(x => x.textContent.includes('Atualizar')); const r = b.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.height > 0; })()"),
            js("JSON.stringify([...document.querySelectorAll('.scene button')].map(x => x.getBoundingClientRect().bottom).concat([innerHeight]))"))
    pausa(1.2)
    nav.foto("versao_cartao")
    clicar("Atualizar agora", ".scene button")
    confere("atualizar agora chama o atualizador", espera("true", 1) and pausa(0.8) and len(chamados) == 1, chamados)
    confere("o botão do topo passa a dizer que está atualizando", espera("document.querySelector('.hd .upd.busy')", 3) and "ATUALIZANDO" in js("document.querySelector('.hd .upd').textContent").upper(), js("document.querySelector('.hd-r').textContent"))
    confere("com a barra recolhida, o ícone do menu avisa com um ponto dourado", js("document.querySelector('.hdm').classList.contains('dot')"))
    confere("o cartão fecha e a pessoa é avisada", espera("!document.querySelector('.scene.open')", 3) and "reinicia" in texto(".toasts"), texto(".toasts"))

    # depois de reiniciar em outra versão, a página recarrega sozinha
    js("window.__marca = 1")
    at.ATUALIZANDO = False
    with open(os.path.join(tmp, "VERSION"), "w", encoding="utf-8") as f:
        f.write("0.3.1\n")
    at.CARREGADA = "0.3.1"
    js("window.__es.onerror(); 1")
    pausa(0.4)
    js("window.__es.onopen(); 1")
    confere("ao voltar em outra versão, a página recarrega sozinha", espera("window.__marca !== 1 && document.querySelector('.gd .hd')", 10))
    pausa(1.2)
    confere("depois de atualizar, o botão some e as preferências mostram a versão nova", js("!document.querySelector('.hd .upd')"), texto(".hd-r"))

    # ---- escuta ----
    h.bus.emitir("estado", v="ouvindo", seguimento=False)
    confere("ouvindo: a tela ensina que Esc cancela", espera("document.querySelector('.gd').innerText.toUpperCase().includes('ESC CANCELA')", 3))
    h.bus.emitir("previa", texto="quero falar com outra pessoa")
    h.bus.cancelar_escuta.clear()
    js("document.querySelector('.st.cur .mic, .gcol .mic, .mic').click()")
    confere("clicar no microfone enquanto ouve pede o cancelamento", pausa(0.6) and h.bus.cancelar_escuta.is_set())
    h.bus.cancelar_escuta.clear()
    h.bus.emitir("previa", texto="")
    pausa(0.5)
    js("window.__notas.length = 0")
    h.bus.emitir("escuta_cancelada")
    h.bus.emitir("estado", v="aguardando")
    confere("a escuta cancelada tem som próprio no painel (duas notas descendo)", pausa(0.6) and js("window.__notas.slice(0, 2).join(',')") == "659,392", js("window.__notas.join(',')"))
    confere("escuta cancelada: volta ao repouso sem mandar nada", espera("!document.querySelector('.gd').innerText.toUpperCase().includes('ESC CANCELA')", 3) and "quero falar com outra pessoa" not in texto(".gd"))

    # ---- guardião completo ----
    h.bus.emitir("completo", ativo=True, pedido="refazer o plano de hoje")
    confere("guardião completo trabalhando: aviso e estado na tela", espera("document.querySelector('.toasts').innerText.includes('Guardião completo trabalhando')", 3)
            and espera("document.querySelector('.gd').innerText.toUpperCase().includes('MONTANDO O SEU PEDIDO')", 3), texto(".toasts"))
    h.bus.emitir("completo", ativo=False)
    confere("ao terminar, o estado volta ao normal", espera("!document.querySelector('.gd').innerText.toUpperCase().includes('MONTANDO O SEU PEDIDO')", 3))

    # ---- janela compacta ----
    pedidos_janela.clear()
    nav.abrir(f"http://localhost:{PORTA}/v2/mini.html")
    confere("a janela compacta tem título próprio (é por ele que o guardião a acha)", espera("document.title === 'Guardião compacto' && document.querySelector('.gd .mini')", 15), js("document.title"))
    confere("ao abrir, ela pede para ficar por cima, no canto, e informa a moldura", pausa(1.5) and pedidos_janela and pedidos_janela[0].get("acao") == "compacta" and "dw" in pedidos_janela[0], pedidos_janela)
    pedidos_janela.clear()
    js("document.querySelector('.mi-hd .ibtn[aria-label=\"Expandir para a janela completa\"]').click()")
    confere("expandir pede a janela grande de volta", pausa(0.8) and any(p.get("acao") == "expandir" for p in pedidos_janela), pedidos_janela)
    confere("sem erro de JavaScript", not nav.erros, nav.erros[:3])
finally:
    nav.fechar()
print("erros js:", nav.erros[:3])
sys.exit(0 if B.placar() else 1)
