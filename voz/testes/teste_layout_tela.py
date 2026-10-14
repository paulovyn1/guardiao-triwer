"""Layout do painel (Edge sem janela): o palco usa a largura toda de uma janela larga, o painel de detalhes ganha espaço e não vaza para os lados,
as barras de rolagem têm a aparência do app e a revisão do plano não deixa cartão vazio na tela."""
import json
import sys
import time

import v2_base as B
from v2_base import confere, h

PORTA = 8796
tmp, relogio = B.preparar(PORTA, hora="09:50", prefs={"execucao_ao_abrir": False})  # o layout é medido na Home em conversa
LONGO = ("ATUALIZAÇÃO, proposta visual compartilhada no grupo da equipe.\n\nReferência: https://exemplo.com/" + "abcdefghij" * 14 + "\n\n"
         + "Ponto a conferir antes de fechar a entrega. " * 22)
detalhes = h.detalhes_extra
h.detalhes_extra = lambda ref: (lambda d: dict(d, linhas=list(d.get("linhas") or []) + [["Descrição no ClickUp", LONGO]]))(detalhes(ref) or {})

nav = B.Navegador(f"http://localhost:{PORTA}/v2/?semabertura=1", porta_cdp=9348, largura=1760, altura=900)
js, espera = nav.js, nav.espera


def pausa(seg):
    time.sleep(seg)
    assentar()  # o navegador de teste desenha por software e atrasa o primeiro quadro das transições: só vale medir depois que elas acabam
    return True


def caixa(seletor):
    return js("(() => { const e = document.querySelector(%s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height, r: r.right, b: r.bottom }; })()" % json.dumps(seletor))


def assentar(limite=10.0):
    """Espera as transições de tela (CSS, que acabam) terminarem: com o computador ocupado elas levam mais que o tempo fixo das pausas, e medir no meio
    de uma transição dava um tamanho diferente a cada rodada. As animações que nunca acabam (a bolinha, o fundo) não contam."""
    fim, zeros = time.time() + limite, 0
    while time.time() < fim:
        n = js("document.getAnimations().filter((a) => a.playState === 'running' && a.effect && a.effect.getTiming().iterations !== Infinity).length")
        zeros = zeros + 1 if not n else 0
        if zeros >= 3:
            return True
        time.sleep(0.15)
    return False


def tamanho(largura, altura):
    nav.cdp("Emulation.setDeviceMetricsOverride", {"width": largura, "height": altura, "deviceScaleFactor": 1, "mobile": False})
    js("window.dispatchEvent(new Event('resize')); 1")
    time.sleep(1.6)
    assentar()


def tela(n):
    js("document.querySelectorAll('.hd .tab')[%d].click()" % n)
    time.sleep(1.3)
    assentar()


