"""Controle da fala (0.7.0), sem navegador, sem o Claude de verdade e sem áudio: fechar a janela no meio da resposta para a fala (e a sessão do
Claude Code é interrompida, sem deixar sobra para a fala seguinte); voz sem janela e página recarregada não param; a saudação tem prazo e cai na frase
local; o erro do Claude (sem login) vira uma frase que a pessoa entende; e os tempos de cada frase ficam em logs\\latencia.jsonl."""
import argparse
import ctypes
import json
import os
import sys
import tempfile
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import limpeza_teste  # noqa: E402,F401
import hud_servidor as h  # noqa: E402
limpeza_teste.fixar_relogio(h)
import controle_fala  # noqa: E402
import guardiao_sessao as gs  # noqa: E402
import guardiao_voz as g  # noqa: E402
import latencia  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


tmp = tempfile.mkdtemp(prefix="gv_oper_cf_")
h.OPER = tmp
g.OPER = tmp
g.SAUDACAO_ARQ = os.path.join(tmp, "logs", "saudacao.json")
os.makedirs(os.path.join(tmp, "logs"), exist_ok=True)
with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"pessoa": {"nome": "Rafa Lima", "artigo": "o"}, "agente": {"nome": "Guardião"}}, f)


class SdFalso:
    """O som de mentira: só conta o que foi tocado e quantas vezes mandaram parar."""
    def __init__(self):
        self.tocadas, self.paradas = [], 0

    def play(self, amostras, taxa):
        self.tocadas.append(round(len(amostras) / taxa, 2))

    def wait(self):
        pass

    def stop(self):
        self.paradas += 1


class KokoroFalso:
    def create(self, texto, voice=None, speed=1.0, lang=None):
        time.sleep(0.03)
        return np.zeros(int(24000 * 0.6), dtype="float32"), 24000  # 0,6 s de fala por frase


responder_original, dizer_original, preferencias_original = g.responder_falando, g.dizer, g.preferencias
sd = SdFalso()
g.sd = sd
controle_fala.sd = sd
g._kokoro = KokoroFalso()
controle_fala.GRACA_JANELA = 0.4
eventos = []
emitir_original = h.bus.emitir
h.bus.emitir = lambda tipo, /, **d: (eventos.append((tipo, d)), emitir_original(tipo, **d))[1]


def fonte(n, espera=0.2, antes=0.0):
    """Um Claude de mentira que escreve n frases, uma a cada `espera` segundos."""
    def gerar():
        time.sleep(antes)
        for i in range(n):
            yield f"Frase número {i + 1} da resposta."
            time.sleep(espera)
    return gerar


def rodar_em_thread(**kw):
    saida = {}

    def alvo():
        try:
            saida["r"] = g.responder_falando("pergunta", "pm_santa", **kw)
        except Exception as erro:
            saida["erro"] = erro

    t = threading.Thread(target=alvo)
    t.start()
    return t, saida


def ultima_linha_do_log():
    linhas = latencia.ler(1)
    return linhas[-1] if linhas else {}


# ---------------- janela fechada no meio da resposta ----------------
janela = h.bus.assinar()  # a janela do painel está aberta
t0 = time.time()
t, saida = rodar_em_thread(fonte=fonte(8))
time.sleep(1.3)  # já disse umas duas frases
h.bus.sair(janela)  # a pessoa fecha a janela
t.join(10)
primeira, total, falado = saida.get("r", (None, None, ""))
n_ditas = falado.count("Frase número")
confere("fechar a janela no meio da resposta para a fala (disse só parte das 8 frases)", not t.is_alive() and 1 <= n_ditas <= 4, (n_ditas, saida))
confere("a fala parou logo (bem antes das 8 frases inteiras, que levariam uns 8 s)", total is not None and total < 3.5, total)
confere("o som foi mandado parar", sd.paradas >= 1, sd.paradas)
confere("fica marcado que a fala foi parada, no registro de tempos", ultima_linha_do_log().get("parado") is True, ultima_linha_do_log())
confere("o que já foi dito aparece na tela como a resposta", any(tp == "guardiao_fim" and "Frase número 1" in d.get("texto", "") for tp, d in eventos))
confere("depois de parar, nada continua marcado como falando", not controle_fala.FALANDO.is_set())

# ---------------- a fala seguinte começa limpa ----------------
sd.paradas = 0
t, saida = rodar_em_thread(fonte=fonte(3))
t.join(10)
confere("a resposta seguinte sai inteira (o 'parar' não fica preso)", saida.get("r") and saida["r"][2].count("Frase número") == 3, saida)

