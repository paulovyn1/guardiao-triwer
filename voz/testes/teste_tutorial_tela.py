"""Tutorial guiado na tela (Edge sem janela): o convite da instalação nova, recusar, começar pelas Preferências, os 14 cartões (cada um no lugar certo, com o destaque
fora do cartão e dentro do palco), a prática de escrever e de falar, as Preferências abertas grupo a grupo, voltar, Esc, continuar de onde parou, concluir com a conquista,
a dica na hora certa e a fala do tour que não entra na conversa. Capturas em capturas\\v2_tour_*.png."""
import json
import os
import queue
import time

import v2_base as B
from v2_base import confere, h

import tutorial as tut

PORTA = 8798
tmp, relogio = B.preparar(PORTA, hora="09:50")
ESTADO = os.path.join(tmp, "tutorial_estado.json")
PASSOS = tut.texto()["passos"]
NOME = "Guardião"


def estado(**dados):
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump(dados, f)


def comandos():
    saida = []
    while True:
        try:
            saida.append(h.bus.comandos.get_nowait())
        except queue.Empty:
            return saida


estado(convidar=True, criado_em="2026-10-22")
nav = B.Navegador(f"http://localhost:{PORTA}/v2/?semabertura=1", porta_cdp=9351)
js, espera = nav.js, nav.espera


def pausa(seg):
    time.sleep(seg)
    return True


def cartao():
    return json.loads(js("""(() => { const c = document.querySelector('.tour-card'), hl = document.querySelector('.tour-hl'); if (!c) return JSON.stringify({}); const r = (e) => { const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
      return JSON.stringify({ on: c.classList.contains('on'), kicker: c.querySelector('.tk span').textContent, titulo: c.querySelector('h3').textContent, texto: c.querySelector('.tx').textContent,
        nobox: hl.classList.contains('nobox'), hl: r(hl), card: r(c), btns: [...c.querySelectorAll('.tacts button')].map((b) => b.textContent.trim()), itens: c.querySelectorAll('.tit div').length,
        ok: (c.querySelector('.tok') || {}).textContent || '', aviso: (c.querySelector('.twarn') || {}).textContent || '', sair: !!c.querySelector('.tk button') }); })()""") or "{}")


def estavel(ate=15, destaque=False):
    """Espera o destaque e o cartão pararem de se mexer: a aba nova entra animada e o cartão se reposiciona a cada 250 ms."""
    fim, ant = time.time() + ate, None
    while time.time() < fim:
        c = cartao()
        atual = (c.get("hl"), c.get("card"), c.get("nobox"))
        if atual == ant and not (destaque and c.get("nobox")):
            return c
        ant = atual
        time.sleep(0.45)
    return cartao()


def cartao_pronto(titulo=None, ate=6):
    ate = max(ate, 12)  # computador ocupado (suíte inteira rodando) atrasa o desenho da tela
    return espera("(() => { const c = document.querySelector('.tour-card.on'); return c && %s; })()" % ("c.querySelector('h3').textContent === %s" % json.dumps(titulo) if titulo else "true"), ate)


def clicar_botao_do_cartao(texto):
    return js("(() => { const b = [...document.querySelectorAll('.tour-card .tacts button')].find((x) => x.textContent.trim() === %s); if (!b) return false; b.click(); return true; })()" % json.dumps(texto))


def sobrepoe(a, b, folga=2):
    return not (a[2] <= b[0] + folga or b[2] <= a[0] + folga or a[3] <= b[1] + folga or b[3] <= a[1] + folga)


def titulo_esperado(c):
    return c["titulo"].replace("{agente}", NOME)