try:
    confere("o painel abre", espera("document.querySelector('.gd .hd')", 20))
    pausa(2.5)
    # ---- janela larga: sem faixas pretas ----
    g = caixa(".gd")
    confere("numa janela de 1760 x 900 o palco ocupa a largura toda", js("document.querySelector('.gd').offsetWidth") == 1760 and abs(g["w"] - 1760) < 2 and abs(g["x"]) < 2, g)
    confere("a bolinha fica no centro da tela", abs(caixa(".orbw")["x"] + caixa(".orbw")["w"] / 2 - 880) < 30, caixa(".orbw"))

    # ---- barra do topo recolhida: só o ícone do menu fica à vista ----
    def barra():
        return js("(() => { const c = getComputedStyle(document.querySelector('.hd')); return c.visibility + ' ' + Math.round(+c.opacity); })()")

    def cursor(x, y):
        nav.cdp("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})

    pausa(2.6)  # logo depois de abrir a barra se mostra um instante e se recolhe
    m = caixa(".hdm")
    confere("passado o instante inicial, a barra do topo se recolhe", barra() == "hidden 0", barra())
    confere("fica só o ícone do menu, no canto de cima à direita", m and abs((1760 - m["r"]) - 28) < 2 and m["y"] < 20 and js("getComputedStyle(document.querySelector('.hdm')).display") != "none", m)
    d = caixa(".orbdate")
    confere("a data e a hora ficam acima da bolinha, centralizadas", d and abs(d["x"] + d["w"] / 2 - 880) < 8 and 150 < d["b"] < 236 and js("getComputedStyle(document.querySelector('.orbdate')).opacity") == "1"
            and js("/^[A-Z]{3} \\d{1,2} [A-Z]{3}09:5\\d$/i.test(document.querySelector('.orbdate').textContent)"), (d, js("document.querySelector('.orbdate').textContent")))
    confere("e saíram da barra do topo", js("!document.querySelector('.hd .clock')") and "09:5" not in js("document.querySelector('.hd').textContent"))
    cursor(700, 30)
    confere("com o cursor na faixa de cima a barra desce", pausa(1.1) and barra() == "visible 1" and abs(caixa(".hd")["y"]) < 1, (barra(), caixa(".hd")))
    cursor(700, 60)
    confere("e fica enquanto o cursor estiver nela", pausa(0.8) and barra() == "visible 1", barra())
    cursor(700, 420)
    confere("ao sair, ela se recolhe de novo", pausa(1.0) and barra() == "hidden 0", barra())
    cursor(1760 - 28 - 22, 36)
    confere("o cursor no ícone do menu também abre a barra", pausa(0.9) and barra() == "visible 1", barra())
    cursor(700, 420)
    pausa(1.0)
    js("document.querySelector('.hdm').click()")
    confere("um clique no ícone fixa a barra aberta (para tela de toque)", pausa(0.9) and barra() == "visible 1" and js("document.querySelector('.hdm').getAttribute('aria-expanded')") == "true", barra())
    js("document.querySelector('.st.cur .gline').click()")
    confere("um clique fora recolhe", pausa(1.0) and barra() == "hidden 0", barra())
    nav.foto("layout_home_recolhida")
    nav.foto("layout_home_largo")

    # ---- Dia: painel de detalhes ----
    tela(1)
    confere("a coluna do dia usa a largura a mais (1020 em vez de 700)", abs(caixa(".st.cur .dia-main")["w"] - 1020) < 3, caixa(".st.cur .dia-main"))
    js("document.querySelector('.st.cur [data-tid=\"b3\"] .r-body').click()")
    confere("o painel de detalhes abre", espera("document.querySelector('.detail.open')", 4))
    pausa(1.6)
    d, corpo, acoes, col = caixa(".detail"), caixa(".detail .dt-body"), caixa(".detail .dt-acts"), caixa(".st.cur .dia-main")
    confere("com espaço sobrando, o painel de detalhes fica mais largo (458 em vez de 330)", abs(d["w"] - 458) < 2, d)
    confere("a descrição longa aparece e o endereço comprido quebra a linha: nada vaza para os lados",
            "Ponto a conferir" in js("document.querySelector('.detail').innerText") and js("(() => { const e = document.querySelector('.detail .dt-body'); return e.scrollWidth <= e.clientWidth + 1; })()"),
            js("(() => { const e = document.querySelector('.detail .dt-body'); return [e.scrollWidth, e.clientWidth]; })()"))
    confere("o conteúdo rola dentro do painel e os botões ficam sempre à vista, embaixo",
            js("(() => { const e = document.querySelector('.detail .dt-body'); return e.scrollHeight > e.clientHeight + 40; })()") and acoes and acoes["b"] <= d["b"] + 1 and acoes["y"] >= corpo["b"] - 1, (corpo, acoes, d))
    confere("com o painel aberto a lista encolhe e não fica debaixo dele", abs(col["w"] - 874) < 3 and col["r"] <= d["x"] + 1 and d["x"] - col["r"] >= 12, (col, d))
    r = caixa(".detail .dt-body")
    with open(B.os.path.join(B.PASTA_PNG, "v2_layout_barra.png"), "wb") as f:  # recorte ampliado da barra de rolagem
        f.write(B.base64.b64decode(nav.cdp("Page.captureScreenshot", {"format": "png", "clip": {"x": r["r"] - 60, "y": r["y"], "width": 70, "height": 300, "scale": 3}})["data"]))
    confere("a barra de rolagem é a do app (fio fino, sem setas)", js("getComputedStyle(document.querySelector('.detail .dt-body'), '::-webkit-scrollbar').width") == "10px"
            and js("getComputedStyle(document.querySelector('.detail .dt-body'), '::-webkit-scrollbar-button').display") == "none",
            js("getComputedStyle(document.querySelector('.detail .dt-body'), '::-webkit-scrollbar').width"))
    confere("nenhuma regra antiga de barra de rolagem sobrou para brigar com a nova",
            js("[...document.querySelectorAll('.gd *')].filter((e) => { const c = getComputedStyle(e); return c.scrollbarWidth === 'thin' || (c.scrollbarColor && c.scrollbarColor !== 'auto'); }).length") == 0)
    nav.foto("layout_dia_detalhe")
    js("document.querySelector('.detail .dt-body').scrollTop = 600")
    pausa(0.4)
    nav.foto("layout_dia_detalhe_rolado")
    js("document.querySelector('.detail .dt-x').click()")
    pausa(0.8)

    # ---- outras telas na largura nova ----
    tela(2)
    nav.foto("layout_plan")
    confere("o planejador acompanha a largura", abs(caixa(".st.cur .pl")["w"] - 1020) < 3, caixa(".st.cur .pl"))
    tela(3)
    nav.foto("layout_cal")
    confere("a calibragem acompanha a largura", abs(caixa(".st.cur .cal")["w"] - 1348) < 3, caixa(".st.cur .cal"))
    tela(4)
    nav.foto("layout_pops")
    confere("os POPs acompanham a largura", abs(caixa(".st.cur .pops-main")["w"] - 1020) < 3, caixa(".st.cur .pops-main"))

    # ---- revisão do plano: nada de cartão vazio ----
    tela(0)
    h.bus.emitir("foco", ids=["b3"])  # ordem antiga: o destaque chegava antes do aviso de revisão
    h.bus.emitir("revisao", ativa=True)
    confere("a revisão abre a lista ao lado", espera("document.querySelector('.detail.open') && document.querySelector('.detail').innerText.toLowerCase().includes('revisão do plano')", 5))
    pausa(1.4)
    confere("nenhum cartão fica aberto no meio da tela (era o cartão vazio)", js("!document.querySelector('.scene.open')"), js("document.querySelector('.scene').className"))
    confere("o bloco citado fica destacado na lista", js("!!document.querySelector('.detail .dl-r.cur[data-tid=\"b3\"]')"))
    nav.foto("layout_revisao")
    h.bus.emitir("foco", ids=["b4"])
    pausa(1.0)
    confere("no bloco seguinte o destaque troca de linha, sem cartão", js("!!document.querySelector('.detail .dl-r.cur[data-tid=\"b4\"]') && !document.querySelector('.scene.open')"))
    h.bus.emitir("foco_fim")
    h.bus.emitir("revisao", ativa=False)
    pausa(1.0)
    # fora da revisão o cartão de foco continua existindo, e sempre com conteúdo
    h.bus.emitir("foco", ids=["b5"])
    confere("fora da revisão, o cartão de foco abre com o título da tarefa", espera("document.querySelector('.scene.open')", 4) and pausa(0.5) and "relatório mensal" in js("document.querySelector('.scene').innerText"),
            js("document.querySelector('.scene').innerText"))
    js("document.querySelector('.detail .dt-x') && 1")
    h.bus.emitir("foco_fim")
    pausa(2.6)
    # cartão aberto e fechado no mesmo instante: não pode sobrar a casca
    js("""(() => { const raiz = document.querySelector('.gd'); const k = Object.keys(raiz).find((x) => x.startsWith('__reactFiber')); let f = raiz[k];
      while (f && !(f.stateNode && f.stateNode.openScene)) f = f.return; if (!f) return false; const c = f.stateNode;
      c.openScene({ kind: 'focus', title: 'Cartão relâmpago', full: 'texto' }); c.closeScene(true); return true; })()""")
    pausa(1.2)
    confere("cartão aberto e fechado no mesmo instante não deixa casca vazia", js("!document.querySelector('.scene.open')"), js("document.querySelector('.scene').className"))

    # ---- janela no formato antigo: tudo como era ----
    tamanho(1440, 900)
    confere("numa janela 1440 x 900 o palco volta a 1440", js("document.querySelector('.gd').offsetWidth") == 1440, js("document.querySelector('.gd').offsetWidth"))
    tela(1)
    js("document.querySelector('.st.cur [data-tid=\"b3\"] .r-body').click()")
    pausa(1.6)
    confere("e as medidas originais valem: coluna de 700 e painel de 330", abs(caixa(".st.cur .dia-main")["w"] - 700) < 2 and abs(caixa(".detail")["w"] - 330) < 2, (caixa(".st.cur .dia-main"), caixa(".detail")))
    nav.foto("layout_dia_detalhe_1440")
    # ---- ultrawide: o fundo e o topo vão de ponta a ponta e o conteúdo fica num bloco centralizado ----
    # Daqui em diante o que se mede é a posição final das coisas, não o movimento: numa janela deste tamanho o Edge sem janela
    # às vezes quase não desenha quadros e as transições ficam paradas no meio do caminho, então elas são desligadas.
    js("(() => { const e = document.createElement('style'); e.textContent = '.gd,.gd *{transition:none!important}'; document.head.appendChild(e); return 1; })()")
    tamanho(2400, 900)
    g, col, d, lado = caixa(".gd"), caixa(".st.cur .dia-main"), caixa(".detail"), caixa(".gcol")
    confere("numa janela de 2400 x 900 o palco ocupa a largura toda, sem faixas pretas", js("document.querySelector('.gd').offsetWidth") == 2400 and abs(g["x"]) < 2 and abs(g["w"] - 2400) < 2, g)
    confere("o conteúdo não estica sem fim: fica num bloco de 1920, com margens iguais dos dois lados", abs(lado["x"] - 264) < 3 and abs((2400 - d["r"]) - 264) < 3, (lado, d))
    confere("no bloco, a lista e o painel de detalhes ficam lado a lado no tamanho máximo", abs(d["w"] - 460) < 2 and col["r"] <= d["x"] + 1 and abs(col["x"] - (lado["r"] + 22)) < 30, (col, d))
    confere("a marca e os botões do topo acompanham o bloco do conteúdo", abs(caixa(".hd .brand")["x"] - 272) < 3 and abs((2400 - caixa(".hd .hd-r")["r"]) - 318) < 3 and abs((2400 - caixa(".hdm")["r"]) - 268) < 3, (caixa(".hd .brand"), caixa(".hd .hd-r"), caixa(".hdm")))
    confere("a barra do topo e o fundo vão de ponta a ponta", abs(caixa(".hd")["w"] - 2400) < 2 and abs(caixa(".bgc")["w"] - 2400) < 2, (caixa(".hd"), caixa(".bgc")))
    nav.foto("layout_ultrawide_dia")
    js("document.querySelector('.detail .dt-x').click()")
    tela(0)
    # a bolinha viaja da coluna até o centro: espera a viagem acabar em vez de contar um tempo fixo (numa janela deste tamanho o Edge sem janela às vezes demora)
    confere("na Home a bolinha continua no centro da tela", espera("(() => { const r = document.querySelector('.orbw').getBoundingClientRect(); return Math.abs(r.left + r.width / 2 - 1200) < 30; })()", 8),
            (caixa(".orbw"), js("document.querySelector('.gd').className")))
    nav.foto("layout_ultrawide_home")
    tamanho(3440, 1440)
    g = caixa(".gd")
    confere("num monitor 21:9 (3440 x 1440) a janela inteira é usada", abs(g["x"]) < 3 and abs(g["w"] - 3440) < 6 and abs(g["h"] - 1440) < 3, g)
    tamanho(5120, 1440)
    g = caixa(".gd")
    confere("num monitor 32:9 (5120 x 1440) também", abs(g["x"]) < 3 and abs(g["w"] - 5120) < 6 and abs(g["h"] - 1440) < 3, g)
    nav.foto("layout_32x9_home")
    confere("sem erro de JavaScript", not nav.erros, nav.erros[:3])
finally:
    nav.fechar()
print("erros js:", nav.erros[:3])
sys.exit(0 if B.placar() else 1)
