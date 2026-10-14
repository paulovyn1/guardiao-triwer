# O aviso do guardião na tela: uma janela própria, preta e dourada como o painel, no canto de baixo da tela.
# Antes o aviso era uma notificação do Windows disparada pelo PowerShell, e o Windows punha nela o nome e o ícone do "Windows PowerShell"
# (pedido de 14/10/2026: um aviso com a cara do guardião).
#
# Não rouba o foco: quem está digitando continua digitando (janela que não se ativa, sem botão na barra de tarefas). Some sozinho depois
# de um tempo (parado enquanto o mouse está em cima), um aviso novo substitui o anterior, e o som respeita as preferências do painel.
# Com o Windows em apresentação ou com um jogo/vídeo em tela cheia, não aparece: --checar diz isso a quem chama, que usa a notificação
# comum do Windows (o Windows a guarda para depois).
#
# Uso: pythonw popup.py --titulo "Agora: ..." --texto "Comece por: ..." [--kicker "Agora"] [--tag "até 10:20"] [--bloco b3] [--segundos 60]
#      pythonw popup.py --checar   (sai com 0 se pode mostrar, 3 se a pessoa está em apresentação ou tela cheia)
import argparse
import ctypes
import json
import math
import os
import struct
import sys
import tempfile
import threading
import time
import urllib.request
import wave
from ctypes import wintypes

BASE = os.path.dirname(os.path.abspath(__file__))
TITULO_JANELA = "Guardião · aviso"
PORTA = 8767
COR = {"fundo": "#0d0f12", "borda": "#3a2c12", "ouro": "#b28431", "ouro2": "#e3b964", "marfim": "#f3ecdc", "marfim2": "#b9b09c", "marfim3": "#8a826f",
       "botao": "#e3b964", "botao_txt": "#15110a", "fantasma": "#171a20"}
LARGURA = 392   # em pontos de tela (a janela escala com o DPI do monitor)
MARGEM = 16

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80, 0x08000000, 0x8
WM_CLOSE = 0x0010


def estado_do_windows():
    """SHQueryUserNotificationState: 2 tela cheia, 3 jogo/vídeo em tela cheia, 4 apresentação, 5 aceita avisos, 6 app em modo silencioso."""
    try:
        estado = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(estado)) == 0:
            return estado.value
    except Exception:
        pass
    return 5


def pode_mostrar():
    return estado_do_windows() not in (2, 3, 4)


def fechar_aviso_anterior():
    """Um aviso novo substitui o que ainda está na tela."""
    hwnd = user32.FindWindowW(None, TITULO_JANELA)
    while hwnd:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(0.15)
        proximo = user32.FindWindowW(None, TITULO_JANELA)
        if proximo == hwnd:
            break
        hwnd = proximo


def area_de_trabalho():
    """A área útil da tela principal (sem a barra de tarefas), em pixels."""
    r = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return r.left, r.top, r.right, r.bottom


