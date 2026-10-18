"""Modo sessão no painel (Edge sem janela): faixa da conversa, lista de conversas (nova e voltar a uma anterior), o aviso do que o guardião
está usando (conector, skill, agente) e o cartão de permissão respondido por clique ou por Esc. O programa de voz não roda aqui:
o teste lê os comandos que a tela manda e emite os eventos que ele emitiria."""
import json
import queue
import sys
import time

import v2_base as B
from v2_base import confere, h

import guardiao_sessao as gs

PORTA = 8788
tmp, relogio = B.preparar(PORTA, hora="09:50", prefs={"sessao": True})
nav = B.Navegador(f"http://localhost:{PORTA}/v2/?semabertura=1", porta_cdp=9347, largura=1760, altura=900)
js, espera = nav.js, nav.espera


def pausa(seg):
    time.sleep(seg)
    return True


def texto(seletor):
    return js("(() => { const e = document.querySelector(%s); return e ? e.textContent : null; })()" % json.dumps(seletor)) or ""


def comandos():
    saida = []
    while True:
        try:
            saida.append(h.bus.comandos.get_nowait())
        except queue.Empty:
            return saida


def tela(n):
    js("document.querySelectorAll('.hd .tab')[%d].click()" % n)
    time.sleep(1.3)


try:
    confere("o painel abre", espera("document.querySelector('.gd .hd')", 20))
    pausa(3.6)
    # ---------------- faixa da conversa ----------------
    confere("com o modo sessão ligado, a Home mostra a faixa da conversa, ainda sem título", espera("document.querySelector('.st.cur .cs-home')", 4) and "Conversa nova" in texto(".st.cur .cs-home .cs-t")
            and "NOVA" in texto(".st.cur .cs-home .cs-n").upper(), texto(".st.cur .cs-home"))
    c1 = gs.atual()
    gs.anotar(c1["id"], "u", "Quais pendências de sábado e domingo são urgentes?")
    gs.anotar(c1["id"], "g", "São doze pendências. Cinco são urgentes.")
    gs._atualizar(c1["id"], contexto=96500)
    gs.avisar_tela()
    confere("depois da primeira fala, a faixa mostra o título da conversa", espera("document.querySelector('.st.cur .cs-home .cs-t').textContent.includes('Quais pendências')", 4), texto(".st.cur .cs-home"))
    nav.foto("sessao_home")

    # ---------------- o que o guardião está usando ----------------
    h.bus.emitir("voce", texto="olha no ClickUp as tarefas do relatório")
    h.bus.emitir("estado", v="pensando")
    h.bus.emitir("ferramenta", fase="inicio", id="t1", tipo="conector", rotulo="Consultando o ClickUp", dentro=False)
    confere("usando um conector, o estado na tela diz qual", espera("document.querySelector('.st.cur .gl-u').textContent.includes('CONSULTANDO O CLICKUP')", 3), texto(".st.cur .gl-u"))
    confere("e a esfera entra no estado 'trabalhando'", espera("!!document.querySelector('.orbw [aria-label=\"Bolinha do Guardião, trabalhando\"]')", 3),
            js("[...document.querySelectorAll('.orbw [aria-label]')].map(e => e.getAttribute('aria-label')).join('|')"))
    pausa(1.2)
    nav.foto("sessao_conector")
    with open(B.os.path.join(B.PASTA_PNG, "v2_sessao_esfera_trabalhando.png"), "wb") as f:
        f.write(B.base64.b64decode(nav.cdp("Page.captureScreenshot", {"format": "png", "clip": {"x": 700, "y": 150, "width": 360, "height": 400, "scale": 2}})["data"]))
    h.bus.emitir("ferramenta", fase="fim", id="t1", erro=False)
    # ---------------- pausa no meio de uma resposta: a tela diz que ele ainda está respondendo ----------------
    h.bus.emitir("estado", v="aguardando")
    pausa(0.5)
    h.bus.emitir("voce", texto="se apresente")
    h.bus.emitir("estado", v="pensando")
    confere("antes da primeira frase, a tela diz 'Pensando'", espera("document.querySelector('.gc-st') && document.querySelector('.gc-st').textContent.toUpperCase().includes('PENSANDO')", 3), texto(".gc-st"))
    h.bus.emitir("estado", v="falando")
    h.bus.emitir("guardiao_texto", texto="Sou o Guardião, seu gestor de projetos.")
    pausa(0.6)
    h.bus.emitir("estado", v="pensando")  # o programa faz isto quando a próxima frase demora mais de meio segundo
    confere("na pausa entre duas frases da mesma resposta, a tela diz 'Ainda respondendo' (não 'Pensando')",
            espera("document.querySelector('.gc-st') && document.querySelector('.gc-st').textContent.toUpperCase().includes('AINDA RESPONDENDO')", 3), texto(".gc-st"))
    confere("e a dica ao lado diz o mesmo, em frase", "ainda estou respondendo" in texto(".gc-hint").lower(), texto(".gc-hint"))
    h.bus.emitir("estado", v="falando")
    h.bus.emitir("guardiao_texto", texto="Sou o Guardião, seu gestor de projetos. Cuido do seu tempo.")
    h.bus.emitir("guardiao_fim", texto="Sou o Guardião, seu gestor de projetos. Cuido do seu tempo.")
    h.bus.emitir("estado", v="aguardando")
    pausa(0.8)
    h.bus.emitir("voce", texto="olha no ClickUp as tarefas do relatório")
    h.bus.emitir("estado", v="pensando")
    confere("e na resposta seguinte, antes de começar, volta a ser 'Pensando'", espera("document.querySelector('.gc-st') && document.querySelector('.gc-st').textContent.toUpperCase().includes('PENSANDO')", 3), texto(".gc-st"))
    h.bus.emitir("ferramenta", fase="inicio", id="t1b", tipo="conector", rotulo="Consultando o ClickUp", dentro=False)
    pausa(0.4)
    h.bus.emitir("ferramenta", fase="fim", id="t1b", erro=False)
    confere("quando o conector termina, volta a pensar", espera("!document.querySelector('.st.cur .gl-u').textContent.includes('CLICKUP')", 3), texto(".st.cur .gl-u"))
    h.bus.emitir("ferramenta", fase="inicio", id="t2", tipo="skill", rotulo="Usando a skill guardiao-triwer", dentro=False)
    confere("com uma skill, o mesmo", espera("document.querySelector('.st.cur .gl-u').textContent.includes('USANDO A SKILL GUARDIAO-TRIWER')", 3), texto(".st.cur .gl-u"))
    h.bus.emitir("ferramenta", fase="fim", id="t2", erro=False)
    h.bus.emitir("ferramenta", fase="inicio", id="t3", tipo="agente", rotulo="Chamando o agente Máximo", dentro=False)
    h.bus.emitir("ferramenta", fase="inicio", id="t4", tipo="conector", rotulo="Consultando a Meta", dentro=True)
    confere("com um agente, aparece o agente (o que ele usa por dentro não troca o aviso)", espera("document.querySelector('.st.cur .gl-u').textContent.includes('CHAMANDO O AGENTE MÁXIMO')", 3), texto(".st.cur .gl-u"))
    h.bus.emitir("ferramenta", fase="fim", id="t3", erro=False)
    h.bus.emitir("estado", v="falando")
    h.bus.emitir("guardiao_texto", texto="Achei duas tarefas do relatório.")
    h.bus.emitir("guardiao_fim", texto="Achei duas tarefas do relatório.")
    h.bus.emitir("estado", v="aguardando")
    confere("parado, a esfera volta a aguardar", espera("!!document.querySelector('.orbw [aria-label=\"Bolinha do Guardião, aguardando\"]')", 3))
    h.bus.emitir("completo", ativo=True)
    confere("com um pedido correndo em segundo plano, a esfera mostra 'trabalhando' mesmo livre para conversar",
            espera("!!document.querySelector('.orbw [aria-label=\"Bolinha do Guardião, trabalhando\"]')", 3) and "MONTANDO O SEU PEDIDO" in texto(".st.cur .gl-u").upper(), texto(".st.cur .gl-u"))
    h.bus.emitir("completo", ativo=False)
    confere("quando o pedido termina, ela volta ao normal", espera("!!document.querySelector('.orbw [aria-label=\"Bolinha do Guardião, aguardando\"]')", 3))
    tela(1)
    confere("a resposta fica com a anotação do que foi usado", espera("document.querySelector('.gcol .m-via')", 4) and texto(".gcol .m-via") == "ClickUp · skill guardiao-triwer · agente Máximo · Meta", texto(".gcol .m-via"))
    confere("a coluna da conversa também tem a faixa", "Quais pendências" in texto(".gcol .cs-col .cs-t"))
    nav.foto("sessao_dia_coluna")

    # ---------------- lista de conversas: nova e voltar ----------------
    js("document.querySelector('.gcol .cs-col .cs-t').click()")
    confere("a faixa abre a lista de conversas", espera("document.querySelector('.detail.open')", 4) and pausa(0.9) and "Conversas" in texto(".detail .dt-title")
            and js("document.querySelectorAll('.detail .dl-r').length") == 1 and "ATUAL" in texto(".detail .dl-r .s").upper() and "97 mil tokens" in texto(".detail"), texto(".detail")[:300])
    nav.foto("sessao_conversas")
    comandos()
    js("[...document.querySelectorAll('.detail .dt-acts button')].find(b => b.textContent.includes('Nova conversa')).click()")
    confere("'Nova conversa' manda o pedido ao programa de voz", pausa(0.6) and comandos() == [("conversa", {"acao": "nova", "id": ""})])
    c2 = gs.trocar()
    confere("na conversa nova a coluna esvazia e a faixa volta a dizer 'Conversa nova'", espera("document.querySelectorAll('.gcol .mw').length === 0", 4) and "Conversa nova" in texto(".gcol .cs-col .cs-t")
            and espera("document.querySelector('.toast') && document.querySelector('.toasts').textContent.includes('Conversa nova')", 3), texto(".gcol .cs-col"))
    gs.anotar(c2["id"], "u", "Monta o meu dia de amanhã")
    gs.anotar(c2["id"], "g", "Amanhã cabem seis blocos.")
    gs.avisar_tela()
    js("document.querySelector('.gcol .cs-col .cs-t').click()")
    confere("a lista passa a ter as duas, a mais recente em cima", espera("document.querySelectorAll('.detail.open .dl-r').length === 2", 4) and "Monta o meu dia" in texto(".detail .dl-r .n"), texto(".detail .dt-list"))
    js("document.querySelectorAll('.detail .dl-r')[1].click()")
    confere("clicar numa conversa anterior pede para voltar a ela", pausa(0.6) and comandos() == [("conversa", {"acao": "abrir", "id": c1["id"]})])
    gs.trocar(c1["id"])
    confere("ao voltar, as falas daquela conversa reaparecem", espera("document.querySelectorAll('.gcol .mw').length === 2", 5) and "doze pendências" in texto(".gcol .gc-log")
            and "Quais pendências" in texto(".gcol .cs-col .cs-t"), texto(".gcol .gc-log"))
    h.bus.emitir("ui", cmd="conversas")
    confere("pedir as conversas por voz abre a mesma lista", espera("document.querySelector('.detail.open') && document.querySelector('.detail .dt-title').textContent.includes('Conversas')", 4))
    js("document.querySelector('.detail .dt-x').click()")
    pausa(0.7)

    # ---------------- pedido de permissão ----------------
    tela(0)
    comandos()
    pedido = gs.descrever("mcp__claude_ai_ClickUp__clickup_create_task", {"name": "Ligar para o contador sobre o imposto do trimestre", "list_id": "L1", "due_date": "2026-10-13", "description": "Confirmar a guia e o valor. " * 12})
    h.bus.emitir("permissao", id="p1", titulo=pedido["titulo"], kicker=pedido["kicker"], linhas=pedido["linhas"], sempre=True)
    confere("o pedido de permissão abre um cartão com a ação, os dados e três botões", espera("document.querySelector('.scene.open.perm')", 4) and pausa(1.0)
            and "Criar uma tarefa no ClickUp" in texto(".scene h3") and "Ligar para o contador" in texto(".scene .srows")
            and js("[...document.querySelectorAll('.scene .dt-acts button')].map(b => b.textContent).join('|')") == "Permitir|Permitir sempre|Negar", texto(".scene"))
    r = js("(() => { const s = document.querySelector('.scene').getBoundingClientRect(); return { y: s.top, b: s.bottom }; })()")
    confere("o cartão cabe na tela mesmo com um texto comprido", r["y"] >= 0 and r["b"] <= 900, r)
    nav.foto("sessao_permissao")
    js("[...document.querySelectorAll('.scene .dt-acts button')].find(b => b.textContent === 'Permitir').click()")
    confere("clicar em Permitir entrega o sim ao programa de voz e interrompe a escuta", pausa(0.6) and comandos() == [("permissao", "sim")] and h.bus.cancelar_escuta.is_set())
    h.bus.emitir("permissao_fim", id="p1", resultado="permitida", sempre=False)
    confere("resolvido, o cartão fecha", espera("!document.querySelector('.scene.open')", 4))
    pausa(0.8)
    pedido = gs.descrever("mcp__claude_ai_Evolution_WhatsApp__send_message", {"number": "5511999990000", "text": "Oi, tudo certo para amanhã?"})
    h.bus.emitir("permissao", id="p2", titulo=pedido["titulo"], kicker=pedido["kicker"], linhas=pedido["linhas"], sempre=False)
    confere("para mensagem que sai, não existe 'Permitir sempre'", espera("document.querySelector('.scene.open.perm')", 4) and pausa(0.8)
            and js("[...document.querySelectorAll('.scene .dt-acts button')].map(b => b.textContent).join('|')") == "Permitir|Negar" and "5511999990000" in texto(".scene .srows"), texto(".scene"))
    nav.cdp("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    confere("Esc no cartão vale como não", pausa(0.6) and comandos() == [("permissao", "nao")])
    h.bus.emitir("permissao_fim", id="p2", resultado="negada", sempre=False)
    confere("e o cartão fecha", espera("!document.querySelector('.scene.open')", 4))
    h.bus.emitir("permissao", id="p3", titulo="Criar uma tarefa no ClickUp", kicker="ClickUp", linhas=[], sempre=True)
    espera("document.querySelector('.scene.open.perm')", 4)
    h.bus.emitir("permissao_fim", id="p3", resultado="expirada", sempre=False)
    confere("pedido sem resposta fecha e avisa", espera("!document.querySelector('.scene.open')", 4) and espera("document.querySelector('.toasts').textContent.includes('sem resposta')", 3))

    # ---------------- preferência ----------------
    js("document.querySelector('.ibtn[aria-label=\"Preferências\"]').click()")
    espera("document.querySelector('.prefs.open')", 3)
    js("[...document.querySelectorAll('.prefs .pg-h')].find(e => e.textContent.includes('Comportamento')).click()")
    pausa(0.7)
    confere("a preferência 'Conversa com memória do Claude' está em Comportamento, ligada", js("document.querySelector('.prefs .sw[aria-label=\"Conversa com memória do Claude\"]').classList.contains('on')"))  # o nome ganhou "do Claude" quando o Codex entrou
    nav.foto("sessao_preferencia")
    js("document.querySelector('.prefs .sw[aria-label=\"Conversa com memória do Claude\"]').click()")
    confere("desligar grava no servidor e tira a faixa da conversa da tela", pausa(1.0) and h.preferencias()["sessao"] is False and js("!document.querySelector('.cstrip')"))
    confere("sem erro de JavaScript", not nav.erros, nav.erros[:3])
finally:
    nav.fechar()
    gs.encerrar()
print("erros js:", nav.erros[:3])
sys.exit(0 if B.placar() else 1)
