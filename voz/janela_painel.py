# A janela do painel. No Windows ela abre sempre no Microsoft Edge, como janela de aplicativo (sem abas nem barra de endereço), numa pasta
# de Edge só do painel: o navegador da pessoa (perfis, conta, extensões, sincronização, configurações) não é tocado nem lido.
#
# Por que uma pasta só do painel (decisão do Paulo em 15/10/2026, voltando atrás na 0.8.0, que abria no perfil da pessoa):
# - a animação depende da placa de vídeo. No perfil da pessoa o painel herda a configuração dela; com a aceleração de hardware desligada
#   (caso real do Paulo) caiu de 88 para 15 quadros por segundo, medido no mesmo computador;
# - o som da abertura precisa de --autoplay-policy. O Edge que já está aberto (e no Windows ele fica aberto em segundo plano desde o logon)
#   ignora qualquer opção da linha de comando, então no perfil da pessoa o som só saía depois de um clique;
# - extensões da pessoa rodam em toda página, inclusive no painel.
# A pasta fica em %LOCALAPPDATA%\GuardiaoDoDia\painel (sempre NTFS, mesmo quando a pasta do guardião está num disco FAT32), nasce sem conta
# e sem sincronização (--disable-sync, msImplicitSignin, medido na 0.7.0) e não aparece na lista de perfis do Edge da pessoa.
#
# Por que o Edge e não o navegador padrão: só Chrome e Edge abrem janela de aplicativo com --app (o Opera ignora a opção e abre como aba).
# O Edge vem com todo Windows 10 e 11. Sem o Edge (raro), vale o Chrome, também com pasta própria; sem os dois, uma aba no navegador padrão.
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
PERFIL_ANTIGO = os.path.join(BASE, "perfil_edge")  # as versões 0.6 e 0.7 guardavam a pasta do painel aqui, dentro da pasta do guardião
ACEITAM_APP = ("chrome", "msedge")  # parte do nome do programa: os que abrem uma janela de aplicativo com --app
# Uma opção --disable-features só: o Chromium fica só com a última que aparecer na linha de comando.
OPCOES = [
    "--no-first-run", "--no-default-browser-check",
    "--autoplay-policy=no-user-gesture-required",  # o som da abertura toca sem esperar um clique
    "--disable-sync", "--disable-features=msImplicitSignin",  # sem conta e sem sincronização
    "--disable-extensions",
    "--hide-crash-restore-bubble",  # desligar o computador com o painel aberto não deixa o aviso de "restaurar páginas"
]


def pasta_do_painel():
    """A pasta de navegador só do painel. Em %LOCALAPPDATA% (NTFS); sem essa variável (raro), ao lado do programa."""
    base = os.environ.get("LOCALAPPDATA")
    return os.path.join(base, "GuardiaoDoDia", "painel") if base else os.path.join(BASE, "painel_navegador")


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


def argumentos(url, tamanho="1456,939", pasta=None):
    """Os argumentos da janela de aplicativo (sem o caminho do programa), sempre com a pasta só do painel."""
    return [f"--user-data-dir={pasta or pasta_do_painel()}", f"--app={url}", f"--window-size={tamanho}", *OPCOES]


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
    """Apaga a pasta que as versões 0.6 e 0.7 criaram dentro da pasta do guardião (hoje ela fica em %LOCALAPPDATA%). Devolve True se apagou.
    Com ela em uso não mexe: tenta na próxima abertura."""
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
            pasta = pasta_do_painel()
            os.makedirs(pasta, exist_ok=True)
            subprocess.Popen([exe, *argumentos(url, tamanho, pasta)])
            return "app"
        except OSError:
            pass
    webbrowser.open(url)
    return "aba"


if __name__ == "__main__":
    abrir(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8767/v2/", sys.argv[2] if len(sys.argv) > 2 else "1456,939")
