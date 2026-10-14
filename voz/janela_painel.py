# A janela do painel. No Windows ela abre sempre no Microsoft Edge, como janela de aplicativo (sem abas nem barra de endereço), no perfil
# que a pessoa já usa no Edge: o guardião não cria perfil, não entra em conta, não liga sincronização e não mexe em extensão.
#
# Por que o Edge e não o navegador padrão: o painel precisa parecer um aplicativo. Só Chrome e Edge abrem uma janela de aplicativo com --app;
# o Opera (e o Opera GX) ignora a opção e abre como aba comum, com a interface do navegador em volta (medido no Opera GX de verdade). O Edge
# vem com todo Windows 10 e 11, então é o mesmo para todo mundo.
# Sem o Edge (raro), vale o Chrome em janela de aplicativo; sem os dois, uma aba nova no navegador padrão.
# No Mac (quando houver versão para Mac) o painel abre no Safari.
#
# Uso: python janela_painel.py <endereço> [largura,altura]
import os
import shutil
import subprocess
import sys
import webbrowser

try:
    import winreg
except ImportError:  # fora do Windows
    winreg = None

BASE = os.path.dirname(os.path.abspath(__file__))
PERFIL_ANTIGO = os.path.join(BASE, "perfil_edge")  # as versões 0.6 e 0.7 abriam o Edge num perfil só do guardião: hoje não se usa mais
ACEITAM_APP = ("chrome", "msedge")  # parte do nome do programa: os que abrem uma janela de aplicativo com --app


def exe_do_comando(comando):
    """O programa de um comando do registro: '"C:\\Program Files\\X\\x.exe" -- "%1"' -> 'C:\\Program Files\\X\\x.exe'."""
    comando = (comando or "").strip()
    if comando.startswith('"'):
        fim = comando.find('"', 1)
        return comando[1:fim] if fim > 0 else comando[1:]
    return comando.split(" ")[0]


def aceita_app(progid, exe=""):
    """O navegador abre uma janela de aplicativo com --app? Só o Chrome e o Edge, conferidos. Opera ignora a opção; os demais não foram conferidos."""
    nome = f"{progid} {os.path.basename(exe or '')}".lower()
    return any(k in nome for k in ACEITAM_APP)


def _ler(raiz, caminho, valor=""):
    try:
        with winreg.OpenKey(raiz, caminho) as chave:
            return winreg.QueryValueEx(chave, valor)[0]
    except OSError:
        return ""


def _app_paths(nome):
    """Onde o Windows diz que está o programa (App Paths), para a pessoa e para a máquina."""
    if winreg is None:
        return ""
    for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        exe = _ler(raiz, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{nome}")
        if exe and os.path.exists(exe):
            return exe
    return ""


def achar_edge():
    """O msedge.exe deste computador, ou '' se não houver."""
    exe = _app_paths("msedge.exe")
    if exe:
        return exe
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            caminho = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(caminho):
                return caminho
    return ""


def achar_chrome():
    """O chrome.exe deste computador, ou '' se não houver (reserva para quem não tem o Edge)."""
    exe = _app_paths("chrome.exe")
    if exe:
        return exe
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            caminho = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.exists(caminho):
                return caminho
    return ""


def navegador_padrao():
    """O navegador que a pessoa escolheu como padrão no Windows: {'progid', 'exe', 'app'}. None se não der para saber. Só informativo (diagnóstico)."""
    if winreg is None:
        return None
    progid = ""
    for esquema in ("https", "http"):
        progid = _ler(winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\{esquema}\UserChoice", "ProgId")
        if progid:
            break
    if not progid:
        return None
    exe = exe_do_comando(_ler(winreg.HKEY_CLASSES_ROOT, rf"{progid}\shell\open\command"))
    if not exe or not os.path.exists(exe):
        return None
    return {"progid": progid, "exe": exe, "app": aceita_app(progid, exe)}


def navegador_do_painel():
    """O programa que abre o painel em janela de aplicativo: o Edge, ou o Chrome se não houver Edge. '' se não houver nenhum dos dois."""
    return achar_edge() or achar_chrome()


def argumentos(url, tamanho="1456,939"):
    """Os argumentos da janela de aplicativo (sem o caminho do programa). De propósito, nada de --user-data-dir: é o perfil da pessoa."""
    return [f"--app={url}", f"--window-size={tamanho}"]


def em_uso(perfil=PERFIL_ANTIGO):
    """O Edge está aberto com este perfil? O arquivo lockfile fica travado enquanto ele roda."""
    trava = os.path.join(perfil, "lockfile")
    if not os.path.exists(trava):
        return False
    try:
        os.remove(trava)  # sem Edge usando, apagar é inofensivo (ele recria)
        return False
    except OSError:
        return True


def limpar_perfil_antigo(perfil=PERFIL_ANTIGO):
    """Apaga a pasta do perfil que as versões antigas criaram para o painel (é só do guardião: o navegador da pessoa e os dados dela na
    nuvem não são tocados). Devolve True se apagou. Com ela em uso não mexe: tenta na próxima abertura."""
    if not os.path.isdir(perfil) or em_uso(perfil):
        return False
    try:
        shutil.rmtree(perfil)
    except OSError:
        return False
    return True


def abrir(url, tamanho="1456,939"):
    """Abre o painel. Devolve 'app' (janela de aplicativo no Edge, ou no Chrome sem Edge), 'safari' (Mac) ou 'aba' (aba nova no navegador padrão)."""
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", "-a", "Safari", url])
            return "safari"
        except OSError:
            webbrowser.open(url)
            return "aba"
    limpar_perfil_antigo()
    exe = navegador_do_painel()
    if exe:
        try:
            subprocess.Popen([exe, *argumentos(url, tamanho)])
            return "app"
        except OSError:
            pass
    webbrowser.open(url)
    return "aba"


if __name__ == "__main__":
    abrir(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8767/v2/", sys.argv[2] if len(sys.argv) > 2 else "1456,939")
