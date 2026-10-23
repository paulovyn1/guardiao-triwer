"""Anexos na tela (Edge sem janela): escolher arquivo pelo botão do clipe, colar um print (Ctrl+V), arrastar para a janela, a miniatura da imagem, tirar um anexo,
mandar só com o anexo, o balão da pessoa com o nome dos arquivos e o aviso no Codex. Capturas em capturas\\v2_anexos_*.png."""
import json
import os
import queue
import tempfile
import time

import v2_base as B
from v2_base import confere, h

PORTA = 8803
tmp, relogio = B.preparar(PORTA, hora="09:50", prefs={"execucao_ao_abrir": False})
import anexos  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a02d4b390000000049454e44ae426082")
nav = B.Navegador(f"http://localhost:{PORTA}/v2/?semabertura=1", porta_cdp=9353)
js, espera = nav.js, nav.espera
pasta = tempfile.mkdtemp(prefix="gv_arquivos_")
foto = os.path.join(pasta, "print da reunião.png")
pdf = os.path.join(pasta, "proposta.pdf")
open(foto, "wb").write(PNG)
open(pdf, "wb").write(b"%PDF-1.4 teste de proposta")


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


def chips():
    return json.loads(js("""JSON.stringify([...document.querySelectorAll('.anx:not(:empty)')].filter((c) => !c.closest('[aria-hidden="true"]') && c.getBoundingClientRect().width > 0).slice(0, 1)
      .flatMap((c) => [...c.querySelectorAll('.anx-i')].map((i) => ({ nome: i.querySelector('.anx-n').textContent, info: i.querySelector('.anx-s').textContent, img: !!i.querySelector('img'), cls: i.className }))))""") or "[]")


def espera_chips(n, ate=8):
    """Espera a faixa de anexos que a pessoa vê ter n itens (o mesmo texto existe na Home, no planejador e na coluna: só conta o visível)."""
    fim = time.time() + ate
    while time.time() < fim:
        if len(chips()) == n:
            return True
        time.sleep(0.2)
    return len(chips()) == n


def nomes_na_fila():
    return sorted(a["nome"] for a in anexos.lista())


def escolher_arquivos(caminhos):
    doc = nav.cdp("DOM.getDocument", {"depth": 1})
    no = nav.cdp("DOM.querySelector", {"nodeId": doc["root"]["nodeId"], "selector": ".anx-file"})
    nav.cdp("DOM.setFileInputFiles", {"nodeId": no["nodeId"], "files": caminhos})


