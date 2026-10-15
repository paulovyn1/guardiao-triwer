"""A janela do painel (janela_painel.py), sem abrir navegador nenhum: o painel abre sempre no Edge, como janela de aplicativo (no Opera ele
virava uma aba comum), numa pasta de navegador só dele (desde a 0.9.8): a placa de vídeo e o som da abertura funcionam seja qual for a
configuração do Edge da pessoa, sem conta, sem sincronização e sem extensões. Sem Edge, o Chrome; sem os dois, uma aba no navegador padrão.
O navegador padrão ainda é lido do registro, só para o diagnóstico.
Também a limpeza da pasta antiga que as versões 0.6 e 0.7 criaram dentro da pasta do guardião, que nunca mexe numa pasta em uso."""
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
args = jp.argumentos("http://localhost:8767/v2/", "1456,939", "C:\\Pasta")
confere("é uma janela de aplicativo no tamanho pedido", "--app=http://localhost:8767/v2/" in args and "--window-size=1456,939" in args, args)
confere("sempre numa pasta de navegador só do painel (o Edge da pessoa não é tocado: as configurações dela não valem para o painel)",
        args[0] == "--user-data-dir=C:\\Pasta" and sum(a.startswith("--user-data-dir") for a in args) == 1, args)
confere("o som da abertura toca sem esperar um clique", "--autoplay-policy=no-user-gesture-required" in args, args)
confere("sem conta, sem sincronização e sem extensões na pasta do painel",
        "--disable-sync" in args and "--disable-extensions" in args and any(a.startswith("--disable-features=") and "msImplicitSignin" in a for a in args), args)
confere("uma opção --disable-features só (o Chromium fica só com a última)", sum(a.startswith("--disable-features") for a in args) == 1, args)
confere("sem primeira execução nem pergunta de navegador padrão", "--no-first-run" in args and "--no-default-browser-check" in args, args)
pasta_real = jp.pasta_do_painel()
confere("a pasta fica em %LOCALAPPDATA%\\GuardiaoDoDia\\painel (NTFS mesmo quando o guardião está num disco FAT32), fora da pasta do guardião",
        pasta_real == os.path.join(os.environ["LOCALAPPDATA"], "GuardiaoDoDia", "painel") and not pasta_real.startswith(jp.BASE), pasta_real)
confere("argumentos sem pasta usam a pasta do painel", jp.argumentos("u")[0] == "--user-data-dir=" + pasta_real)
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
orig = (jp.subprocess.Popen, jp.webbrowser.open, jp.achar_edge, jp.achar_chrome, jp.limpar_perfil_antigo, jp.navegador_padrao)
jp.subprocess.Popen = lambda cmd, *a, **k: chamadas["popen"].append(cmd)
jp.webbrowser.open = lambda url, *a, **k: chamadas["web"].append(url)
jp.limpar_perfil_antigo = lambda *a, **k: False


def zerar():
    chamadas["popen"].clear()
    chamadas["web"].clear()


try:
    jp.achar_edge = lambda: "C:\\Edge\\msedge.exe"
    jp.achar_chrome = lambda: "C:\\Chrome\\chrome.exe"
    for padrao in ({"progid": "Opera GXStable", "exe": "C:\\Opera GX\\opera.exe", "app": False}, {"progid": "ChromeHTML", "exe": "C:\\Chrome\\chrome.exe", "app": True}, None):
        jp.navegador_padrao = lambda padrao=padrao: padrao
        modo = jp.abrir("http://localhost:8767/v2/", "1500,940")
        confere(f"com o navegador padrão {(padrao or {}).get('progid')}: abre no Edge, como janela de aplicativo, na pasta do painel",
                modo == "app" and chamadas["popen"] == [["C:\\Edge\\msedge.exe", *jp.argumentos("http://localhost:8767/v2/", "1500,940")]] and not chamadas["web"], (modo, chamadas))
        zerar()
    jp.achar_edge = lambda: ""
    modo = jp.abrir("http://localhost:8767/v2/")
    confere("sem Edge: o Chrome, também como janela de aplicativo", modo == "app" and chamadas["popen"] and chamadas["popen"][0][0] == "C:\\Chrome\\chrome.exe", (modo, chamadas))
    zerar()
    jp.achar_chrome = lambda: ""
    modo = jp.abrir("http://localhost:8767/v2/")
    confere("sem Edge e sem Chrome: aba nova no navegador padrão", modo == "aba" and chamadas["web"] == ["http://localhost:8767/v2/"] and not chamadas["popen"], (modo, chamadas))
    zerar()

    def quebra(cmd, *a, **k):
        raise OSError("programa sumiu")
    jp.subprocess.Popen = quebra
    jp.achar_edge = lambda: "C:\\Edge\\msedge.exe"
    modo = jp.abrir("http://localhost:8767/v2/")
    confere("se o Edge falhar ao abrir, cai na aba nova em vez de dar erro", modo == "aba" and chamadas["web"] == ["http://localhost:8767/v2/"], (modo, chamadas))
finally:
    jp.subprocess.Popen, jp.webbrowser.open, jp.achar_edge, jp.achar_chrome, jp.limpar_perfil_antigo, jp.navegador_padrao = orig

# ---------------- o Edge deste computador ----------------
edge = jp.achar_edge()
confere("o Edge deste computador é achado (ele vem com o Windows) e o programa existe", bool(edge) and os.path.exists(edge) and edge.lower().endswith("msedge.exe"), edge)
confere("o painel usa o Edge quando ele existe", jp.navegador_do_painel() == edge, jp.navegador_do_painel())

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
