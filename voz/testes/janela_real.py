"""Conferência manual da janela compacta com o Edge de verdade (abre uma janelinha por alguns segundos no canto da tela).
Mostra o título que o Windows enxerga, se ficou por cima das outras, o tamanho e a posição. Não mexe na janela grande do guardião.
Uso: python janela_real.py"""
import os
import subprocess
import sys
import tempfile
import time

import v2_base as B
from v2_base import confere

import guardiao_janela as jan

PORTA = 8795
tmp, relogio = B.preparar(PORTA, hora="09:50")
respostas = []
jan.rota = lambda dados: (respostas.append((dados, jan.fixar_compacta(dados.get("dw", 16), dados.get("dh", 39), principal=None, minimizar=False)
                                              if dados.get("acao") == "compacta" else {"ok": True})), respostas[-1][1])[1]

edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(edge):
    edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
perfil = tempfile.mkdtemp(prefix="gv_edge_janela_")
antes = {h for h, _ in jan.janelas()}
proc = subprocess.Popen([edge, f"--app=http://localhost:{PORTA}/v2/mini.html", f"--user-data-dir={perfil}", "--window-size=1100,800", "--no-first-run", "--no-default-browser-check",
                         "--autoplay-policy=no-user-gesture-required", "--mute-audio"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    fim = time.time() + 25
    while time.time() < fim and not any(d.get("acao") == "compacta" for d, _ in respostas):
        time.sleep(0.3)
    time.sleep(2.0)
    novas = [(h, t) for h, t in jan.janelas() if h not in antes]
    print("janelas novas do Edge:", novas)
    print("pedidos da página:", respostas)
    confere("a página pediu para ser fixada", any(d.get("acao") == "compacta" for d, _ in respostas), respostas)
    hwnd = jan._achar(jan.TITULO_MINI, jan.CLASSE)
    confere("o Windows enxerga a janela pelo título 'Guardião compacto'", bool(hwnd), novas)
    if hwnd:
        anterior = jan._em_pixels_reais()
        r = jan._retangulo(hwnd)
        info = jan._MONITORINFO()
        info.cbSize = jan.ctypes.sizeof(info)
        jan._u.GetMonitorInfoW(jan._u.MonitorFromWindow(hwnd, 2), jan.ctypes.byref(info))
        escala = jan._u.GetDpiForWindow(hwnd) / 96.0
        jan._voltar_modo(anterior)
        print(f"retângulo: {r.left},{r.top} a {r.right},{r.bottom} ({r.right - r.left} x {r.bottom - r.top}); área de trabalho até {info.rcWork.right},{info.rcWork.bottom}; escala {escala}")
        confere("fica por cima das outras janelas", jan.por_cima(hwnd))
        confere("largura perto de 320 mais a moldura", 320 * escala <= r.right - r.left <= 380 * escala, r.right - r.left)
        confere("altura perto de 420 mais a moldura", 420 * escala <= r.bottom - r.top <= 560 * escala, r.bottom - r.top)
        confere("encostada no canto inferior direito", 0 <= info.rcWork.right - r.right + 12 * escala <= 44 * escala and 0 <= info.rcWork.bottom - r.bottom + 12 * escala <= 44 * escala,
                (info.rcWork.right - r.right, info.rcWork.bottom - r.bottom))
finally:
    for h, t in jan.janelas():
        if h not in antes and t.startswith(jan.TITULO_MINI):
            jan._u.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
    time.sleep(0.8)
    try:
        proc.terminate()
    except Exception:
        pass
sys.exit(0 if B.placar() else 1)