# ---------------- só voz, sem janela: não para ----------------
t, saida = rodar_em_thread(fonte=fonte(5))
t.join(15)
confere("sem nenhuma janela aberta (só voz), a resposta sai inteira", saida.get("r") and saida["r"][2].count("Frase número") == 5 and sd.paradas == 0, saida)
j2 = h.bus.assinar()
h.bus.sair(j2)  # a janela abriu e fechou antes de qualquer fala
time.sleep(0.7)
t, saida = rodar_em_thread(fonte=fonte(4))
t.join(15)
confere("janela que fechou ANTES da resposta não impede a fala", saida.get("r") and saida["r"][2].count("Frase número") == 4, saida)

# ---------------- página recarregada: a conexão volta logo e a fala continua ----------------
j3 = h.bus.assinar()
t, saida = rodar_em_thread(fonte=fonte(6))
time.sleep(1.0)
h.bus.sair(j3)
time.sleep(0.15)
j3b = h.bus.assinar()  # a página recarregou dentro do prazo de tolerância
t.join(15)
confere("página recarregada (a conexão volta em 0,15 s) não corta a fala", saida.get("r") and saida["r"][2].count("Frase número") == 6, saida)
h.bus.sair(j3b)
time.sleep(0.6)

# ---------------- as frases fixas (dizer) também param ----------------
a = argparse.Namespace(cerebro=True, voz="kokoro", voz_kokoro="pm_santa", voz_nome="", sem_preview=True, previa_local=True, sem_escuta_aberta=False)
j4 = h.bus.assinar()
tocadas_antes = len(sd.tocadas)
th = threading.Thread(target=lambda: g.dizer("Uma frase. Outra frase. Mais uma frase. E a última frase.", a))
th.start()
time.sleep(0.9)
h.bus.sair(j4)
th.join(10)
confere("uma frase fixa (dizer) também para quando a janela fecha", not th.is_alive() and len(sd.tocadas) - tocadas_antes < 4, len(sd.tocadas) - tocadas_antes)
time.sleep(0.6)

# ---------------- registro de tempos ----------------
t, saida = rodar_em_thread(fonte=fonte(3), modo="rapido", motivo="teste")
t.join(10)
linha = ultima_linha_do_log()
nomes = [p[1] for p in linha.get("passos", [])]
confere("o registro de tempos guarda, por frase, a chegada, a geração da voz e o toque", nomes.count("frase") == 3 and nomes.count("sintese_fim") == 3 and nomes.count("toque_fim") == 3, nomes)
sint = [p[2] for p in linha.get("passos", []) if p[1] == "sintese_fim"]
confere("cada geração de voz diz quanto tempo de fala saiu e quanto tempo levou (a base do fator de tempo real)", sint and all("fala" in x and "gasto" in x for x in sint), sint)
confere("o registro traz modo, tempo total e uso do computador", linha.get("modo") == "rapido" and linha.get("total", 0) > 0 and "cpu_pct" in linha, linha)

# ---------------- a saudação tem prazo ----------------
inicio = time.time()
try:
    g.responder_falando("p", "pm_santa", fonte=fonte(2, antes=3.0), limite_primeira=0.8, modo="saudacao")
    estourou = False
except TimeoutError:
    estourou = True
confere("saudação que não chega no prazo é abandonada em cerca de 1 s (não espera os 3 s do Claude)", estourou and time.time() - inicio < 2.2, time.time() - inicio)
time.sleep(0.5)
confere("e o Claude dela não fica falando 'do nada' depois", not controle_fala.FALANDO.is_set())

ditas, registradas = [], []
def dizer_falso(texto, a_, *x, **k):
    controle_fala.comecar()  # o dizer de verdade começa assim: limpa o 'parar' que o prazo da saudação acionou
    ditas.append(texto)
    controle_fala.terminar()


g.dizer = dizer_falso
g.registrar_saudacao = lambda texto: registradas.append(texto)
g.preferencias = lambda: {"saudacao": True, "voz_guardiao": True, "sessao": False, "escuta_aberta": True}
eventos.clear()


def estoura(*x, **k):
    raise TimeoutError("a primeira frase não chegou")


