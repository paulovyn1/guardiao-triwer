# A janela do painel, aberta no navegador padrão da pessoa e no perfil dela. O guardião não cria perfil, não entra em conta, não liga
# sincronização e não mexe em extensão: quem abre é o navegador que a pessoa já usa, do jeito que ela já usa.
#
# Chrome e Edge: abrem como janela de aplicativo (sem abas nem barra de endereço) com --app, sem nenhuma outra opção. Se o navegador já está
# aberto, a janela nasce nele; se não, ele abre com o perfil de sempre.
# Qualquer outro (Opera, Opera GX, Brave, Vivaldi, Firefox...), ou navegador que não se achou: abre numa aba nova pelo próprio Windows.
# Por que só esses dois: medido no Opera GX de verdade, ele ignora o --app e abre uma janela vazia de "Discagem Rápida", sem o painel. Uma aba
# no navegador da pessoa é feia, mas funciona sempre; uma janela vazia deixa a pessoa sem painel.
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
ACEITAM_APP = ("chrome", "msedge")  # parte do identificador do navegador no Windows (ProgId) ou do nome do programa: os que abrem uma janela de aplicativo com --app


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


def navegador_padrao():
    """O navegador que a pessoa escolheu como padrão no Windows: {'progid', 'exe', 'chromium'}. None se não der para saber."""
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
    """Abre o painel. Devolve 'app' (janela de aplicativo, no Chrome ou no Edge padrão) ou 'aba' (aba nova no navegador padrão, pelo Windows)."""
    limpar_perfil_antigo()
    nav = navegador_padrao()
    if nav and nav["app"]:
        try:
            subprocess.Popen([nav["exe"], *argumentos(url, tamanho)])
            return "app"
        except OSError:
            pass
    webbrowser.open(url)
    return "aba"


if __name__ == "__main__":
    abrir(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8767/v2/", sys.argv[2] if len(sys.argv) > 2 else "1456,939")