def preferencias():
    try:
        with open(os.path.join(BASE, "preferencias.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def tocar_som():
    """Dois toques curtos e suaves, gerados aqui (sem arquivo de som), no volume das preferências do painel."""
    p = preferencias()
    if p.get("sons") is False or p.get("som_avisos") is False or os.environ.get("GUARDIAO_POPUP_MUDO"):  # os testes não fazem barulho
        return
    volume = float(p.get("volume", 0.7) if isinstance(p.get("volume", 0.7), (int, float)) else 0.7)
    if volume <= 0:
        return
    try:
        import winsound
        taxa, amostras = 24000, []
        for freq, ini, dur in ((880.0, 0.0, 0.32), (1318.5, 0.11, 0.42)):
            for i in range(int(taxa * (ini + dur))):
                t = i / taxa
                if len(amostras) <= i:
                    amostras.append(0.0)
                if t >= ini:
                    u = t - ini
                    amostras[i] += math.sin(2 * math.pi * freq * u) * math.exp(-u * 9) * min(1.0, u * 300) * 0.22 * volume
        arq = os.path.join(tempfile.gettempdir(), "guardiao_aviso.wav")
        with wave.open(arq, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(taxa)
            w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, a)) * 32000)) for a in amostras))
        winsound.PlaySound(arq, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


def _post(caminho, corpo):
    req = urllib.request.Request(f"http://localhost:{PORTA}{caminho}", data=json.dumps(corpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def janela_do_painel():
    """A janela do painel já aberta (título "Guardião"), para trazer para a frente em vez de abrir outra."""
    achada = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def olhar(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            classe = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, classe, 64)
            if classe.value.startswith("Chrome_WidgetWin") and (buf.value == "Guardião" or buf.value.startswith("Guardião ")):
                achada.append(hwnd)
                return False
        return True

    user32.EnumWindows(olhar, 0)
    return achada[0] if achada else None


def abrir_painel():
    hwnd = janela_do_painel()
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return
    try:
        import janela_painel
        janela_painel.abrir(f"http://localhost:{PORTA}/v2/")
    except Exception:
        import webbrowser
        webbrowser.open(f"http://localhost:{PORTA}/v2/")


class Aviso:
    def __init__(self, titulo, texto, kicker="", tag="", bloco="", segundos=60):
        import tkinter as tk
        import tkinter.font as tkfont
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        self.tk = tk
        self.bloco = bloco
        self.segundos = segundos
        self.raiz = tk.Tk()
        self.raiz.withdraw()
        self.raiz.title(TITULO_JANELA)
        self.raiz.overrideredirect(True)
        self.raiz.attributes("-topmost", True)
        self.raiz.attributes("-alpha", 0.0)
        self.raiz.configure(bg=COR["fundo"])
        escala = self.raiz.winfo_fpixels("1i") / 96.0
        self.e = escala
        px = lambda v: int(round(v * escala))  # noqa: E731
        self.px = px
        f_kick = tkfont.Font(family="Consolas", size=8)
        f_titulo = tkfont.Font(family="Georgia", size=13)
        f_texto = tkfont.Font(family="Segoe UI", size=10)
        f_botao = tkfont.Font(family="Segoe UI Semibold", size=9)
        w = px(LARGURA)
        pad = px(20)
        c = tk.Canvas(self.raiz, width=w, height=px(200), bg=COR["fundo"], highlightthickness=0, bd=0)
        c.pack()
        self.c = c
        # filete dourado no alto, como a borda dos cartões do painel
        for i in range(w):
            luz = 1 - abs(i / w - 0.5) * 2
            cor = self._mistura(COR["fundo"], COR["ouro2"], 0.25 + 0.75 * luz)
            c.create_line(i, 0, i + 1, 0, fill=cor)
            c.create_line(i, 1, i + 1, 1, fill=self._mistura(COR["fundo"], COR["ouro"], 0.35 * luz))
        y = px(18)
        c.create_oval(pad, y + px(3), pad + px(6), y + px(9), fill=COR["ouro2"], outline="")
        topo = "GUARDIÃO" + (" · " + kicker.upper() if kicker else "")
        c.create_text(pad + px(14), y + px(6), text=self._espacar(topo), anchor="w", font=f_kick, fill=COR["ouro2"])
        if tag:
            c.create_text(w - pad - px(22), y + px(6), text=tag.upper(), anchor="e", font=f_kick, fill=COR["marfim3"])
        self.x_fechar = c.create_text(w - pad, y + px(6), text="×", anchor="e", font=tkfont.Font(family="Segoe UI", size=12), fill=COR["marfim3"])
        c.tag_bind(self.x_fechar, "<Button-1>", lambda _e: self.fechar())
        y += px(24)
        t1 = c.create_text(pad, y, text=titulo, anchor="nw", font=f_titulo, fill=COR["marfim"], width=w - 2 * pad)
        y = c.bbox(t1)[3] + px(6)
        if texto:
            t2 = c.create_text(pad, y, text=texto, anchor="nw", font=f_texto, fill=COR["marfim2"], width=w - 2 * pad)
            y = c.bbox(t2)[3]
        y += px(16)
        # botões: o principal em dourado (Iniciar, quando o aviso é do começo de uma tarefa; senão Abrir o painel) e Dispensar
        principal = "Iniciar a tarefa" if bloco else "Abrir o painel"
        x = pad
        x = self._botao(x, y, principal, f_botao, True, self.acao_principal)
        if bloco:
            x = self._botao(x + px(8), y, "Abrir o painel", f_botao, False, self.acao_abrir)
        self._botao(x + px(8), y, "Dispensar", f_botao, False, lambda: self.fechar())
        altura = y + px(34) + px(18)
        c.configure(height=altura)
        c.bind("<Enter>", lambda _e: self._pausar(True))
        c.bind("<Leave>", lambda _e: self._pausar(False))
        esq, top, dir_, base = area_de_trabalho()
        self.x_final = dir_ - w - px(MARGEM)
        self.y = base - altura - px(MARGEM)
        self.raiz.geometry(f"{w}x{altura}+{self.x_final + px(28)}+{self.y}")
        self.parado = False
        self.fim_em = time.time() + segundos

    @staticmethod
    def _espacar(txt):
        return txt.replace(" · ", "  ·  ")

    @staticmethod
    def _mistura(a, b, t):
        a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
        return "#" + "".join(f"{int(x + (y - x) * max(0.0, min(1.0, t))):02x}" for x, y in zip(a, b))

    def _botao(self, x, y, rotulo, fonte, principal, acao):
        c, px = self.c, self.px
        larg = fonte.measure(rotulo) + px(28)
        alt = px(34)
        fundo = COR["botao"] if principal else COR["fantasma"]
        borda = COR["botao"] if principal else COR["borda"]
        r = alt // 2
        partes = [c.create_oval(x, y, x + alt, y + alt, fill=fundo, outline=borda),
                  c.create_oval(x + larg - alt, y, x + larg, y + alt, fill=fundo, outline=borda),
                  c.create_rectangle(x + r, y, x + larg - r, y + alt, fill=fundo, outline=fundo),
                  c.create_line(x + r, y, x + larg - r, y, fill=borda), c.create_line(x + r, y + alt, x + larg - r, y + alt, fill=borda)]
        partes.append(c.create_text(x + larg / 2, y + alt / 2, text=rotulo, font=fonte, fill=COR["botao_txt"] if principal else COR["marfim"]))
        for p in partes:
            c.tag_bind(p, "<Button-1>", lambda _e: acao())
            c.tag_bind(p, "<Enter>", lambda _e: c.configure(cursor="hand2"))
            c.tag_bind(p, "<Leave>", lambda _e: c.configure(cursor=""))
        return x + larg

    def _pausar(self, sim):
        # o ponteiro que já estava parado onde o aviso nasceu não conta: só pausa se a pessoa levou o mouse até ele
        if sim and getattr(self, "ponteiro_inicial", None) == self.raiz.winfo_pointerxy():
            return
        self.parado = sim
        if not sim:
            self.fim_em = max(self.fim_em, time.time() + 6)

    def _estilo_windows(self):
        """Não ativa (não rouba o foco), não aparece na barra de tarefas, fica por cima; cantos arredondados e borda dourada no Windows 11."""
        hwnd = user32.GetParent(self.raiz.winfo_id()) or self.raiz.winfo_id()
        self.hwnd = hwnd
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
        try:
            dwm = ctypes.windll.dwmapi
            canto = ctypes.c_int(2)  # DWMWCP_ROUND
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(canto), 4)
            cor = ctypes.c_uint(0x0031_84B2 & 0xFFFFFF)  # COLORREF 0x00BBGGRR do dourado #b28431
            dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(cor), 4)
        except Exception:
            pass

    def mostrar(self):
        anterior = user32.GetForegroundWindow()  # quem estava em uso: o foco volta para ele se o Tk pegar ao aparecer
        self.ponteiro_inicial = self.raiz.winfo_pointerxy()
        self.raiz.update_idletasks()
        self._estilo_windows()
        user32.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE
        self.raiz.deiconify()
        user32.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_TOPMOST, sem mover, sem ativar
        self.raiz.update()
        self._devolver_foco(anterior)
        self.raiz.after(120, lambda: self._devolver_foco(anterior))
        threading.Thread(target=tocar_som, daemon=True).start()
        self._entrar(0)
        self.raiz.after(500, self._relogio)
        self.raiz.mainloop()

    def _devolver_foco(self, anterior):
        """O Tk ativa a janela quando ela aparece; o aviso não pode tirar o teclado de quem está digitando."""
        atual = user32.GetForegroundWindow()
        if anterior and atual != anterior:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(atual, ctypes.byref(pid))
            if pid.value == os.getpid():
                user32.SetForegroundWindow(anterior)

    def _entrar(self, passo):
        n = 14
        t = min(1.0, passo / n)
        suave = 1 - (1 - t) ** 3
        x = int(self.x_final + self.px(28) * (1 - suave))
        self.raiz.geometry(f"+{x}+{self.y}")
        self.raiz.attributes("-alpha", 0.97 * suave)
        if passo < n:
            self.raiz.after(16, lambda: self._entrar(passo + 1))

    def _relogio(self):
        if not self.parado and time.time() >= self.fim_em:
            self.fechar()
            return
        self.raiz.after(500, self._relogio)

    def fechar(self, passo=0):
        n = 10
        try:
            self.raiz.attributes("-alpha", 0.97 * (1 - passo / n))
            if passo < n:
                self.raiz.after(16, lambda: self.fechar(passo + 1))
            else:
                self.raiz.destroy()
        except Exception:
            pass

    def acao_abrir(self):
        abrir_painel()
        self.fechar()

    def acao_principal(self):
        if self.bloco:
            try:
                r = _post("/execucao", {"acao": "iniciar", "id": self.bloco})
                if not r.get("ok"):
                    abrir_painel()  # a tarefa do aviso já não é a de agora: o painel mostra o que fazer
            except Exception:
                abrir_painel()
        else:
            abrir_painel()
        self.fechar()


def main():
    ap = argparse.ArgumentParser(description="Aviso do guardião na tela")
    ap.add_argument("--titulo", default="")
    ap.add_argument("--texto", default="")
    ap.add_argument("--kicker", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--bloco", default="")
    ap.add_argument("--segundos", type=float, default=60)
    ap.add_argument("--json", default="", help="arquivo com titulo, texto, kicker, tag e bloco (o avisos.ps1 usa, para não brigar com aspas e acentos)")
    ap.add_argument("--checar", action="store_true", help="só diz se dá para mostrar agora (0) ou não (3)")
    a = ap.parse_args()
    if a.checar:
        sys.exit(0 if pode_mostrar() else 3)
    if a.json:
        try:
            with open(a.json, encoding="utf-8-sig") as f:
                d = json.load(f)
            os.remove(a.json)
        except (OSError, ValueError):
            d = {}
        for k in ("titulo", "texto", "kicker", "tag", "bloco"):
            if d.get(k):
                setattr(a, k, str(d[k]))
    if not pode_mostrar():
        sys.exit(3)
    fechar_aviso_anterior()
    Aviso(a.titulo or "Guardião", a.texto, a.kicker, a.tag, a.bloco, a.segundos).mostrar()


if __name__ == "__main__":
    main()