try:
    confere("o painel abre", espera("document.querySelector('.gd .hd')", 20))

    # ---------- o convite (instalação nova) ----------
    confere("instalação nova: logo depois da abertura aparece o convite do tour, com os dois botões", cartao_pronto("Quer um tour de 4 minutos?", 40))
    c = cartao()
    confere("o convite diz o que o tour mostra e não tem o link de sair", c["kicker"].upper() == "TOUR GUIADO" and "Preferências" in c["texto"] and c["btns"] == ["Começar o tour", "Agora não"] and not c["sair"], c)
    confere("o convite fica no meio da tela, dentro do palco", 0 <= c["card"][0] and c["card"][2] <= 1440 and 0 <= c["card"][1] and c["card"][3] <= 900 and abs((c["card"][0] + c["card"][2]) / 2 - 720) < 40, c["card"])
    pedidos = []

    def pediu_a_voz():  # a voz sai 650 ms depois de o cartão aparecer
        pedidos.extend(comandos())
        return any(x[0] == "narrar" for x in pedidos)

    confere("o servidor contou o convite mostrado e a voz do convite foi pedida", B.esperar_py(lambda: tut.estado(tmp)["convites"] == 1, 3) and B.esperar_py(pediu_a_voz, 4), pedidos)
    pausa(0.5)
    nav.foto("tour_convite")
    clicar_botao_do_cartao("Agora não")
    confere("agora não: o cartão some e o painel avisa onde o tour fica", espera("!document.querySelector('.tour-card.on')", 8) and "Rever o tutorial" in (js("document.querySelector('.toasts').innerText") or ""))
    confere("a recusa fica guardada: o convite não volta", B.esperar_py(lambda: tut.estado(tmp)["recusado"] is True, 3) and tut.convidar(tmp) is False)

    # ---------- começar pelas Preferências ----------
    js("document.querySelector('.ibtn[aria-label=\"Preferências\"]').click()")
    confere("as preferências abrem com o botão Rever o tutorial no alto", espera("document.querySelector('.prefs.open')", 3) and "Rever o tutorial" in (js("document.querySelector('.prefs .ptop').innerText") or ""))
    js("(() => { const r = [...document.querySelectorAll('.prefs .ptop .pr')].find((x) => x.innerText.includes('Rever o tutorial')); r.querySelector('button').click(); })()")
    confere("o botão começa o tour no passo 1 de 9 (as preferências se fecham)", cartao_pronto("Bem-vindo ao Guardião", 5) and cartao()["kicker"].upper() == "PASSO 1 DE 9" and js("!document.querySelector('.prefs.open')"), cartao())
    confere("o servidor guarda que o tour começou", B.esperar_py(lambda: bool(tut.estado(tmp)["iniciado_em"]), 3))
    c = cartao()
    confere("a boas-vindas fica no meio, sem destaque (a tela inteira escurece), com Sair do tour e só o Próximo", c["nobox"] and c["sair"] and c["btns"] == ["Próximo"], c)
    nav.foto("tour_boas_vindas")

    # ---------- os cartões, um por um ----------
    destaque_esperado = {x["alvo"] for x in PASSOS if x.get("alvo")} - {"aprovar"}  # a barra de aprovar só existe quando há plano novo esperando
    vistos = []
    for i, passo in enumerate(PASSOS):
        titulo = titulo_esperado(passo)
        if i > 0:
            rotulo = cartao()["btns"][-1]  # Próximo, ou Pular este passo se a prática do cartão não foi feita
            confere(f"cartão {i}: o botão {rotulo} leva ao cartão {i + 1}", clicar_botao_do_cartao(rotulo) and cartao_pronto(titulo, 6), (titulo, cartao()))
        quer_destaque = passo.get("alvo") in destaque_esperado and passo.get("lado") != "centro"
        c = estavel(destaque=quer_destaque)
        vistos.append(c["titulo"])
        dentro = 0 <= c["card"][0] and c["card"][2] <= 1440 and 0 <= c["card"][1] and c["card"][3] <= 900
        confere(f"cartão {i + 1} ({passo['id']}): kicker 'Passo {passo['passo']} de 9', dentro do palco e com o texto do tutorial.json",
                c["kicker"].upper() == f"PASSO {passo['passo']} DE 9" and dentro and c["texto"].strip() == passo["texto"].replace("{agente}", NOME).strip() and c["itens"] == len(passo.get("itens") or []), c)
        if quer_destaque:
            confere(f"cartão {i + 1}: o destaque '{passo['alvo']}' aparece e não fica por baixo do cartão", not c["nobox"] and not sobrepoe(c["hl"], c["card"]), (c["hl"], c["card"], c["nobox"], js("JSON.stringify({ w: innerWidth, h: innerHeight, gd: window.GD_W, tela: (document.querySelector('.st.cur') || {}).ariaLabel, alvos: [...document.querySelectorAll('[data-tour]')].filter((e) => e.getBoundingClientRect().width > 0 && !e.closest('[aria-hidden=\"true\"]')).map((e) => e.getAttribute('data-tour')) })")))
        if passo.get("tela"):
            rot = {"home": "Home", "dia": "Dia", "plan": "Planejador", "cal": "Calibragem", "pops": "POPs"}[passo["tela"]]
            confere(f"cartão {i + 1}: o tour abre a aba {rot}", js("(() => { const s = document.querySelector('section.st[aria-label=%s]'); return !!s && s.getAttribute('aria-hidden') !== 'true'; })()" % json.dumps(rot)), rot)
        if passo.get("prefs"):
            confere(f"cartão {i + 1}: as Preferências estão abertas" + (f" com a seção {passo['grupo']} aberta" if passo.get("grupo") else ""),
                    js("!!document.querySelector('.prefs.open')") and (not passo.get("grupo") or js("!!document.querySelector('.prefs .pg.open')")), passo.get("grupo"))
        if passo["id"] == "escrever":
            c = cartao()
            confere("escrever: antes da prática o botão é Pular este passo e não há 'isso' na tela", c["btns"][-1] == "Pular este passo" and not c["ok"], c)
            nav.foto("tour_escrever")
            comandos()
            js("""(() => { const e = [...document.querySelectorAll('[data-tour="campo"]')].find((x) => !x.closest('[aria-hidden="true"]') && x.getBoundingClientRect().width > 0); const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
              set.call(e, 'o que eu faço agora?'); e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); })()""")
            confere("escrever de verdade: a mensagem vai para o guardião e o cartão confirma, com o botão Próximo", espera("document.querySelector('.tour-card .tok')", 8)
                    and ("perguntar", "o que eu faço agora?") in comandos() and cartao()["btns"][-1] == "Próximo", cartao())
        if passo["id"] == "microfone":
            c = cartao()
            confere("microfone: com microfone e chave de transcrição, nenhum aviso de problema", not c["aviso"] and c["btns"][-1] == "Pular este passo", c)
            comandos()
            js("[...document.querySelectorAll('[data-tour=\"mic\"]')].find((x) => !x.closest('[aria-hidden=\"true\"]') && x.getBoundingClientRect().width > 0).click()")
            confere("falar de verdade: o clique no microfone abre a escuta e o cartão confirma", espera("document.querySelector('.tour-card .tok')", 8) and ("acionar", None) in comandos(), cartao())
            h.bus.emitir("estado", v="aguardando")
        if passo["id"] == "calar":
            nav.foto("tour_menu_voz")
        if passo["id"] == "prefs_som":
            nav.foto("tour_prefs_som")
        if passo["id"] == "dia":
            nav.foto("tour_dia")
        if passo["id"] == "calibragem":
            nav.foto("tour_calibragem")
        if passo["id"] == "fim":
            c = cartao()
            confere("o último cartão tem o botão Concluir o tour e os atalhos do dia a dia", c["btns"] == ["Voltar", "Concluir o tour"] or c["btns"][-1] == "Concluir o tour", c)
            nav.foto("tour_fim")

    confere("o tour passou pelos 14 cartões, na ordem do tutorial.json", vistos == [titulo_esperado(p) for p in PASSOS], vistos)

    # ---------- voltar, Esc, continuar ----------
    clicar_botao_do_cartao("Voltar")
    confere("Voltar mostra o cartão anterior", cartao_pronto(titulo_esperado(PASSOS[-2]), 5))
    js("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    confere("Esc sai do tour", espera("!document.querySelector('.tour-card.on')", 8))
    confere("sair de propósito não deixa o tour para continuar", B.esperar_py(lambda: tut.continuar(tmp) is False, 3))
    estado(convidar=False, aceito=True, iniciado_em="2026-10-22", cartao=5)
    t0 = time.time()
    nav.abrir(f"http://localhost:{PORTA}/v2/?semabertura=1")
    confere("fechou a janela no meio do tour: ao abrir de novo o painel oferece continuar", cartao_pronto("Continuar o tour?", 60), cartao())
    print(f"   (a oferta apareceu {time.time() - t0:.1f} s depois de abrir)")
    c = cartao()
    confere("a oferta de continuar tem os dois botões", c["btns"] == ["Continuar de onde parei", "Agora não"], c)
    clicar_botao_do_cartao("Continuar de onde parei")
    confere("continuar abre o cartão em que parou", cartao_pronto(titulo_esperado(PASSOS[5]), 6) and cartao()["kicker"].upper() == "PASSO 5 DE 9", cartao())

    # ---------- concluir e a conquista ----------
    for _ in range(len(PASSOS) - 1 - 5):
        clicar_botao_do_cartao("Próximo")
        pausa(0.25)
    confere("de volta ao último cartão", cartao_pronto(titulo_esperado(PASSOS[-1]), 6))
    comandos()
    clicar_botao_do_cartao("Concluir o tour")
    confere("concluir: o cartão some, a pessoa volta para a Home e é avisada", espera("!document.querySelector('.tour-card.on')", 8) and "Tour concluído" in (js("document.querySelector('.toasts').innerText") or ""))
    confere("o servidor guarda a conclusão", B.esperar_py(lambda: bool(tut.estado(tmp)["concluido"]), 3))
    cq = None
    for _ in range(20):
        cq = next((x for x in (B.requests.get(f"http://localhost:{PORTA}/calibragem", timeout=5).json().get("conquistas") or {}).get("lista", []) if x["id"] == "primeiros_passos"), None)
        if cq and cq.get("desbloqueada"):
            break
        pausa(0.2)
    confere("a conquista Primeiros passos aparece desbloqueada na aba Conquistas", cq and cq.get("desbloqueada"), cq)

    # ---------- dica na hora certa ----------
    js("[...document.querySelectorAll('.tabs button, .tab')].find((x) => x.textContent.trim().toUpperCase().startsWith('POPS')).click()")
    confere("depois do tour, a primeira ida a POPs mostra a dica uma vez só", espera("document.querySelector('.toasts').innerText.includes('POP é um processo pronto')", 5))

    # ---------- a fala do tour não entra na conversa ----------
    h.bus.emitir("guardiao_texto", texto="FALA-DO-TOUR", tutorial=True)
    h.bus.emitir("guardiao_fim", texto="FALA-DO-TOUR", tutorial=True)
    pausa(0.8)
    confere("o texto da narração do tour não vira mensagem na conversa", "FALA-DO-TOUR" not in (js("document.querySelector('.gd').textContent") or ""))
    h.bus.emitir("guardiao_texto", texto="RESPOSTA-NORMAL")
    h.bus.emitir("guardiao_fim", texto="RESPOSTA-NORMAL")
    confere("a resposta normal continua aparecendo", espera("document.querySelector('.gd').textContent.includes('RESPOSTA-NORMAL')", 4))

    # ---------- o pedido por voz abre o tour, e quem já usava o guardião não recebe convite ----------
    h.bus.emitir("ui", cmd="tutorial")
    confere("o comando de voz 'tutorial' abre o tour", cartao_pronto("Bem-vindo ao Guardião", 6))
    js("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    espera("!document.querySelector('.tour-card.on')", 8)
    os.remove(ESTADO)
    nav.abrir(f"http://localhost:{PORTA}/v2/?semabertura=1")
    espera("document.querySelector('.gd .hd')", 15)
    pausa(3.2)
    confere("quem já usava o guardião (sem o arquivo de estado) não recebe convite", js("!document.querySelector('.tour-card.on')"))
finally:
    erros = nav.erros
    nav.fechar()

confere("sem erro de JavaScript na tela", not erros, erros[:3])
ok = B.placar()
raise SystemExit(0 if ok else 1)
