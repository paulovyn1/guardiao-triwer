"""O que impede o guardião de travar ou de aparecer duas vezes (0.9.8, caso de 15/10/2026), sem microfone, sem Claude e sem mexer nas
tarefas agendadas de verdade:
- um guardião só: a trava de instância única e a porta exclusiva do painel (o padrão do Python deixava dois programas na mesma porta);
- a escuta nunca espera o microfone sem prazo: Esc, clique, texto digitado e microfone mudo encerram a escuta;
- o registro tem data, hora e processo em cada linha;
- tarefas agendadas e atalho sem janela de terminal (a conversão do XML, o lançador sem janela e o atalho)."""
import io
import os
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
VOZ = os.path.dirname(AQUI)
sys.path.insert(0, VOZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import guardiao_voz as g  # noqa: E402
import hud_servidor as h  # noqa: E402
import instancia  # noqa: E402
import registro  # noqa: E402
import sem_janela  # noqa: E402
import tarefas  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe != "" and not ok else ""))


# ---------------- um guardião só ----------------
NOME = f"Local\\GuardiaoTeste{os.getpid()}"  # nunca a trava de verdade: o guardião da pessoa pode estar ligado
confere("sem ninguém com a trava, ela não existe", not instancia.existe(NOME))
confere("o primeiro fica com a trava", instancia.tomar(NOME))
confere("com a trava tomada, ela existe (é o que o abrir_guardiao_v2.ps1 olha)", instancia.existe(NOME))
outro = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {VOZ!r}); import instancia; print(instancia.tomar({NOME!r}))"],
                       capture_output=True, text=True, timeout=60)
confere("um segundo programa não consegue a trava (sai antes de carregar qualquer coisa)", outro.stdout.strip() == "False", outro.stdout + outro.stderr)
ps = subprocess.run(["powershell.exe", "-NoProfile", "-Command", f"try {{ [System.Threading.Mutex]::OpenExisting('{NOME}').Dispose(); 'sim' }} catch {{ 'nao' }}"],
                    capture_output=True, text=True, timeout=60)
confere("o PowerShell enxerga a mesma trava pelo nome", ps.stdout.strip() == "sim", ps.stdout + ps.stderr)
instancia.soltar()
confere("solta a trava, ela some (o Windows também solta quando o processo morre)", not instancia.existe(NOME))
fonte_voz = open(os.path.join(VOZ, "guardiao_voz.py"), encoding="utf-8").read()
confere("o guardião toma a trava (a do painel dele) antes de carregar a escuta e a voz",
        fonte_voz.index("instancia.tomar(instancia.nome_da_trava(PORTA_TELA))") < fonte_voz.index("nativo.carregar_escuta(BASE)") < fonte_voz.index("carregar_kokoro()\n        except"))
abrir_ps = open(os.path.join(VOZ, "abrir_guardiao_v2.ps1"), encoding="utf-8-sig").read()
confere("abrir o painel com o guardião ligando espera por ele, em vez de ligar outro (mesmo nome de trava, pela porta)",
        'Local\\GuardiaoTriwerVoz-$porta' in abrir_ps and "$porta = 8767" in abrir_ps and "if (Ligando) { EsperarPorta" in abrir_ps
        and instancia.nome_da_trava(8767) == "Local\\GuardiaoTriwerVoz-8767" == instancia.NOME)
trava_a, trava_b = instancia.nome_da_trava(61001), instancia.nome_da_trava(61002)
instancia.tomar(trava_a)
outra = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {VOZ!r}); import instancia; print(instancia.tomar({trava_b!r}))"],
                       capture_output=True, text=True, timeout=60)
confere("um guardião de outro painel (outra porta, como o dos testes) não é barrado pelo guardião de verdade", outra.stdout.strip() == "True", outra.stdout + outra.stderr)
instancia.soltar()

# ---------------- porta exclusiva ----------------
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PORTA = s.getsockname()[1]
primeiro = h.ServidorExclusivo(("127.0.0.1", PORTA), h.Pedido)
threading.Thread(target=primeiro.serve_forever, daemon=True).start()
try:
    h.ServidorExclusivo(("127.0.0.1", PORTA), h.Pedido)
    segundo_ligou = True
except OSError:
    segundo_ligou = False
confere("um segundo servidor na mesma porta recebe erro (antes os dois ligavam)", not segundo_ligou)
with socket.socket() as s:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", PORTA))
        roubou = True
    except OSError:
        roubou = False
confere("nem com SO_REUSEADDR (o padrão do Python) outro programa divide a porta", not roubou)
confere("iniciar_servidor numa porta ocupada devolve None (o guardião desiste em vez de ficar meio ligado)", h.iniciar_servidor(PORTA) is None)
erros = io.StringIO()
antigo_err, sys.stderr = sys.stderr, erros
try:
    try:
        raise ConnectionResetError(10054, "o painel fechou")
    except ConnectionResetError:
        primeiro.handle_error(None, ("127.0.0.1", 1))
finally:
    sys.stderr = antigo_err
confere("painel que fecha no meio de uma resposta não enche o registro de erro", erros.getvalue() == "", erros.getvalue()[:200])
primeiro.shutdown()
primeiro.server_close()

