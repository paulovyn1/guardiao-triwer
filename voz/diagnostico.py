# Diagnóstico do guardião: o que o computador tem, se cada peça funciona e onde o tempo vai. Escreve o resultado também em logs\diagnostico.txt
# (para mandar a quem está ajudando). Não grava nada fora da pasta de logs e não mostra a chave do Groq.
#
# Uso: diagnostico.bat           (ou: python diagnostico.py [--sem-claude])
# O teste com o Claude faz UMA pergunta curta ("Responda apenas: ok"), do jeito que o guardião pergunta: custa alguns centavos do plano. --sem-claude pula.
import ctypes
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
OPER = os.path.dirname(BASE)
linhas = []


def dizer(texto=""):
    print(texto, flush=True)
    linhas.append(texto)


def titulo(texto):
    dizer()
    dizer(f"== {texto}")


def lido(caminho):
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return ""


def powershell(comando):
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    except Exception:
        return ""


def memoria():
    class MEM(ctypes.Structure):
        _fields_ = [("tam", ctypes.c_ulong), ("uso", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("livre", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong),
                    ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
    m = MEM()
    m.tam = ctypes.sizeof(MEM)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.total / 2**30, m.livre / 2**30


avisos = []

dizer(f"Diagnóstico do guardião, {time.strftime('%Y-%m-%d %H:%M')}")

# ---------------- o computador ----------------
titulo("Computador")
total, livre = memoria()
cpu = powershell("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name")
dizer(f"Windows {platform.version()} | {cpu or 'processador não identificado'} | {os.cpu_count()} núcleos lógicos")
dizer(f"Memória: {total:.1f} GB no total, {livre:.1f} GB livres agora")
if livre < 1.0:
    avisos.append("Quase não há memória livre: o guardião (e tudo o mais) fica lento. Feche programas pesados, como o navegador com muitas abas.")
try:
    raiz = os.path.splitdrive(BASE)[0] + "\\"
    formato = powershell(f"(New-Object System.IO.DriveInfo('{raiz}')).DriveFormat")
    espaco = shutil.disk_usage(BASE).free / 2**30
    dizer(f"Disco da pasta do guardião ({raiz}): {formato or '?'}, {espaco:.1f} GB livres")
    if espaco < 1.0:
        avisos.append("Menos de 1 GB livre no disco do guardião: ele para de gravar o plano e os registros.")
except OSError:
    pass

# ---------------- o guardião ----------------
titulo("Guardião")
dizer(f"Versão: {lido(os.path.join(OPER, 'VERSION')).strip() or '?'} | Python {platform.python_version()} | pasta: {OPER}")
config = {}
try:
    config = json.loads(lido(os.path.join(OPER, "config.json")) or "{}")
except ValueError:
    pass
prefs = {}
try:
    prefs = json.loads(lido(os.path.join(BASE, "preferencias.json")) or "{}")
except ValueError:
    pass
dizer(f"Configurado: {'sim' if config else 'NÃO (falta o config.json: rode o onboarding)'} | conversa com memória: {'ligada' if prefs.get('sessao') else 'desligada'} | "
      f"voz do guardião: {'ligada' if prefs.get('voz_guardiao', True) else 'desligada'} | voz escolhida: {(config.get('agente') or {}).get('voz') or 'pm_santa'}")

# ---------------- Claude Code ----------------
titulo("Claude Code")
import guardiao_sessao as gs  # noqa: E402

t = time.time()
estado = gs.estado_do_claude()
if estado["ok"]:
    dizer(f"{estado['versao']} em {estado['de']} (conferido em {time.time() - t:.1f} s)")
    dizer(f"Chamado por: {' '.join(estado['comando'])}")
else:
    dizer("NÃO ACHEI um Claude Code que execute." + (f" Tentativas: {estado['erro']}" if estado["erro"] else ""))
    avisos.append("Sem o Claude Code o guardião não responde. Instale em https://claude.com/claude-code, entre com a sua conta e abra o guardião de novo.")
erros = [x for x in lido(os.path.join(OPER, "logs", "claude_erro.log")).strip().splitlines() if "unrecognized_model" not in x][-4:]  # (essa linha é um aviso sem consequência de versões do Claude Code)
if erros:
    dizer("O que o Claude Code escreveu de erro por último: " + " | ".join(x.strip()[:160] for x in erros))

if estado["ok"] and "--sem-claude" not in sys.argv:
    dizer("Pergunta de teste ao Claude (como o guardião pergunta)...")
    try:
        import guardiao_voz as g  # noqa: E402
        cmd, env = g.comando_claude("Responda apenas: ok", streaming=True)
        t0 = time.time()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env, cwd=OPER,
                                creationflags=gs.FLAGS_CLAUDE)
        primeira = texto = erro_do_claude = None
        for linha in proc.stdout:
            if primeira is None:
                primeira = time.time() - t0
            try:
                ev = json.loads(linha)
            except ValueError:
                continue
            if ev.get("type") == "stream_event" and (ev.get("event") or {}).get("type") == "content_block_delta" and texto is None:
                texto = time.time() - t0
            if ev.get("type") == "result":
                custo = ev.get("total_cost_usd")
                if ev.get("is_error"):
                    erro_do_claude = str(ev.get("result"))
        proc.wait(timeout=60)
        total_claude = time.time() - t0
        if erro_do_claude:
            dizer(f"O Claude respondeu com erro: {erro_do_claude}")
            avisos.append(gs.explicar_erro_do_claude(erro_do_claude) or f"O Claude Code respondeu com erro: {erro_do_claude}")
        else:
            dizer(f"Primeira linha em {primeira:.1f} s, primeiro texto em {texto if texto is None else round(texto, 1)} s, resposta completa em {total_claude:.1f} s"
                  + (f", custo US$ {custo:.4f}" if custo is not None else ""))
            if texto and texto > 8:
                avisos.append(f"O Claude levou {texto:.0f} s para começar a responder. Normal é de 3 a 6 s. Pode ser a conexão, o computador ocupado ou o plano no limite.")
    except Exception as erro:
        dizer(f"Não consegui fazer a pergunta de teste: {erro}")

# ---------------- voz e escuta ----------------
titulo("Voz do guardião (gerada neste computador)")
try:
    import nativo  # noqa: E402
    t = time.time()
    k = nativo.carregar_voz(BASE)
    k.create("Pronto.", voice="pm_santa", speed=1.0, lang="pt-br")
    dizer(f"Voz carregada em {time.time() - t:.1f} s")
    fatores = []
    for frase in ("Bom dia. Hoje é terça-feira.", "Seu próximo bloco começa às nove horas, e vale a pena revisar o plano com calma antes.",
                  "Eu monto o plano, crio as tarefas no ClickUp, aviso quando o horário de um bloco está acabando e confiro o dia com você no fim."):
        t = time.time()
        amostras, taxa = k.create(frase, voice="pm_santa", speed=1.0, lang="pt-br")
        gasto, fala = time.time() - t, len(amostras) / taxa
        fatores.append(gasto / fala)
        dizer(f"  {len(frase.split()):2d} palavras: {fala:.1f} s de fala gerados em {gasto:.1f} s (fator {gasto / fala:.2f})")
    fator = statistics.median(fatores)
    dizer(f"Fator de tempo real: {fator:.2f} (abaixo de 1 a voz sai sem pausas; acima de 1 ela atrasa entre uma frase e outra)")
    if fator >= 1.0:
        avisos.append(f"A voz leva {fator:.1f} s para gerar cada segundo de fala neste computador: a fala vai ter pausas longas entre as frases. "
                      "Feche o que estiver pesado; se continuar assim, desligue a voz em Preferências, Voz e sons (o guardião passa a só escrever).")
    elif fator >= 0.7:
        avisos.append(f"A voz está no limite (fator {fator:.2f}): com o computador ocupado pode haver pequenas pausas entre as frases.")
except Exception as erro:
    dizer(f"A voz não funcionou: {erro}")
    avisos.append("A voz do guardião não carregou. Rode o instalar.bat de novo.")

titulo("Escuta (palavra 'Ei guardião')")
try:
    from vosk import SetLogLevel
    SetLogLevel(-1)
    t = time.time()
    nativo.carregar_escuta(BASE)
    dizer(f"Modelo de escuta carregado em {time.time() - t:.1f} s")
except Exception as erro:
    dizer(f"O modelo de escuta não carregou: {erro}")
    avisos.append("O modelo de escuta não carregou. Rode o instalar.bat de novo.")

titulo("Microfone e transcrição")
try:
    import sounddevice as sd
    entradas = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    padrao = sd.query_devices(kind="input")["name"] if entradas else "nenhum"
    dizer(f"{len(entradas)} entradas de áudio | padrão do Windows: {padrao}")
    if not entradas:
        avisos.append("Nenhum microfone encontrado. Conecte um e abra o guardião de novo (ele tenta de novo sozinho em até 30 segundos).")
    else:
        try:
            fluxo = sd.RawInputStream(samplerate=16000, blocksize=1600, dtype="int16", channels=1)
            fluxo.start()
            dado, _ = fluxo.read(1600)
            fluxo.stop()
            fluxo.close()
            dizer("O microfone abre normalmente.")
        except Exception as erro:
            dizer(f"O microfone existe, mas não abriu: {erro}")
            avisos.append("O Windows está bloqueando o microfone. Em Configurações, Privacidade e segurança, Microfone, deixe ligado 'Permitir que aplicativos da área de trabalho acessem o microfone'.")
except Exception as erro:
    dizer(f"Não consegui listar os microfones: {erro}")
chave = os.environ.get("GROQ_API_KEY")
if not chave:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k_:
            chave = winreg.QueryValueEx(k_, "GROQ_API_KEY")[0]
    except OSError:
        chave = None
if not chave:
    dizer("Chave do Groq: NÃO gravada")
    avisos.append("Falta a chave gratuita do Groq (a transcrição da sua fala). Dê dois cliques em definir_chave_groq.bat, nesta pasta. Sem ela o painel funciona só por texto.")
else:
    try:
        import requests
        t = time.time()
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": "Bearer " + chave}, timeout=15)
        dizer(f"Chave do Groq: gravada ({len(chave)} caracteres), {'aceita' if r.ok else f'RECUSADA (código {r.status_code})'}, resposta em {time.time() - t:.1f} s")
        if not r.ok:
            avisos.append("O Groq recusou a chave gravada. Gere outra em https://console.groq.com/keys e dê dois cliques em definir_chave_groq.bat.")
    except Exception as erro:
        dizer(f"Chave do Groq: gravada, mas não consegui falar com o Groq: {erro}")
        avisos.append("Sem conexão com o Groq agora. Confira a internet.")

# ---------------- a janela ----------------
titulo("Janela do painel")
import janela_painel  # noqa: E402

_nav = janela_painel.navegador_padrao()
if _nav:
    dizer(f"Navegador padrão: {_nav['progid']} ({_nav['exe']}). O painel abre " + ("como janela de aplicativo, no seu perfil." if _nav["app"] else "numa aba, no seu perfil."))
else:
    dizer("Não consegui descobrir o navegador padrão. O painel abre numa aba nova pelo Windows.")
if os.path.isdir(janela_painel.PERFIL_ANTIGO):
    dizer("Sobrou a pasta do perfil antigo do painel (voz\\perfil_edge). Ela é apagada na próxima abertura do painel.")
try:
    import requests
    v = requests.get("http://localhost:8767/versao", timeout=3).json()
    dizer(f"O painel responde em localhost:8767 (versão carregada {v.get('carregada')}, instalada {v.get('instalada')})")
except Exception:
    dizer("O painel não está respondendo em localhost:8767 (o guardião está desligado?). Para ligar: o atalho Guardião na área de trabalho.")

# ---------------- o que aconteceu nas últimas respostas ----------------
titulo("Últimas respostas (logs\\latencia.jsonl)")
import latencia  # noqa: E402
import hud_servidor as h  # noqa: E402
h.OPER = OPER
registros = latencia.ler(60)
if not registros:
    dizer("Ainda não há respostas medidas.")
for modo in ("rapido", "sessao", "saudacao"):
    do_modo = [r for r in registros if r.get("modo") == modo and r.get("primeira") is not None]
    if not do_modo:
        continue
    primeiras = [r["primeira"] for r in do_modo]
    totais = [r["total"] for r in do_modo]
    cpus = [r["cpu_pct"] for r in do_modo if r.get("cpu_pct") is not None]
    fatores = []
    pausas = []
    for r in do_modo:
        passos = r.get("passos", [])
        for p in passos:
            if p[1] == "sintese_fim" and p[2].get("fala"):
                fatores.append(p[2]["gasto"] / p[2]["fala"])
        toques = {p[2]["n"]: p[0] for p in passos if p[1] == "toque_ini"}
        fins = {p[2]["n"]: p[0] for p in passos if p[1] == "toque_fim"}
        for n, ini in toques.items():
            if n - 1 in fins:
                pausas.append(ini - fins[n - 1])
    dizer(f"{modo}: {len(do_modo)} respostas | primeira fala: mediana {statistics.median(primeiras):.1f} s, pior {max(primeiras):.1f} s | resposta inteira: mediana {statistics.median(totais):.1f} s"
          + (f" | computador {statistics.mean(cpus):.0f}% ocupado" if cpus else "")
          + (f" | voz: fator {statistics.median(fatores):.2f}" if fatores else "")
          + (f" | pausa entre frases: mediana {statistics.median(pausas):.1f} s, pior {max(pausas):.1f} s" if pausas else ""))
    if pausas and max(pausas) > 5:
        avisos.append(f"No modo {modo} houve pausas de até {max(pausas):.0f} s entre as frases. Os passos de cada resposta estão em logs\\latencia.jsonl: mande esse arquivo.")
    if cpus and statistics.mean(cpus) > 85:
        avisos.append(f"O computador ficou {statistics.mean(cpus):.0f}% ocupado durante as respostas: tudo fica mais lento. Feche programas pesados.")
paradas = sum(1 for r in registros if r.get("parado"))
if paradas:
    dizer(f"{paradas} resposta(s) foram interrompidas porque a janela do painel foi fechada.")

# ---------------- o que fazer ----------------
titulo("O que fazer")
if avisos:
    for a in avisos:
        dizer(f"- {a}")
else:
    dizer("Nada de errado encontrado.")

try:
    os.makedirs(os.path.join(OPER, "logs"), exist_ok=True)
    with open(os.path.join(OPER, "logs", "diagnostico.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    print(f"\nEste relatório ficou em {os.path.join(OPER, 'logs', 'diagnostico.txt')}. Para pedir ajuda, mande esse arquivo (e logs\\latencia.jsonl, se pedirem).")
except OSError:
    pass