try:
    confere("o painel abre", espera("document.querySelector('.gd .hd')", 20))
    pausa(1.5)
    confere("o botão do clipe aparece ao lado do campo de escrever", js("[...document.querySelectorAll('.clip')].some((b) => !b.closest('[aria-hidden=\"true\"]') && b.getBoundingClientRect().width > 0)"))
    confere("sem anexo não há faixa de anexos", chips() == [])

    # ---------- escolher arquivos ----------
    escolher_arquivos([foto, pdf])
    confere("escolher uma imagem e um PDF: os dois aparecem como anexos", espera_chips(2), chips())
    pausa(0.8)
    c = {i["nome"]: i for i in chips()}
    confere("a imagem tem miniatura e o PDF tem o ícone de arquivo, com o tamanho", len(c) == 2 and c["print da reunião.png"]["img"] and not c["proposta.pdf"]["img"] and "KB" in c["proposta.pdf"]["info"], c)
    confere("a miniatura de verdade carrega do servidor", js("(() => { const i = [...document.querySelectorAll('.anx-i img')][0]; return !!i && i.complete && i.naturalWidth > 0; })()"))
    confere("os arquivos estão na fila do servidor, que espera a próxima pergunta", nomes_na_fila() == ["print da reunião.png", "proposta.pdf"], anexos.lista())
    nav.foto("anexos_fila")

    # ---------- tirar um ----------
    js("[...document.querySelectorAll('.anx-i')].find((i) => i.textContent.includes('proposta')).querySelector('.anx-x').click()")
    confere("tirar um anexo: some da tela e da fila do servidor", espera_chips(1, 5) and B.esperar_py(lambda: nomes_na_fila() == ["print da reunião.png"], 4), anexos.lista())

    # ---------- colar um print (Ctrl+V) ----------
    js("""(() => { const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137])], 'image.png', { type: 'image/png' }));
      window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); })()""")
    confere("colar um print (Ctrl+V) com uma imagem anexa direto na conversa", espera_chips(2) and any(a["nome"] == "image.png" for a in anexos.lista()), (chips(), anexos.lista()))
    js("""(() => { const dt = new DataTransfer(); dt.setData('text/plain', 'só texto'); window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); })()""")
    pausa(0.5)
    confere("colar só texto não anexa nada", len(chips()) == 2)

    # ---------- arrastar para a janela ----------
    js("""(() => { const dt = new DataTransfer(); dt.items.add(new File(['ola'], 'notas da reunião.txt', { type: 'text/plain' }));
      window.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true })); })()""")
    confere("arrastando um arquivo para a janela aparece o aviso de soltar", espera("document.querySelector('.anx-drop.on')", 4))
    nav.foto("anexos_soltar")
    js("""(() => { const dt = new DataTransfer(); dt.items.add(new File(['ola'], 'notas da reunião.txt', { type: 'text/plain' }));
      window.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); })()""")
    confere("soltar o arquivo anexa e tira o aviso", espera_chips(3) and espera("!document.querySelector('.anx-drop.on')", 4), chips())
    js("""(() => { const dt = new DataTransfer(); dt.setData('text/plain', 'x'); window.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true })); })()""")
    pausa(0.3)
    confere("arrastar só texto (sem arquivo) não mostra o aviso", js("!document.querySelector('.anx-drop.on')"))

    # ---------- enviar só com os anexos ----------
    comandos()
    js("""(() => { const e = [...document.querySelectorAll('[data-tour="campo"]')].find((x) => !x.closest('[aria-hidden="true"]') && x.getBoundingClientRect().width > 0);
      e.focus(); e.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); })()""")
    pausa(0.6)
    enviados = comandos()
    confere("enviar sem escrever nada manda uma frase pedindo para ver os anexos", ("perguntar", "Veja o que anexei.") in enviados, enviados)

    # o guardião consumiu a fila: a tela esvazia e o balão da pessoa leva os nomes
    h.bus.emitir("voce", texto="Veja o que anexei.")
    h.bus.emitir("anexos", itens=[])
    h.bus.emitir("anexos_enviados", nomes=["print da reunião.png", "image.png", "notas da reunião.txt"])
    confere("a pergunta seguiu: a faixa de anexos esvazia", espera_chips(0, 5))
    confere("o balão da pessoa mostra o nome dos arquivos que foram junto", espera("[...document.querySelectorAll('.m-anx span')].some((s) => s.textContent.includes('print da reunião.png'))", 5))
    nav.foto("anexos_balao")

    # ---------- erro e Codex ----------
    anexos.PENDENTES.clear()
    js("""(() => { const dt = new DataTransfer(); dt.items.add(new File([], 'vazio.txt', { type: 'text/plain' })); window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); })()""")
    confere("arquivo vazio: aviso com o motivo e nada na fila", espera("document.querySelector('.toasts').innerText.includes('vazio')", 5) and len(chips()) == 0)
    h.salvar_preferencias({"provedor_ia": "codex"})
    pausa(1.0)
    confere("no Codex o clipe fica apagado", js("[...document.querySelectorAll('.clip')].some((b) => b.classList.contains('off'))"))
    js("[...document.querySelectorAll('.clip')].find((b) => !b.closest('[aria-hidden=\"true\"]') && b.getBoundingClientRect().width > 0).click()")
    confere("clicar no clipe com o Codex explica que anexo é do Claude", espera("document.querySelector('.toasts').innerText.includes('Anexos funcionam com o Claude')", 5))
    js("""(() => { const dt = new DataTransfer(); dt.items.add(new File(['x'], 'a.txt', { type: 'text/plain' })); window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); })()""")
    pausa(0.6)
    confere("no Codex colar arquivo também não anexa", not anexos.PENDENTES)
    h.salvar_preferencias({"provedor_ia": "claude"})
finally:
    erros = nav.erros
    nav.fechar()

confere("sem erro de JavaScript na tela", not erros, erros[:3])
ok = B.placar()
raise SystemExit(0 if ok else 1)