# ---------------- a escuta nunca fica presa ----------------
g.bus.emitir = lambda *a, **k: None
g.esc_apertado = lambda: False
g.SEM_AUDIO = 0.6  # no teste o microfone "morre" mais rápido


def escuta_sem_audio(acao=None):
    """Grava com um microfone que não manda nada. acao() roda em paralelo, 0,3 s depois."""
    q = queue.Queue()
    if acao:
        threading.Timer(0.3, acao).start()
    t0 = time.time()
    r = g.gravar(q, 80.0)
    return r, time.time() - t0


r, seg = escuta_sem_audio()
confere("microfone mudo: a escuta termina sozinha (MUDO) em vez de esperar para sempre", r is g.MUDO and seg < 2.0, (r, seg))
r, seg = escuta_sem_audio(g.bus.cancelar_escuta.set)
confere("Esc ou clique no microfone encerra a escuta mesmo sem nenhum áudio chegar", r is g.CANCELADO and seg < 0.6, (r, seg))
r, seg = escuta_sem_audio(lambda: g.bus.comandos.put(("perguntar", "concluí a tarefa")))
confere("texto digitado no painel encerra a escuta, e o texto continua na fila para ser atendido",
        r is g.CANCELADO and seg < 0.6 and g.bus.comandos.get_nowait() == ("perguntar", "concluí a tarefa"), (r, seg))
g.bus.comandos.put(("checkin", {"texto": "x"}))
r, _ = escuta_sem_audio(lambda: None)
confere("outro pedido da fila (aviso de tempo) não corta a escuta de ninguém", r is g.MUDO, r)
g.bus.comandos.get_nowait()
fechados = []


class MicFalso:
    def parar(self):
        fechados.append(1)

    def tentar(self, chave):
        return True


g.MIC, g.escuta_continua = MicFalso(), (lambda: False)
avisos = []
g.bus.emitir = lambda tipo, **k: avisos.append((tipo, k))
g.time.sleep, sono = (lambda s: None), g.time.sleep
texto, _, motivo = g.escutar(type("A", (), {"sem_preview": True})(), queue.Queue(), None, "chave", 80.0, seguimento=True)
g.time.sleep = sono
confere("escuta com microfone mudo: reconecta o microfone, avisa na tela e volta a esperar",
        motivo == "erro" and fechados and any(t == "aviso" and "microfone parou" in k.get("texto", "") for t, k in avisos)
        and avisos[-1] == ("estado", {"v": "aguardando"}), (motivo, fechados, avisos[-3:]))
confere("a espera pelo áudio da escuta tem prazo (q.get com timeout)", "dado = q.get(timeout=0.2)" in fonte_voz and "dado = q.get()\n" not in fonte_voz)

# ---------------- registro com hora ----------------
pasta = tempfile.mkdtemp(prefix="gv_reg_")
arq = registro.abrir(pasta)
arq.write("primeira linha\n")
arq.write("  ouvindo: parcial")
arq.write(" e o resto\nsegunda\n")
arq.flush()
linhas = open(os.path.join(pasta, "voz.log"), encoding="utf-8").read().splitlines()
padrao = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \[" + str(os.getpid()) + r"\] ")
confere("cada linha do registro começa com data, hora e o número do processo",
        len(linhas) == 3 and all(padrao.match(x) for x in linhas) and linhas[1].endswith("  ouvindo: parcial e o resto"), linhas)
arq.arquivo.close()
with open(os.path.join(pasta, "voz.log"), "a", encoding="utf-8") as f:
    f.write("x" * (registro.LIMITE + 10))
registro.abrir(pasta).arquivo.close()
confere("registro grande vira voz.log.1 (o de ontem continua lá) em vez de ser apagado",
        os.path.getsize(os.path.join(pasta, "voz.log.1")) > registro.LIMITE and os.path.getsize(os.path.join(pasta, "voz.log")) == 0)

# ---------------- tarefas e atalho sem janela ----------------
NS = 'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"'
XML = (f'<?xml version="1.0" encoding="UTF-16"?>\n<Task version="1.3" {NS}><Triggers><LogonTrigger><UserId>PC\\pessoa</UserId></LogonTrigger>'
       '<CalendarTrigger><StartBoundary>2026-10-12T08:45:00-03:00</StartBoundary></CalendarTrigger></Triggers>'
       '<Actions Context="Author"><Exec><Command>powershell.exe</Command><Arguments>-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass '
       '-File "C:\\Users\\José Conceição\\Guardiao-do-dia\\ler_clickup.ps1" -Forcar</Arguments></Exec></Actions></Task>')
PYW, LANC = r"C:\Users\José Conceição\Guardiao-do-dia\voz\.venv\Scripts\pythonw.exe", r"C:\Users\José Conceição\Guardiao-do-dia\voz\sem_janela.py"
novo = tarefas.converter(XML, PYW, LANC, "PT1M")
confere("tarefa com powershell passa a chamar o pythonw com sem_janela.py, mantendo o script e os argumentos dele",
        novo and f"<Command>{PYW}</Command>" in novo
        and f'<Arguments>"{LANC}" "C:\\Users\\José Conceição\\Guardiao-do-dia\\ler_clickup.ps1" -Forcar</Arguments>' in novo
        and "powershell" not in novo.lower(), novo)
