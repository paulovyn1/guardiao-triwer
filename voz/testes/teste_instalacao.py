"""Instalação de um computador novo, sem baixar nada e sem tocar em ClickUp, Groq ou Claude:
o que o -Verificar diz, o config.json que o onboarding gera (tratamento, voz, sessão, origem das atualizações, sem a tela antiga),
as tarefas agendadas que seriam criadas, o tratamento no feminino, a voz escolhida e o programa abrindo sem a chave do Groq (só texto)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

VOZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, VOZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import limpeza_teste  # noqa: E402,F401
import hud_servidor as h  # noqa: E402
import guardiao_voz as g  # noqa: E402
import requests  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


def ps(script, *args, env=None):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ---------------- uma cópia da skill numa pasta temporária (o memoria.md nasce nela, nunca no repositório) ----------------
raiz = next(c for c in (os.path.dirname(VOZ), ) if os.path.isdir(os.path.join(c, "scripts")) or True)
tem_scripts = os.path.isdir(os.path.join(raiz, "scripts")) and os.path.isdir(os.path.join(raiz, "app"))
if not tem_scripts:
    print("(esta pasta é uma instalação, sem scripts\\ e app\\ da skill: pulei a parte dos scripts; rode no clone do repositório)")
else:
    tmp = tempfile.mkdtemp(prefix="gv_inst2_")
    skill = os.path.join(tmp, "skill")
    for pasta in ("scripts", "app", "templates"):
        shutil.copytree(os.path.join(raiz, pasta), os.path.join(skill, pasta))
    shutil.copy(os.path.join(raiz, "VERSION"), skill)
    with open(os.path.join(skill, "origem.json"), "w", encoding="utf-8") as f:  # começa sem endereço publicado
        json.dump({"origem": "", "ramo": "main", "pasta": "guardiao-triwer"}, f)
    with open(os.path.join(raiz, "origem.json"), encoding="utf-8") as f:
        publicado = json.load(f)
    confere("o origem.json do repositório aponta para um endereço público do GitHub, com o guardião na raiz",
            publicado.get("origem", "").startswith("https://github.com/") and publicado.get("pasta") == "" and publicado.get("ramo") == "main", publicado)
    oper = os.path.join(tmp, "oper")
    env = dict(os.environ, USERPROFILE=os.path.join(tmp, "casa"))
    os.makedirs(env["USERPROFILE"])

    codigo, saida = ps(os.path.join(skill, "scripts", "instalar_painel.ps1"), "-Pasta", oper, "-Verificar")
    linhas = dict(x.split("=", 1) for x in saida.splitlines() if "=" in x)
    confere("-Verificar num computador vazio: diz a pasta e que falta tudo, sem criar nada",
            codigo == 0 and linhas.get("pasta_operacional") == oper and linhas.get("painel_instalado") == "nao" and linhas.get("programa") == "falta"
            and linhas.get("config") == "falta" and not os.path.exists(oper), saida)
    confere("-Verificar traz as nove conferências", set(linhas) >= {"programa", "python", "modelo_escuta", "voz", "chave_groq", "token_clickup", "claude", "config", "painel_instalado"}, linhas)
    codigo, saida = ps(os.path.join(skill, "scripts", "instalar_painel.ps1"), "-Pasta", oper)
    confere("skill sem a pasta voz: o instalador explica o que fazer em vez de instalar pela metade", codigo != 0 and "instalar.bat" in saida and not os.path.exists(os.path.join(oper, "voz")), saida[-400:])

    respostas = {
        "pessoa": {"nome": "Marina Souza", "artigo": "A"}, "agente": {"nome": "Sentinela", "voz": "pf_dora"},
        "pastas": {"operacional": oper, "memoria": os.path.join(oper, "memoria")},
        "rotina": {"chegada": "08:00", "almoco": "12:00", "fim": "17:00", "abrir_tela_as": "08:15"},
        "clickup": {"workspace_id": 123, "user_id": 456, "status_abertos": ["to do"], "atrasadas_dias": 10,
                    "listas": [{"id": 1, "nome": "Rotinas", "quando_usar": "tarefas do dia a dia"}], "membros": [{"nome": "Marina", "id": 456, "papel": "dona"}]},
        "sessao": {"pasta": "C:\\Trabalho"},
        "tela": {"titulo": "Antigo", "cor_fundo": "#000000"},  # respostas de uma versão antiga: os campos da tela são ignorados
    }
    arq = os.path.join(tmp, "respostas.json")
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(respostas, f, ensure_ascii=False)
    codigo, saida = ps(os.path.join(skill, "scripts", "configurar.ps1"), "-Respostas", arq, env=env)
    cfg = {}
    if os.path.exists(os.path.join(oper, "config.json")):
        with open(os.path.join(oper, "config.json"), encoding="utf-8-sig") as f:
            cfg = json.load(f)
    confere("configurar.ps1 -Respostas termina bem e avisa que o painel ainda não está instalado", codigo == 0 and "instalar_painel.ps1" in saida, saida[-500:])
    confere("o config.json leva tratamento, nome e voz do guardião",
            cfg.get("pessoa") == {"nome": "Marina Souza", "artigo": "a"} and cfg.get("agente") == {"nome": "Sentinela", "voz": "pf_dora"}, (cfg.get("pessoa"), cfg.get("agente")))
    confere("os campos opcionais entram só quando respondidos (abrir o painel, tarefas vencidas, sessão)",
            cfg.get("rotina", {}).get("abrir_tela_as") == "08:15" and cfg.get("clickup", {}).get("atrasadas_dias") == 10
            and cfg.get("sessao") == {"pasta": "C:\\Trabalho", "esforco": "low", "nova_conversa_apos_horas": 3, "fecha_apos_min": 15}, cfg)
    confere("a tela antiga não existe mais no config nem na pasta", "tela" not in cfg and not os.path.exists(os.path.join(oper, "favicon.svg"))
            and not os.path.exists(os.path.join(oper, "servidor_tela.ps1")) and not os.path.exists(os.path.join(oper, "tela_modelo.html")), list(cfg))
    confere("sem endereço publicado, a conferência diária de versão fica desligada", cfg.get("atualizacao", {}).get("verificar") is False and cfg["atualizacao"].get("origem") == "", cfg.get("atualizacao"))
    confere("scripts, esqueletos da memória e o ponteiro da skill foram criados",
            all(os.path.exists(os.path.join(oper, x)) for x in ("ler_clickup.ps1", "atualizar.ps1", "abrir_guardiao.bat", os.path.join("memoria", "perfil.md"), os.path.join("memoria", "equipe.md"), "planos"))
            and "pasta_operacional: " + oper in open(os.path.join(skill, "memoria.md"), encoding="utf-8").read())
    confere("o esqueleto da equipe pergunta por canais e agentes", "## Canais e agentes" in open(os.path.join(oper, "memoria", "equipe.md"), encoding="utf-8").read())

    with open(os.path.join(skill, "origem.json"), "w", encoding="utf-8") as f:
        json.dump({"origem": "https://github.com/exemplo/guardiao", "ramo": "main", "pasta": ""}, f)
    ps(os.path.join(skill, "scripts", "configurar.ps1"), "-Respostas", arq, env=env)
    with open(os.path.join(oper, "config.json"), encoding="utf-8-sig") as f:
        at = json.load(f)["atualizacao"]
    confere("com endereço publicado no origem.json, ele vira a origem das atualizações", at == {"origem": "https://github.com/exemplo/guardiao", "ramo": "main", "pasta": "", "verificar": True}, at)
    clone_interno = os.path.join(tmp, "clone_interno")  # repositório em que o guardião fica numa subpasta
    os.makedirs(os.path.join(clone_interno, "guardiao-triwer"))
    shutil.copy(os.path.join(raiz, "VERSION"), os.path.join(clone_interno, "guardiao-triwer"))
    with open(os.path.join(skill, ".repo-path"), "w", encoding="utf-8") as f:
        f.write(clone_interno + "\n")
    ps(os.path.join(skill, "scripts", "configurar.ps1"), "-Respostas", arq, env=env)
    with open(os.path.join(oper, "config.json"), encoding="utf-8-sig") as f:
        at = json.load(f)["atualizacao"]
    confere("instalada a partir de um clone, o clone vence o endereço publicado", at["origem"] == clone_interno and at["pasta"] == "guardiao-triwer" and at["verificar"] is True, at)
    clone_publico = os.path.join(tmp, "clone_publico")  # clone do repositório público: o guardião está na raiz
    os.makedirs(clone_publico)
    shutil.copy(os.path.join(raiz, "VERSION"), clone_publico)
    with open(os.path.join(skill, ".repo-path"), "w", encoding="utf-8") as f:
        f.write(clone_publico + "\n")
    ps(os.path.join(skill, "scripts", "configurar.ps1"), "-Respostas", arq, env=env)
    with open(os.path.join(oper, "config.json"), encoding="utf-8-sig") as f:
        at = json.load(f)["atualizacao"]
    confere("clone em que o guardião está na raiz: a subpasta fica vazia", at["origem"] == clone_publico and at["pasta"] == "" and at["verificar"] is True, at)

    ruim = dict(respostas, pessoa={"nome": "Marina", "artigo": "x"}, agente={"nome": "S", "voz": "voz_que_nao_existe"})
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(ruim, f, ensure_ascii=False)
    codigo, saida = ps(os.path.join(skill, "scripts", "configurar.ps1"), "-Respostas", arq, env=env)
    confere("tratamento ou voz inválidos: recusa e diz o que corrigir", codigo != 0 and "pessoa.artigo" in saida and "agente.voz" in saida, saida[-400:])

    codigo, saida = ps(os.path.join(skill, "scripts", "registrar_tarefas.ps1"), "-SomenteMostrar", "-Pasta", oper)
    criaria = [x for x in saida.splitlines() if x.startswith("Criaria:")]
    confere("as tarefas agendadas que seriam criadas: plano, ClickUp, o guardião ligado e a janela do painel",
            codigo == 0 and len(criaria) == 4 and "gerar plano" in criaria[0] and "ler ClickUp" in criaria[1] and "voz" in criaria[2] and "15 minutos" in criaria[2]
            and "tela" in criaria[3] and "08:15" in criaria[3], saida)
    codigo, saida = ps(os.path.join(skill, "scripts", "registrar_tarefas.ps1"), "-Pasta", oper)
    confere("sem o painel instalado, criar as tarefas de verdade é recusado com a instrução certa", codigo != 0 and "instalar_painel.ps1" in saida, saida[-300:])

    bat = open(os.path.join(oper, "abrir_guardiao.bat"), encoding="ascii").read()
    avisos = open(os.path.join(oper, "avisos.ps1"), encoding="utf-8-sig").read()
    tarefas = open(os.path.join(skill, "scripts", "registrar_tarefas.ps1"), encoding="utf-8-sig").read()
    abrir = open(os.path.join(VOZ, "abrir_guardiao_v2.ps1"), encoding="utf-8-sig").read()
    confere("caminho com espaço no nome do usuário: o programa agendado e o janela_edge.py vão entre aspas (e a pasta do perfil, pelo Popen em lista)",
            '-Execute "`"$pythonw`""' in tarefas and 'janela_edge.py`"' in abrir)
    instalar = open(os.path.join(raiz, "instalar.bat"), encoding="ascii").read()
    confere("instalar.bat aberto de dentro do zip avisa para extrair, em vez de falhar sem explicar", "goto :faltando" in instalar and "Extrair tudo" in instalar and "\r\n" in open(os.path.join(raiz, "instalar.bat"), newline="").read())
    confere("o atalho da pasta e o pop-up de aviso abrem o painel", "abrir_guardiao_v2.ps1" in bat and "servidor_tela" not in bat and "http://localhost:8767/v2/" in avisos)

# ---------------- toda biblioteca de fora que o programa importa está no requirements.txt ----------------
import re  # noqa: E402

locais = {os.path.splitext(n)[0] for n in os.listdir(VOZ) if n.endswith(".py")}
importados = set()
for nome in os.listdir(VOZ):
    if nome.endswith(".py"):
        with open(os.path.join(VOZ, nome), encoding="utf-8") as f:
            for linha in f:
                m = re.match(r"\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", linha)
                if m:
                    importados.add(m.group(1))
de_fora = importados - set(sys.stdlib_module_names) - locais
with open(os.path.join(VOZ, "requirements.txt"), encoding="utf-8") as f:
    pedidos = {re.split(r"[=<>!~ ]", x.strip())[0].lower().replace("-", "_") for x in f if x.strip() and not x.lstrip().startswith("#")}
pedidos |= {"phonemizer"}  # vem junto com o kokoro-onnx
confere("toda biblioteca de fora que o programa importa está no requirements.txt", de_fora <= pedidos, sorted(de_fora - pedidos))

# ---------------- tratamento no feminino e voz escolhida ----------------
tmp2 = tempfile.mkdtemp(prefix="gv_oper_inst_")
h.OPER = tmp2
h.ARQ_PREFS = os.path.join(tmp2, "preferencias.json")
for pasta in ("planos", "registros", "logs", "memoria"):
    os.makedirs(os.path.join(tmp2, pasta), exist_ok=True)


def config(**c):
    with open(os.path.join(tmp2, "config.json"), "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)


config(pessoa={"nome": "Marina Souza", "artigo": "a"}, agente={"nome": "Sentinela", "voz": "pf_dora"})
intro, sessao = g._p(g.INTRO_VOZ), g._p(g.INTRO_SESSAO)
confere("com artigo \"a\", as instruções da voz e da sessão mandam tratar a pessoa no feminino",
        "A Marina é mulher" in intro and "A Marina é mulher" in sessao and "<genero>" not in intro + sessao and "<" not in intro, intro[:300])
confere("a voz escolhida no onboarding é a usada", g.voz_configurada() == "pf_dora")
config(pessoa={"nome": "Rafa Lima", "artigo": "o"}, agente={"nome": "Guardião", "voz": "inventada"})
intro, sessao = g._p(g.INTRO_VOZ), g._p(g.INTRO_SESSAO)
confere("com artigo \"o\", nada muda no texto das instruções", "mulher" not in intro + sessao and "<genero>" not in intro + sessao and "falando por voz. Responda" in intro, intro[:200])
confere("voz com nome que não existe cai na padrão", g.voz_configurada() == g.VOZ_KOKORO)
config(pessoa={"nome": "Dani"})
confere("sem artigo, nada sobre gênero entra nas instruções", "mulher" not in g._p(g.INTRO_VOZ) and g.voz_configurada() == g.VOZ_KOKORO)

# ---------------- o programa abre sem a chave do Groq: painel no ar, conversa por texto, microfone explicado ----------------
com_modelo = next((c for c in (VOZ, os.environ.get("GUARDIAO_VOZ_INSTALADA", ""), os.path.join(os.path.expanduser("~"), "Guardiao-do-dia", "voz"))
                   if c and os.path.isfile(os.path.join(c, "modelo", "final.mdl"))), None)
if not com_modelo:
    print("(não achei o modelo de escuta em nenhuma pasta: pulei o teste do programa sem a chave)")
else:
    PORTA = 8776
    eventos = []
    emitir = h.bus.emitir

    def anotar(tipo, **dados):
        eventos.append((tipo, dados))
        return emitir(tipo, **dados)

    h.bus.emitir = anotar
    g.BASE = com_modelo            # só para o modelo de escuta: o resto do teste não lê nada dessa pasta
    g.PORTA_TELA = PORTA
    g.chave_groq = lambda: None    # computador sem a chave
    g.carregar_kokoro = lambda: None
    g.vigiar_avisos = lambda: None
    abertas = []
    g.abrir_tela = abertas.append
    config(pessoa={"nome": "Marina Souza", "artigo": "a"}, agente={"nome": "Sentinela", "voz": "pm_alex"})
    sys.argv = ["guardiao_voz.py", "--cerebro", "--sem-saudacao"]
    threading.Thread(target=g.main, daemon=True).start()

    def espera(cond, limite=40.0):
        fim = time.time() + limite
        while time.time() < fim:
            if cond():
                return True
            time.sleep(0.1)
        return False

    no_ar = espera(lambda: any(t == "saude" for t, _ in eventos))
    saude = next((d for t, d in eventos if t == "saude"), {})
    confere("sem a chave do Groq o programa não fecha: fica no ar com o microfone marcado como desligado", no_ar and saude.get("mic") is False and saude.get("groq") is False, saude)
    confere("a janela que ele abre é a do painel", abertas == [f"http://localhost:{PORTA}/v2/"], abertas)
    try:
        r = requests.get(f"http://localhost:{PORTA}/v2/", timeout=5)
        plano = requests.get(f"http://localhost:{PORTA}/plano", timeout=5)
        confere("o painel e o plano respondem", r.status_code == 200 and "<" in r.text and plano.status_code == 200, (r.status_code, plano.status_code))
        del eventos[:]
        requests.post(f"http://localhost:{PORTA}/acionar", json={}, timeout=5)
        avisou = espera(lambda: any(t == "aviso" for t, _ in eventos), 6)
        aviso = next((d for t, d in eventos if t == "aviso"), {})
        confere("clique no microfone sem a chave: a tela explica como ligar, em vez de ficar esperando uma fala",
                avisou and "Groq" in aviso.get("texto", "") and "definir_chave_groq.bat" in aviso.get("texto", "") and aviso.get("erro") is False, aviso)
        confere("depois do aviso ele volta a aguardar (não trava)", espera(lambda: eventos and eventos[-1] == ("estado", {"v": "aguardando"}), 4), eventos[-3:])

        # a pessoa grava a chave do Groq com o guardião já aberto: o microfone liga sozinho e a tela é avisada (antes só valia depois de reiniciar)
        class FluxoFalso:
            def __init__(self, **k):
                pass

            def start(self):
                pass

            def stop(self):
                pass

            def close(self):
                pass

        original_stream = g.sd.RawInputStream
        g.sd.RawInputStream = FluxoFalso
        del eventos[:]
        g.chave_groq = lambda: "gsk_de_teste"
        ligou = espera(lambda: any(t == "saude" and d.get("mic") and d.get("groq") for t, d in eventos), 25)
        confere("chave gravada com o guardião aberto: o microfone liga sozinho e a tela passa a mostrar o microfone e a transcrição prontos", ligou, [e for e in eventos if e[0] == "saude"])
        g.sd.RawInputStream = original_stream
    except Exception as erro:
        confere("o painel responde sem a chave", False, erro)
    h.bus.emitir = emitir

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
