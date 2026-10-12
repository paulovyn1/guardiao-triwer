# Janela compacta do painel: fica por cima das outras janelas, no tamanho certo e no canto inferior direito da tela.
# Enquanto ela está aberta, a janela grande fica minimizada; ao expandir, a grande volta.
# O navegador não deixa uma página se fixar por cima das outras, então quem faz isso é este programa, pelo Windows (ctypes).
# Tudo local: não chama nada de fora.
import ctypes
import time
from ctypes import wintypes

TITULO_MINI = "Guardião compacto"  # título da página mini.html; é por ele que a janela é achada
TITULO_PRINCIPAL = "Guardião"
CLASSE = "Chrome_WidgetWin_1"  # janelas do Edge e do Chrome
LARGURA, ALTURA = 320, 420  # tamanho do palco da janela compacta (o mesmo de palco.js)
MARGEM = 16

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
SW_SHOWMINNOACTIVE, SW_RESTORE = 7, 9
GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x8
DWMWA_EXTENDED_FRAME_BOUNDS = 9


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


_ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
try:
    _u = ctypes.windll.user32
    _dwm = ctypes.windll.dwmapi
    _u.EnumWindows.argtypes = [_ENUM, wintypes.LPARAM]
    _u.IsWindowVisible.argtypes = [wintypes.HWND]
    _u.IsIconic.argtypes = [wintypes.HWND]
    _u.IsZoomed.argtypes = [wintypes.HWND]
    _u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _u.SetForegroundWindow.argtypes = [wintypes.HWND]
    _u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _u.MonitorFromWindow.restype = wintypes.HANDLE
    _u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
    _u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
except (AttributeError, OSError):  # fora do Windows: as funções abaixo devolvem "não disponível"
    _u = _dwm = None


def _em_pixels_reais():
    """Faz esta thread enxergar os pixels de verdade do monitor (telas com escala de 125% ou 150%). Devolve o modo anterior."""
    try:
        _u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        _u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        return _u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # por monitor, versão 2
    except (AttributeError, OSError):
        return None


def _voltar_modo(anterior):
    if anterior:
        try:
            _u.SetThreadDpiAwarenessContext(ctypes.c_void_p(anterior))
        except (AttributeError, OSError):
            pass


def janelas(classe=CLASSE):
    """Janelas visíveis dessa classe: lista de (identificador, título)."""
    achadas = []

    def cada(hwnd, _):
        if _u.IsWindowVisible(hwnd):
            n = _u.GetWindowTextLengthW(hwnd)
            if n:
                titulo = ctypes.create_unicode_buffer(n + 1)
                _u.GetWindowTextW(hwnd, titulo, n + 1)
                nome = ctypes.create_unicode_buffer(80)
                _u.GetClassNameW(hwnd, nome, 80)
                if not classe or nome.value == classe:
                    achadas.append((hwnd, titulo.value))
        return True

    _u.EnumWindows(_ENUM(cada), 0)
    return achadas


def _achar(titulo, classe, exato=False, espera=0.0):
    fim = time.time() + espera
    while True:
        for hwnd, t in janelas(classe):
            if (t == titulo) if exato else t.startswith(titulo):
                return hwnd
        if time.time() >= fim:
            return None
        time.sleep(0.15)


def _retangulo(hwnd):
    r = wintypes.RECT()
    _u.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def _borda_invisivel(hwnd):
    """O Windows 10 e 11 contam uma borda invisível no tamanho da janela. Devolve (esquerda, cima, direita, baixo) dessa sobra."""
    fora, visivel = _retangulo(hwnd), wintypes.RECT()
    try:
        if _dwm.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(visivel), ctypes.sizeof(visivel)) != 0:
            return 0, 0, 0, 0
    except (AttributeError, OSError):
        return 0, 0, 0, 0
    return max(0, visivel.left - fora.left), max(0, visivel.top - fora.top), max(0, fora.right - visivel.right), max(0, fora.bottom - visivel.bottom)


def por_cima(hwnd):
    return bool(_u.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)


def fixar_compacta(dw=16, dh=39, titulo=TITULO_MINI, principal=TITULO_PRINCIPAL, classe=CLASSE, espera=4.0, minimizar=True):
    """Põe a janela compacta no canto inferior direito, com o palco no tamanho certo, por cima das outras janelas.
    dw e dh são a moldura da janela medida pela própria página (janela inteira menos a área da página), na unidade da página."""
    if _u is None:
        return {"ok": False, "erro": "Só funciona no Windows."}
    anterior = _em_pixels_reais()
    try:
        mini = _achar(titulo, classe, espera=espera)
        if not mini:
            return {"ok": False, "erro": "Não achei a janela compacta."}
        grande = _achar(principal, classe, exato=True) if principal else None
        if _u.IsIconic(mini) or _u.IsZoomed(mini):
            _u.ShowWindow(mini, SW_RESTORE)
        try:
            escala = (_u.GetDpiForWindow(wintypes.HWND(mini)) or 96) / 96.0
        except (AttributeError, OSError):
            escala = 1.0
        dw = min(60.0, max(0.0, float(dw)))
        dh = min(140.0, max(0.0, float(dh)))
        w, h = round((LARGURA + dw) * escala), round((ALTURA + dh) * escala)
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        base = grande if grande and not _u.IsIconic(grande) else mini  # o monitor onde a janela grande está
        _u.GetMonitorInfoW(_u.MonitorFromWindow(base, 2), ctypes.byref(info))
        area = info.rcWork
        m = round(MARGEM * escala)
        _u.SetWindowPos(mini, HWND_TOPMOST, area.right - w - m, area.bottom - h - m, w, h, SWP_SHOWWINDOW)
        _, _, sobra_d, sobra_b = _borda_invisivel(mini)  # encosta a parte visível na margem, descontando a borda invisível
        x, y = area.right - w - m + sobra_d, area.bottom - h - m + sobra_b
        _u.SetWindowPos(mini, HWND_TOPMOST, x, y, w, h, SWP_SHOWWINDOW)
        if minimizar and grande and not _u.IsIconic(grande):
            _u.ShowWindow(grande, SW_SHOWMINNOACTIVE)
        _u.SetForegroundWindow(mini)
        return {"ok": True, "por_cima": por_cima(mini), "x": x, "y": y, "largura": w, "altura": h, "escala": escala}
    finally:
        _voltar_modo(anterior)


def restaurar_principal(principal=TITULO_PRINCIPAL, classe=CLASSE):
    """Traz a janela grande de volta (a compacta se fecha sozinha pela página)."""
    if _u is None:
        return {"ok": False, "erro": "Só funciona no Windows."}
    grande = _achar(principal, classe, exato=True)
    if not grande:
        return {"ok": False, "erro": "A janela grande não está aberta."}
    if _u.IsIconic(grande):
        _u.ShowWindow(grande, SW_RESTORE)
    _u.SetForegroundWindow(grande)
    return {"ok": True}


def rota(dados):
    """POST /janela: {"acao": "compacta", "dw": .., "dh": ..} ou {"acao": "expandir"}."""
    acao = str((dados or {}).get("acao") or "")
    try:
        if acao == "compacta":
            return fixar_compacta(dados.get("dw", 16), dados.get("dh", 39))
        if acao == "expandir":
            return restaurar_principal()
    except Exception as erro:  # nunca derruba o servidor por causa de janela
        return {"ok": False, "erro": str(erro)}
    return {"ok": False, "erro": "Ação desconhecida."}
