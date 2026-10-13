"""A janela do painel (janela_painel.py), sem abrir navegador nenhum: o navegador padrão é reconhecido pelo registro do Windows, só o Chrome e o Edge
abrem como janela de aplicativo, e isso sem criar perfil, sem entrar em conta e sem opção que mexa no navegador da pessoa. Os outros (Opera, Brave,
Vivaldi, Firefox...) abrem numa aba.
Também a limpeza do perfil antigo que as versões 0.6 e 0.7 criaram, que nunca mexe num perfil em uso."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import janela_painel as jp  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


# ---------------- ler o comando de abrir do navegador ----------------
confere("comando com aspas e espaço no caminho: pega só o programa",
        jp.exe_do_comando('"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --single-argument %1') == "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
confere("comando do Opera GX (opções antes do endereço)", jp.exe_do_comando('"D:\\Programas\\Opera GX\\opera.exe" -noautoupdate -- "%1"') == "D:\\Programas\\Opera GX\\opera.exe")
confere("comando sem aspas", jp.exe_do_comando("C:\\x\\nav.exe %1") == "C:\\x\\nav.exe")
confere("comando vazio não dá erro", jp.exe_do_comando("") == "" and jp.exe_do_comando(None) == "")

# ---------------- quem aceita --app ----------------
# Conferido no Opera GX de verdade (13/10/2026): com --app ele abre uma janela vazia de "Discagem Rápida" e não carrega o painel; com o endereço
# simples abre uma aba com o painel. Por isso só o Chrome e o Edge, que são os que se conferiu, abrem como janela de aplicativo.
for progid, exe in (("ChromeHTML", "chrome.exe"), ("MSEdgeHTM", "msedge.exe"), ("ChromeBHTML", "chrome.exe")):
    confere(f"{progid} abre como janela de aplicativo", jp.aceita_app(progid, exe))
for progid, exe in (("OperaStable", "opera.exe"), ("Opera GXStable", "opera.exe"), ("BraveHTML", "brave.exe"), ("VivaldiHTM", "vivaldi.exe"),
                    ("FirefoxURL-308046B0AF4A39CB", "firefox.exe"), ("AppXq0fevzme2pys62n3e0fbqa7peapykr8v", "RuntimeBroker.exe")):
    confere(f"{progid} abre numa aba (o --app não foi conferido ou é ignorado)", not jp.aceita_app(progid, exe))

# ---------------- os argumentos: janela de aplicativo e mais nada ----------------
args = jp.argumentos("http://localhost:8767/v2/", "1456,939")
confere("é uma janela de aplicativo no tamanho pedido", args == ["--app=http://localhost:8767/v2/", "--window-size=1456,939"], args)
confere("nenhum perfil novo: sem --user-data-dir", not any(a.startswith("--user-data-dir") for a in args), args)
confere("nenhuma opção que mexa no navegador da pessoa (sincronização, extensões, primeira execução)",
        not any(a.startswith(("--disable", "--no-first-run", "--no-default-browser-check", "--autoplay")) for a in args), args)
confere("o módulo não carrega mais opção de perfil, de sincronização nem de extensão", not hasattr(jp, "OPCOES_SEGURAS") and not hasattr(jp, "PERFIL"))
# quem usa o resultado de navegador_padrao() lê a chave certa (o roteiro de aluno pegou um KeyError no diagnostico.py, que ninguém executa nos testes)
voz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
usos = {}
for nome in sorted(os.listdir(voz)):
    if nome.endswith(".py"):
        texto_py = open(os.path.join(voz, nome), encoding="utf-8").read()
        if "navegador_padrao" in texto_py and nome != "janela_painel.py":
            usos[nome] = ('["chromium"]' not in texto_py and "['chromium']" not in texto_py and "eh_chromium" not in texto_py)
confere("quem chama navegador_padrao() não lê chaves que não existem mais", usos and all(usos.values()), usos)

# ---------------- o registro de verdade, neste computador ----------------
try:
    nav = jp.navegador_padrao()
    ok = nav is None or (os.path.exists(nav["exe"]) and isinstance(nav["app"], bool) and nav["progid"])
    confere("ler o navegador padrão no registro deste computador não dá erro e, se achou, o programa existe", ok, nav)
    print("  (neste computador:", (nav or {}).get("progid"), "| exe:", (nav or {}).get("exe"), "| janela de aplicativo:", (nav or {}).get("app"), ")")
except Exception as erro:
    confere("ler o navegador padrão no registro deste computador não dá erro", False, erro)

# ---------------- abrir: o que acontece em cada caso (sem abrir nada de verdade) ----------------
chamadas = {"popen": [], "web": []}
orig = (jp.subprocess.Popen, jp.webbrowser.open, jp.navegador_padrao, jp.limpar_perfil_antigo)
jp.subprocess.Popen = lambda cmd, *a, **k: chamadas["popen"].append(cmd)
jp.webbrowser.open = lambda url, *a, **k: chamadas["web"].append(url)
jp.limpar_perfil_antigo = lambda *a, **k: False


def zerar():
    chamadas["popen"].clear()
    chamadas["web"].clear()


try:
    jp.navegador_padrao = lambda: {"progid": "ChromeHTML", "exe": "C:\\Chrome\\chrome.exe", "app": True}
    modo = jp.abrir("http://localhost:8767/v2/", "1500,940")
    confere("Chrome ou Edge: janela de aplicativo no navegador padrão, só com --app e o tamanho",
            modo == "app" and chamadas["popen"] == [["C:\\Chrome\\chrome.exe", "--app=http://localhost:8767/v2/", "--window-size=1500,940"]] and not chamadas["web"], (modo, chamadas))
    zerar()
    for progid, exe in (("Opera GXStable", "C:\\Opera GX\\opera.exe"), ("FirefoxURL-1", "C:\\Firefox\\firefox.exe"), ("BraveHTML", "C:\\Brave\\brave.exe")):
        jp.navegador_padrao = lambda progid=progid, exe=exe: {"progid": progid, "exe": exe, "app": jp.aceita_app(progid, exe)}
        modo = jp.abrir("http://localhost:8767/v2/")
        confere(f"{progid}: aba nova pelo Windows, sem lançar programa nenhum nem opção", modo == "aba" and chamadas["web"] == ["http://localhost:8767/v2/"] and not chamadas["popen"], (modo, chamadas))
        zerar()
    jp.navegador_padrao = lambda: None
    modo = jp.abrir("http://localhost:8767/v2/")
    confere("navegador não encontrado: aba nova pelo Windows", modo == "aba" and chamadas["web"] == ["http://localhost:8767/v2/"] and not chamadas["popen"], (modo, chamadas))
    zerar()

    def quebra(cmd, *a, **k):
        raise OSError("programa sumiu")
    jp.subprocess.Popen = quebra
    jp.navegador_padrao = lambda: {"progid": "ChromeHTML", "exe": "C:\\Chrome\\chrome.exe", "app": True}
    modo = jp.abrir("http://localhost:8767/v2/")
    confere("se o programa do navegador falhar ao abrir, cai na aba nova em vez de dar erro", modo == "aba" and chamadas["web"] == ["http://localhost:8767/v2/"], (modo, chamadas))
finally:
    jp.subprocess.Popen, jp.webbrowser.open, jp.navegador_padrao, jp.limpar_perfil_antigo = orig

# ---------------- o perfil antigo ----------------
tmp = tempfile.mkdtemp(prefix="gv_painel_")


def perfil(nome):
    pasta = os.path.join(tmp, nome)
    os.makedirs(os.path.join(pasta, "Default"))
    with open(os.path.join(pasta, "Default", "Bookmarks"), "w") as f:
        f.write("favoritos")
    return pasta


velho = perfil("velho")
vazio = os.path.join(tmp, "nao_existe")
confere("a pasta do perfil antigo é a perfil_edge da pasta do programa", os.path.basename(jp.PERFIL_ANTIGO) == "perfil_edge" and os.path.dirname(jp.PERFIL_ANTIGO) == jp.BASE)

with open(os.path.join(velho, "lockfile"), "w") as f:
    f.write("x")
trava = open(os.path.join(velho, "lockfile"), "r")  # o Edge segura o lockfile enquanto roda: um arquivo aberto faz o mesmo papel
confere("com o Edge do painel antigo ainda aberto, o perfil é visto como em uso", jp.em_uso(velho))
confere("e então a limpeza não mexe em nada", not jp.limpar_perfil_antigo(velho) and os.path.exists(os.path.join(velho, "Default", "Bookmarks")))
trava.close()
confere("fechado o Edge, não está mais em uso", not jp.em_uso(velho))
confere("a limpeza apaga a pasta do perfil antigo do painel", jp.limpar_perfil_antigo(velho) and not os.path.exists(velho))
confere("perfil que não existe: nada a fazer", not jp.limpar_perfil_antigo(vazio))

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