g.responder_falando = estoura
import queue  # noqa: E402
r = g.atender(a, queue.Queue(), None, None, 0, texto_digitado="Isto é um pedido de saudação", saudacao=True)
parte = "Bom dia" if 5 <= time.localtime().tm_hour < 12 else "Boa tarde" if 12 <= time.localtime().tm_hour < 18 else "Boa noite"
confere("saudação que estoura o prazo fala a frase local (horário e nome), sem mostrar erro", ditas == [f"{parte}, Rafa."] and not any(tp == "erro" for tp, _ in eventos), (ditas, eventos))
confere("a saudação fica registrada como feita (não repete no próximo reinício)", registradas == [f"{parte}, Rafa."] and not g.pode_saudar(), registradas)
confere("e o microfone reabre para a pessoa responder, como numa saudação normal", r is True, r)

ditas.clear()
registradas.clear()
eventos.clear()
g.SAUDACAO_ARQ = os.path.join(tmp, "logs", "saudacao2.json")


def quebra(*x, **k):
    raise FileNotFoundError(g.AVISO_SEM_CLAUDE)


g.responder_falando = quebra
g.atender(a, queue.Queue(), None, None, 0, texto_digitado="Isto é um pedido de saudação", saudacao=True)
confere("sem Claude Code: a abertura ainda cumprimenta e, na mesma fala, diz o que falta (sem aviso de erro solto na tela)",
        ditas == [f"{parte}, Rafa. {g.AVISO_SEM_CLAUDE}"] and not any(tp == "erro" for tp, _ in eventos), (ditas, eventos))

# ---- uma pergunta com a conta no limite: o motivo é falado e escrito, o microfone não reabre e nada é repetido por outro caminho ----
MENSAGEM_LIMITE = "Você atingiu o limite semanal do seu plano do Claude. Ele volta em 17 de outubro, às 19h. Até lá não consigo responder."
ditas.clear()
eventos.clear()


def no_limite(*x, **k):
    raise gs.ErroDeConta(MENSAGEM_LIMITE)


g.responder_falando = no_limite
seguir = g.atender(a, queue.Queue(), None, None, 0, texto_digitado="o que eu tenho hoje")
confere("pergunta com a conta no limite: o motivo é falado, sem aviso de erro genérico", ditas == [MENSAGEM_LIMITE] and not any(tp == "erro" for tp, _ in eventos), (ditas, eventos))
confere("e o microfone não reabre esperando resposta", seguir is False, seguir)
ditas.clear()
g.atender(a, queue.Queue(), None, None, 0, texto_digitado="Isto é um pedido de saudação", saudacao=True)
confere("abertura com a conta no limite: cumprimenta e já avisa, numa fala só", ditas == [f"{parte}, Rafa. {MENSAGEM_LIMITE}"], ditas)

# ---------------- o erro do Claude vira uma frase que a pessoa entende ----------------
confere("'Not logged in' vira 'não está conectado à sua conta'", "não está conectado à sua conta" in gs.explicar_erro_do_claude("Not logged in · Please run /login"))
confere("limite de uso genérico vira uma frase em português", "limite de uso" in gs.explicar_erro_do_claude("Claude usage limit reached") and "mais tarde" in gs.explicar_erro_do_claude("You've hit your limit"))
confere("limite semanal diz quando volta, com dia e hora (a mensagem do Claude Code vem em inglês e na hora de quem usa)",
        gs.explicar_erro_do_claude("You've hit your weekly limit \u00b7 resets Oct 17, 7pm (America/Fortaleza)")
        == "Você atingiu o limite semanal do seu plano do Claude. Ele volta em 17 de outubro, às 19h. Até lá não consigo responder.")
confere("limite da sessão (5 horas) diz só a hora", gs.explicar_erro_do_claude("You've hit your session limit \u00b7 resets 3pm (America/Sao_Paulo)").endswith("Ele volta às 15h."))
confere("hora com minutos e formato antigo da mensagem", gs.explicar_erro_do_claude("5-hour limit reached \u2219 resets 8:30pm").endswith("Ele volta às 20h30.")
        and gs.explicar_erro_do_claude("Claude usage limit reached. Your limit will reset at 5am (America/New_York)").endswith("Ele volta às 5h."))
confere("servidor sobrecarregado não é limite de uso", "sobrecarregado" in gs.explicar_erro_do_claude("API Error: 529 overloaded_error") and "limite" not in gs.explicar_erro_do_claude("overloaded"))
confere("erro desconhecido não inventa explicação", gs.explicar_erro_do_claude("algo estranho") == "")

falso = os.path.join(tmp, "claude_sem_login.py")
with open(falso, "w", encoding="utf-8") as f:
    f.write('import json, sys\nsys.stdout.reconfigure(encoding="utf-8")\n'
            'print(json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login", "total_cost_usd": 0, "usage": {}}))\n')
