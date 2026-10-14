"""Painel novo no navegador (Edge sem janela), com ClickUp falso e relógio do teste: Home em dois estágios, modo execução, aviso de tempo,
concluir com comentário, adiar com motivo, eventos do guardião (fala, foco, ação, proposta), Dia, Planejador, Calibragem, POPs e preferências."""
import json
import os
import queue
import sys
import time

import v2_base as B
from v2_base import confere, h, v2

SO = sys.argv[1] if len(sys.argv) > 1 else ""  # nome de uma etapa para parar depois dela (depuração)
tmp, relogio = B.preparar(8776, hora="09:50", prefs={"execucao_ao_abrir": False})  # começa na Home em conversa (o padrão vai direto para a execução)
nav = B.Navegador("http://localhost:8776/v2/?semabertura=1", porta_cdp=9342)
js, espera, foto, clicar = nav.js, nav.espera, nav.foto, nav.clicar_texto


def digitar(seletor, texto, enter=False):
    return js("""(() => { const el = document.querySelector(%s); if (!el) return false;
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, %s); el.dispatchEvent(new Event('input', { bubbles: true }));
      if (%s) el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return true; })()""" % (json.dumps(seletor), json.dumps(texto), "true" if enter else "false"))


def texto(seletor):
    return js("(() => { const e = document.querySelector(%s); return e ? e.innerText : null; })()" % json.dumps(seletor)) or ""


def contem(seletor, trecho):
    return trecho.lower() in texto(seletor).lower()


def pausa(seg):
    time.sleep(seg)
    return True


def tem(classe):
    return js("document.querySelector('.gd').classList.contains(%s)" % json.dumps(classe))


def comandos():
    saida = []
    while True:
        try:
            saida.append(h.bus.comandos.get_nowait())
        except queue.Empty:
            return saida


def falar(frase, pausa=0.03):
    h.bus.emitir("estado", v="falando")
    for i in range(6, len(frase) + 6, 6):
        h.bus.emitir("guardiao_texto", texto=frase[:i])
        h.bus.emitir("nivel", voz=0.6)
        time.sleep(pausa)
    h.bus.emitir("guardiao_fim", texto=frase)
    h.bus.emitir("estado", v="aguardando")


