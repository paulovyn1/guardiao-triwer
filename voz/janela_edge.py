# A janela do painel no Edge, aberta sempre do mesmo jeito: um perfil só do guardião, sem entrar na conta Microsoft da pessoa, sem sincronizar
# e sem extensões.
# Por quê: medido no Edge, um perfil novo aberto sem estas opções entra sozinho na conta do Windows, liga a sincronização de favoritos,
# preenchimento automático e extensões, e as extensões da pessoa passam a rodar dentro do painel (uma delas abriu uma segunda janela).
# Com --disable-sync e --disable-features=msImplicitSignin o perfil nasce sem conta e sem sincronização.
#
# Uso: python janela_edge.py <endereço> [largura,altura]
import json
import os
import shutil
import subprocess
import sys
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
PERFIL = os.path.join(BASE, "perfil_edge")
CAMINHOS_DO_EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
OPCOES_SEGURAS = ["--disable-sync", "--disable-features=msImplicitSignin", "--disable-extensions"]
OPCOES_BASE = ["--autoplay-policy=no-user-gesture-required", "--no-first-run", "--no-default-browser-check"]  # o som da abertura toca sem clique


def caminho_do_edge():
    return next((c for c in CAMINHOS_DO_EDGE if os.path.exists(c)), None)


def argumentos(url, tamanho="1456,939", perfil=PERFIL):
    """Os argumentos do Edge para a janela do painel (sem o caminho do programa)."""
    return [f"--app={url}", f"--window-size={tamanho}", f"--user-data-dir={perfil}", *OPCOES_BASE, *OPCOES_SEGURAS]


def perfil_contaminado(perfil=PERFIL):
    """O perfil já entrou numa conta ou sincronizou? As versões anteriores abriam o Edge sem as opções seguras."""
    try:
        with open(os.path.join(perfil, "Default", "Preferences"), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False
    servicos = (d.get("google") or {}).get("services") or {}
    return bool(d.get("account_info")) or bool(servicos.get("consented_to_sync")) or bool(d.get("sync"))


def em_uso(perfil=PERFIL):
    """O Edge está aberto com este perfil? O arquivo lockfile fica travado enquanto ele roda."""
    trava = os.path.join(perfil, "lockfile")
    if not os.path.exists(trava):
        return False
    try:
        os.remove(trava)  # sem Edge usando, apagar é inofensivo (ele recria)
        return False
    except OSError:
        return True


def limpar_perfil_contaminado(perfil=PERFIL):
    """Apaga o perfil do guardião que já entrou na conta ou sincronizou (é só do painel: o Edge da pessoa e os dados dela na nuvem não são tocados).
    Devolve True se apagou. Com o Edge do painel aberto não mexe: tenta na próxima abertura."""
    if not os.path.isdir(perfil) or not perfil_contaminado(perfil) or em_uso(perfil):
        return False
    try:
        shutil.rmtree(perfil)
    except OSError:
        return False
    return True


def abrir(url, tamanho="1456,939", perfil=PERFIL):
    """Abre a janela do painel. Devolve True se foi no Edge com as opções seguras. Sem Edge, abre no navegador padrão."""
    limpar_perfil_contaminado(perfil)
    edge = caminho_do_edge()
    if not edge:
        webbrowser.open(url)
        return False
    subprocess.Popen([edge, *argumentos(url, tamanho, perfil)])
    return True


if __name__ == "__main__":
    abrir(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8767/v2/", sys.argv[2] if len(sys.argv) > 2 else "1456,939")