g.comando_claude = lambda pergunta, streaming, modelo=None: ([sys.executable, falso], dict(os.environ))
try:
    list(g.frases_do_claude("oi"))
    mensagem = ""
except RuntimeError as erro:
    mensagem = str(erro)
confere("sem login, o modo rápido levanta o motivo de verdade (não o 'não respondeu')", "não está conectado à sua conta" in mensagem, mensagem)

# ---------------- sessão do Claude Code: fechar a janela interrompe o turno ----------------
AQUI = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(tmp, "claude_falso.log")
os.environ["GUARDIAO_FALSO_LOG"] = LOG
gs.COMANDO = [sys.executable, os.path.join(AQUI, "claude_falso.py")]
arq_prompt = os.path.join(tmp, "prompt_sessao.txt")
with open(arq_prompt, "w", encoding="utf-8") as f:
    f.write("prompt de teste")
g.arquivo_prompt_sessao = lambda: arq_prompt
gs.AO_FECHAR_TURNO.clear()
eventos.clear()
g.responder_falando = responder_original
g.dizer = dizer_original
g.preferencias = preferencias_original
gs._fechar_processo()


def turno_inteiro(pedido):
    """Um turno pela sessão, como o programa faz: o texto falado e a lista de ferramentas."""
    falas = []
    for tipo, dado in gs.turno(pedido, arq_prompt):
        if tipo == "texto":
            falas.append(dado)
    return "".join(falas)


def do_falso(tipo):
    try:
        with open(LOG, encoding="utf-8") as f:
            return [x for x in map(json.loads, f) if x.get("tipo") == tipo]
    except OSError:
        return []


janela5 = h.bus.assinar()
inicio = time.time()
t, saida = rodar_em_thread(fonte=lambda: g.frases_da_sessao("responda devagar"), modo="sessao")
time.sleep(2.2)  # a sessão abriu e já escreveu umas frases
h.bus.sair(janela5)
t.join(12)
falado = saida.get("r", (0, 0, ""))[2]
confere("sessão: fechar a janela para a fala no meio de uma resposta de 14 frases", not t.is_alive() and 1 <= falado.count("Frase número") <= 8, (falado, saida))
time.sleep(0.8)
confere("sessão: o Claude Code recebeu o pedido de interrupção", len(do_falso("interrupt")) == 1, do_falso("interrupt"))
confere("sessão: o que sobrou da resposta interrompida NÃO vira fala depois (nada na fila de falas pendentes)",
        not any(c[0] == "sessao_fala" for c in list(h.bus.comandos.queue)), list(h.bus.comandos.queue))
t_seguinte = time.time()
resposta2 = turno_inteiro("quantas vezes eu falei")
espera_seguinte = time.time() - t_seguinte
confere("sessão: a fala seguinte funciona e não confunde o fecho do turno interrompido com o dela", "Você já falou 2 vezes" in resposta2, resposta2)
confere("sessão: e ela não espera à toa pelo fecho da interrupção (que já foi consumido)", espera_seguinte < 2.0, round(espera_seguinte, 2))

# ---- conta no limite de uso pela sessão: o motivo chega em português, e o modo rápido NÃO é tentado (falharia igual e dobraria a espera) ----
tentou_rapido = []
frases_do_claude_original = g.frases_do_claude
g.frases_do_claude = lambda *x, **k: (tentou_rapido.append(1), iter(()))[1]
try:
    list(g.frases_da_sessao("estoure o limite"))
    erro_conta = None
except gs.ErroDeConta as erro:
    erro_conta = str(erro)
g.frases_do_claude = frases_do_claude_original
confere("sessão no limite de uso: levanta o motivo em português com o dia e a hora em que volta", erro_conta == MENSAGEM_LIMITE, erro_conta)
confere("e não cai no modo rápido", not tentou_rapido, tentou_rapido)
confere("a sessão segue de pé depois do erro (a próxima fala funciona)", "Você já falou" in turno_inteiro("quantas vezes eu falei"))


def classe_de_prioridade(pid):
    k = ctypes.windll.kernel32
    k.OpenProcess.restype = ctypes.c_void_p
    k.GetPriorityClass.argtypes = [ctypes.c_void_p]
    manipulador = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    try:
        return k.GetPriorityClass(manipulador)
    finally:
        k.CloseHandle(ctypes.c_void_p(manipulador))


confere("o Claude da sessão roda em prioridade abaixo do normal (a voz, gerada neste computador, não perde CPU para os conectores que arrancam)",
        classe_de_prioridade(gs._proc.proc.pid) == 0x4000, classe_de_prioridade(gs._proc.proc.pid))
gs._fechar_processo()

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