confere("o gatilho de logon ganha o atraso; o de horário fica como estava",
        "<UserId>PC\\pessoa</UserId><Delay>PT1M</Delay></LogonTrigger>" in novo and novo.count("<Delay>") == 1, novo)
confere("a pasta de trabalho da tarefa é a do programa", "<WorkingDirectory>C:\\Users\\José Conceição\\Guardiao-do-dia\\voz</WorkingDirectory>" in novo, novo)
confere("tarefa já ajustada não muda de novo (roda a cada vez que o guardião liga)", tarefas.converter(novo, PYW, LANC, "PT1M") is None)
ja_com_atraso = XML.replace("</UserId></LogonTrigger>", "</UserId><Delay>PT5M</Delay></LogonTrigger>")
confere("atraso que a pessoa já tinha posto fica", "<Delay>PT5M</Delay>" in tarefas.converter(ja_com_atraso, PYW, LANC, "PT1M"))
sem_ps = XML.replace("powershell.exe", "pythonw.exe")
confere("tarefa que não usa o powershell e não tem atraso pedido fica como está", tarefas.converter(sem_ps, PYW, LANC, None) is None)
confere("a tarefa antiga 'avisos' sai (o guardião mantém o aviso ligado sozinho)", "avisos" in tarefas.ANTIGAS)

lnk = os.path.join(tempfile.mkdtemp(prefix="gv_lnk_"), "Guardião.lnk")
with open(lnk, "wb") as f:
    f.write(b"L\x00\x00\x00" + "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\PowerShell.exe".encode("utf-16-le"))
confere("atalho antigo (pelo powershell) é reconhecido", tarefas.atalho_usa_powershell(lnk))
with open(lnk, "wb") as f:
    f.write(b"L\x00\x00\x00" + PYW.encode("utf-16-le"))
confere("atalho novo (pelo pythonw) não é refeito", not tarefas.atalho_usa_powershell(lnk))
atalho_ps = open(os.path.join(VOZ, "criar_atalho.ps1"), encoding="utf-8-sig").read()
confere("o atalho novo chama o pythonw com sem_janela.py", "sem_janela.py" in atalho_ps and "$atalho.TargetPath = $pythonw" in atalho_ps)

pasta = tempfile.mkdtemp(prefix="gv_sj_")
sem_janela.LOG = os.path.join(pasta, "logs", "tarefas.log")
ok_ps1, ruim_ps1, saida = os.path.join(pasta, "ok.ps1"), os.path.join(pasta, "ruim.ps1"), os.path.join(pasta, "saida.txt")
with open(ok_ps1, "w", encoding="utf-8-sig") as f:
    f.write("param([string]$Texto)\nSet-Content -LiteralPath $PSScriptRoot\\saida.txt -Value $Texto -Encoding utf8\n")
with open(ruim_ps1, "w", encoding="utf-8-sig") as f:
    f.write("Write-Error 'falhou de propósito'\nexit 7\n")
codigo = sem_janela.rodar(ok_ps1, ["-Texto", "Conceição"])
confere("o lançador roda o script com os argumentos e devolve o código dele",
        codigo == 0 and open(saida, encoding="utf-8-sig").read().strip() == "Conceição", (codigo, os.path.exists(saida)))
codigo = sem_janela.rodar(ruim_ps1)
log = open(sem_janela.LOG, encoding="utf-8").read() if os.path.exists(sem_janela.LOG) else ""
confere("script que falha: o código volta e o motivo fica em logs\\tarefas.log, com data e hora",
        codigo == 7 and "ruim.ps1 terminou com código 7" in log and "falhou de propósito" in log and re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ", log), (codigo, log))
confere("o lançador abre o PowerShell sem janela (CREATE_NO_WINDOW)", sem_janela.SEM_JANELA == subprocess.CREATE_NO_WINDOW)
# no repositório o registrar_tarefas.ps1 fica em scripts\ ao lado do programa; numa instalação, na pasta da skill
candidatos = [os.path.join(os.path.dirname(VOZ), "scripts"), os.path.join(os.path.expanduser("~"), ".claude", "skills", "guardiao-triwer", "scripts")]
arq_registrar = next((os.path.join(c, "registrar_tarefas.ps1") for c in candidatos if os.path.exists(os.path.join(c, "registrar_tarefas.ps1"))), None)
if arq_registrar:
    registrar = open(arq_registrar, encoding="utf-8-sig").read()
    confere("instalação nova já nasce sem janela e com atraso no logon",
            "sem_janela.py" in registrar and "-Execute 'powershell.exe'" not in registrar and "$t.Delay = $atraso" in registrar and registrar.count("(Logon '") == 4)
else:
    print("  (não achei o registrar_tarefas.ps1 nesta instalação: pulei a checagem das tarefas novas)")

print(f"{sum(resultados)} de {len(resultados)} checagens passaram.")
sys.exit(0 if all(resultados) else 1)