try:
    # ---------------- Home, estágio de conversa
    confere("a tela carrega e sai da preparação", espera("document.querySelector('.gd') && !document.querySelector('.gd').classList.contains('is-prep') && !document.querySelector('.gd').classList.contains('is-introskip')", 15))
    confere("palco encaixado na janela", js("getComputedStyle(document.getElementById('dc-root')).transform !== 'none'"))
    # o cabeçalho se esconde sozinho no desktop meio segundo depois de abrir: o nome é lido pelo conteúdo, não pelo texto visível
    marca = js("(document.querySelector('.brand') || {}).textContent || ''").lower()
    confere("cabeçalho com nome e abas, e o relógio do servidor acima da bolinha", "guardião" in marca and "rafa" in marca and contem(".orbdate", "09:50") and js("document.querySelectorAll('.tab').length") == 5, texto(".hd"))
    confere("Home em conversa: só a bolinha, o estado e três atalhos", not tem("is-exec") and contem(".gl-u", "DIGA EI GUARDIÃO") and js("[...document.querySelectorAll('.st.cur .arow .chip')].map(e => e.textContent).join('|')") == "Modo execução|Próximas tarefas|Ver o dia")
    confere("a bolinha 3D está desenhando", js("(() => { const c = document.querySelector('.orbw canvas'); return !!c && c.width > 100; })()"))
    confere("o console de simulação saiu", js("!document.querySelector('.simchip') && !document.querySelector('.sim')"))
    foto("01_home_conversa")

    # ---------------- modo execução
    clicar("Modo execução", ".st.cur .chip")
    confere("entrar em execução: a tarefa de agora aparece", espera("document.querySelector('.gd').classList.contains('is-exec')", 4) and contem(".f-title", "Montar as campanhas"))
    confere("no horário dela, mas sem o clique, a tarefa NÃO começa: o botão é Iniciar", B.esperar_py(lambda: v2.estado_exec()["ativo"], 5) and v2.estado_exec()["sessao"] is None
            and (contem(".st.cur .btn-pri", "INICIAR · 09:50") or contem(".st.cur .btn-pri", "INICIAR · 09:51")) and contem(".f-kick", "ainda não iniciada"), (texto(".st.cur .btn-pri"), texto(".f-kick")))
    confere("a bolinha diz que é hora de começar", contem(".orbw", "HORA DE COMEÇAR") or "HORA DE COMEÇAR" in js("document.querySelector('.gd').textContent").upper())
    js("document.querySelector('.st.cur .btn-pri').click()")
    confere("Iniciar: o servidor passa a acompanhar o tempo a partir do clique", pausa(0.8) and v2.estado_exec()["sessao"] and v2.estado_exec()["sessao"]["bloco"] == "b3" and v2.estado_exec()["sessao"]["inicio"] in ("09:50", "09:51"), v2.estado_exec())
    espera("document.querySelector('.st.cur .btn-pri').innerText.toUpperCase().includes('CONCLUIR')", 5)
    confere("botão Concluir com a hora e os quatro discretos", (contem(".st.cur .btn-pri", "CONCLUIR · 09:50") or contem(".st.cur .btn-pri", "CONCLUIR · 09:51")) and js("[...document.querySelectorAll('.f-sec .sec-b')].map(e => e.textContent.trim()).join('|')") == "Detalhes|ClickUp|Adiar|Sair", texto(".f-sec"))
    confere("linha de tempo restante", contem(".f-kick", "09:00 às 10:30") and (contem(".f-kick", "40 min restantes") or contem(".f-kick", "39 min restantes")), texto(".f-kick"))
    time.sleep(1.6)
    foto("02_home_execucao")

    # ---------------- conversa por voz (eventos do guardião)
    h.bus.emitir("estado", v="ouvindo")
    h.bus.emitir("nivel", mic=0.7)
    h.bus.emitir("previa", texto="quanto tempo falta")
    confere("ouvindo: estado e prévia do que a pessoa fala", espera("document.querySelector('.gl-u').innerText.toLowerCase().includes('quanto tempo falta')", 3) and js("document.querySelector('.st.cur .mic').classList.contains('on')"), texto(".gl-u"))
    h.bus.emitir("voce", texto="Quanto tempo falta para essa tarefa?")
    h.bus.emitir("estado", v="pensando")
    time.sleep(0.4)
    falar("Faltam quarenta minutos para as campanhas da Clínica Vitta.")
    confere("a fala do guardião aparece na linha dele", espera("document.querySelector('.gl-g').innerText.toLowerCase().includes('faltam quarenta minutos')", 4), texto(".gl-g"))
    confere("o volume real chega à bolinha", js("window.GD_NIVEL.vivo === true && window.GD_NIVEL.voz > 0"))
    # ---------------- velocidade da voz: botão discreto ao lado do campo de texto, só enquanto ele fala
    h.bus.emitir("estado", v="aguardando")
    confere("sem fala, o botão de velocidade não aparece", pausa(0.4) and not js("!!document.querySelector('.st.cur .cmd .spd')"))
    h.bus.emitir("estado", v="falando")
    confere("falando, com a voz ligada, aparece o botão de velocidade em 1x", espera("!!document.querySelector('.st.cur .cmd .spd')", 3) and contem(".st.cur .cmd .spd", "1x"), texto(".st.cur .cmd"))
    js("document.querySelector('.st.cur .cmd .spd').click()")
    confere("um toque troca para 1,5x e grava (a fala em curso acelera)", pausa(0.6) and h.preferencias()["voz_velocidade"] == 1.5 and contem(".st.cur .cmd .spd", "1,5x"), (h.preferencias()["voz_velocidade"], texto(".st.cur .cmd .spd")))
    js("document.querySelector('.st.cur .cmd .spd').click()")
    js("document.querySelector('.st.cur .cmd .spd').click()")
    confere("depois 2x e de volta a 1x", pausa(0.6) and h.preferencias()["voz_velocidade"] == 1.0, h.preferencias()["voz_velocidade"])
    eventos_esc = []
    import controle_fala  # noqa: E402
    esc_original = controle_fala.esc
    controle_fala.esc = lambda: (eventos_esc.append(1), "voz")[1]
    js("document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    confere("Esc enquanto ele fala vai para o guardião (e não tira do modo execução)", pausa(0.6) and eventos_esc == [1] and tem("is-exec"), eventos_esc)
    confere("e a tela avisa que a voz foi desligada", espera("[...document.querySelectorAll('.toast')].some(t => t.innerText.includes('Voz desligada'))", 3))
    controle_fala.esc = esc_original
    h.bus.emitir("estado", v="aguardando")
    foto("03_home_fala")

    # ---------------- foco: a tarefa aparece em destaque enquanto ele fala dela
    h.bus.emitir("foco", ids=["b5"])
    confere("foco abre o cartão da tarefa citada", espera("document.querySelector('.scene.open') && document.querySelector('.scene h3').innerText.toLowerCase().includes('relatório mensal')", 4), texto(".scene"))
    time.sleep(1.2)
    foto("04_cena_foco")
    h.bus.emitir("foco", ids=["b6"])
    confere("novo foco troca o cartão", espera("document.querySelector('.scene h3').innerText.toLowerCase().includes('stories')", 4))
    h.bus.emitir("foco_fim")
    confere("fim do foco fecha o cartão", espera("!document.querySelector('.scene.open')", 5))

    # ---------------- aviso de tempo (popup) e respostas pelos botões
    relogio.hora = "10:01"
    c = v2._tique()
    confere("aviso de tempo vira um cartão com 4 respostas", bool(c) and espera("document.querySelector('.scene.open') && document.querySelectorAll('.scene .dt-acts button').length === 4", 5), texto(".scene"))
    confere("os botões de resposta já aparecem, sem esperar o texto terminar", js("document.querySelector('.scene .dt-acts').style.display !== 'none'"))
    confere("o cartão mostra quanto falta e a pergunta", contem(".scene .tag-g", "FALTAM 29 MIN") and espera("document.querySelector('.scene .sx').innerText.toLowerCase().includes('como está o andamento')", 6), texto(".scene"))
    foto("05_aviso_tempo")
    clicar("Preciso de mais tempo", ".scene button")
    confere("passo seguinte: quanto tempo", espera("document.querySelector('.scene.open') && document.querySelector('.scene h3').innerText.toLowerCase().includes('quanto tempo')", 5), texto(".scene"))
    time.sleep(0.8)
    clicar("Mais 30 min", ".scene button")
    confere("depois, o motivo (com a opção de outro motivo)", espera("document.querySelector('.scene.open') && document.querySelector('.scene h3').innerText.toLowerCase().includes('o que fez o tempo passar')", 5) and espera("[...document.querySelectorAll('.scene button')].some(b => b.textContent.includes('Outro motivo'))", 3), texto(".scene"))
    time.sleep(0.8)
    foto("06_aviso_motivo")
    clicar("Interrupções", ".scene button")
    confere("o cartão fecha e o horário novo aparece", espera("!document.querySelector('.scene.open')", 5) and espera("document.querySelector('.f-kick').innerText.toLowerCase().includes('09:00 às 11:00')", 5), texto(".f-kick"))
    confere("a tela mostra que a tarefa foi estendida", contem(".f-trk", "ESTENDIDA EM 30 MIN"), texto(".f-trk"))
    ditos = [v for t, v in comandos() if t == "dizer"]
    confere("cada passo foi mandado para a voz", len(ditos) == 3 and "até as 11:00" in ditos[-1], ditos)

    # ---------------- concluir: o check fecha a tarefa na hora, sem pedir frase e sem comentar (decisão de produto de 13/10/2026)
    relogio.hora = "10:40"
    h.bus.emitir("plano")
    espera("document.querySelector('.st.cur .btn-pri').innerText.toLowerCase().includes('10:40')", 8)
    n_antes = len(B.ClickUpFalso.chamadas)
    js("document.querySelector('.st.cur .btn-pri').click()")
    confere("concluir carimba a hora", espera("document.querySelector('.st.cur .btn-pri').classList.contains('stamped')", 3) and contem(".st.cur .btn-pri", "CONCLUÍDO · 10:40"), texto(".st.cur .btn-pri"))
    foto("07_concluir_carimbo")
    confere("não pede frase nenhuma: o check conclui na hora", not js("!!document.querySelector('.st.cur .arow .tin')"), texto(".after"))
    confere("a próxima tarefa já subiu", contem(".f-title", "Revisar o roteiro"), texto(".f-title"))
    time.sleep(1.0)
    foto("08_concluir_sem_frase")
    confere("fecha no ClickUp na hora, com o prazo combinado intacto e o horário realizado num comentário",
            pausa(1.5) and any(m == "PUT" and "cid3" in u and isinstance(c, dict) and c.get("status") == "complete" and "due_date" not in c for m, u, c in B.ClickUpFalso.chamadas)
            and any(m == "POST" and "cid3/comment" in u and str((c or {}).get("comment_text", "")).startswith("Realizado: das 09:50 às 10:40") for m, u, c in B.ClickUpFalso.chamadas),
            B.ClickUpFalso.chamadas[n_antes:][-3:])
    reg = {b["id"]: b for b in h._registro_de_hoje()["blocos"]}
    confere("o registro guarda o horário real medido", reg["b3"]["estado"] == "feito" and reg["b3"]["real"] == {"inicio": "09:50", "fim": "10:40", "minutos": 50} and reg["b3"].get("nao_confirmado") is False, reg["b3"])
    confere("o tempo real entra no tempos.json", h._ler_json(os.path.join(tmp, "tempos.json"))["tipos"]["Tráfego"]["registros"][-1]["real"] == 50)

    # ---------------- adiar pergunta o motivo
    clicar("Adiar", ".f-sec .sec-b")
    confere("adiar pergunta o que impediu", espera("document.querySelectorAll('.st.cur .arow .chip').length === 7", 12), texto(".after"))
    foto("09_adiar_motivo")
    clicar("Sem energia", ".st.cur .arow .chip")
    confere("adia com o motivo e passa para a próxima", espera("document.querySelector('.f-title').innerText.toLowerCase().includes('relatório mensal')", 6) and {b["id"]: b for b in h._registro_de_hoje()["blocos"]}["b4"]["estado"] == "adiado", texto(".f-title"))
    confere("o motivo foi para a calibragem", any(e["tipo"] == "adiamento" and e.get("motivo") == "Sem energia" for e in v2._eventos()))

    # ---------------- ação e proposta do guardião
    h.bus.emitir("acao", tipo="comentar", ref="b5", titulo="Fechar o relatório mensal da Loja Nativa", texto="Números exportados, falta conferir.")
    confere("ação do guardião: cartão com o texto sendo digitado", espera("document.querySelector('.scene.open') && document.querySelector('.scene .sx').innerText.toLowerCase().includes('anotação')", 5), texto(".scene"))
    time.sleep(2.2)
    h.bus.emitir("acao_fim", tipo="comentar", ref="b5", titulo="Fechar o relatório mensal da Loja Nativa", ok=True)
    time.sleep(0.5)
    foto("10_cena_acao")
    confere("com o fim da ação o cartão fecha", espera("!document.querySelector('.scene.open')", 6))
    h.bus.emitir("proposta", tipo="criar", dados={"titulo": "Enviar a proposta da Padaria Sol", "lista": "Lista de teste", "prazo": "2026-10-13", "descricao": "Proposta de conteúdo."})
    confere("proposta de tarefa: cartão com Criar e Descartar", espera("document.querySelector('.scene.open') && [...document.querySelectorAll('.scene button')].some(b => b.textContent.trim() === 'Criar')", 6), texto(".scene"))
    time.sleep(2.4)
    foto("11_cena_proposta")
    comandos()
    clicar("Criar", ".scene button")
    confere("Criar manda o 'sim' para o guardião", pausa(0.6) and ("perguntar", "sim") in comandos())
    h.bus.emitir("proposta_fim", resultado="confirmada")
    espera("!document.querySelector('.scene.open')", 5)

    # ---------------- sair da execução
    clicar("Sair", ".f-sec .sec-b")
    confere("sair volta para a conversa e para de acompanhar", espera("!document.querySelector('.gd').classList.contains('is-exec')", 4) and pausa(0.5) and not v2.estado_exec()["ativo"])

    # ---------------- Dia
    js("[...document.querySelectorAll('.tab')][1].click()")
    confere("aba Dia: linha do tempo com os estados", espera("document.querySelector('.gd').classList.contains('scr-dia')", 3) and espera("document.querySelectorAll('.st.cur .row').length === 8", 5), js("document.querySelectorAll('.st.cur .row').length"))
    linhas = texto(".st.cur .ly.on").upper()
    confere("feitas, adiada, atual e fixo aparecem certo", "FEITO 10:40" in linhas and "ADIADO 1X" in linhas and "FIXO" in linhas and contem(".dia-note", "3 de 7 feitas"), linhas[:300])
    confere("a coluna do Guardião aparece com a conversa", tem("col-on") and contem(".gcol .gc-log", "Faltam quarenta minutos"), texto(".gcol")[:200])
    time.sleep(1.3)
    foto("12_dia")
    js("[...document.querySelectorAll('.st.cur .row .r-body')].find(b => b.innerText.includes('Loja Nativa')).click()")
    confere("clicar numa tarefa abre os detalhes, com dados do ClickUp", espera("document.querySelector('.detail.open')", 3) and espera("document.querySelector('.detail').innerText.toLowerCase().includes('vencimento')", 5) and contem(".detail", "Comece por"), texto(".detail")[:300])
    time.sleep(0.9)
    foto("13_dia_detalhe")
    js("document.querySelector('.detail .dt-x').click()")
    js("[...document.querySelectorAll('.seg-b')].find(b => b.textContent.includes('Próximos dias')).click()")
    confere("camada Próximos dias traz o plano de amanhã", espera("document.querySelector('.st.cur .ly.on .dgrp')", 3) and contem(".st.cur .ly.on", "Gravar o vídeo da Padaria Sol"))
    js("[...document.querySelectorAll('.seg-b')].find(b => b.textContent.includes('Prazos')).click()")
    confere("camada Prazos traz as tarefas do ClickUp", espera("document.querySelector('.st.cur .ly.on .due-row')", 3) and contem(".st.cur .ly.on", "Loja Nativa"))

    # ---------------- Planejador
    js("[...document.querySelectorAll('.tab')][2].click()")
    confere("Planejador: chat com o histórico e os roteiros", espera("document.querySelector('.gd').classList.contains('scr-plan')", 3) and espera("document.querySelectorAll('.pl .chips-row .chip').length === 6", 4) and contem(".pl .msgs", "Quanto tempo falta"))
    comandos()
    digitar(".pl .cmd .fld", "Cria uma tarefa para revisar o contrato da Loja Nativa", enter=True)
    confere("texto digitado vai para o guardião", pausa(0.6) and ("perguntar", "Cria uma tarefa para revisar o contrato da Loja Nativa") in comandos())
    clicar("Report do dia", ".pl .chips-row .chip")
    confere("o roteiro Report do dia é pedido ao guardião", pausa(0.6) and ("roteiro", "report") in comandos())
    h.bus.emitir("roteiro", ativo=True, id="report", passo=2, total=4)
    confere("a tela mostra em que pergunta está", espera("document.querySelector('.pl-sub').innerText.toLowerCase().includes('pergunta 2 de 4')", 3))
    h.bus.emitir("roteiro", ativo=False)
    time.sleep(1.0)
    foto("14_planejador")

    # ---------------- Calibragem
    js("[...document.querySelectorAll('.tab')][3].click()")
    confere("Calibragem no dia 1 explica como funciona", espera("document.querySelector('.gd').classList.contains('scr-cal')", 3) and espera("document.querySelector('.st.cur .rep').innerText.toLowerCase().includes('como a calibragem funciona')", 5) and js("document.querySelectorAll('.st.cur .tdw').length") == 30)
    time.sleep(1.0)
    foto("15_calibragem_dia1")
    clicar("Fazer o primeiro report", ".st.cur .rep button")
    confere("abre o formulário de 4 respostas", espera("document.querySelectorAll('.st.cur .rep textarea').length === 4", 4))
    for i, resp in enumerate(["Mais folga entre as reuniões.", "Das 9h às 11h.", "Blocos de 90 minutos.", "Duas ligações no fim da tarde."]):
        digitar(f"#cal-f{i}", resp)
    clicar("Enviar report", ".st.cur .rep button")
    confere("enviar grava o report e mostra a conquista", espera("document.querySelector('.st.cur .ach')", 6) and contem(".st.cur .ach", "Dia 1 calibrado") and v2.calibragem()["reports"] == 1, texto(".st.cur .rep"))
    confere("o que foi medido hoje já aparece como aprendizado", espera("document.querySelectorAll('.st.cur .lc').length >= 1", 5) and contem(".st.cur .col2", "Por que as tarefas atrasam"), texto(".st.cur .col2")[:300])
    time.sleep(1.3)
    foto("16_calibragem_enviado")

    # ---------------- POPs
    js("[...document.querySelectorAll('.tab')][4].click()")
    confere("POPs: biblioteca vazia com convite para criar", espera("document.querySelector('.gd').classList.contains('scr-pops')", 3) and espera("document.querySelector('.st.cur .pstate')", 5) and contem(".st.cur .pgrid", "ainda não tem POPs"))
    js("[...document.querySelectorAll('.st.cur .seg-b')].find(b => b.textContent.includes('escola')).click()")
    confere("catálogo da escola: diz que ainda não foi publicado, sem inventar POPs", espera("document.querySelector('.st.cur .pstate h3').innerText.toLowerCase().includes('ainda não foi publicado')", 4), texto(".st.cur .pgrid"))
    time.sleep(0.8)
    foto("17_pops_escola")
    # catálogo da escola no ar, mas sem nenhum POP publicado ainda: diz isso, em vez de "Nada encontrado"
    with open(os.path.join(tmp, "catalogo_vazio.json"), "w", encoding="utf-8") as f:
        json.dump({"pops": []}, f)
    cfg_pops = h._config()
    cfg_pops["pops"] = {"catalogo": "catalogo_vazio.json"}
    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg_pops, f, ensure_ascii=False)
    js("[...document.querySelectorAll('.tab')][0].click()")
    time.sleep(0.8)
    js("[...document.querySelectorAll('.tab')][4].click()")
    espera("document.querySelector('.gd').classList.contains('scr-pops')", 3)
    js("[...document.querySelectorAll('.st.cur .seg-b')].find(b => b.textContent.includes('escola')).click()")
    confere("catálogo da escola sem POPs publicados diz que a escola ainda não publicou, e não 'Nada encontrado'",
            espera("document.querySelector('.st.cur .pstate h3') && document.querySelector('.st.cur .pstate h3').innerText.toLowerCase().includes('escola ainda não publicou')", 5)
            and "nada encontrado" not in texto(".st.cur .pgrid").lower(), texto(".st.cur .pgrid"))
    cfg_pops.pop("pops")
    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg_pops, f, ensure_ascii=False)
    r = v2.rascunho_pop({"bloco": "b3"})
    js("[...document.querySelectorAll('.tab')][1].click()")
    espera("document.querySelector('.gd').classList.contains('scr-dia')", 3)
    js("[...document.querySelectorAll('.seg-b')].find(b => b.textContent.trim() === 'Hoje').click()")
    time.sleep(0.9)
    js("[...document.querySelectorAll('.st.cur .row .r-body')].find(b => b.innerText.toLowerCase().includes('montar as campanhas')).click()")
    espera("document.querySelector('.detail.open')", 3)
    clicar("Criar POP desta tarefa", ".detail button")
    confere("criar POP de uma tarefa feita abre o rascunho com as etapas", espera("document.querySelector('.gd').classList.contains('scr-pops') && document.querySelectorAll('.st.cur .draft .stp').length === 3", 8) and js("document.querySelector('.st.cur .draft .stp .tin').value") == "Reler o briefing", texto(".st.cur .draft"))
    digitar(".st.cur .draft > .tin", "Montagem de campanhas de tráfego")
    time.sleep(0.9)
    foto("18_pops_rascunho")
    clicar("Salvar POP", ".st.cur .draft button")
    arq = os.path.join(tmp, "memoria", "pops", "POP - Montagem de campanhas de tráfego.md")
    confere("salvar cria o arquivo do POP na pasta de memória", espera("document.querySelectorAll('.st.cur .pc').length === 1", 6) and os.path.exists(arq), os.listdir(os.path.join(tmp, "memoria", "pops")))
    js("document.querySelector('.st.cur .pc').click()")
    confere("abrir o POP mostra as etapas e 'Usar agora'", espera("document.querySelector('.detail.open')", 3) and contem(".detail", "Definir os públicos") and contem(".detail", "Usar agora"))
    time.sleep(0.9)
    foto("19_pops_detalhe")
    js("document.querySelector('.detail .dt-x').click()")

    # ---------------- preferências
    js("document.querySelector('.ibtn[aria-label=\"Preferências\"]').click()")
    confere("preferências abrem com três grupos", espera("document.querySelector('.prefs.open')", 3) and js("[...document.querySelectorAll('.prefs .pg-h .mono')].map(e => e.textContent).join('|')") == "Voz e sons|Comportamento|Aparência",
            js("[...document.querySelectorAll('.prefs .pg-h .mono')].map(e => e.textContent).join('|')"))
    confere("as seções abrem fechadas, cada uma com um resumo do que tem dentro",
            js("document.querySelectorAll('.prefs .pg.open').length") == 0 and js("getComputedStyle(document.querySelector('.prefs .pg .sw')).visibility") == "hidden"
            and "Voz ligada" in js("document.querySelector('.prefs .pg-s').textContent"), js("[...document.querySelectorAll('.prefs .pg-s')].map(e => e.textContent).join('|')"))
    topo = js("document.querySelector('.prefs .ptop').textContent") if pausa(0.8) else ""
    confere("à vista, sem abrir nada: a versão, os serviços e o modo leve", "Guardião" in topo and "Microfone:" in topo and "Claude:" in topo and "Modo leve" in topo
            and js("getComputedStyle(document.querySelector('.prefs .ptop .sw[aria-label=\"Modo leve\"]')).visibility") == "visible", topo)
    confere("as opções que saíram não aparecem mais", all(x not in texto(".prefs") for x in ("Animação de abertura", "Saudação ao abrir", "Vidro com desfoque", "Rever a abertura")), texto(".prefs")[:600])
    js("document.querySelectorAll('.prefs .pg-h')[0].click()")
    confere("clicar numa seção mostra as opções dela", pausa(0.7) and js("document.querySelectorAll('.prefs .pg.open').length") == 1
            and js("getComputedStyle(document.querySelector('.prefs .sw[aria-label=\"Voz do Guardião\"]')).visibility") == "visible")
    js("document.querySelectorAll('.prefs .pg-h')[2].click()")
    confere("abrir outra seção fecha a anterior", pausa(0.7) and js("[...document.querySelectorAll('.prefs .pg')].map(e => e.classList.contains('open') ? 1 : 0).join('')") == "001")
    js("document.querySelectorAll('.prefs .pg-h')[0].click()")
    pausa(0.7)
    confere("os sons viraram três controles: Sons, Volume e Som de digitação, e a velocidade da voz entrou",
            all(x in texto(".prefs .pg.open") for x in ("Sons", "Volume", "Som de digitação", "Velocidade da voz")) and "Movimento" not in texto(".prefs .pg.open") and "Toques" not in texto(".prefs .pg.open"), texto(".prefs .pg.open"))
    js("[...document.querySelectorAll('.prefs .seg-b')].find(b => b.textContent.trim() === '2x').click()")
    confere("velocidade escolhida nas preferências grava", pausa(0.6) and h.preferencias()["voz_velocidade"] == 2.0, h.preferencias()["voz_velocidade"])
    js("document.querySelector('.prefs .sw[aria-label=\"Sons\"]').click()")
    pr = h.preferencias() if pausa(0.8) else {}
    confere("desligar Sons desliga o grupo inteiro (cliques, telas, avisos, estados e trilha); a digitação tem chave própria",
            not pr["sons"] and not any(pr[k] for k in ("som_movimento", "som_toques", "som_avisos", "som_estados", "som_abertura")) and pr["som_digitacao"], pr)
    js("document.querySelector('.prefs .sw[aria-label=\"Sons\"]').click()")
    confere("e ligar religa todos", pausa(0.8) and all(h.preferencias()[k] for k in ("sons", "som_movimento", "som_toques", "som_avisos", "som_estados", "som_abertura")))
    h.salvar_preferencias({"voz_velocidade": 1.0})
    time.sleep(0.9)
    foto("20_preferencias")
    js("document.querySelector('.prefs .sw[aria-label=\"Voz do Guardião\"]').click()")
    confere("desligar a voz grava no servidor", pausa(0.8) and h.preferencias()["voz_guardiao"] is False)
    confere("sem voz, o estado convida a escrever", contem(".prefs", "silenciada") and js("document.querySelector('.ibtn.muted') !== null"))
    js("[...document.querySelectorAll('.prefs .seg-b')].find(b => b.textContent.includes('Relógio')).click()")
    confere("trocar a bolinha para o Relógio grava e troca o desenho", pausa(1.0) and h.preferencias()["bolinha"] == "A")
    js("document.querySelector('.prefs .dt-x').click()")
    js("[...document.querySelectorAll('.tab')][0].click()")
    time.sleep(1.6)
    foto("21_home_relogio_sem_voz")
    h.salvar_preferencias({"bolinha": "N", "voz_guardiao": True})

    # ---------------- revisão do plano e teclado
    h.bus.emitir("revisao", ativa=True)
    confere("revisão do plano abre a agenda ao lado", espera("document.querySelector('.detail.open') && document.querySelector('.detail').innerText.toLowerCase().includes('revisão do plano')", 5))
    h.bus.emitir("foco", ids=["b5"])
    confere("o bloco citado fica marcado na agenda", espera("document.querySelector('.detail .dl-r.cur')", 4))
    time.sleep(2.0)
    foto("22_revisao")
    h.bus.emitir("foco_fim")
    h.bus.emitir("revisao", ativa=False)
    confere("fim da revisão fecha a agenda", espera("!document.querySelector('.detail.open')", 5))
    espera("!document.querySelector('.scene.open')", 5)
    js("window.dispatchEvent(new KeyboardEvent('keydown', { key: '2' }))")
    confere("tecla 2 vai para o Dia", espera("document.querySelector('.gd').classList.contains('scr-dia')", 3))
    comandos()
    js("window.dispatchEvent(new KeyboardEvent('keydown', { key: ' ' }))")
    confere("barra de espaço aciona o microfone", pausa(0.6) and ("acionar", None) in comandos())
    h.bus.emitir("ui", cmd="tela", id="home")
    confere("comando de voz 'abre a home' troca de tela", espera("document.querySelector('.gd').classList.contains('scr-home')", 3))

    confere("nenhum erro de JavaScript na sessão toda", not nav.erros, nav.erros[:4])
finally:
    print("erros js:", nav.erros[:6])
    nav.fechar()

raise SystemExit(0 if B.placar() else 1)
