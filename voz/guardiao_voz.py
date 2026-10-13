# Guardião por voz: MVP de teste.
# Fica escutando o microfone no PC (Vosk, local, sem internet). Ao ouvir "Ei guardião", toca um bipe, grava o que você
# falar até o silêncio e transcreve no Groq (Whisper). Com --cerebro, pergunta ao Claude (guardião enxuto, dentro da
# assinatura) e fala a resposta com a voz Kokoro (local), mostrando o texto junto com a fala.
# A tela (http://localhost:8767) acompanha tudo ao vivo. O áudio só sai do PC depois da palavra de ativação, e só para o Groq.
import argparse
import atexit
import asyncio
import ctypes
import io
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import wave
import winreg
import winsound

import edge_tts
import numpy as np
import requests
import sounddevice as sd
from vosk import KaldiRecognizer, SetLogLevel

import controle_fala
import guardiao_sessao
import guardiao_v2 as v2
import janela_painel
import latencia
import memoria_conversa
import nativo
from fala import normalizar_para_fala
from hud_servidor import (_config, _norm, _plano_de_hoje, _registro_de_hoje, agir, bus, conflitos_do_plano, editar_plano, iniciar_servidor,
                          pendencias_texto, pessoa, preferencias, refs_conhecidas, resolver_lista, resumo_aprovacao, salvar_preferencias)

BASE = os.path.dirname(os.path.abspath(__file__))
OPER = os.path.dirname(BASE)  # pasta operacional do guardião

if sys.stdout is None or sys.stderr is None:  # rodando em segundo plano (pythonw): sem terminal, escreve num arquivo de registro
    _pasta_logs = os.path.join(OPER, "logs")
    os.makedirs(_pasta_logs, exist_ok=True)
    _arq_log = os.path.join(_pasta_logs, "voz.log")
    if os.path.exists(_arq_log) and os.path.getsize(_arq_log) > 2_000_000:
        os.remove(_arq_log)
    sys.stdout = sys.stderr = open(_arq_log, "a", encoding="utf-8", buffering=1)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # nenhuma janelinha de terminal ao chamar o Claude ou o PowerShell
SR = 16000
BLOCO = 1600  # 0,1 s de áudio por bloco
# Só "ei guardião" aciona o microfone. As palavras curtas estão na lista para o Vosk ter como entender "o guardião", "do guardião" ou "meu guardião"
# sem empurrar o som para "ei" (antes, qualquer frase com a palavra guardião acionava).
GRAMATICA = json.dumps(["ei guardião", "ei", "guardião", "guardiã", "o", "a", "e", "é", "do", "da", "de", "no", "ao", "pro", "meu", "esse", "que", "um", "com", "eu", "[unk]"],
                       ensure_ascii=False)
VOZ_WINDOWS = "Microsoft Maria Desktop"
VOZ_EDGE = "pt-BR-FranciscaNeural"  # vozes neurais do Edge: ThalitaNeural, AntonioNeural
VOZ_KOKORO = "pm_santa"  # voz padrão; outras em português: pm_alex, pf_dora
VOZES_KOKORO = ("pm_santa", "pm_alex", "pf_dora")  # a escolhida no onboarding fica em agente.voz do config.json
AVISO_SEM_CHAVE = ("Microfone desligado: falta a chave gratuita do Groq. Dê dois cliques em definir_chave_groq.bat, na pasta voz. "
                   "Em até um minuto depois de gravar a chave o microfone liga sozinho. Enquanto isso, escreva aqui embaixo.")
AVISO_SEM_MIC = "Não achei um microfone neste computador. Escreva aqui embaixo."
INTERVALO_PREVIA = 3.3  # segundos entre prévias no Groq (limite grátis: 20 pedidos por minuto)
PORTA_TELA = 8767
_kokoro = None


def reconhecedor(modelo):
    """O ouvido da palavra de ativação: só conhece as palavras da GRAMATICA e devolve cada uma com o grau de certeza."""
    rec = KaldiRecognizer(modelo, SR, GRAMATICA)
    rec.SetWords(True)
    return rec


def chamou(resultado):
    """A pessoa disse "ei guardião"? Vale com as duas palavras coladas e no começo da fala (no máximo uma palavra antes).
    A palavra guardião sozinha, ou no meio de uma frase dita para outra pessoa, não aciona."""
    p = resultado.get("result") or []
    for i in range(min(2, len(p) - 1)):
        a, b = p[i], p[i + 1]
        if (a.get("word") == "ei" and str(b.get("word") or "").startswith("guardi") and b.get("start", 0) - a.get("end", 0) < 0.45
                and a.get("conf", 0) >= 0.3 and b.get("conf", 0) >= 0.6):
            return True
    return False


def achar_claude(refazer=False):
    """O Claude Code está instalado e executa? (npm, instalador oficial ou extensão do VS Code: veja guardiao_sessao.comando_do_claude)"""
    return bool(guardiao_sessao.comando_do_claude(refazer))


AVISO_SEM_CLAUDE = guardiao_sessao.AVISO_SEM_CLAUDE


def voz_configurada():
    """A voz escolhida no onboarding (agente.voz do config.json). Sem escolha, ou com um nome que não existe, a padrão."""
    escolhida = str((_config().get("agente") or {}).get("voz") or "").strip()
    return escolhida if escolhida in VOZES_KOKORO else VOZ_KOKORO


def chave_groq():
    valor = os.environ.get("GROQ_API_KEY")
    if valor:
        return valor
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, "GROQ_API_KEY")[0]
    except OSError:
        return None


class Microfone:
    """O microfone do guardião. Se faltar a chave do Groq ou o aparelho na hora de ligar, a pessoa pode resolver com o guardião aberto
    (gravar a chave, plugar o fone): o programa tenta de novo sozinho e a tela passa a mostrar o microfone ligado."""

    def __init__(self, a, entrada):
        self.a, self.entrada, self.stream, self.ultimo_erro = a, entrada, None, ""

    def tentar(self, chave):
        if self.stream is not None:
            return True
        if not chave:  # sem a chave não há o que fazer com o áudio: o microfone fica desligado
            return False
        try:
            stream = sd.RawInputStream(samplerate=SR, blocksize=BLOCO, dtype="int16", channels=1, device=self.a.mic,
                                       callback=lambda indata, frames, tempo, status: self.entrada.put(bytes(indata)))
            stream.start()
        except Exception as erro:  # computador sem microfone (ou com ele bloqueado): o painel segue por texto
            if str(erro) != self.ultimo_erro:  # o problema é contado uma vez só, não a cada tentativa
                self.ultimo_erro = str(erro)
                print("  (não consegui abrir o microfone:", erro, ")")
            return False
        self.stream = stream
        return True

    def parar(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def existe(self):
        """Há um aparelho de entrada? Só consulta a lista, não abre nada (abrir acende o indicador de microfone em uso do Windows)."""
        try:
            return any(d.get("max_input_channels", 0) > 0 for d in sd.query_devices())
        except Exception:
            return False


MIC = None  # o Microfone do main(); as gravações por botão abrem e fecham por ele


def escuta_continua():
    """Preferência "Escuta contínua" (mic_sempre_ligado). Desligada (padrão), o microfone fica fechado e só abre durante uma gravação
    pedida por botão; ligada, ele fica aberto esperando "Ei guardião" e reabre sozinho depois de uma pergunta do guardião."""
    return bool(preferencias().get("mic_sempre_ligado", False))


def abrir_para_gravar():
    """Começo de uma gravação por botão. Devolve False se o microfone não abriu (a gravação não pode esperar um áudio que não vem)."""
    return MIC is None or MIC.tentar(chave_groq())


def fechar_apos_gravar(q):
    """Fim da gravação: sem a escuta contínua o microfone fecha de verdade, para o indicador do Windows apagar."""
    if MIC is not None and not escuta_continua():
        MIC.parar()
        drenar(q)


def rms_de(dado):
    x = np.frombuffer(dado, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def nivel_mic(rms):
    """Converte o volume do microfone para 0 a 1, para a tela."""
    return float(min(1.0, max(0.0, (rms - 150.0) / 2500.0)))


def drenar(q):
    while not q.empty():
        try:
            q.get_nowait()
        except queue.Empty:
            break


def para_wav(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return buf.getvalue()


PAUSA_CURTA = 1.2  # s de silêncio que encerram uma fala curta ("sim", "pode aprovar")
PAUSA_LONGA = 2.4  # depois de alguns segundos falando, a pausa para pensar no meio da frase é maior
FALA_LONGA = 3.0  # s de voz a partir dos quais vale a pausa longa
ESPERA_FALA = 7.0  # sem ninguém falar nesse tempo, a escuta se encerra
TETO_FALA = 240.0  # trava de segurança (4 minutos), para um ruído contínuo não prender o microfone
CANCELADO = object()  # a pessoa apertou Esc (ou clicou no microfone) enquanto o guardião escutava


def bipe(frequencia, ms):
    """Sinal sonoro de reserva. Com o painel aberto quem toca é ele (som do microfone ligando, desligando e da escuta cancelada);
    o bipe do Windows só existe para quem roda o guardião sem tela, senão a pessoa não saberia a hora de falar."""
    if bus.assinantes:
        return False
    winsound.Beep(frequencia, ms)
    return True


def esc_apertado():
    """Esc em qualquer janela do computador (não só no painel). Só é consultado enquanto o guardião está ouvindo."""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8001)
    except Exception:
        return False


def gravar(q, piso, ao_bloco=None):
    """Grava até a pessoa parar de falar. Devolve o áudio, None (ninguém falou) ou CANCELADO (Esc ou clique no microfone).
    A pausa que encerra cresce com a fala: 1,2 s numa resposta curta e 2,4 s depois de alguns segundos falando.
    ao_bloco(dado, falando) pode devolver o texto ao vivo: enquanto ele muda, a pessoa ainda está falando."""
    limiar = max(250.0, piso * 3.0)
    manter = limiar * 0.6  # depois que a fala começou, um trecho mais baixo ainda conta como voz
    inicio = time.time()
    ultimo = inicio
    falou = False
    voz_s = 0.0
    seguidos = 0
    recentes = []
    texto_antes = ""
    primeiro = fim_voz = 0
    blocos = []
    esc_apertado()  # zera um Esc antigo
    bus.cancelar_escuta.clear()
    while True:
        dado = q.get()
        blocos.append(dado)
        rms = rms_de(dado)
        bus.emitir("nivel", mic=nivel_mic(rms))
        agora = time.time()
        if esc_apertado() or bus.cancelar_escuta.is_set():
            bus.cancelar_escuta.clear()
            return CANCELADO
        recentes = (recentes + [rms])[-5:]
        if not falou:
            seguidos = seguidos + 1 if rms > limiar else 0
            if seguidos >= 3:  # 0,3 s de voz seguida: um estalo ou uma tecla não contam como fala
                falou = True
                primeiro = max(0, len(blocos) - 6)
                voz_s = 0.3
                ultimo = agora
                fim_voz = len(blocos)
        elif rms > manter:
            voz_s += BLOCO / SR
            ultimo = agora
            fim_voz = len(blocos)
        texto = ao_bloco(dado, falou) if ao_bloco else None
        if falou and texto and texto != texto_antes and max(recentes) > limiar * 0.4:  # o texto ao vivo ainda está andando
            ultimo = agora
            fim_voz = len(blocos)
        texto_antes = texto or texto_antes
        if falou and agora - ultimo > (PAUSA_LONGA if voz_s >= FALA_LONGA else PAUSA_CURTA):
            break
        if not falou and agora - inicio > ESPERA_FALA:
            return None
        if agora - inicio > TETO_FALA:
            if not falou:
                return None
            break
    return b"".join(blocos[primeiro:fim_voz + 4])  # sem o silêncio das pontas: silêncio longo faz o Whisper inventar frases


# Frases que o Whisper inventa quando recebe silêncio ou ruído (vêm das legendas com que ele foi treinado).
ALUCINACAO = re.compile(
    r"(?:[Ll]egendas?|[Ll]egendad[oa]s?|[Tt]ranscri[cç][aã]o|[Tt]radu[cç][aã]o|[Rr]evis[aã]o)\s+(?:e\s+\w+\s+)?(?:por|pela|pelo|de|da|do)\s+(?:a\s+|o\s+)?"
    r"(?:comunidade(?:\s+[\wÀ-ú.]+){0,3}|[A-ZÀ-Ú][\wÀ-ú]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ú][\wÀ-ú.]+)*)"
    r"|[^.!?]*\b[Aa]mara\.org[^.!?]*|[^.!?]*\b[Ss][oô]nia [Rr]uberti[^.!?]*|[Oo]brigad[oa] por assistir[^.!?]*|[Ii]nscreva-se no canal[^.!?]*"
    r"|[^.!?]*\bdeixe (?:o|seu) like\b[^.!?]*|\bwww\.\S+|[♪♫]+"
    r"|[\[(](?:[Mm][úu]sica|[Aa]plausos|[Rr]isos|[Rr]isadas)[\])]|[Oo]brigad[oa] por ter assistido[^.!?]*|[Ss]e inscreva no canal[^.!?]*|[Aa]tive o sininho[^.!?]*"
    r"|[Aa]té a próxima[.!]?(?=\s*$)|[Aa]té o próximo v[ií]deo[^.!?]*")
_PONTAS = " \"'“”.,;:!?-"


def limpar_alucinacao(texto):
    """Tira as frases inventadas pelo Whisper. Se não sobrar fala de verdade, devolve vazio."""
    original = (texto or "").strip()
    limpo = re.sub(r"\s+", " ", ALUCINACAO.sub(" ", original)).strip()
    if limpo == original:
        return original
    limpo = limpo.strip(_PONTAS)
    if len(re.sub(r"[^A-Za-zÀ-ú0-9]", "", limpo)) < 2:
        return ""
    return limpo


# Uma palavra só, dita em menos de um segundo e meio, quase sempre é ruído que o Whisper "transcreve" mesmo assim (um clique vira "Mãe.", o silêncio vira
# "Obrigado."). Vale como fala só se for um comando ou uma resposta conhecida; palavra curta de até 3 letras que não está na lista também cai.
RUIDO_COMUM = {"obrigado", "obrigada", "tchau", "mae", "ah", "eh", "hm", "hum", "uhum", "ne", "ta", "to", "tudo", "bom", "tá", "valeu", "aplausos", "musica", "gente", "pai", "papai"}
CURTAS_VALIDAS = {"sim", "nao", "ok", "oi", "ola", "pare", "para", "pode", "isso", "certo", "claro", "aprova", "aprovar", "cancela", "cancelar", "volta", "voltar",
                  "sempre", "feito", "pronto", "conclui", "ajuda", "agora", "hoje", "plano", "amanha", "resumo", "pendencias", "continua", "continue", "repete", "repita"}


def fala_confiavel(texto, segundos_de_voz):
    """False quando o que foi 'ouvido' é quase certamente ruído: uma palavra só, curta no tempo, que não é comando nem resposta conhecida."""
    palavras = _norm(texto).split()
    if len(palavras) != 1 or segundos_de_voz >= 1.5:
        return True
    palavra = palavras[0]
    if palavra in CURTAS_VALIDAS:
        return True
    return not (palavra in RUIDO_COMUM or len(palavra) <= 3)


def transcrever(wav_bytes, chave):
    t0 = time.time()
    r = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": "Bearer " + chave},
        files={"file": ("fala.wav", wav_bytes, "audio/wav")},
        data={"model": "whisper-large-v3-turbo", "language": "pt", "response_format": "json", "temperature": "0"},
        timeout=30,
    )
    r.raise_for_status()
    return limpar_alucinacao(r.json().get("text", "").strip()), time.time() - t0


class PreviaGroq:
    """Enquanto você fala, manda o áudio acumulado ao Groq a cada poucos segundos e guarda o texto certo mais recente."""

    def __init__(self, chave):
        self.chave = chave
        self.blocos = []
        self.texto = ""
        self.ocupado = False
        self.ativo = False
        self.ultimo = time.time()

    def alimentar(self, dado, falando=True):
        self.blocos.append(dado)
        if not self.ativo:
            if not falando:  # antes da fala só fica um resto curto de áudio: silêncio enviado ao Whisper vira frase inventada
                del self.blocos[:-6]
                return
            self.ativo = True
            self.ultimo = time.time() - INTERVALO_PREVIA / 2
        agora = time.time()
        segundos = len(self.blocos) * BLOCO / SR
        intervalo = INTERVALO_PREVIA if segundos < 20 else 7.0 if segundos < 60 else 15.0  # fala longa: prévias mais espaçadas, para caber no limite do Groq
        if not self.ocupado and agora - self.ultimo >= intervalo and len(self.blocos) >= 20:
            self.ocupado = True
            self.ultimo = agora
            threading.Thread(target=self._enviar, args=(b"".join(self.blocos),), daemon=True).start()

    def _enviar(self, pcm):
        try:
            self.texto, _ = transcrever(para_wav(pcm), self.chave)
        except Exception:
            pass
        finally:
            self.ocupado = False


def contexto_proximos_dias():
    """Planos já montados para os próximos 3 dias e tarefas do ClickUp com prazo nesse período."""
    hoje = time.strftime("%Y-%m-%d")
    limite = time.strftime("%Y-%m-%d", time.localtime(time.time() + 3 * 86400))
    partes = []
    pasta = os.path.join(OPER, "planos")
    if os.path.isdir(pasta):
        for nome in sorted(os.listdir(pasta)):
            m = re.match(r"plano_(\d{4}-\d{2}-\d{2})\.json$", nome)
            if m and hoje < m.group(1) <= limite:
                with open(os.path.join(pasta, nome), encoding="utf-8") as f:
                    partes.append(f"PLANO DE {m.group(1)}:\n" + f.read())
    resumo = os.path.join(OPER, "resumo_clickup.json")
    if os.path.exists(resumo):
        try:
            with open(resumo, encoding="utf-8-sig") as f:
                tarefas = json.load(f).get("tarefas", [])
            linhas = [
                f"{t['prazo']} {t.get('inicio') or ''} | {t['nome']} ({t.get('lista', '')})"
                for t in tarefas
                if hoje <= t.get("prazo", "") <= limite
            ]
            if linhas:
                partes.append("TAREFAS DO CLICKUP COM PRAZO NOS PROXIMOS 3 DIAS:\n" + "\n".join(linhas[:20]))
        except (OSError, ValueError, KeyError):
            pass
    return "\n\n".join(partes)


def pasta_memoria():
    """Onde ficam o perfil e as outras notas: pastas.memoria do config.json (pode ser um cofre do Obsidian) ou a pasta memoria ao lado."""
    return (_config().get("pastas") or {}).get("memoria") or os.path.join(OPER, "memoria")


def _perfil():
    """O perfil da pessoa (memória). Sem o arquivo, a voz funciona do mesmo jeito, só sem conhecer a rotina dela."""
    try:
        with open(os.path.join(pasta_memoria(), "perfil.md"), encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return "(o perfil ainda não foi criado: rode o onboarding do guardião)"


# Os textos das instruções tratam a pessoa por "ele". Com pessoa.artigo = "a", esta frase entra na abertura das instruções.
GENERO_FEMININO = "<O Fulano> é mulher: onde estas instruções dizem ele ou dele, entenda ela ou dela, e fale com ela e sobre ela sempre no feminino. "


def _p(texto):
    """Troca as marcas <o Fulano>, <O Fulano>, <do Fulano>, <ao Fulano> e <Fulano> pelo jeito de chamar a pessoa (config.json: pessoa.nome e pessoa.artigo)."""
    quem = pessoa()
    feminino = str((_config().get("pessoa") or {}).get("artigo") or "").strip().lower() == "a"
    texto = texto.replace("<genero>", GENERO_FEMININO if feminino else "")
    return (texto.replace("<o Fulano>", quem["o"]).replace("<O Fulano>", quem["o"][:1].upper() + quem["o"][1:]).replace("<do Fulano>", quem["do"])
            .replace("<ao Fulano>", quem["ao"]).replace("<Fulano>", quem["primeiro"]))


def iniciar_revisao():
    global REVISAO
    REVISAO = {"inicio": time.time(), "ultimo": time.time()}
    bus.emitir("revisao", ativa=True)


def encerrar_revisao():
    global REVISAO
    if REVISAO is not None:
        REVISAO = None
        bus.emitir("revisao", ativa=False)


def revisao_ativa():
    if REVISAO and time.time() - REVISAO["ultimo"] > 1200:  # 20 minutos sem conversa: a revisão se encerra sozinha
        encerrar_revisao()
    return REVISAO is not None


def tocar_revisao():
    if REVISAO:
        REVISAO["ultimo"] = time.time()


def avisar_modelo(texto):
    AVISOS_AO_MODELO.append(texto)
    del AVISOS_AO_MODELO[:-5]


# ---------------- ação por voz que não deu certo ----------------
# O guardião diz "estou concluindo" na hora em que a frase sai, e o resultado só chega depois: quem já falou não volta atrás.
# Aqui o programa fecha a conta. Se a ação falhou, ou foi recusada porque a pessoa não a pediu, ele mesmo diz isso em voz alta no fim
# da resposta e avisa o modelo, que não deve repetir nem afirmar que deu certo. (O toast de erro na tela já existia.)
VERBO_ACAO = {"concluir": ("concluir", "conclua"), "reabrir": ("reabrir", "reabra"), "comentar": ("anotar em", "anote em"),
              "criar": ("criar a tarefa", "crie a tarefa"), "aprovar": ("aprovar o plano", "aprove o plano")}
ACOES_EM_CURSO = 0
_TRAVA_ACOES = threading.Lock()
CORRECOES = []  # frases a dizer quando a resposta termina


def _titulo_da_acao(ref):
    try:
        import hud_servidor
        info = hud_servidor.resolver_ref(ref) if ref else None
    except Exception:
        info = None
    return str((info or {}).get("titulo") or "")


def registrar_falha_de_acao(nome, ref, erro):
    verbo = VERBO_ACAO.get(nome, (nome, nome))[0]
    titulo = _titulo_da_acao(ref)
    motivo = str(erro or "algo deu errado").strip().rstrip(".")
    with _TRAVA_ACOES:
        CORRECOES.append(f"Não consegui {verbo}{' ' + titulo if titulo else ''}: {motivo}.")
    avisar_modelo(f"A ação '{nome}'{' em ' + titulo if titulo else ''} NÃO deu certo ({motivo}). A pessoa já foi avisada em voz alta: não repita e nunca diga que deu certo.")


def registrar_recusa_de_acao(nome, ref):
    infinitivo, subjuntivo = VERBO_ACAO.get(nome, (nome, nome))
    titulo = _titulo_da_acao(ref)
    alvo = f" {titulo}" if titulo else " isso"
    with _TRAVA_ACOES:
        CORRECOES.append(f"Não fiz nada ainda: você não me pediu para {infinitivo}{alvo}. Quer que eu {subjuntivo}{alvo}?")
    avisar_modelo(f"A ação '{nome}' NÃO foi feita, porque a pessoa não pediu. A pessoa já foi avisada em voz alta: não repita e nunca diga que fez.")


def agir_e_contar(nome, ref=None, texto=None):
    """Roda agir() e guarda o que precisa ser dito se não deu certo. Conta as ações em curso para o fim da resposta esperar por elas."""
    global ACOES_EM_CURSO
    with _TRAVA_ACOES:
        ACOES_EM_CURSO += 1
    try:
        r = agir(nome, ref, texto)
        if not (r or {}).get("ok"):
            registrar_falha_de_acao(nome, ref, (r or {}).get("erro"))
    except Exception as erro:
        registrar_falha_de_acao(nome, ref, erro)
    finally:
        with _TRAVA_ACOES:
            ACOES_EM_CURSO -= 1


def falar_correcoes(a, espera=15.0):
    """No fim da resposta: espera as ações que ainda rodam e diz o que não deu certo. Devolve o que falou ('' se nada).
    A fala entra na conversa: se terminou em pergunta ("Quer que eu conclua?"), o sim da pessoa vale como pedido."""
    fim = time.time() + espera
    while ACOES_EM_CURSO > 0 and time.time() < fim and not controle_fala.PARAR.is_set():
        time.sleep(0.1)
    with _TRAVA_ACOES:
        frases = list(CORRECOES)
        CORRECOES.clear()
    if not frases or controle_fala.PARAR.is_set():  # a pessoa mandou calar (fechou a janela): não fala depois
        return ""
    fala = " ".join(frases)
    dizer(fala, a)
    if CONVERSA:
        quando, pessoa_disse, guardiao_disse = CONVERSA[-1]
        CONVERSA[-1] = (quando, pessoa_disse, (str(guardiao_disse or "") + " " + fala).strip())
    return fala


def situacao_plano():
    """Status do plano de hoje, choques de horário e resultado dos últimos ajustes: vai no prompt a cada pergunta."""
    plano = _plano_de_hoje()
    if not plano:
        return "STATUS DO PLANO DE HOJE: ainda não existe plano para hoje."
    sugerido = plano.get("status") == "sugerido"
    linhas = ["STATUS DO PLANO DE HOJE: " + (str(plano.get("status") or "sem status")) +
              (_p(" (aguardando a aprovação <do Fulano>; ajustes pela voz são permitidos)") if sugerido
               else " (já aprovado; ajustes pela voz não valem mais, só refazendo o plano com o guardião completo)")]
    conflitos = conflitos_do_plano(plano)
    if conflitos:
        linhas.append("CONFLITOS ATUAIS NO PLANO: " + "; ".join(c["texto"] for c in conflitos))
    if revisao_ativa():
        linhas.append(_p("MODO REVISAO ATIVO: você está revisando o plano com <o Fulano>. Continue ajustando o que ele pedir e, quando ele terminar, peça a aprovação."))
    if AVISOS_AO_MODELO:
        linhas.append(_p("RESULTADO DOS SEUS ÚLTIMOS AJUSTES (se algo falhou, conte <ao Fulano> em uma frase): ") + " | ".join(AVISOS_AO_MODELO))
        AVISOS_AO_MODELO.clear()
    execucao = v2.contexto_voz()  # modo execução e aviso de tempo em aberto (painel novo)
    if execucao:
        linhas.append(execucao)
    if COMPLETO:
        linhas.append(f"GUARDIAO COMPLETO TRABALHANDO há {int(time.time() - COMPLETO['inicio'])} segundos neste pedido: {COMPLETO['pedido']}. "
                      "Não use a marca completo de novo: diga que ainda está montando e que avisa quando terminar.")
    return "\n".join(linhas)


# Prompt estável (cache): o prompt de sistema antigo começava com "Agora são HH:MM", que muda a cada minuto, e por isso o cache do Claude
# nunca era reaproveitado (cada resposta reescrevia ~6,9 mil tokens). No modo estável o prompt de sistema só tem o que quase não muda
# (regras, perfil, planos dos próximos dias) e tudo que muda a cada turno vai junto da pergunta, num bloco marcado "CONTEXTO DESTE MOMENTO".
# O plano de hoje fica no prompt de sistema quando já está aprovado (não muda mais) e vai junto da pergunta enquanto está sendo revisado.
# Medido no Sonnet em sessão de 12 turnos: ~43% menos gasto de entrada (até ~69% depois da aprovação do plano), mesma qualidade nos 21 casos da bateria.
# Ligado por padrão desde 2026-10-11. Desligar: --prompt-antigo ou GUARDIAO_PROMPT_ESTAVEL=0.
PROMPT_ESTAVEL = os.environ.get("GUARDIAO_PROMPT_ESTAVEL", "1") != "0"
PLANO_NO_CONTEXTO = os.environ.get("GUARDIAO_PLANO_NO_CONTEXTO", "sugerido")  # "sempre", "sugerido" (enquanto não aprovado) ou "nunca"
INTRO_VOZ = (
    "Voce e o Guardiao <do Fulano>, assistente de gestao de projetos dele, falando por voz. <genero>"
    "Responda em no maximo 3 frases curtas, cada uma com ate 20 palavras, em portugues do Brasil, direto, sem travessao, "
    "sem listas e sem markdown, porque sua resposta sera falada em voz alta. "
    "Comece pela informacao mais importante, em uma primeira frase curta. "
    "Evite siglas e abreviacoes quando houver um jeito natural de dizer. "
    "As excecoes ao limite de frases sao a revisao do plano e a leitura das pendencias (veja abaixo). "
    "Se o pedido exigir refazer o plano inteiro, mexer num plano ja aprovado, planejar outro dia ou a semana, ou destrinchar um projeto, "
    "passe o pedido ao guardiao completo com a marca completo (veja GUARDIAO COMPLETO abaixo). "
)
COMO_LER_O_CONTEXTO = (
    "Cada turno chega em duas partes: o CONTEXTO DESTE MOMENTO (horario de agora, status do plano de hoje, tarefas conhecidas, conversa recente e, "
    "enquanto o plano esta em revisao, o proprio plano de hoje), que vem do sistema e nao e fala <do Fulano>, e o PEDIDO DESTE TURNO. "
    "Use o contexto para responder, mas nunca o leia em voz alta nem diga que <o Fulano> falou o que esta no contexto."
)


def _plano_texto():
    caminho = os.path.join(OPER, "plano_do_dia.json")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            return f.read()
    return "(sem plano hoje)"


def plano_vai_no_contexto():
    if not PROMPT_ESTAVEL or PLANO_NO_CONTEXTO == "nunca":
        return False
    if PLANO_NO_CONTEXTO == "sempre":
        return True
    return (_plano_de_hoje() or {}).get("status") != "aprovado"  # enquanto o plano muda (revisão), ele vai junto da pergunta


PEDE_PENDENCIAS = re.compile(r"penden|atras|vencid|venceu|ficou|ficaram|sobrou|sobraram|(para|pra) tras|sabado|domingo|fim de semana|final de semana"
                             r"|\bontem\b|anteontem|semana passada|urgent|nao (fiz|terminei|conclui|deu tempo)")


def quer_pendencias(pergunta):
    """A conversa (o pedido de agora ou as duas últimas trocas) toca no que ficou para trás?"""
    recente = [u for t, u, _ in CONVERSA[-2:] if time.time() - t < 300]
    return bool(PEDE_PENDENCIAS.search(_norm(" ".join(recente + [pergunta or ""]))))


def contexto_do_turno(pergunta=""):
    """Tudo que muda a cada turno (só no modo estável; no antigo isto já está dentro do prompt de sistema)."""
    if not PROMPT_ESTAVEL:
        return ""
    partes = [f"Agora sao {time.strftime('%d/%m/%Y %H:%M')}."]
    if plano_vai_no_contexto():
        partes.append(f"PLANO DE HOJE:\n{_plano_texto()}")
    partes.append(situacao_plano())
    if quer_pendencias(pergunta):
        partes.append(pendencias_texto())
    partes.append(f"TAREFAS CONHECIDAS (id | quando | titulo | estado ou lista):\n{refs_conhecidas()}")
    conversa = bloco_conversa()
    if conversa:
        partes.append(conversa)
    return "\n\n".join(partes)


def mensagem_do_turno(pergunta):
    """O que vai no -p do Claude: no modo antigo só a pergunta; no estável, o contexto do momento e depois o pedido."""
    contexto = contexto_do_turno(pergunta)
    if not contexto:
        return pergunta
    return _p("[CONTEXTO DESTE MOMENTO: dados do sistema, nao e fala <do Fulano>]") + f"\n{contexto}\n\n[PEDIDO DESTE TURNO]\n{pergunta}"


def prompt_sistema():
    if PROMPT_ESTAVEL:
        perfil = _perfil()
        bloco_plano = "" if plano_vai_no_contexto() else f"\n\nPLANO DE HOJE:\n{_plano_texto()}"
        return f"{_p(INTRO_VOZ)}{_p(COMO_LER_O_CONTEXTO)}{texto_acoes()}\n\nPERFIL:\n{perfil}{bloco_plano}\n\n{contexto_proximos_dias()}"
    return _prompt_sistema_antigo()


def _prompt_sistema_antigo():
    perfil = _perfil()
    caminho_plano = os.path.join(OPER, "plano_do_dia.json")
    plano = "(sem plano hoje)"
    if os.path.exists(caminho_plano):
        with open(caminho_plano, encoding="utf-8") as f:
            plano = f.read()
    agora = time.strftime("%d/%m/%Y %H:%M")
    return (
        _p("Voce e o Guardiao <do Fulano>, assistente de gestao de projetos dele, falando por voz. ") +
        "Responda em no maximo 3 frases curtas, cada uma com ate 20 palavras, em portugues do Brasil, direto, sem travessao, "
        "sem listas e sem markdown, porque sua resposta sera falada em voz alta. "
        "Comece pela informacao mais importante, em uma primeira frase curta. "
        "Evite siglas e abreviacoes quando houver um jeito natural de dizer. "
        "A unica excecao ao limite de frases e a revisao do plano (veja abaixo): ali pode ser uma frase por bloco. "
        "Se o pedido exigir refazer o plano inteiro ou mexer num plano ja aprovado, passe o pedido ao guardiao completo com a marca completo. "
        f"Agora sao {agora}.{texto_acoes()}\n\nPERFIL:\n{perfil}\n\nPLANO DE HOJE:\n{plano}\n\n{contexto_proximos_dias()}"
        f"\n\n{situacao_plano()}"
        f"\n\nTAREFAS CONHECIDAS (id | quando | titulo | estado ou lista):\n{refs_conhecidas()}\n\n{bloco_conversa()}"
    )


# ---------------- diretivas: o guardião destaca tarefas na tela e age sobre elas ----------------
# Na resposta, o Claude escreve marcas entre chaves duplas (não são faladas nem mostradas como texto):
#   {{foco:ID}} destaca a tarefa na lista | {{detalhe:ID}} abre o cartão dela no centro
#   {{concluir:ID|comentário}} {{reabrir:ID}} {{comentar:ID|texto}} agem na tarefa (só se a pessoa pediu)
#   {{criar:titulo=..|descricao=..|lista=..|dono=..|prazo=AAAA-MM-DD HH:MM}} só PROPÕE; a criação espera o "sim" da pessoa
#   {{estender:ID|minutos|motivo}} {{adiar:ID|motivo}} {{motivo:ID|texto}} {{checkin:ok}} acompanham a execução (painel novo)
#   {{completo:pedido}} passa o pedido ao guardião completo (a skill inteira, em segundo plano); a resposta chega depois
DIRETIVA = re.compile(r"\{\{\s*(foco|detalhe|concluir|reabrir|comentar|criar|mover|editar|remover|adicionar|desfazer|aprovar|revisao|estender|adiar|motivo|checkin|completo)\s*:?\s*(.*?)\s*\}\}", re.S)
ACOES_ATIVAS = True
PROPOSTA = None  # algo aguardando o "sim" da pessoa: {"tipo": "criar" ou "aprovar", "dados": {...}, "quando": time}
REVISAO = None  # revisão do plano em andamento: {"inicio": time, "ultimo": time}; enquanto durar, o microfone reabre depois de cada resposta
AVISOS_AO_MODELO = []  # resultado dos últimos ajustes do plano, para o guardião saber se deu certo na próxima fala
INTERVALO_SAUDACAO = 3 * 3600  # a saudação não se repete se a janela for reaberta antes disso
LIMITE_SAUDACAO = 18  # segundos desde que a saudação começa a ser preparada: a abertura da tela dura uns 9, o Claude leva uns 4. Passou disso, vale a frase local
CONVERSA = []  # últimas trocas, para o guardião entender "e a da Marina?" ou o comentário que ele pediu
VALIDADE_PROPOSTA = 180  # segundos
INTENCAO = {  # a ação só acontece se o que a pessoa disse realmente pede aquilo
    "concluir": re.compile(r"conclu|termin|finaliz|\bfiz\b|feito|fechei|fechar|acabei|marc"),
    "reabrir": re.compile(r"reabr|desfaz|desmarc|volt|ainda nao"),
    "comentar": re.compile(r"anot|coment|registr|escrev|adicion|inclu|coloc|\bpoe\b|bota|deix"),
    "criar": re.compile(r"cri[ae]|nova tarefa|adicion|lanc|cadastr|coloc|agend|abr[ae]|monta|faz uma tarefa|anota uma tarefa"),
    # ajustes do plano: valem sempre que a revisão está aberta; fora dela, só se a frase pedir
    "mover": re.compile(r"\bmov|\btroc|\bpass[ae]\b|\badi[ae]\b|antecip|desloc|\bmuda|\balter|\bjoga|empurr|\bremarc|\breagend"),
    "editar": re.compile(r"renome|\bmuda|\balter|\btroc|\bedit|corrig|\bajust|\bchama"),
    "remover": re.compile(r"remov|\btira\b|\btirar\b|\bexclu|\bapag|\bcorta|nao vou|nao da pra|nao preciso|esquece|de fora"),
    "adicionar": re.compile(r"adicion|\binclu|acrescent|\bcri[ae]|novo bloco|mais um|encaix|\bcoloc|\bbota"),
    "desfazer": re.compile(r"desfaz|\bvolt|como estava|errei|\banul"),
    "aprovar": re.compile(r"aprov"),
    # acompanhamento da execução: valem sempre que há um aviso de tempo em aberto; fora dele, só se a frase pedir
    "estender": re.compile(r"mais tempo|mais \d+|mais (uns|umas|meia|um|uma|dez|quinze|vinte|trinta)|estend|prorrog|\bate as\b|nao (vai|vou) (dar|terminar|conseguir)|preciso de mais"),
    "adiar": re.compile(r"\badi[ae]|reprogram|remarc|deixa (pra|para)|fica (pra|para)|(pra|para) (amanha|outro dia|depois)|nao vou (conseguir|fazer|terminar)"),
    "motivo": re.compile(r"."),
    # guardião completo: pedidos de planejar, refazer ou organizar várias coisas de uma vez
    "completo": re.compile(r"refa[zc]|replanej|reorganiz|planej|\bmont|remont|\bsemana|\bamanha|destrinch|\bquebr|encaix|redistribu|reprogram|prioriz|organiz"
                           r"|penden|atras|\bplano\b|\bdia\b|\bagenda|complet"),
}
EDITA = re.compile(r"mov|troc|pass[ae]|adi[ae]|remov|tira|inclu|acrescent|mud|alter|antes|depois|hora|cedo|tarde|renome|apag")
SIM_APROVAR = {"sim", "sim pode", "pode", "pode sim", "pode aprovar", "aprova", "aprove", "aprovado", "aprova sim", "isso", "isso mesmo", "claro",
               "com certeza", "confirmo", "confirmado", "fechado", "fechou", "ok", "beleza", "bora", "manda", "manda ver", "vai", "positivo",
               "combinado", "pode ser", "tudo certo", "ta bom", "esta bom", "ta certo", "sim aprova", "sim aprove"}
SIM = re.compile(r"\b(sim|pode|confirma|confirmo|manda|cria|crie|isso|certo|ok|vai|faz|positivo|claro|beleza|combinado|bora)\b")
NAO = re.compile(r"\b(nao|cancela|cancele|deixa|esquece|melhor nao|para)\b")


# ---------------- qual modelo do Claude responde ----------------
# Padrão: Sonnet 5.5, para planejar, revisar o plano, escrever tarefa ou comentário, agir no ClickUp e a saudação.
# Leve: Haiku 4.5, só para consulta curta, somente de leitura e sem conta de horário ("o que é essa tarefa?", "qual o prazo dela?").
# Na bateria de testes o Haiku errou conta de horas e "o que tenho agora" (docs: testes-llm-locais/guardiao-voz-llm-local-vs-claude.md),
# então tudo que envolve relógio fica com o padrão. Na dúvida o padrão responde. Trocar: --modelo e --modelo-leve, ou as variáveis GUARDIAO_MODELO e GUARDIAO_MODELO_LEVE
# ("nenhum" desliga o leve e tudo vai para o padrão). A conta é feita por regra local: não gasta uma chamada para decidir.
MODELO_PADRAO = os.environ.get("GUARDIAO_MODELO") or "claude-sonnet-5-5"
MODELO_LEVE = os.environ.get("GUARDIAO_MODELO_LEVE", "claude-haiku-4-5-20251001")
ESCRITAS = ("concluir", "reabrir", "comentar", "criar", "mover", "editar", "remover", "adicionar", "desfazer", "aprovar", "estender", "adiar")
PEDE_PENSAR = re.compile(r"\bplanej|\breplanej|\breorganiz|\brefa[zc]|\bpriori|\bencaix|\bcabe\b|\bda tempo|\bconsigo|\bestrateg|\bsug[ei]r|\bsugest|\bideia"
                         r"|\bescrev|\bredij|\bresum|\bcompar|\banalis|\bpor ?que\b|\bmelhor\b|\bdevo\b|\bdeveria|\bvoce acha")


PEDE_HORARIO = re.compile(r"\bagora\b|\bproxim|\bquant[oa]s?\b|\bfalt[ao]|\batras|\bque horas?\b|\bcabe\b|\bate quando|\bdemora|\bamanha\b|\bdepois\b|\bantes\b|\bhorario|\bexpediente|\balmoc|\bsobr[ao]u?\b")


def modelo_leve_ligado():
    return bool(MODELO_LEVE) and MODELO_LEVE.lower() not in ("nenhum", "igual", "off") and MODELO_LEVE != MODELO_PADRAO


def escolher_modelo(texto_usuario, saudacao=False):
    """Devolve (modelo, motivo). Só consulta curta e de leitura vai para o modelo leve; na dúvida, o padrão."""
    if saudacao:
        return MODELO_PADRAO, "saudação"
    if not modelo_leve_ligado():
        return MODELO_PADRAO, "sem modelo leve"
    if revisao_ativa():
        return MODELO_PADRAO, "revisão do plano"
    if PROPOSTA and time.time() - PROPOSTA["quando"] < VALIDADE_PROPOSTA:
        return MODELO_PADRAO, "proposta pendente"
    if v2.CHECKIN:
        return MODELO_PADRAO, "aviso de tempo em aberto"
    if quer_pendencias(texto_usuario):
        return MODELO_PADRAO, "pendências"
    recente = [u for t, u, _ in CONVERSA[-2:] if time.time() - t < 180]
    alvo = _norm(" ".join(recente + [texto_usuario]))
    for nome in ESCRITAS:
        if INTENCAO[nome].search(alvo):
            return MODELO_PADRAO, f"pode agir ({nome})"
    if PEDE_PENSAR.search(alvo) or len(_norm(texto_usuario).split()) > 30:
        return MODELO_PADRAO, "planejar ou escrever"
    if PEDE_HORARIO.search(alvo):
        return MODELO_PADRAO, "conta de horário"
    return MODELO_LEVE, "consulta curta"


def registrar_chamada(modelo, motivo, ev):
    """Uma linha por resposta em logs/modelos.jsonl: qual modelo respondeu, por quê, quanto custou e quanto demorou."""
    try:
        uso = ev.get("usage") or {}
        linha = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "modelo": modelo, "motivo": motivo, "custo_usd": ev.get("total_cost_usd"),
                 "entrada": sum(uso.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
                 "cache_lido": uso.get("cache_read_input_tokens"), "cache_escrito": uso.get("cache_creation_input_tokens"),
                 "saida": uso.get("output_tokens"), "ms": ev.get("duration_ms"), "prompt_estavel": PROMPT_ESTAVEL}
        pasta = os.path.join(OPER, "logs")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, "modelos.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except Exception:
        pass


def mascarar(buf):
    """Troca o conteúdo das diretivas por 'x' (mesmo tamanho), inclusive uma diretiva ainda aberta no fim,
    para os cortes de frase nunca caírem dentro dela."""
    saida = DIRETIVA.sub(lambda m: "x" * len(m.group(0)), buf)
    aberto = saida.rfind("{{")
    if aberto != -1:
        saida = saida[:aberto] + "x" * (len(saida) - aberto)
    return saida


def extrair_diretivas(frase):
    """Devolve (texto sem as marcas, lista de (nome, argumento))."""
    diretivas = [(m.group(1), m.group(2)) for m in DIRETIVA.finditer(frase)]
    limpo = DIRETIVA.sub("", frase)
    limpo = re.sub(r"\{\{.*", "", limpo, flags=re.S)  # marca que ficou aberta
    return re.sub(r"\s+", " ", limpo).strip(), diretivas


def campos(arg):
    """'titulo=A|descricao=B' -> {'titulo': 'A', 'descricao': 'B'}"""
    saida = {}
    for parte in arg.split("|"):
        if "=" in parte:
            k, v = parte.split("=", 1)
            saida[k.strip().lower()] = v.strip()
    return saida


def lembrar(usuario, guardiao, na_sessao=False):
    agora = time.time()
    if not na_sessao and modo_sessao():  # saudação, comando da tela, aviso de tempo: a sessão fica sabendo na próxima fala
        FORA_DA_SESSAO.append((usuario, guardiao))
        del FORA_DA_SESSAO[:-8]
    if CONVERSA and agora - CONVERSA[-1][0] > 600:
        CONVERSA.clear()
    CONVERSA.append((agora, usuario, guardiao))
    del CONVERSA[:-4]
    memoria_conversa.lembrar(usuario, guardiao, agora)  # em arquivo: sobrevive a reinício e a horas de intervalo (o CONVERSA acima só serve para as janelas curtas de intenção)


def bloco_conversa():
    """O que o guardião lembra, para ir junto da pergunta: o resumo do dia e as últimas 10 trocas (memoria_conversa.py)."""
    base = memoria_conversa.bloco(pessoa()["primeiro"])
    if not base:
        return ""
    pendente = ""
    if PROPOSTA and time.time() - PROPOSTA["quando"] < VALIDADE_PROPOSTA:
        pendente = f"\nPROPOSTA PENDENTE ({PROPOSTA.get('tipo', 'criar')}) aguardando o sim {pessoa()['do']}: {json.dumps(PROPOSTA['dados'], ensure_ascii=False)}"
    return base + pendente


def _chamar_resumo(pedido):
    """O resumo do dia: uma chamada curta ao modelo leve, sem ferramentas, sem conectores e sem pensamento. Devolve o texto ou None."""
    base = guardiao_sessao.comando_do_claude()
    if not base:
        return None
    arq = os.path.join(tempfile.gettempdir(), "guardiao_voz_resumo.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write("Você escreve resumos curtos e fiéis do que foi dito. Responda só com o resumo.")
    modelo = MODELO_LEVE if modelo_leve_ligado() and MODELO_LEVE else MODELO_PADRAO
    cmd = [*base, "-p", pedido, "--model", modelo, "--system-prompt-file", arq, "--tools", "", "--disable-slash-commands", "--strict-mcp-config",
           "--setting-sources", "local", "--no-session-persistence", "--effort", "low", "--output-format", "json"]
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    env["MAX_THINKING_TOKENS"] = "0"
    erro = guardiao_sessao.arquivo_de_erro()
    try:
        saida = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=erro, text=True, encoding="utf-8", errors="replace", env=env, cwd=OPER, timeout=90,
                               creationflags=guardiao_sessao.FLAGS_CLAUDE)
    finally:
        if erro is not subprocess.DEVNULL:
            erro.close()
    try:
        ev = json.loads(saida.stdout)
    except ValueError:
        return None
    registrar_chamada(modelo, "resumo do dia", ev)
    return None if ev.get("is_error") else str(ev.get("result") or "").strip()


def texto_acoes(sessao=False):
    if not ACOES_ATIVAS:
        return ""
    texto = _p(
        "\n\nDESTAQUES E AÇÕES NA TELA. Você controla a tela <do Fulano> com marcas entre chaves duplas dentro da sua resposta. "
        "As marcas não são faladas. Os ids vêm da lista TAREFAS CONHECIDAS" + ("" if PROMPT_ESTAVEL else " abaixo") + "; nunca invente um id.\n"
        "- {{foco:ID}} logo antes da frase em que você cita uma tarefa: ela fica destacada na lista. Cite uma tarefa por marca.\n"
        "- {{detalhe:ID}} quando <o Fulano> perguntar sobre UMA tarefa específica: o cartão dela abre no centro enquanto você fala.\n"
        "Só quando <o Fulano> pedir de forma explícita, e dizendo em voz alta o que vai fazer, use as marcas a seguir, escritas logo antes da frase em que você diz o que vai fazer "
        "(nunca soltas no fim da resposta), para a ação acontecer na tela enquanto você fala:\n"
        "- {{concluir:ID}}. Basta ele dizer que terminou: não peça nem escreva \"o que foi feito\", não existe comentário de status. "
        "Se for uma tarefa repetida, cópia de outra, use {{concluir:ID}} do mesmo jeito.\n"
        "Nunca mande <o Fulano> ir ao ClickUp fazer o que estas marcas fazem (concluir, reabrir, anotar): ofereça em uma frase e, com o sim dele, faça você.\n"
        "- {{reabrir:ID}}\n"
        "- {{comentar:ID|texto da anotação}}\n"
        "- {{criar:titulo=...|descricao=...|lista=nome da lista|dono=nome|prazo=AAAA-MM-DD HH:MM}} (dono e prazo são opcionais). "
        "Isto só PROPÕE a tarefa: diga o título, a lista e o prazo e pergunte se pode criar. A criação só acontece quando <o Fulano> disser sim. "
        "O prazo é exatamente o dia e a hora que <o Fulano> disse: nunca antecipe nem adie por conta própria, nem para dar folga. Se ele não disse a hora, escreva só a data (AAAA-MM-DD).\n"
        "Nos comentários e anotações escreva só o que <o Fulano> disse, sem inventar detalhes. "
        "Nunca use ações para perguntas de consulta. Textos das marcas não podem ter a sequência }} nem o caractere | fora do lugar das marcas.\n\n"
        "REVISÃO DO PLANO DE HOJE (só quando STATUS DO PLANO DE HOJE for sugerido). É o momento em que <o Fulano> confere o plano com você, "
        "aponta imprevistos e pede mudanças, e só então aprova.\n"
        "- Se ele topar revisar ou pedir isso, comece com {{revisao:inicio}} e leia TODOS os blocos de hoje que ainda não foram feitos, em ordem de horário, "
        "uma frase curta por bloco, no formato \"das 14h às 14h30, título\", com {{foco:ID}} logo antes de cada frase. "
        "Se algum horário já passou, diga isso em uma frase. Depois pergunte se há algum imprevisto, algo que não foi mapeado ou algo que ele queira mudar. "
        "Nesta leitura você pode falar até 14 frases curtas.\n"
        "- Ajustes que ele pedir (confirme cada um em voz alta, em uma frase): "
        "{{mover:ID|HH:MM-HH:MM}} muda o horário (se ele só disser o começo, escreva o começo e a mesma duração); "
        "{{editar:ID|titulo=...|descricao=...}} muda o texto; {{remover:ID}} tira do plano de hoje; "
        "{{adicionar:titulo=...|inicio=HH:MM|fim=HH:MM|descricao=...|lista=nome da lista|dono=nome}} inclui um bloco novo "
        "(vira tarefa no ClickUp quando o plano for aprovado); {{desfazer}} volta o último ajuste. Horários sempre em 24 horas.\n"
        "- Antes de mover ou adicionar, confira os CONFLITOS ATUAIS e os compromissos fixos do plano. Se o horário bater com outro bloco, avise "
        "e proponha outro horário em vez de aplicar.\n"
        "- Quando ele disser que está bom e pedir para aprovar, use {{aprovar}} e diga quantas tarefas novas serão criadas no ClickUp. "
        "Se ele ainda não tiver dito a palavra aprovar, pergunte \"Posso aprovar o plano?\" com {{aprovar}} na mesma frase: "
        "a aprovação só acontece depois do sim dele. Ao usar {{aprovar}}, fale no presente, como estou aprovando ou posso aprovar, "
        "e nunca diga que o plano já foi aprovado: o resultado aparece na tela e você confirma na próxima fala.\n"
        "- Quando a revisão acabar (aprovada, recusada ou se ele quiser parar), escreva {{revisao:fim}}.\n"
        "- Depois de aprovado, os ajustes pela voz não valem mais: para mudar, só refazendo o plano com o guardião completo.\n\n"
        "PENDÊNCIAS (só quando o contexto trouxer TAREFAS ATRASADAS OU NÃO CONCLUÍDAS). <O Fulano> quer saber o que ficou para trás e o que é urgente.\n"
        "- Diga quantas são e cite as mais urgentes, no máximo 5 por resposta, uma frase curta por tarefa, com {{foco:ID}} logo antes de cada uma, "
        "e diga o porquê em poucas palavras. É urgente: conta a pagar ou a receber, entrega com outra pessoa esperando, o que trava outra tarefa "
        "e o que venceu há mais tempo. Nesta leitura você pode falar até 8 frases curtas. Se ele pedir, leia as seguintes.\n"
        "- Depois pergunte quais ele quer resolver hoje. Com o plano ainda sugerido, traga uma por vez com {{adicionar:id=ID|inicio=HH:MM|fim=HH:MM}}, "
        "num horário livre (confira os CONFLITOS ATUAIS e os compromissos fixos) e depois de agora, confirmando em voz alta. "
        "A tarefa não é duplicada: ela muda de data no ClickUp quando o plano for aprovado.\n"
        "- Não decida sozinho o que entra no dia: proponha e só aplique quando ele concordar. Tarefa marcada JÁ ESTÁ NO PLANO DE HOJE não precisa entrar de novo. "
        "Se forem muitas para encaixar, ou se o plano já estiver aprovado, passe o pedido ao guardião completo.\n\n"
        "GUARDIÃO COMPLETO. Você é a versão rápida, feita para conversar. O guardião completo é a skill inteira, que lê a memória toda e monta planos com calma, "
        "em segundo plano, e costuma levar de dois a cinco minutos.\n"
        "- Use {{completo:o pedido dele, inteiro, em uma ou duas frases, com os detalhes que ele deu}} quando o pedido passar do que as marcas acima fazem: "
        "montar ou refazer o plano de hoje, mexer num plano já aprovado, encaixar várias tarefas de uma vez, planejar amanhã ou a semana, destrinchar um projeto.\n"
        "- Ao usar, diga em uma frase que vai montar isso com calma e que avisa quando terminar. Não prometa o resultado: ele chega depois, na sua próxima fala. "
        "Para <o Fulano> você é um só: nunca diga guardião completo em voz alta.\n"
        "- Para consulta e ajuste simples, responda você mesmo. Nunca use a marca sem ele ter pedido algo assim.\n\n"
        "ACOMPANHAMENTO DA EXECUÇÃO (só quando o contexto trouxer MODO EXECUCAO ligado). Você acompanha o tempo de cada tarefa e ajuda <o Fulano> a não se perder nela.\n"
        "- Com AVISO DE TEMPO EM ABERTO no contexto, a fala dele responde à sua pergunta sobre o andamento. Se ele disser que termina no horário, "
        "responda em uma frase curta e use {{checkin:ok}}.\n"
        "- Se ele precisar de mais tempo, use {{estender:ID|minutos|motivo}}, com os minutos em número. Se ele não disse quanto tempo, pergunte antes e não use a marca. "
        "Se ele quiser deixar para depois ou reprogramar, use {{adiar:ID|motivo}}.\n"
        "- Sempre que uma tarefa não terminar no horário, o motivo precisa ficar registrado: se ele não disse por quê, pergunte em uma frase, sem julgar, e só use a marca quando souber. "
        "Escreva o motivo com as palavras dele, em poucas palavras. Se ele só contar um imprevisto ou uma interrupção, sem pedir mudança, use {{motivo:ID|o que ele contou}}.\n"
        "- Depois de anotar, ofereça UMA ajuda prática e curta, ligada ao motivo: distração pede um trecho de 25 minutos só nessa tarefa; falta de informação pede cobrar agora quem tem a resposta; "
        "tempo subestimado pede separar o que falta em um próximo passo pequeno; cansaço pede fazer só o próximo passo e parar. Sem sermão.\n"
        "- Estender não empurra os blocos seguintes: se o novo fim encostar no próximo bloco ou em um compromisso fixo, avise em uma frase.\n"
        "- Se ele disser que concluiu, vale a regra de concluir: precisa do que foi feito."
    )
    if sessao:  # na sessão do Claude Code o próprio guardião é o completo: a marca completo não existe
        texto = re.sub(r"GUARDIÃO COMPLETO\..*?(?=ACOMPANHAMENTO DA EXECUÇÃO)",
                       "GUARDIÃO COMPLETO. Nesta sessão você mesmo é o guardião completo: a marca completo não existe aqui. "
                       "Para montar ou refazer um plano, siga a skill guardiao-triwer.\n\n", texto, flags=re.S)
        texto = (texto.replace("passe o pedido ao guardião completo", "resolva você mesmo, seguindo a skill guardiao-triwer")
                 .replace("só refazendo o plano com o guardião completo", "só refazendo o plano, seguindo a skill guardiao-triwer"))
    return texto


# ---------------- modo sessão: a conversa é uma sessão normal do Claude Code (guardiao_sessao.py) ----------------
# Ligado pela preferência "sessao". Cada fala entra na mesma conversa, que lembra do que foi dito e tem os conectores, as skills e os agentes
# da pasta da pessoa. O modo rápido (uma chamada solta por fala) continua sendo o padrão e a saída de emergência se a sessão falhar.

INTRO_SESSAO = (
    "MODO PAINEL DE VOZ. Nesta sessão você é o Guardião <do Fulano>, o gestor de projetos pessoal dele (skill guardiao-triwer), conversando pelo painel do Guardião: "
    "<o Fulano> fala ou escreve e a sua resposta é lida em voz alta. <genero>Estas regras valem acima do seu estilo normal de escrita.\n"
    "- Responda em português do Brasil, em até 3 frases curtas, cada uma com até 20 palavras, sem markdown, sem listas, sem títulos, sem emoji, sem travessão "
    "e sem caminhos de arquivo. Comece pelo que importa. Detalhe só quando ele pedir. As exceções ao limite de frases são a revisão do plano e a leitura das pendências.\n"
    "- Antes de usar uma ferramenta que demora (conector, skill, agente, pesquisa), diga uma frase curta do que vai fazer, para ele não ficar no silêncio.\n"
    "- Ação que altera algo fora deste computador (ClickUp, WhatsApp, e-mail, agenda, anúncios) passa por um pedido de permissão que o próprio painel mostra e lê em voz alta. "
    "Por isso não pergunte se pode antes: diga em uma frase o que vai fazer, com os dados principais, e chame a ferramenta. "
    "Se ele negar, a ferramenta volta negada: aceite, não tente outro caminho para fazer a mesma coisa e pergunte o que ajustar.\n"
    "- Não use AskUserQuestion nem modo de planejamento: pergunte em voz alta, uma pergunta por vez, e espere a resposta.\n"
    "- Para consulta simples sobre o dia (o que tenho agora, a que horas é tal tarefa), responda direto pelo CONTEXTO DESTE MOMENTO que chega junto de cada pedido. "
    "Acione a skill guardiao-triwer quando o pedido for planejar o dia ou a semana, destrinchar uma tarefa, decidir algo ou mexer na memória, e siga as regras dela, "
    "inclusive as extensões locais que ela mandar ler.\n"
    "- Você tem os conectores, as skills e os agentes desta pasta. Use quando o pedido precisar, sem listar o que existe.\n"
    "- Nunca mande <o Fulano> fazer num conector o que você mesmo pode fazer por ele (concluir, apagar, mover ou comentar uma tarefa, criar um evento, e parecidos): "
    "diga o que vai fazer e faça pelo conector. Ao concluir uma tarefa no ClickUp, siga a regra de registro da skill e das extensões locais.\n"
    "- Para <o Fulano> você é um só: não fale em guardião completo, em sessão nem em limites técnicos.\n"
)
COMO_LER_NA_SESSAO = (
    "Cada pedido chega em duas partes: o CONTEXTO DESTE MOMENTO (horario de agora, status do plano de hoje e, quando mudam, o plano, os proximos dias e as tarefas conhecidas; "
    "as vezes tambem as falas que aconteceram no painel fora desta sessao), que vem do sistema e nao e fala <do Fulano>, e o PEDIDO DESTE TURNO. "
    "Use o contexto para responder, mas nunca o leia em voz alta nem diga que <o Fulano> falou o que esta no contexto. O contexto mais recente vale sobre os anteriores."
)
FORA_DA_SESSAO = []  # trocas que aconteceram no painel sem passar pela sessão (saudação, comando da tela, aviso de tempo)
_ENVIADO = {}  # por conversa: o que do contexto já foi mandado, para não repetir a cada fala
_CONVERSA_DA_VEZ = [None]


def modo_sessao():
    return bool(preferencias().get("sessao")) and os.environ.get("GUARDIAO_SEM_SESSAO") != "1"


def arquivo_prompt_sessao():
    """O que é acrescentado ao prompt normal do Claude Code nesta sessão: as regras do painel de voz, as marcas da tela e o perfil."""
    arq = os.path.join(tempfile.gettempdir(), "guardiao_voz_sessao.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write(f"{_p(INTRO_SESSAO)}{_p(COMO_LER_NA_SESSAO)}{texto_acoes(sessao=True)}"
                f"\n\nPASTAS DO GUARDIÃO. Operacional (plano_do_dia.json, registros, resumo do ClickUp, scripts): {OPER}. Memória (perfil, estado, decisões, POPs): {pasta_memoria()}."
                f"\n\nPLANO DE HOJE EM ARQUIVO. Para montar ou refazer o plano de hoje (inclusive um plano já aprovado), grave plano_do_dia.json na pasta operacional. {REGRAS_DO_PLANO} "
                "Depois diga em voz alta o que mudou e pergunte se ele quer revisar o plano. Plano de outro dia vai em planos\\plano_AAAA-MM-DD.json, na mesma pasta."
                f"\n\nREGRAS LOCAIS DA PESSOA (valem sempre, mesmo sem acionar a skill; só somam às regras da skill):\n{_regras_locais()}"
                f"\n\nPERFIL:\n{_perfil()}")
    return arq


def _regras_locais():
    """extensoes-*.md da skill e aprendizados.md da memória, sempre carregados na sessão do app: a sessão roda na pasta operacional,
    sem o CLAUDE.md nem a memória do projeto, e só leria isso se decidisse acionar a skill."""
    partes = []
    skill = os.path.join(os.path.expanduser("~"), ".claude", "skills", "guardiao-triwer")
    try:
        arquivos = sorted(os.path.join(skill, n) for n in os.listdir(skill) if n.startswith("extensoes-") and n.endswith(".md"))
    except OSError:
        arquivos = []
    arquivos.append(os.path.join(pasta_memoria(), "aprendizados.md"))
    for caminho in arquivos:
        try:
            with open(caminho, encoding="utf-8-sig") as f:
                partes.append(f"[{os.path.basename(caminho)}]\n{f.read()}")
        except OSError:
            continue
    return "\n\n".join(partes) or "(nenhuma)"


def mensagem_da_sessao(pergunta, conversa):
    """O que entra na sessão a cada fala: a hora, o estado do plano, o que mudou desde a última fala e o pedido."""
    partes = [f"Agora sao {time.strftime('%d/%m/%Y %H:%M')}."]
    enviado = _ENVIADO.setdefault(conversa, {})
    for nome, bloco in (("plano", f"PLANO DE HOJE:\n{_plano_texto()}"), ("proximos", contexto_proximos_dias()),
                        ("tarefas", f"TAREFAS CONHECIDAS (id | quando | titulo | estado ou lista):\n{refs_conhecidas()}")):
        if bloco and enviado.get(nome) != bloco:
            enviado[nome] = bloco
            partes.append(bloco)
    partes.append(situacao_plano().replace("só refazendo o plano com o guardião completo", "só refazendo o plano, seguindo a skill guardiao-triwer"))
    if quer_pendencias(pergunta):
        partes.append(pendencias_texto())
    if FORA_DA_SESSAO:
        falas = "\n".join(f"{pessoa()['primeiro']}: {u}\nGuardiao: {g}" for u, g in FORA_DA_SESSAO)
        partes.append("FALAS QUE ACONTECERAM NO PAINEL FORA DESTA SESSAO (ja foram ditas; nao repita):\n" + falas)
        FORA_DA_SESSAO.clear()
    return _p("[CONTEXTO DESTE MOMENTO: dados do sistema, nao e fala <do Fulano>]") + "\n" + "\n\n".join(p for p in partes if p) + f"\n\n[PEDIDO DESTE TURNO]\n{pergunta}"


def frases_da_sessao(pergunta):
    """Como frases_do_claude, mas dentro da sessão do Claude Code. Além das frases, devolve ("permissao", pedido) quando o guardião quer usar
    algo que precisa do sim da pessoa. Se a sessão falhar antes de dizer qualquer coisa, a resposta sai pelo modo rápido."""
    saiu = False
    try:
        conversa = guardiao_sessao.atual()["id"]
        if _CONVERSA_DA_VEZ[0] and _CONVERSA_DA_VEZ[0] != conversa:  # a anterior ficou parada tempo demais: esta fala abre uma conversa nova
            CONVERSA.clear()
            guardiao_sessao.avisar_tela(troca=True)
        _CONVERSA_DA_VEZ[0] = conversa
        cortador = Cortador()
        viu_texto = False
        latencia.marca("sessao_turno_enviado")
        for tipo, dado in guardiao_sessao.turno(mensagem_da_sessao(pergunta, conversa), arquivo_prompt_sessao()):
            if tipo == "texto":
                if not viu_texto:
                    viu_texto = True
                    latencia.marca("sessao_primeiro_texto")
                for frase in cortador.alimentar(dado):
                    saiu = True
                    yield frase
            elif tipo == "ferramenta":
                latencia.marca("ferramenta", fase=dado.get("fase"), rotulo=dado.get("rotulo"), dentro=bool(dado.get("dentro")))
                if dado.get("fase") == "inicio" and not dado.get("dentro"):
                    antes = cortador.resto()  # "Vou olhar no ClickUp" é dito já, enquanto a ferramenta trabalha
                    if antes:
                        saiu = True
                        yield antes
                bus.emitir("ferramenta", **dado)
            elif tipo == "permissao":
                antes = cortador.resto()  # o que ele disse antes de pedir precisa ser falado antes da pergunta
                if antes:
                    saiu = True
                    yield antes
                yield "permissao", dado
            elif tipo == "fim":
                if not saiu and isinstance(dado, dict) and dado.get("is_error") and not dado.get("_interrompido"):
                    raise guardiao_sessao.erro_de_conta(dado.get("result"))  # limite de uso, sem login...: dizer o motivo, não ficar mudo nem tentar de novo
                break
        resto = cortador.resto()
        if resto:
            yield resto
    except Exception as erro:
        if saiu or isinstance(erro, guardiao_sessao.ErroDeConta):  # erro de conta: o modo rápido falharia igual, só dobraria a espera
            raise
        print("  (a sessão do Claude Code falhou, respondo pelo modo rápido:", erro, ")")
        bus.emitir("aviso", texto="A sessão do Claude Code não respondeu. Respondi pelo modo rápido.", erro=True)
        yield from frases_do_claude(pergunta, None, "sessão indisponível")


def _uso_da_sessao(processo, ev):
    registrar_chamada(processo.modelo, "sessão", dict(ev, total_cost_usd=ev.get("_custo_do_turno")))
    guardiao_sessao.avisar_tela()


guardiao_sessao.AO_FECHAR_TURNO.append(_uso_da_sessao)
SEMPRE = re.compile(r"\bsempre\b")
AUTORIZA = re.compile(r"\b(permit\w+|autoriz\w+|liber\w+|aprov\w+|envia|enviar|manda ver)\b")


def interpretar_permissao(texto, pode_sempre):
    """O que a pessoa respondeu ao pedido de permissão: ('sim' | 'sempre' | 'nao', recado para o guardião) ou None se não disse nada."""
    t = re.sub(r"\s+", " ", _norm(texto)).strip()
    if not t:
        return None
    palavras = len(t.split())
    recado = f"A pessoa não autorizou e respondeu: \"{texto.strip()}\". Não execute a ação; leve em conta o que ela disse."
    if NAO.search(t):  # um não curto é só não; numa resposta comprida ela está pedindo um ajuste, e o guardião precisa saber qual
        return "nao", ("" if palavras <= 6 else recado)
    if palavras <= 12 and (SIM.search(t) or AUTORIZA.search(t)):
        return ("sempre" if pode_sempre and SEMPRE.search(t) else "sim"), ""
    return "nao", recado


def _resposta_da_tela():
    """Clique num botão do cartão de permissão ou resposta digitada, se houver. Os outros comandos voltam para a fila."""
    guardar, achou = [], None
    while achou is None:
        try:
            c = bus.comandos.get_nowait()
        except queue.Empty:
            break
        if c[0] == "permissao":
            achou = ("clique", str(c[1]))
        elif c[0] == "perguntar":
            achou = ("texto", str(c[1]))
        elif c[0] != "acionar":
            guardar.append(c)
    for c in guardar:
        bus.comandos.put(c)
    return achou


def pedir_permissao(a, q, modelo, chave, piso, pedido, por_voz):
    """Mostra o cartão do pedido, faz a pergunta em voz alta e espera o sim ou o não: falado, digitado ou clicado. Sem resposta, é não."""
    bus.emitir("permissao", id=pedido["id"], titulo=pedido["titulo"], kicker=pedido["kicker"], linhas=pedido["linhas"], sempre=pedido["sempre"])
    dizer(pedido["pergunta"], a)
    drenar(q)
    limite, decisao, escutas = time.time() + 90, None, 0
    while decisao is None and time.time() < limite:
        r = _resposta_da_tela()
        if r:
            if r[0] == "clique":
                decisao = (r[1] if r[1] in ("sim", "sempre") else "nao"), ""
            else:
                bus.emitir("voce", texto=r[1])
                decisao = interpretar_permissao(r[1], pedido["sempre"])
            continue
        if por_voz and escutas < 3 and not getattr(a, "sem_escuta_aberta", False) and escuta_continua():
            escutas += 1
            texto, _, motivo = escutar(a, q, modelo, chave, piso, seguimento=True, avisar_cancelamento=False)
            if texto:
                bus.emitir("voce", texto=texto)
                decisao = interpretar_permissao(texto, pedido["sempre"])
            elif motivo == "cancelado" and bus.comandos.empty():  # Esc sem clique no cartão: vale como não
                decisao = "nao", ""
        else:
            time.sleep(0.25)
    expirou = decisao is None
    if expirou:
        decisao = "nao", "A pessoa não respondeu ao pedido de permissão. Não execute; diga que ficou sem resposta."
    if decisao[0] == "sempre" and not pedido["sempre"]:
        decisao = "sim", ""
    bus.emitir("permissao_fim", id=pedido["id"], resultado="expirada" if expirou else "permitida" if decisao[0] != "nao" else "negada", sempre=decisao[0] == "sempre")
    bus.emitir("previa", texto="")
    bus.emitir("estado", v="pensando")
    return decisao


def trocar_conversa(cid=None):
    """Conversa nova (sem id) ou volta a uma anterior. A memória curta do modo rápido também é zerada."""
    CONVERSA.clear()
    FORA_DA_SESSAO.clear()
    memoria_conversa.zerar()
    return guardiao_sessao.trocar(cid)


def comando_claude(pergunta, streaming, modelo=None):
    arq = os.path.join(tempfile.gettempdir(), "guardiao_voz_sistema.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write(prompt_sistema())
    mensagem = mensagem_do_turno(pergunta)  # depois do prompt de sistema: o aviso dos últimos ajustes só pode ser lido uma vez por turno
    if mensagem != pergunta:  # para depurar: o que foi junto da pergunta neste turno (o prompt de sistema fica no arquivo ao lado)
        with open(os.path.join(tempfile.gettempdir(), "guardiao_voz_mensagem.txt"), "w", encoding="utf-8") as f:
            f.write(mensagem)
    base = guardiao_sessao.comando_do_claude()
    if not base:
        raise guardiao_sessao.ErroDeConta(AVISO_SEM_CLAUDE)
    cmd = [
        *base, "-p", mensagem,
        "--model", modelo or MODELO_PADRAO,
        "--system-prompt-file", arq,
        "--tools", "Read",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--setting-sources", "local",
        "--no-session-persistence",
        "--effort", "low",
    ]
    if streaming:
        cmd += ["--output-format", "stream-json", "--verbose", "--include-partial-messages"]
    else:
        cmd += ["--output-format", "json"]
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    if modelo_leve_ligado() and (modelo or MODELO_PADRAO) == MODELO_LEVE:
        # o Haiku pensa por conta própria mesmo com --effort low (medido: 10 a 36 s até a primeira frase, 5x o custo);
        # para consulta curta o pensamento só atrasa a voz, então no modelo leve ele fica desligado
        env["MAX_THINKING_TOKENS"] = "0"
    return cmd, env


def perguntar_claude(pergunta, modelo=None):
    t0 = time.time()
    cmd, env = comando_claude(pergunta, streaming=False, modelo=modelo)
    saida = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env, cwd=OPER, timeout=90, creationflags=guardiao_sessao.FLAGS_CLAUDE)
    try:
        resposta = json.loads(saida.stdout).get("result", "").strip()
    except json.JSONDecodeError:
        resposta = "Não consegui falar com o Claude agora."
    return resposta, time.time() - t0


FIM_FRASE = re.compile(r"(.+?[.!?…]+)(?=\s)", re.S)


class Cortador:
    """Junta os pedaços de texto que chegam do Claude e devolve cada frase assim que ela fica completa."""

    def __init__(self):
        self.buf = ""
        self.pendente = ""

    def alimentar(self, pedaco):
        self.buf += pedaco or ""
        prontas = []
        while True:
            # corta no fim da frase ou, se a frase for comprida, na primeira vírgula depois de 35 letras
            # (nunca dentro de uma diretiva: a conta é feita no texto mascarado, que tem o mesmo tamanho)
            mascarado = mascarar(self.buf)
            m_frase = FIM_FRASE.match(mascarado)
            m_pausa = re.search(r"[,;:](?=\s)", mascarado[35:])
            cortes = []
            if m_frase:
                cortes.append(m_frase.end(1))
            if m_pausa:
                cortes.append(35 + m_pausa.end())
            if not cortes:
                return prontas
            corte = min(cortes)
            frase = (self.pendente + " " + self.buf[:corte]).strip()
            self.buf = self.buf[corte:].lstrip()
            if len(extrair_diretivas(frase)[0]) < 15 and not DIRETIVA.search(frase):  # frase curtinha demais, junta com a próxima
                self.pendente = frase
                continue
            self.pendente = ""
            prontas.append(frase)

    def resto(self):
        """O que sobrou sem ponto final (o fim da resposta, ou o que foi dito antes de uma pausa para usar uma ferramenta)."""
        resto = (self.pendente + " " + self.buf).strip()
        self.buf = self.pendente = ""
        return resto


def frases_do_claude(pergunta, modelo=None, motivo=""):
    """Pergunta ao Claude em streaming e devolve cada frase assim que ela fica completa."""
    cmd, env = comando_claude(pergunta, streaming=True, modelo=modelo)
    erro_arq = guardiao_sessao.arquivo_de_erro()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=erro_arq, text=True, encoding="utf-8", env=env, cwd=OPER, creationflags=guardiao_sessao.FLAGS_CLAUDE)
    if erro_arq is not subprocess.DEVNULL:
        erro_arq.close()  # o processo filho tem a própria cópia
    controle_fala.registrar_processo(proc)
    latencia.marca("claude_iniciou")
    cortador = Cortador()
    falou, erro_do_claude, viu_linha, viu_texto = False, "", False, False
    try:
        for linha in proc.stdout:
            if not viu_linha:
                viu_linha = True
                latencia.marca("claude_primeira_linha")
            try:
                ev = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "result":
                registrar_chamada(modelo or MODELO_PADRAO, motivo, ev)
                if ev.get("is_error"):
                    erro_do_claude = str(ev.get("result") or "erro")
            if ev.get("type") == "stream_event" and ev["event"].get("type") == "content_block_delta":
                if not viu_texto:
                    viu_texto = True
                    latencia.marca("claude_primeiro_texto")
                for frase in cortador.alimentar(ev["event"].get("delta", {}).get("text", "")):
                    falou = True
                    yield frase
        resto = cortador.resto()
        if resto:
            falou = True
            yield resto
        if erro_do_claude and not falou:  # sem login, sem limite de uso...: a pessoa precisa saber o que fazer, não ouvir "não respondeu"
            raise guardiao_sessao.erro_de_conta(erro_do_claude)
    finally:
        controle_fala.esquecer_processo(proc)
        try:
            proc.terminate()
        except OSError:
            pass


def carregar_kokoro():
    """Carrega o Kokoro (local, sem internet) uma vez e faz uma frase de aquecimento, porque a primeira é lenta."""
    global _kokoro
    if _kokoro is None:
        _kokoro = nativo.carregar_voz(BASE)  # por caminho relativo: funciona com acento no nome da pasta do usuário
        _kokoro.create("Pronto.", voice=VOZ_KOKORO, speed=1.0, lang="pt-br")
    return _kokoro


def dividir_frases(texto):
    partes = re.split(r"(?<=[.!?…])\s+", texto.strip())
    return [p for p in partes if p.strip()]


def sintetizar_kokoro(texto, voz):
    k = carregar_kokoro()
    return [k.create(normalizar_para_fala(f), voice=voz, speed=1.0, lang="pt-br") for f in dividir_frases(texto)]


def tocar_e_revelar(texto, amostras, taxa, antes=""):
    """Toca a frase e mostra o texto aos poucos, no ritmo da fala (no terminal e na tela)."""
    duracao = len(amostras) / taxa
    sd.play(amostras, taxa)
    t0 = time.time()
    mostrado = 0
    janela = int(taxa * 0.05)
    while True:
        if controle_fala.PARAR.is_set():  # a pessoa fechou a janela: a frase é cortada no meio
            sd.stop()
            return
        decorrido = time.time() - t0
        alvo = len(texto) if decorrido >= duracao else int(len(texto) * decorrido / duracao)
        if alvo > mostrado:
            print(texto[mostrado:alvo], end="", flush=True)
            mostrado = alvo
            bus.emitir("guardiao_texto", texto=(antes + texto[:alvo]).strip())
        if decorrido >= duracao:
            break
        inicio = int(decorrido * taxa)
        trecho = amostras[inicio:inicio + janela]
        if len(trecho):
            bus.emitir("nivel", voz=float(min(1.0, np.sqrt(np.mean(np.square(trecho))) / 0.2)))
        time.sleep(0.045)
    print(" ", end="", flush=True)
    sd.wait()


def permitido(nome, texto_usuario):
    """A ação só acontece se o que a pessoa disse (agora ou na troca anterior, por causa de 'o que registro?') realmente a pede."""
    recente = [u for t, u, _ in CONVERSA[-2:] if time.time() - t < 180]
    alvo = _norm(" ".join(recente + [texto_usuario]))
    if INTENCAO[nome].search(alvo):
        return True
    # a pessoa só disse sim: vale quando foi o próprio guardião que ofereceu aquilo na fala anterior ("quer que eu conclua a repetida?")
    dito = re.sub(r"\s+", " ", _norm(texto_usuario)).strip()
    if CONVERSA and time.time() - CONVERSA[-1][0] < 180 and len(dito.split()) <= 6 and SIM.search(dito) and not NAO.search(dito):
        oferta = str(CONVERSA[-1][2] or "")
        return oferta.rstrip().endswith("?") and bool(INTENCAO[nome].search(_norm(oferta)))
    return False


def plano_permitido(nome, texto_usuario):
    """Ajustes do plano valem durante a revisão; fora dela, só se a frase da pessoa pedir aquilo."""
    return revisao_ativa() or permitido(nome, texto_usuario)


def executar_diretivas(diretivas, texto_usuario, acoes=True):
    """Faz o que a frase pede na tela: destacar, abrir o cartão, agir sobre a tarefa, ajustar o plano ou propor algo.
    Com acoes=False (a saudação) só o que é visual acontece."""
    global PROPOSTA
    if ACOES_ATIVAS and acoes and REVISAO is None and any(n == "revisao" and a.strip().lower().startswith("inicio") for n, a in diretivas):
        iniciar_revisao()  # antes dos destaques: a tela abre a lista da revisão primeiro e destaca as linhas nela
    ids = []
    for nome, arg in diretivas:
        if nome == "foco":
            ids += [x.strip() for x in arg.split(",") if x.strip()]
        elif nome == "detalhe" and arg.strip():
            ids.append(arg.split("|")[0].strip())
        elif nome in ("concluir", "reabrir", "comentar", "mover", "editar", "estender", "adiar"):
            ids.append(arg.split("|")[0].strip())
    if ids:
        bus.emitir("foco", ids=list(dict.fromkeys(ids)))
    for nome, arg in diretivas:
        if nome == "detalhe" and arg.strip():
            bus.emitir("detalhe", id=arg.split("|")[0].strip())
    if not ACOES_ATIVAS or not acoes:
        return
    for nome, arg in diretivas:
        if nome in ("concluir", "reabrir", "comentar"):
            ref, _, texto = arg.partition("|")
            if not permitido(nome, texto_usuario):
                print(f"  (ignorei a ação '{nome}': a pessoa não pediu isso)")
                registrar_recusa_de_acao(nome, ref.strip())  # ele já disse que ia fazer: no fim da resposta conta que não fez e pergunta
                continue
            threading.Thread(target=agir_e_contar, args=(nome, ref.strip(), texto.strip() or None), daemon=True).start()
        elif nome == "criar":
            if not permitido("criar", texto_usuario):
                print("  (ignorei a proposta de tarefa: a pessoa não pediu isso)")
                continue
            dados = campos(arg)
            if not dados.get("titulo"):
                continue
            lista = resolver_lista(dados.get("lista"))
            dados["lista"] = lista["nome"] if lista else dados.get("lista", "")
            PROPOSTA = {"tipo": "criar", "dados": dados, "quando": time.time()}
            bus.emitir("proposta", tipo="criar", dados=dados)
        elif nome == "revisao":
            if arg.strip().lower().startswith("inicio"):
                if REVISAO is None:
                    iniciar_revisao()
            else:
                encerrar_revisao()
        elif nome in ("estender", "adiar", "motivo", "checkin"):  # acompanhamento da execução (painel novo)
            partes = [x.strip() for x in arg.split("|")]
            if nome == "checkin":
                v2.registrar_evento("checkin_resposta", v2.bloco_atual(), resposta="no_prazo")
                v2.fechar_checkin()
                continue
            if not (v2.CHECKIN or permitido(nome, texto_usuario)):
                print(f"  (ignorei '{nome}': a pessoa não pediu isso)")
                continue
            ref = partes[0]
            if nome == "estender":
                minutos = re.sub(r"\D", "", partes[1] if len(partes) > 1 else "") or "15"
                r = v2.estender_bloco(ref, int(minutos), (partes[2] if len(partes) > 2 else "") or None)
                nota = f"estender ok: novo fim às {r.get('fim')}" + (f". ATENÇÃO: {r['conflito']}" if r.get("conflito") else "") if r.get("ok") else f"estender FALHOU: {r.get('erro')}"
            elif nome == "adiar":
                r = v2.adiar_com_motivo(ref, (partes[1] if len(partes) > 1 else "") or None)
                nota = "adiar ok: a tarefa ficou como adiada" if r.get("ok") else f"adiar FALHOU: {r.get('erro')}"
            else:
                r = v2.registrar_motivo(ref, partes[1] if len(partes) > 1 else "", "imprevisto")
                nota = "motivo anotado"
            if not r.get("ok"):
                bus.emitir("aviso", texto=r.get("erro") or "Não consegui ajustar a tarefa.", erro=True)
            avisar_modelo(nota)
            if nome != "motivo":
                v2.fechar_checkin()
        elif nome == "completo":
            pedido = re.sub(r"\s+", " ", arg).strip()
            if not pedido or not permitido("completo", texto_usuario):
                print("  (ignorei o pedido ao guardião completo: a pessoa não pediu isso)")
                continue
            if not iniciar_completo(pedido):
                avisar_modelo("o guardião completo já está trabalhando em outro pedido; este não foi enviado")
        elif nome in ("mover", "editar", "remover", "adicionar", "desfazer"):
            if not plano_permitido(nome, texto_usuario):
                print(f"  (ignorei o ajuste '{nome}': a pessoa não pediu isso)")
                continue
            ref, _, resto = arg.partition("|")
            ref = ref.strip()
            if nome == "mover":
                dados = {"horario": resto.strip()}
            elif nome == "editar":
                dados = campos(resto)
            elif nome == "adicionar":
                ref, dados = None, campos(arg)
            else:
                dados = {}
            r = editar_plano(nome, ref or None, dados)
            if r.get("ok"):
                nota = f"{nome} '{r.get('titulo')}' ok" + (f" ({r.get('depois')})" if r.get("depois") else "")
                if r.get("conflitos"):
                    nota += ". ATENÇÃO, bate com: " + "; ".join(r["conflitos"])
            else:
                nota = f"{nome} FALHOU: {r.get('erro')}"
                bus.emitir("aviso", texto=r.get("erro") or "Não consegui ajustar o plano.", erro=True)
            avisar_modelo(nota)
            tocar_revisao()
        elif nome == "aprovar":
            plano = _plano_de_hoje() or {}
            if plano.get("status") != "sugerido":
                bus.emitir("aviso", texto="O plano de hoje não está aguardando aprovação.", erro=False)
                continue
            if EXPLICITO_APROVAR.search(_norm(texto_usuario)) and not NAO.search(_norm(texto_usuario)):
                encerrar_revisao()
                threading.Thread(target=agir_e_contar, args=("aprovar",), daemon=True).start()
            else:
                resumo = resumo_aprovacao()
                PROPOSTA = {"tipo": "aprovar", "dados": resumo, "quando": time.time()}
                bus.emitir("proposta", tipo="aprovar", dados=resumo)


EXPLICITO_APROVAR = re.compile(r"aprov")


# ---------------- guardião completo: a skill inteira, em segundo plano ----------------
# A voz é a versão rápida (prompt curto, resposta em segundos). Pedido grande (refazer o plano, planejar a semana, destrinchar um projeto)
# vai para o Claude com a skill guardiao-triwer, do mesmo jeito que o gerar_plano.ps1 faz: leva de dois a cinco minutos e não trava a conversa.
# Ele só pode gravar arquivo de plano, nunca o ClickUp: o plano volta como "sugerido" e a pessoa aprova na tela ou pela voz.
REGRAS_DO_PLANO = (
    "Ao gravar o plano de hoje: grave o plano inteiro, em JSON válido, no formato de plano_exemplo.json, com \"status\": \"sugerido\" "
    "(a pessoa aprova na tela e o servidor cria ou move as tarefas no ClickUp). Mantenha os blocos já feitos, mantenha o id e o clickup_id dos blocos que continuam, "
    "dê aos blocos novos um id ainda não usado (b seguido de número), use clickup_id para tarefa que já existe no resumo e lista_id só para bloco realmente novo, "
    "e ponha \"reagendado\": true em todo bloco com clickup_id que mudou de horário ou que entrou no dia agora. Nenhum bloco pendente pode começar antes de agora."
)
COMPLETO = None  # pedido em andamento: {"pedido": texto, "inicio": time}
COMANDO_COMPLETO = None  # os testes trocam por uma função (pedido, arquivo do plano) -> texto da resposta
TEMPO_COMPLETO = 900  # segundos


def prompt_completo(pedido, arquivo_plano):
    cfg = _config()
    quem = pessoa()
    memoria = pasta_memoria()
    hoje = time.strftime("%Y-%m-%d")
    conversa = "\n".join(f"{quem['primeiro']}: {u}\nGuardião: {g}" for _, u, g in memoria_conversa.recentes(3))
    return (
        f"Use a skill guardiao-triwer. Pedido de {quem['nome']}, feito por voz no painel do guardião: \"{pedido}\"\n"
        f"Hoje é {hoje} e agora são {time.strftime('%H:%M')}. Pasta operacional (plano, registros, resumo do ClickUp, scripts): {OPER}. Pasta de memória: {memoria}.\n"
        + (f"Conversa recente por voz, só para contexto:\n{conversa}\n" if conversa else "") +
        "Esta execução não tem conversa: não pergunte nada. Se faltar informação, escolha o caminho mais seguro e diga isso em uma frase.\n"
        "Leia o que a skill manda carregar e, se o pedido tocar o plano de hoje, leia também o plano atual (plano_do_dia.json) e o registro de hoje "
        f"(registros\\registro_{hoje}.json, com os blocos já feitos ou adiados), os dois na pasta operacional.\n"
        "Não crie nem altere nada no ClickUp nem em outro lugar, e não edite os arquivos de memória. As únicas escritas permitidas são: "
        f"o arquivo {arquivo_plano} (plano de hoje) e planos\\plano_AAAA-MM-DD.json na pasta operacional (plano de outro dia), e só se o pedido for montar ou mudar um plano.\n"
        + REGRAS_DO_PLANO + "\n"
        "No fim, responda SOMENTE com o que deve ser dito em voz alta: até 6 frases curtas, sem lista, sem markdown e sem travessão. "
        "Fale na primeira pessoa, como o mesmo guardião da conversa: não cite esta execução, o guardião completo, checagens técnicas nem o que você não tem permissão de fazer. "
        "Diga o que você montou ou concluiu, o que ficou de fora e por quê, e o que a pessoa precisa decidir. "
        "Se sobrar algo para resolver no ClickUp (concluir, apagar ou mover uma tarefa), não mande a pessoa fazer: diga qual é a tarefa, pelo título, e pergunte se ela quer que você resolva. "
        "Termine com uma pergunta só: a do ClickUp, se houver; senão, se você mudou o plano de hoje, pergunte se ela quer revisar o plano."
    )


def _chamar_completo(pedido, arquivo_plano):
    memoria = pasta_memoria()
    base = guardiao_sessao.comando_do_claude()
    if not base:
        raise guardiao_sessao.ErroDeConta(AVISO_SEM_CLAUDE)
    cmd = [*base, "-p", prompt_completo(pedido, arquivo_plano), "--model", MODELO_PADRAO, "--add-dir", memoria,
           "--allowedTools", "Read,Write,Glob,Skill", "--max-turns", "30", "--output-format", "json"]
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    saida = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=OPER, timeout=TEMPO_COMPLETO, creationflags=guardiao_sessao.FLAGS_CLAUDE)
    ev = json.loads(saida.stdout)
    registrar_chamada(MODELO_PADRAO, "guardião completo", ev)
    return str(ev.get("result") or "")


def _plano_valido(texto):
    try:
        plano = json.loads(texto)
        return isinstance(plano, dict) and isinstance(plano.get("blocos"), list) and all(
            isinstance(b, dict) and b.get("id") and b.get("titulo") and re.fullmatch(r"\d{1,2}:\d{2}", str(b.get("inicio") or "")) and re.fullmatch(r"\d{1,2}:\d{2}", str(b.get("fim") or ""))
            for b in plano["blocos"])
    except ValueError:
        return False


def ler_plano():
    try:
        with open(os.path.join(OPER, "plano_do_dia.json"), encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return None


def conferir_plano(antes):
    """Depois que o Claude pôde mexer no plano de hoje (pedido em segundo plano ou sessão): "igual", "mudou" ou "defeito".
    Plano com defeito não fica (volta o que estava) e plano mudado sempre volta para "sugerido", para passar pela aprovação."""
    arq = os.path.join(OPER, "plano_do_dia.json")
    depois = ler_plano()
    if depois == antes:
        return "igual"
    if depois is None or not _plano_valido(depois):
        if antes is None:
            if os.path.exists(arq):
                os.remove(arq)
        else:
            with open(arq, "w", encoding="utf-8") as f:
                f.write(antes)
        return "defeito"
    plano = json.loads(depois)
    if plano.get("status") != "sugerido":
        plano["status"] = "sugerido"
        plano.pop("aprovado_em", None)
        with open(arq, "w", encoding="utf-8") as f:
            json.dump(plano, f, ensure_ascii=False, indent=2)
    return "mudou"


def rodar_completo(pedido):
    """Roda o pedido na skill inteira. Confere o plano que voltou e entrega a fala para o guardião dizer."""
    global COMPLETO
    arq = os.path.join(OPER, "plano_do_dia.json")
    antes = ler_plano()
    mudou = False
    try:
        resposta = (COMANDO_COMPLETO or _chamar_completo)(pedido, arq)
        fala = extrair_diretivas(re.sub(r"[*_#`]+", "", resposta))[0].replace("—", ",").strip()
        conferido = conferir_plano(antes)
        if conferido == "defeito":
            fala = "Montei o plano, mas ele saiu com defeito e eu desfiz a mudança. Pode pedir de novo?"
        mudou = conferido == "mudou"
        if not fala:
            fala = "Terminei, mas não tenho um resumo para te dar. Dá uma olhada no plano." if mudou else "Não consegui concluir esse pedido agora."
    except subprocess.TimeoutExpired:
        fala = "Esse pedido demorou demais e eu parei. Tenta pedir uma parte menor."
    except Exception as erro:
        print("  Erro no guardião completo:", erro)
        fala = "Não consegui terminar esse pedido agora. Tenta de novo daqui a pouco."
    finally:
        COMPLETO = None
        bus.emitir("completo", ativo=False)
    if mudou:
        bus.emitir("plano")
    bus.comandos.put(("completo_fim", {"pedido": pedido, "fala": fala, "mudou": mudou}))


def iniciar_completo(pedido):
    """Liga o trabalho em segundo plano. Devolve False se já houver um pedido em andamento."""
    global COMPLETO
    if COMPLETO:
        return False
    COMPLETO = {"pedido": pedido, "inicio": time.time()}
    bus.emitir("completo", ativo=True, pedido=pedido)
    threading.Thread(target=rodar_completo, args=(pedido,), daemon=True).start()
    return True


def resolver_proposta(texto):
    """'sim', 'nao', 'outro' ou None: o que a pessoa respondeu sobre o que está pendente. Proposta velha é descartada.
    'outro' (só para aprovar) = ele falou de outra coisa, por exemplo pediu uma mudança: a proposta cai e a conversa segue."""
    global PROPOSTA
    if not PROPOSTA:
        return None
    if time.time() - PROPOSTA["quando"] > VALIDADE_PROPOSTA:
        PROPOSTA = None
        bus.emitir("proposta_fim", resultado="expirada")
        return None
    t = _norm(texto)
    if PROPOSTA.get("tipo") == "aprovar":
        limpo = re.sub(r"\b(por favor|guardiao|pode|entao|ai)\b", " ", t).strip() if t.strip() not in SIM_APROVAR else t.strip()
        limpo = re.sub(r"\s+", " ", limpo)
        if EDITA.search(t) and not EXPLICITO_APROVAR.search(t):
            return "outro"
        if NAO.search(t) and not EXPLICITO_APROVAR.search(t):
            return "nao"
        if t.strip() in SIM_APROVAR or limpo in SIM_APROVAR or (EXPLICITO_APROVAR.search(t) and len(t.split()) <= 8):
            return "sim"
        return "outro"
    if len(t.split()) > 8:
        return None
    if NAO.search(t):
        return "nao"
    if SIM.search(t):
        return "sim"
    return None


def proximo_bloco():
    plano = _plano_de_hoje() or {}
    estados = {b.get("id"): b.get("estado") for b in _registro_de_hoje().get("blocos", [])}
    pend = [b for b in plano.get("blocos", []) if estados.get(b.get("id")) not in ("feito", "adiado")]
    agora = time.strftime("%H:%M")
    futuros = [b for b in pend if b["fim"] > agora]
    return (futuros or pend or [None])[0]


def resposta_pos_aprovacao(r):
    if not r.get("ok"):
        return f"Não consegui aprovar o plano. {r.get('erro') or ''}".strip()
    partes = ["Plano aprovado."]
    n, m = r.get("criadas") or 0, r.get("reagendadas") or 0
    if n:
        partes.append(f"Criei {n} {'tarefa' if n == 1 else 'tarefas'} no ClickUp.")
    if m:
        partes.append(f"Reagendei {m} no ClickUp.")
    if r.get("erros"):
        partes.append(f"{len(r['erros'])} não deram certo, olhe na tela.")
    prox = proximo_bloco()
    if prox:
        partes.append(f"O próximo bloco é {prox['titulo']}, às {prox['inicio']}.")
    return " ".join(partes)


# ---------------- saudação ao abrir o app ----------------

SAUDACAO_ARQ = os.path.join(OPER, "logs", "saudacao.json")
DIAS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _ler_saudacoes():
    try:
        with open(SAUDACAO_ARQ, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def pode_saudar(forcar=False):
    if not preferencias().get("saudacao", True):  # desligada no painel de configurações
        return False
    if PROPOSTA or revisao_ativa():
        return False
    return bool(forcar) or time.time() - _ler_saudacoes().get("ts", 0) > INTERVALO_SAUDACAO


def marcar_saudacao():
    """Anota que a saudação começou. Fica anotado já no começo e não só no fim: se ela falhar ou demorar, o próximo reinício não repete a saudação."""
    d = _ler_saudacoes()
    os.makedirs(os.path.dirname(SAUDACAO_ARQ), exist_ok=True)
    with open(SAUDACAO_ARQ, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "textos": d.get("textos") or []}, f, ensure_ascii=False)


def saudacao_local():
    """A saudação que não depende do Claude: usada quando a dele demora ou falha. Só o horário e o nome."""
    hora = time.localtime().tm_hour
    parte = "Bom dia" if 5 <= hora < 12 else "Boa tarde" if 12 <= hora < 18 else "Boa noite"
    return f"{parte}, {pessoa()['primeiro']}."


def registrar_saudacao(texto):
    d = _ler_saudacoes()
    textos = (d.get("textos") or [])[-2:] + [texto]
    os.makedirs(os.path.dirname(SAUDACAO_ARQ), exist_ok=True)
    with open(SAUDACAO_ARQ, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "textos": textos}, f, ensure_ascii=False)


def pedido_saudacao():
    """O 'pedido' que vira a saudação do dia. O Claude escreve a fala; aqui só vão os fatos e o objetivo, para ela mudar a cada dia."""
    agora = time.localtime()
    hora = agora.tm_hour
    parte = "bom dia" if 5 <= hora < 12 else "boa tarde" if 12 <= hora < 18 else "boa noite"
    data = f"{DIAS_PT[agora.tm_wday]}, {agora.tm_mday} de {MESES_PT[agora.tm_mon - 1]}"
    plano = _plano_de_hoje()
    if not plano or not plano.get("blocos"):
        situacao = "Ainda não existe plano para hoje. Diga isso com naturalidade e pergunte se ele quer ajuda para organizar o dia."
    elif plano.get("status") == "sugerido":
        situacao = (f"O plano de hoje tem {len(plano['blocos'])} blocos e ainda NÃO foi aprovado. Convide <o Fulano> a revisar o plano com você agora, "
                    "bloco a bloco, e aprová-lo, e pergunte se ele topa.")
    else:
        prox = proximo_bloco()
        situacao = ("O plano de hoje já está aprovado. " +
                    (f"O próximo bloco é {prox['titulo']}, às {prox['inicio']}. Diga isso em uma frase e " if prox else "Não sobrou bloco pendente hoje. Diga isso e ") +
                    "pergunte como ele quer começar.")
    anteriores = _ler_saudacoes().get("textos") or []
    evitar = ("\nSaudações recentes (não repita as palavras iniciais nem a estrutura delas): " + " || ".join(anteriores)) if anteriores else ""
    return _p(
        f"[ABERTURA DO APP. Isto não é uma fala <do Fulano>: o app acabou de abrir.] Agora são {time.strftime('%H:%M')}, {data}. "
        f"Cumprimente <o Fulano> pelo horário ({parte}), diga a data de hoje de um jeito natural e pergunte como ele gostaria de começar. {situacao} "
        "Fale como uma pessoa, em duas ou três frases curtas. A forma de falar deve mudar de um dia para o outro, mas o objetivo é sempre este. "
        "Termine com uma pergunta clara. Não use marcas de ação; se citar um bloco, pode usar {{foco:ID}}." + evitar
    )


def voz_ligada():
    """Preferência do painel: com a voz do guardião desligada ele só escreve (o microfone da pessoa continua valendo)."""
    return bool(preferencias().get("voz_guardiao", True))


def revelar_sem_voz(texto, antes=""):
    """Mostra o texto aos poucos, no ritmo de quem digita, sem tocar áudio."""
    cps, passo = 42.0, 0.05
    mostrado = 0
    t0 = time.time()
    while mostrado < len(texto):
        mostrado = min(len(texto), int((time.time() - t0) * cps) + 1)
        bus.emitir("guardiao_texto", texto=(antes + texto[:mostrado]).strip())
        time.sleep(passo)
    print(texto + " ", end="", flush=True)


def dizer(texto, a):
    """Fala uma resposta curta e fixa (sem passar pelo Claude), mostrando o texto junto, como nas respostas normais."""
    controle_fala.comecar()
    bus.emitir("estado", v="falando")
    try:
        if not voz_ligada():
            acumulado = ""
            for frase in dividir_frases(texto):
                revelar_sem_voz(frase, acumulado)
                acumulado += frase + " "
            print()
        elif a.voz == "kokoro":
            k = carregar_kokoro()
            frases = dividir_frases(texto)
            prontas = queue.Queue()

            def gerar():  # a próxima frase é gerada enquanto a anterior toca
                for frase in frases:
                    if controle_fala.PARAR.is_set():
                        break
                    try:
                        amostras, taxa = k.create(normalizar_para_fala(frase), voice=a.voz_kokoro, speed=1.0, lang="pt-br")
                        prontas.put((frase, amostras, taxa))
                    except Exception:
                        prontas.put((frase, None, None))
                prontas.put(None)

            threading.Thread(target=gerar, daemon=True).start()
            acumulado = ""
            while True:
                item = prontas.get()
                if item is None or controle_fala.PARAR.is_set():
                    break
                frase, amostras, taxa = item
                if amostras is None:
                    revelar_sem_voz(frase, acumulado)
                else:
                    tocar_e_revelar(frase, amostras, taxa, acumulado)
                acumulado += frase + " "
            print()
        else:
            bus.emitir("guardiao_texto", texto=texto)
            falar(texto, a.voz, a.voz_nome)
    except Exception as erro:
        print("  (não consegui falar:", erro, ")")
        bus.emitir("guardiao_texto", texto=texto)
    finally:
        controle_fala.terminar()
    bus.emitir("guardiao_fim", texto=texto)


def responder_falando(pergunta, voz_kokoro, texto_usuario=None, acoes=True, portao=None, modelo=None, motivo="", fonte=None, pedir=None,
                      limite_primeira=None, modo="rapido"):
    """Claude em streaming -> frases -> voz Kokoro, com o texto aparecendo junto com a fala e as diretivas
    (destaque, cartão, ações) acontecendo na hora em que a frase começa a ser falada.
    limite_primeira: segundos até a primeira frase. Passou disso, a resposta é abandonada e a função lança TimeoutError (a saudação usa).
    Se a pessoa fechar a janela no meio, a fala para e o que já foi dito é devolvido.
    Devolve (tempo até a primeira fala, tempo total, texto falado). Lança exceção se o Claude não responder."""
    texto_usuario = texto_usuario if texto_usuario is not None else pergunta
    t0 = time.time()
    medidor = latencia.iniciar(modo, motivo)
    controle_fala.comecar()
    primeira, acumulado, dito, parado, erro_final = None, "", [], False, ""  # dito: mensagens já fechadas neste turno (o que veio antes de um pedido de permissão)
    try:
        mudo = not voz_ligada()  # voz desligada no painel: nem sintetiza, só escreve
        k = None if mudo else carregar_kokoro()
        fila_frases = queue.Queue()
        fila_audio = queue.Queue()
        erro_leitura = []

        def ler():
            try:
                for frase in (fonte() if fonte else frases_do_claude(pergunta, modelo, motivo)):
                    if controle_fala.PARAR.is_set():
                        break
                    fila_frases.put(frase)
            except Exception as erro:  # o motivo de verdade (sem login, sem limite...) chega a quem está esperando a primeira frase
                erro_leitura.append(erro)
            finally:
                fila_frases.put(None)

        def sintetizar():
            n = 0
            while True:
                frase = fila_frases.get()
                if frase is None:
                    fila_audio.put(None)
                    return
                if controle_fala.PARAR.is_set():
                    continue  # a pessoa fechou a janela: o resto da fila é esvaziado sem gerar voz
                if not isinstance(frase, str):  # pedido de permissão: segue na ordem, depois do que já foi dito
                    fila_audio.put(frase)
                    continue
                limpo, diretivas = extrair_diretivas(frase)
                n += 1
                medidor.marca("frase", n=n, palavras=len(limpo.split()))
                if not limpo or mudo:
                    fila_audio.put((limpo, diretivas, None, None))
                    continue
                try:
                    inicio = time.time()
                    medidor.marca("sintese_ini", n=n)
                    amostras, taxa = k.create(normalizar_para_fala(limpo), voice=voz_kokoro, speed=1.0, lang="pt-br")
                    medidor.marca("sintese_fim", n=n, fala=round(len(amostras) / taxa, 1), gasto=round(time.time() - inicio, 2))
                    fila_audio.put((limpo, diretivas, amostras, taxa))
                except Exception:
                    fila_audio.put((limpo, diretivas, None, None))

        threading.Thread(target=ler, daemon=True).start()
        threading.Thread(target=sintetizar, daemon=True).start()
        print("  pensando...", end="\r", flush=True)
        calado = False  # parou de falar para usar uma ferramenta: a tela volta a mostrar que ele está trabalhando
        toques = 0
        while True:
            if controle_fala.PARAR.is_set():
                parado = True
                break
            if limite_primeira and primeira is None and time.time() - t0 > limite_primeira:
                controle_fala.parar(f"a primeira frase não chegou em {limite_primeira} s")
                raise TimeoutError(f"a primeira frase não chegou em {limite_primeira} s")
            try:
                item = fila_audio.get(timeout=0.5)
            except queue.Empty:
                if primeira is not None and not calado:
                    calado = True
                    bus.emitir("estado", v="pensando")
                continue
            if item is None:
                break
            if len(item) == 2 and item[0] == "permissao":
                if acumulado.strip():
                    print()
                    bus.emitir("guardiao_fim", texto=acumulado.strip())
                    dito.append(acumulado.strip())
                    acumulado = ""
                guardiao_sessao.decidir(item[1], *(pedir(item[1]) if pedir else ("nao", "")))
                calado = True
                continue
            limpo, diretivas, amostras, taxa = item
            if portao is not None and primeira is None and limpo:
                portao.wait(timeout=15)  # a saudação espera a abertura da tela terminar
            if controle_fala.PARAR.is_set():
                parado = True
                break
            if diretivas:
                executar_diretivas(diretivas, texto_usuario, acoes)
            if not limpo:
                continue
            if primeira is None:
                primeira = time.time() - t0
                print(" " * 40, end="\r")
                print("  Guardião: ", end="", flush=True)
                bus.emitir("estado", v="falando")
            elif calado:
                bus.emitir("estado", v="falando")
            calado = False
            toques += 1
            medidor.marca("toque_ini", n=toques)
            if amostras is None:
                revelar_sem_voz(limpo, acumulado)
            else:
                tocar_e_revelar(limpo, amostras, taxa, acumulado)
            medidor.marca("toque_fim", n=toques)
            acumulado += limpo + " "
        print()
        if primeira is None and not dito and not parado:
            raise (erro_leitura[0] if erro_leitura else RuntimeError("o Claude não respondeu"))
        if acumulado.strip():
            bus.emitir("guardiao_fim", texto=acumulado.strip())
            dito.append(acumulado.strip())
        bus.emitir("foco_fim")
        return primeira or 0.0, time.time() - t0, " ".join(dito)
    except Exception as erro:
        erro_final = f"{type(erro).__name__}: {erro}"
        raise
    finally:
        controle_fala.terminar()
        medidor.fechar(primeira=round(primeira, 2) if primeira is not None else None, parado=parado, erro=erro_final or None)


def tocar_mp3(caminho):
    mci = ctypes.windll.winmm.mciSendStringW
    mci("close gv", None, 0, 0)
    if mci(f'open "{caminho}" type mpegvideo alias gv', None, 0, 0) != 0:
        raise RuntimeError("o Windows não conseguiu abrir o áudio")
    mci("play gv wait", None, 0, 0)
    mci("close gv", None, 0, 0)


async def _salvar_edge(texto, voz, caminho):
    await edge_tts.Communicate(texto, voz).save(caminho)


def falar(texto, motor="edge", voz_edge=VOZ_EDGE):
    """Fala a resposta já pronta (usado quando o Kokoro não está disponível)."""
    fala = normalizar_para_fala(texto)
    if motor == "edge":
        try:
            caminho = os.path.join(tempfile.gettempdir(), "guardiao_voz_fala.mp3")
            asyncio.run(_salvar_edge(fala, voz_edge, caminho))
            tocar_mp3(caminho)
            return
        except Exception as erro:
            print("  (voz neural indisponível, usando a do Windows:", erro, ")")
    falar_windows(fala)


def falar_windows(texto):
    arq = os.path.join(tempfile.gettempdir(), "guardiao_voz_fala.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write(texto)
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"try {{ $s.SelectVoice('{VOZ_WINDOWS}') }} catch {{ }};"
        f"$s.Speak([IO.File]::ReadAllText('{arq}', [Text.Encoding]::UTF8));"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=SEM_JANELA)


def sapi_para_wav(texto, caminho):
    arq = os.path.join(tempfile.gettempdir(), "guardiao_voz_teste.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write(texto)
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"try {{ $s.SelectVoice('{VOZ_WINDOWS}') }} catch {{ }};"
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono);"
        f"$s.SetOutputToWaveFile('{caminho}', $f);"
        f"$s.Speak([IO.File]::ReadAllText('{arq}', [Text.Encoding]::UTF8)); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=SEM_JANELA)


def ler_wav_pcm(caminho):
    with wave.open(caminho, "rb") as w:
        return w.readframes(w.getnframes())


def autoteste(modelo, chave, com_cerebro):
    """Usa a voz do Windows no lugar do seu microfone para checar a cadeia inteira, menos a captura do microfone."""
    pasta = tempfile.gettempdir()
    print("1) Palavra de ativação com a voz sintética 'Ei guardião':")
    wav = os.path.join(pasta, "gv_ativacao.wav")
    sapi_para_wav("Ei guardião", wav)
    pcm = ler_wav_pcm(wav) + b"\x00\x00" * SR  # 1 s de silêncio no fim
    rec = reconhecedor(modelo)
    ouvidos = []
    for i in range(0, len(pcm), BLOCO * 2):
        bloco = pcm[i:i + BLOCO * 2]
        if rec.AcceptWaveform(bloco):
            ouvidos.append(json.loads(rec.Result()))
    ouvidos.append(json.loads(rec.FinalResult()))
    achou = any(chamou(r) for r in ouvidos)
    print("   Vosk entendeu:", [r.get("text") for r in ouvidos if r.get("text")], "->", "ATIVOU" if achou else "NAO ATIVOU")

    print("2) Transcrição no Groq de uma frase com a voz sintética:")
    if not chave:
        print("   sem GROQ_API_KEY, pulei esta etapa.")
        return
    wav2 = os.path.join(pasta, "gv_pergunta.wav")
    sapi_para_wav("Qual é o meu próximo bloco do plano de hoje?", wav2)
    with open(wav2, "rb") as f:
        texto, seg = transcrever(f.read(), chave)
    print(f"   Groq devolveu em {seg:.1f}s: {texto}")

    if com_cerebro and texto:
        print("3) Guardião enxuto (Claude):")
        resp, seg2 = perguntar_claude(texto)
        print(f"   Respondeu em {seg2:.1f}s: {resp}")
        print("   Como a voz vai ler:", normalizar_para_fala(resp))


def porta_em_uso(porta):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def vigiar_avisos():
    """Mantém o aviso por pop-up (avisos.ps1) ligado: se ele morrer, o guardião o liga de novo em até 30 s."""
    script = os.path.join(OPER, "avisos.ps1")
    while True:
        try:
            aberto = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, "Local\\GuardiaoTriwerAvisos")
            if aberto:
                ctypes.windll.kernel32.CloseHandle(aberto)
            elif os.path.exists(script):
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script],
                    creationflags=SEM_JANELA, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                print("  (aviso por pop-up estava desligado, liguei de novo)")
        except Exception as erro:
            print("  (vigia do aviso falhou:", erro, ")")
        time.sleep(30)


# o painel abre no navegador padrão da pessoa, no perfil dela. Nesse caso o navegador pode segurar o som da abertura até o primeiro clique:
# a página já espera o clique (o áudio só liga depois de um gesto), então não há o que fazer do lado de cá
def abrir_tela(url):
    """Abre o painel no navegador padrão da pessoa: janela de aplicativo (sem abas nem barra de endereço) no Chrome e no Edge, aba nova nos outros (veja janela_painel.py)."""
    janela_painel.abrir(url, "1500,940")


# ---------------- pedidos que a própria máquina resolve (painel novo), sem gastar uma chamada ao Claude ----------------

SAIR_EXEC = re.compile(r"\b(sair|sai|saia|saindo) d[oa] (modo )?(de )?(execucao|foco)\b|\bparar? (a |o )?(modo )?(de )?execucao\b|\bpausar? (a )?execucao\b"
                       r"|\bvolta\w* (pra|para) (a )?conversa\b|\bdesativ\w* (o )?modo\b|\bencerr\w* (a |o )?(modo )?(de )?execucao\b")
ENTRAR_EXEC = re.compile(r"\bmodo (de )?(execucao|foco)\b|\bativ\w* (a |o )?(execucao|modo)\b|\bentr\w+ (no |em )?(modo )?(de )?(execucao|foco)\b"
                         r"|^bora( trabalhar| comecar| la)?$|^vamos (la|nessa|comecar|trabalhar)$|\bvou (executar|trabalhar|focar|comecar)\b|\bcomecar (a )?(executar|trabalhar)\b")
PROXIMAS = re.compile(r"^(quais|qual|mostra|mostrar|abre|abrir|ver|me mostra)?\s*(sao |e )?(as |a |os |o )?(minhas? |meus? )?proxim\w+( tarefas?| blocos?)?$|^o que vem depois$")
AGENDA = re.compile(r"^(abre|abrir|mostra|mostrar|ver|me mostra)\s+(a |o )?(minha |meu )?(agenda|dia|plano)( do dia| de hoje| complet[ao])?$")
FECHAR = re.compile(r"^(fecha|fechar|pode fechar|esconde|esconder)( isso| o painel| a janela| os detalhes| tudo)?$")
NAVEGAR = re.compile(r"^(?:abre|abrir|vai para|ir para|vai pra|mostra|mostrar)\s+(?:a |o |os )?(?:tela |aba )?(?:d[aeo]s? )?(?P<tela>home|inicio|dia|planejador|calibragem|pops?)$")
TELAS = {"home": "home", "inicio": "home", "dia": "dia", "planejador": "plan", "calibragem": "cal", "pops": "pops", "pop": "pops"}
MUDO = re.compile(r"^(fica|fique|ficar) (mudo|quieto|calado|em silencio)$|^silenci\w+( a (sua )?voz)?$|^(modo )?sem voz$|^deslig\w+ a (sua )?voz$")
FALAR = re.compile(r"^(pode falar|pode voltar a falar|lig\w+ a (sua )?voz|volt\w+ a falar)$")
PEDE_REPORT = re.compile(r"^(quero |vamos |bora )?(fazer |mandar |enviar )?(o |meu )?report( do dia| de hoje)?$")
DETALHES = re.compile(r"^(abre |abrir |mostra |me mostra )?(os )?detalhes?( da tarefa| dessa tarefa| desta tarefa)?$")
E_PERGUNTA = re.compile(r"^(o que|como|por ?que|quando|quanto|onde|quem)\b")
NOVA_CONVERSA = re.compile(r"^((abre|abrir|comec\w+|inici\w+|cri\w+|quero) )?(uma )?(nova conversa|conversa nova)$|^(limp\w+|zer\w+) (a |o )?(conversa|contexto)$|^esquece (essa|esta|a) conversa$")
VER_CONVERSAS = re.compile(r"^((abre|abrir|mostra|mostrar|ver|me mostra) )?(as |o )?(minhas |meu )?(conversas|historico)( anteriores| antigas| passadas| de conversas)?$")


def _limpar_comando(texto):
    t = re.sub(r"\s+", " ", _norm(texto)).strip()
    t = re.sub(r"^(ei |oi |ola )?(guardiao|guardia)\b\s*", "", t)
    t = re.sub(r"\b(por favor|por gentileza|pra mim|para mim)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


CONCLUI = re.compile(r"^(ja )?(conclui|terminei|acabei|finalizei|fechei|encerrei|fiz tudo)\b|^ja fiz\b")
NEGA_CONCLUSAO = re.compile(r"\b(nao|ainda nao|quase|metade|falta|faltam|so falta)\b")
LIGACAO = {"para", "como", "com", "uma", "dois", "tres", "sobre", "essa", "esse", "isso", "depois", "antes", "ainda", "hoje", "todos", "todas"}


def _palavras(texto):
    return {w for w in re.findall(r"[a-z]{4,}", _norm(texto or "")) if w not in LIGACAO}


def concluir_local(texto):
    """"Concluí...", "terminei...", "acabei...": conclui a tarefa de agora direto, sem chamar o Claude (que gasta dezenas de milhares de tokens para registrar uma frase).
    O que a pessoa contou fica no registro de eventos para a análise e o report. Na dúvida (a fala cita outra tarefa, ou nega), devolve None e o Claude responde."""
    t = _limpar_comando(texto)
    if not t or not CONCLUI.match(t) or NEGA_CONCLUSAO.search(t):
        return None
    plano = _plano_de_hoje() or {}
    atual = v2.bloco_atual(plano)
    if not atual:
        return None
    falado = _palavras(texto)
    estados = {b.get("id"): b.get("estado") for b in _registro_de_hoje().get("blocos", [])}
    pontos = lambda b: len(_palavras(b.get("titulo")) & falado)
    for b in plano.get("blocos", []):
        if b.get("id") != atual.get("id") and estados.get(b.get("id")) not in ("feito", "adiado") and pontos(b) > pontos(atual):
            return None  # ele fala de outra tarefa que não é a de agora: o Claude decide
    if pontos(atual) == 0 and len(t.split()) > 4:
        return None  # fala longa que não cita nada da tarefa de agora: pode ser outra, o Claude decide
    agora = time.strftime("%H:%M")
    d = v2._ler_exec()
    sessao = v2._sessao(d, atual.get("id"))
    inicio = sessao["trechos"][0]["de"] if sessao and sessao.get("trechos") else None
    medido = bool(inicio)
    inicio = inicio or atual["inicio"]
    if v2.h._min(agora) <= v2.h._min(inicio):
        m = max(0, v2.h._min(agora) - 1)
        inicio = f"{m // 60:02d}:{m % 60:02d}"
    r = v2.h.concluir_bloco({"id": atual["id"], "concluido": True, "nota": "", "inicio": inicio, "fim": agora, "nao_confirmado": not medido})
    if not r.get("ok"):
        return {"fala": f"Não consegui concluir {atual.get('titulo')}: {r.get('erro') or 'erro desconhecido'}."}
    v2.registrar_evento("relato", atual, texto=str(texto).strip()[:800])
    proximo = v2.bloco_atual(_plano_de_hoje() or {})
    return {"fala": f"Feito às {agora}. " + (f"A seguir: {proximo['titulo']}, às {proximo['inicio']}." if proximo else "Era a última do dia.")}


def comando_local(texto):
    """Devolve {"fala": ..., "roteiro": ...} se o pedido é um comando da tela (modo execução, abrir uma aba, silenciar...), ou None para o Claude responder."""
    feito = concluir_local(texto)
    if feito:
        return feito
    t = _limpar_comando(texto)
    if not t or len(t.split()) > 9:
        return None
    pergunta = bool(E_PERGUNTA.match(t))
    if SAIR_EXEC.search(t) and not pergunta:
        if not v2.estado_exec()["ativo"]:
            return {"fala": "O modo execução já está desligado."}
        v2.sair()
        return {"fala": "Saí do modo execução. Estou por aqui se precisar."}
    if ENTRAR_EXEC.search(t) and not pergunta:
        plano = _plano_de_hoje()
        if not plano or not plano.get("blocos"):
            return {"fala": "Ainda não há plano para hoje."}
        if plano.get("status") != "aprovado":
            return {"fala": "Aprove o plano primeiro. Depois entramos em execução."}
        b = v2.bloco_atual(plano)
        if not b:
            return {"fala": "Hoje não sobrou tarefa para executar."}
        v2.entrar()
        if v2.h._min(time.strftime("%H:%M")) < v2.h._min(b["inicio"]):
            return {"fala": f"Modo execução. A próxima é {b['titulo']}, às {b['inicio']}."}
        return {"fala": f"Modo execução. Foco em {b['titulo']}. Eu aviso antes de o tempo acabar."}
    if PROXIMAS.search(t):
        plano = _plano_de_hoje() or {}
        estados = {b.get("id"): b.get("estado") for b in _registro_de_hoje().get("blocos", [])}
        pend = sorted((b for b in plano.get("blocos", []) if estados.get(b.get("id")) not in ("feito", "adiado")), key=lambda b: v2.h._min(b["inicio"]))
        agora = v2.h._min(time.strftime("%H:%M"))
        depois = [b for b in pend[1:]] if pend and agora >= v2.h._min(pend[0]["inicio"]) else pend
        if not depois:
            return {"fala": "Não há mais nada depois desta." if pend else "Não há tarefa em aberto hoje."}
        bus.emitir("ui", cmd="lista", kind="next")
        return {"fala": f"A seguir: {depois[0]['titulo']}, às {depois[0]['inicio']}. Deixei as próximas na tela."}
    if AGENDA.search(t):
        plano = _plano_de_hoje() or {}
        blocos = plano.get("blocos", [])
        if not blocos:
            return {"fala": "Ainda não há plano para hoje."}
        feitos = sum(1 for b in _registro_de_hoje().get("blocos", []) if b.get("estado") == "feito")
        bus.emitir("ui", cmd="lista", kind="agenda")
        return {"fala": f"Aqui está o dia: {feitos} de {len(blocos)} feitas."}
    if FECHAR.search(t):
        bus.emitir("ui", cmd="fechar")
        return {"fala": "Fechado."}
    m = NAVEGAR.search(t)
    if m:
        bus.emitir("ui", cmd="tela", id=TELAS[m.group("tela")])
        return {"fala": ""}
    if DETALHES.search(t):
        bus.emitir("ui", cmd="detalhe")
        return {"fala": ""}
    if MUDO.search(t):
        salvar_preferencias({"voz_guardiao": False})
        return {"fala": "Voz silenciada. Continuo escrevendo."}
    if FALAR.search(t):
        salvar_preferencias({"voz_guardiao": True})
        return {"fala": "Voz ligada."}
    if PEDE_REPORT.search(t):
        return {"fala": "", "roteiro": "report"}
    if NOVA_CONVERSA.search(t):
        if modo_sessao():
            trocar_conversa()
        else:
            CONVERSA.clear()
            memoria_conversa.zerar()
        return {"fala": "Conversa nova. Pode falar."}
    if VER_CONVERSAS.search(t) and modo_sessao():
        bus.emitir("ui", cmd="conversas")
        return {"fala": ""}
    return None


# ---------------- report do dia por voz (roteiro de 4 perguntas fixas; as respostas vão para a calibragem) ----------------

ROTEIRO = None  # {"id": "report", "i": pergunta atual, "respostas": [...], "quando": time}
PERGUNTAS_REPORT = ["Primeira: que ajustes o seu plano precisa para amanhã?", "Em que horas você rendeu mais hoje?", "O que funcionou hoje?", "Última: o que apareceu de última hora?"]
CANCELA_ROTEIRO = re.compile(r"\b(cancela|cancelar|esquece|deixa (pra|para) la|deixa quieto|para o report|parar o report)\b")
PULA_PERGUNTA = re.compile(r"^(pula|pular|passa|nada|nenhum|nenhuma|nao sei|sem resposta|nao teve|nao houve)$")


def iniciar_roteiro(a):
    global ROTEIRO
    ROTEIRO = {"id": "report", "i": 0, "respostas": [], "quando": time.time()}
    bus.emitir("roteiro", ativo=True, id="report", passo=1, total=len(PERGUNTAS_REPORT))
    dizer("Report do dia, quatro perguntas rápidas. " + PERGUNTAS_REPORT[0], a)
    bus.emitir("estado", v="aguardando")
    return True


def tratar_roteiro(texto, a, digitado):
    """A fala da pessoa é a resposta da pergunta atual. Devolve True se o microfone deve reabrir para a próxima."""
    global ROTEIRO
    r = ROTEIRO
    t = re.sub(r"\s+", " ", _norm(texto)).strip()
    if CANCELA_ROTEIRO.search(t) and len(t.split()) <= 6:
        ROTEIRO = None
        bus.emitir("roteiro", ativo=False)
        dizer("Tudo bem, deixei o report de lado.", a)
        bus.emitir("estado", v="aguardando")
        return False
    r["respostas"].append("" if PULA_PERGUNTA.match(t) else texto.strip())
    r["i"] += 1
    r["quando"] = time.time()
    if r["i"] < len(PERGUNTAS_REPORT):
        bus.emitir("roteiro", ativo=True, id=r["id"], passo=r["i"] + 1, total=len(PERGUNTAS_REPORT))
        dizer(PERGUNTAS_REPORT[r["i"]], a)
        bus.emitir("estado", v="aguardando")
        return not digitado
    ROTEIRO = None
    bus.emitir("roteiro", ativo=False)
    res = v2.salvar_report(r["respostas"], "voz")
    if res.get("ok"):
        fala = "Report recebido. Obrigado." + (f" Você chegou ao marco dos {res['dia']} dias." if res.get("marco") else "")
    else:
        fala = res.get("erro") or "Não consegui salvar o report."
    dizer(fala, a)
    bus.emitir("estado", v="aguardando")
    return False


def ditar(q, chave, piso, campo):
    """Grava uma fala e devolve só o texto para a tela (um campo do report), sem passar pelo Claude."""
    if not abrir_para_gravar():
        bus.emitir("aviso", texto=AVISO_SEM_MIC, erro=False)
        bus.emitir("estado", v="aguardando")
        return
    time.sleep(0.3 if bipe(880, 120) else 0.15)
    drenar(q)
    bus.emitir("estado", v="ouvindo", seguimento=False)
    try:
        pcm = gravar(q, piso)
    finally:
        fechar_apos_gravar(q)
    if pcm is CANCELADO:
        bipe(440, 90)
        bus.emitir("escuta_cancelada")
    elif pcm:
        bus.emitir("estado", v="transcrevendo")
        try:
            texto, _ = transcrever(para_wav(pcm), chave)
            if texto:
                bus.emitir("ditado", campo=campo, texto=texto)
        except Exception as erro:
            bus.emitir("erro", msg=f"A transcrição falhou: {erro}")
    drenar(q)
    bus.emitir("estado", v="aguardando")


def escutar(a, q, modelo, chave, piso, seguimento=False, avisar_cancelamento=True):
    """Abre o microfone, grava até o silêncio e transcreve. Devolve (texto, tempo da transcrição, motivo): com texto vazio, o motivo diz por quê
    ("cancelado" = Esc ou clique, "silencio" = ninguém falou, "erro" = a transcrição falhou)."""
    if not abrir_para_gravar():
        bus.emitir("aviso", texto=AVISO_SEM_MIC, erro=False)
        bus.emitir("estado", v="aguardando")
        return "", None, "erro"
    if seguimento:
        time.sleep(0.35)  # o final da voz do guardião no ar não pode virar uma pergunta
    else:
        time.sleep(0.3 if bipe(880, 120) else 0.15)  # com o painel aberto o som é dele, tocado quando a escuta começa
    drenar(q)
    bus.emitir("estado", v="ouvindo", seguimento=bool(seguimento))

    ao_vivo = None
    if not a.sem_preview:
        live = KaldiRecognizer(modelo, SR)
        fechados = []
        groq_previa = None if a.previa_local else PreviaGroq(chave)

        def ao_vivo(dado, falando=True, live=live, fechados=fechados, groq_previa=groq_previa):
            if live.AcceptWaveform(dado):
                trecho = json.loads(live.Result()).get("text", "")
                if trecho:
                    fechados.append(trecho)
                parcial = ""
            else:
                parcial = json.loads(live.PartialResult()).get("partial", "")
            texto_local = " ".join(fechados + ([parcial] if parcial else []))
            texto_vivo = texto_local
            if groq_previa:
                groq_previa.alimentar(dado, falando)
                # o texto do Groq é o certo; o local é mais rápido. Mostra o mais completo.
                if groq_previa.texto and len(groq_previa.texto) >= 0.8 * len(texto_local):
                    texto_vivo = groq_previa.texto
            if texto_vivo and falando:
                print("\r  ouvindo: " + texto_vivo[-90:].ljust(90), end="", flush=True)
                bus.emitir("previa", texto=texto_vivo)
            return texto_local

    try:
        pcm = gravar(q, piso, ao_vivo)
    finally:
        fechar_apos_gravar(q)
    if ao_vivo:
        print()
    if pcm is CANCELADO:  # Esc ou clique no microfone: a escuta acaba aqui e nada é enviado
        print("  (escuta cancelada)")
        drenar(q)
        bus.emitir("previa", texto="")
        if avisar_cancelamento:
            bipe(440, 90)
            bus.emitir("escuta_cancelada")
        bus.emitir("estado", v="aguardando")
        return "", None, "cancelado"
    if not pcm:
        print("  (ninguém falou)")
        bus.emitir("previa", texto="")
        bus.emitir("estado", v="aguardando")
        return "", None, "silencio"
    bus.emitir("estado", v="transcrevendo")
    try:
        texto, stt = transcrever(para_wav(pcm), chave)
    except Exception as erro:  # rede, limite do Groq, etc.
        print("  Erro:", erro)
        bus.emitir("erro", msg=f"A transcrição falhou: {erro}")
        bus.emitir("estado", v="aguardando")
        return "", None, "erro"
    print(f"  Você disse (Groq, {stt:.1f}s): {texto}")
    segundos_de_voz = len(pcm) / (2.0 * SR)
    if texto and not fala_confiavel(texto, segundos_de_voz):
        print(f"  (descartei: uma palavra só, em {segundos_de_voz:.1f}s, parece ruído)")
        bus.emitir("previa", texto="")
        bus.emitir("estado", v="aguardando")
        return "", stt, "silencio"
    return texto, stt, "ok" if texto else "silencio"


def atender(a, q, modelo, chave, piso, texto_digitado=None, saudacao=False, seguimento=False):
    """Uma rodada: grava (ou usa o texto digitado), transcreve, pergunta ao Claude e fala.
    Devolve True quando a conversa continua e o microfone deve reabrir sem precisar dizer 'Ei guardião'."""
    stt = None
    if texto_digitado is None:
        texto, stt, motivo = escutar(a, q, modelo, chave, piso, seguimento)
        if motivo != "ok" and not texto:
            if motivo == "silencio":
                bus.emitir("estado", v="aguardando")
            return False
    else:
        texto = texto_digitado
        print(f"  Você escreveu: {texto}")

    if not texto:
        bus.emitir("estado", v="aguardando")
        return False
    if not saudacao:
        bus.emitir("voce", texto=texto)

    if not a.cerebro:
        bus.emitir("guardiao_fim", texto="Estou só transcrevendo. Abra o guardião completo para eu responder.")
        bus.emitir("estado", v="aguardando")
        return False

    global PROPOSTA, ROTEIRO
    if ROTEIRO and time.time() - ROTEIRO["quando"] > 900:  # report esquecido pela metade: sai sozinho depois de 15 minutos
        ROTEIRO = None
        bus.emitir("roteiro", ativo=False)
    if ROTEIRO and not saudacao:
        seguir = tratar_roteiro(texto, a, texto_digitado is not None)
        drenar(q)
        return seguir
    decisao = None if saudacao else resolver_proposta(texto)  # há algo esperando o sim da pessoa?
    if decisao == "outro":  # ele respondeu outra coisa (um ajuste, por exemplo): a proposta cai e a conversa segue normal
        PROPOSTA = None
        bus.emitir("proposta_fim", resultado="cancelada")
        decisao = None
    if decisao:
        proposta = PROPOSTA
        dados = proposta["dados"]
        aprovar = proposta.get("tipo") == "aprovar"
        PROPOSTA = None
        try:
            if decisao == "sim":
                bus.emitir("proposta_fim", resultado="confirmada")
                if aprovar:
                    dizer("Aprovando o plano.", a)
                    encerrar_revisao()
                    resposta = resposta_pos_aprovacao(agir("aprovar"))
                else:
                    dizer("Criando a tarefa.", a)
                    r = agir("criar", dados=dados)
                    resposta = (f"Pronto, criei a tarefa na lista {r.get('lista') or dados.get('lista')}." if r.get("ok")
                                else f"Não consegui criar a tarefa. {r.get('erro') or ''}")
            else:
                bus.emitir("proposta_fim", resultado="cancelada")
                resposta = "Tudo bem, não aprovei. O que você quer ajustar?" if aprovar else "Tudo bem, cancelei."
            dizer(resposta, a)
            lembrar(texto, resposta)
        except Exception as erro:
            print("  Erro:", erro)
            bus.emitir("erro", msg=f"Não consegui concluir: {erro}")
        bus.emitir("foco_fim")
        drenar(q)
        bus.emitir("estado", v="aguardando")
        return bool(aprovar and decisao == "nao")  # recusou a aprovação: quer ajustar, então o microfone reabre

    local = None if saudacao or revisao_ativa() else comando_local(texto)  # comando da tela: resolve aqui, sem o Claude
    if local is not None:
        if local.get("roteiro"):
            seguir = iniciar_roteiro(a)
            drenar(q)
            return seguir and texto_digitado is None
        if local.get("fala"):
            dizer(local["fala"], a)
            lembrar(texto, local["fala"])
        bus.emitir("foco_fim")
        drenar(q)
        bus.emitir("estado", v="aguardando")
        return False

    bus.emitir("estado", v="pensando")
    falado = ""
    sem_conta = False
    if saudacao:
        marcar_saudacao()
    na_sessao = modo_sessao() and not saudacao  # a saudação continua no modo rápido: é curta e não precisa de memória
    llm, motivo_llm = escolher_modelo("" if saudacao else texto, saudacao)
    print("  (sessão do Claude Code)" if na_sessao else f"  (modelo: {llm}, {motivo_llm})")

    def pedir(pedido):
        return pedir_permissao(a, q, modelo, chave, piso, pedido, texto_digitado is None)
    plano_antes = ler_plano() if na_sessao else None
    try:
        if a.voz == "kokoro":
            primeira, total, falado = responder_falando(texto, a.voz_kokoro, "" if saudacao else texto, acoes=not saudacao,
                                                        portao=bus.portao_saudacao if saudacao else None, modelo=llm, motivo=motivo_llm,
                                                        fonte=(lambda: frases_da_sessao(texto)) if na_sessao else None, pedir=pedir if na_sessao else None,
                                                        limite_primeira=LIMITE_SAUDACAO if saudacao else None,
                                                        modo="saudacao" if saudacao else "sessao" if na_sessao else "rapido")
            print(f"  (voz começou em {primeira:.1f}s, resposta completa em {total:.1f}s)")
        else:
            if na_sessao:
                t0, partes = time.time(), []
                for frase in frases_da_sessao(texto):
                    if isinstance(frase, str):
                        partes.append(frase)
                    else:
                        guardiao_sessao.decidir(frase[1], *pedir(frase[1]))
                resposta, seg2 = " ".join(partes), time.time() - t0
            else:
                resposta, seg2 = perguntar_claude(texto, llm)
            falado, diretivas = extrair_diretivas(resposta)
            print(f"  Guardião (Claude, {seg2:.1f}s): {falado}")
            if saudacao:
                bus.portao_saudacao.wait(timeout=15)
            executar_diretivas(diretivas, "" if saudacao else texto, not saudacao)
            bus.emitir("estado", v="falando")
            bus.emitir("guardiao_texto", texto=falado)
            falar(falado, a.voz, a.voz_nome)
            bus.emitir("guardiao_fim", texto=falado)
            bus.emitir("foco_fim")
            primeira = total = seg2
        lembrar(_p("(<o Fulano> abriu o app)") if saudacao else texto, falado, na_sessao=na_sessao)
        if na_sessao:  # a sessão pode ter gravado o plano de hoje: confere, devolve para aprovação e avisa a tela
            conferido = conferir_plano(plano_antes)
            if conferido == "mudou":
                bus.emitir("plano")
            elif conferido == "defeito":
                bus.emitir("aviso", texto="O plano gravado saiu com defeito e eu desfiz a mudança.", erro=True)
                FORA_DA_SESSAO.append(("(aviso do painel)", "O arquivo do plano de hoje que você gravou estava com defeito e foi desfeito. Refaça se ainda for preciso."))
        if na_sessao and falado:  # guarda a troca para a conversa poder ser reaberta na tela
            conversa = guardiao_sessao.atual(criar=False)
            if conversa:
                guardiao_sessao.anotar(conversa["id"], "u", texto)
                guardiao_sessao.anotar(conversa["id"], "g", falado)
                guardiao_sessao.avisar_tela()
        if saudacao:
            registrar_saudacao(falado)
        bus.emitir("metricas", stt=stt, primeira=primeira, total=total)
    except Exception as erro:
        print("  Erro:", erro)
        conta = isinstance(erro, (guardiao_sessao.ErroDeConta, FileNotFoundError))  # sem Claude Code, sem login, no limite de uso...
        if conta:
            sem_conta = True
        elif not isinstance(erro, TimeoutError):  # demorar demais na saudação não é erro para mostrar: ela só vira a frase local
            bus.emitir("erro", msg=f"Não consegui responder: {erro}")
        falado = ""
        if saudacao:  # a abertura nunca fica muda nem fala tarde: o cumprimento local entra no lugar (e, se o problema é a conta, já avisa)
            falado = saudacao_local() + (f" {erro}" if conta else "")
            dizer(falado, a)
            registrar_saudacao(falado)
        elif conta:
            dizer(str(erro), a)  # escreve na conversa e fala: o motivo e o que fazer, sem depender do Claude
    drenar(q)
    guardar = []
    while not bus.comandos.empty():  # cliques e perguntas acumulados durante a resposta não disparam de novo
        try:
            c = bus.comandos.get_nowait()
            if c[0] in ("checkin", "dizer", "roteiro", "completo", "completo_fim", "conversa", "sessao_fala"):  # aviso de tempo e fala pendente não podem se perder
                guardar.append(c)
        except queue.Empty:
            break
    for c in guardar:
        bus.comandos.put(c)
    corrigiu = falar_correcoes(a)  # ação por voz que falhou ou foi recusada: diz isso, em vez de deixar valer o "estou concluindo" já falado
    if corrigiu:
        falado = (falado + " " + corrigiu).strip()
    tocar_revisao()
    # o microfone reabre quando ele precisa responder: depois da saudação, durante a revisão do plano,
    # com algo esperando o sim, ou quando o guardião terminou a fala com uma pergunta
    seguir = bool(falado) and not sem_conta and not controle_fala.PARAR.is_set() and (texto_digitado is None or saudacao) and (
        saudacao or revisao_ativa() or PROPOSTA is not None or falado.rstrip().endswith("?"))
    bus.emitir("estado", v="aguardando")
    return seguir


def continuar(a, q, modelo, chave, piso, seguir):
    """Enquanto o guardião espera resposta, novas rodadas com o microfone aberto (no máximo 12 seguidas)."""
    n = 0
    while seguir and n < 12 and not getattr(a, "sem_escuta_aberta", False) and preferencias().get("escuta_aberta", True) and escuta_continua():
        n += 1
        seguir = atender(a, q, modelo, chave, piso, seguimento=True)


def conversar(a, q, modelo, chave, piso, **kw):
    """Uma rodada e, enquanto o guardião espera resposta, as seguintes com o microfone aberto."""
    continuar(a, q, modelo, chave, piso, atender(a, q, modelo, chave, piso, **kw))


def main():
    global ACOES_ATIVAS, MODELO_PADRAO, MODELO_LEVE, PROMPT_ESTAVEL
    ap = argparse.ArgumentParser(description="Guardião por voz (MVP de teste)")
    ap.add_argument("--cerebro", action="store_true", help="pergunta ao Claude e fala a resposta")
    ap.add_argument("--mic", type=int, help="número do microfone (veja --dispositivos)")
    ap.add_argument("--dispositivos", action="store_true", help="lista os microfones e sai")
    ap.add_argument("--debug", action="store_true", help="mostra o que o reconhecedor local está ouvindo")
    ap.add_argument("--autoteste", action="store_true", help="testa a cadeia com a voz do Windows, sem microfone")
    ap.add_argument("--voz", choices=["kokoro", "edge", "windows"], default="kokoro", help="motor da voz (padrão: Kokoro, local)")
    ap.add_argument("--voz-kokoro", default=VOZ_KOKORO, help="voz do Kokoro (pm_santa, pm_alex, pf_dora)")
    ap.add_argument("--voz-nome", default=VOZ_EDGE, help="voz neural do Edge (ex.: pt-BR-ThalitaNeural)")
    ap.add_argument("--sem-preview", action="store_true", help="não mostra o texto aparecendo enquanto você fala")
    ap.add_argument("--previa-local", action="store_true", help="prévia só com o reconhecedor local (sem gastar pedidos do Groq)")
    ap.add_argument("--sem-tela", action="store_true", help="não liga a tela (http://localhost:8767)")
    ap.add_argument("--sem-janela", action="store_true", help="liga a tela, mas não abre a janela sozinho")
    ap.add_argument("--sem-acoes", action="store_true", help="o guardião só destaca tarefas na tela, sem concluir, anotar ou criar nada")
    ap.add_argument("--sem-saudacao", action="store_true", help="não faz a saudação de boas-vindas quando a tela abre")
    ap.add_argument("--sem-escuta-aberta", action="store_true", help="depois de uma pergunta do guardião, o microfone não reabre sozinho")
    ap.add_argument("--modelo", help=f"modelo do Claude para planejar, revisar, escrever e agir (padrão: {MODELO_PADRAO})")
    ap.add_argument("--modelo-leve", help=f"modelo para consulta curta e de leitura (padrão: {MODELO_LEVE}); 'nenhum' usa sempre o modelo padrão")
    ap.add_argument("--prompt-estavel", action="store_true", help="prompt de sistema fixo e o que muda vai junto da pergunta (aproveita o cache do Claude)")
    ap.add_argument("--prompt-antigo", action="store_true", help="volta ao prompt de sistema com o relógio no começo (sem aproveitar o cache)")
    ap.add_argument("--vigia", action="store_true", help="usado pela tarefa agendada: se o guardião já estiver ligado, sai em silêncio")
    ap.add_argument("--v2", action="store_true", help="sem efeito, mantido para atalhos antigos: o painel aberto é sempre o de http://localhost:8767/v2/")
    a = ap.parse_args()

    if a.vigia and porta_em_uso(PORTA_TELA):
        return
    if a.voz_kokoro == VOZ_KOKORO:  # sem escolha na linha de comando, vale a voz escolhida no onboarding
        a.voz_kokoro = voz_configurada()
    if a.cerebro:
        memoria_conversa.vigiar(_chamar_resumo, lambda: pessoa()["primeiro"])  # o resumo do dia é atualizado quando a pessoa fica uns minutos sem falar
        estado = guardiao_sessao.estado_do_claude()
        if estado["ok"]:
            print(f"Claude Code: {estado['versao']} ({estado['de']})")
        else:
            print("Não achei um Claude Code que execute. O painel abre, mas o guardião não responde até ele ser instalado: https://claude.com/claude-code")
            if estado["erro"]:
                print("  tentativas:", estado["erro"])
    ACOES_ATIVAS = not a.sem_acoes
    if a.prompt_estavel:
        PROMPT_ESTAVEL = True
    if a.prompt_antigo:
        PROMPT_ESTAVEL = False
    if a.modelo:
        MODELO_PADRAO = a.modelo
    if a.modelo_leve:
        MODELO_LEVE = "" if a.modelo_leve.lower() in ("nenhum", "igual", "off") else a.modelo_leve
    if a.cerebro:
        print(f"Modelos do Claude: padrão {MODELO_PADRAO}; leve {MODELO_LEVE if modelo_leve_ligado() else '(desligado)'}; prompt {'estável (cache)' if PROMPT_ESTAVEL else 'antigo'}")

    if a.dispositivos:
        print(sd.query_devices())
        return

    SetLogLevel(-1)
    modelo = nativo.carregar_escuta(BASE)
    chave = chave_groq()

    if a.autoteste:
        autoteste(modelo, chave, a.cerebro)
        return

    if not chave:  # sem a chave o painel abre do mesmo jeito: a conversa é por texto e o microfone fica desligado
        print("Sem a chave do Groq: microfone desligado, conversa só por texto. Para ligar: dois cliques em definir_chave_groq.bat; o microfone liga sozinho em até um minuto.")

    if not a.sem_tela:
        servidor = iniciar_servidor(PORTA_TELA)
        url = f"http://localhost:{PORTA_TELA}/"
        if not servidor:
            print(f"A porta {PORTA_TELA} já está em uso: deve haver outro guardião aberto.")
            print("Feche a janela do outro guardião (ou o Python dele no Gerenciador de Tarefas) e rode de novo.")
            return
        print("Tela do guardião:", url)
        threading.Thread(target=vigiar_avisos, daemon=True).start()

    voz_ok = a.voz
    if a.cerebro and a.voz == "kokoro":
        print("Carregando a voz do guardião...")
        try:
            carregar_kokoro()
        except Exception as erro:
            print("  (Kokoro não carregou, vou usar a voz do Edge:", erro, ")")
            a.voz = "edge"
            voz_ok = "edge"

    if not a.sem_tela and not a.sem_janela:
        abrir_tela(url + "v2/")

    q = queue.Queue()
    piso = 120.0
    escuta_aberta_original = bool(getattr(a, "sem_escuta_aberta", False))
    global MIC
    mic = MIC = Microfone(a, q)
    continuo = escuta_continua()
    if continuo:  # escuta contínua (opção): o microfone abre já e fica esperando "Ei guardião"
        mic.tentar(chave)
    # no padrão o microfone só abre durante uma gravação por botão; "pronto" = tem chave e aparelho
    sem_mic = (mic.stream is None) if continuo else not (chave and mic.existe())
    if sem_mic:
        a.sem_escuta_aberta = True  # sem microfone, ninguém fica esperando uma resposta falada
    try:
        modo = "com o cérebro (Claude)" if a.cerebro else "só transcrevendo"
        print(f"Pronto, {modo}. " + ("Microfone desligado: escreva no painel." if sem_mic else "Diga 'Ei guardião', espere o bipe e fale." if continuo else "Microfone fechado: ele só liga quando você clica no botão do microfone.") + " Ctrl+C para sair.")
        saude = {"mic": not sem_mic, "groq": bool(chave), "claude": bool(a.cerebro and achar_claude()), "voz": voz_ok}
        bus.emitir("saude", **saude)
        revisar_em = mic_em = claude_em = time.time() + 5
        bus.emitir("estado", v="aguardando")
        atexit.register(guardiao_sessao.encerrar)  # o Claude Code da sessão fecha junto com o guardião
        if a.cerebro and modo_sessao():  # abre a sessão do Claude Code já, para a primeira fala não esperar a partida
            threading.Thread(target=lambda: guardiao_sessao.preparar(arquivo_prompt_sessao()), daemon=True).start()
        rec = reconhecedor(modelo)
        sessao_ligada, olhar_em = modo_sessao(), 0.0
        while True:
            try:
                dado = q.get(timeout=0.2)
            except queue.Empty:
                dado = None
            if time.time() > revisar_em:  # o que pode mudar com o guardião aberto: a chave gravada depois, o fone ligado depois, o Claude Code instalado depois
                revisar_em = time.time() + 5
                if not chave:
                    chave = chave_groq()
                continuo = escuta_continua()  # a pessoa muda isso nas preferências com o guardião aberto
                if not continuo and mic.stream is not None:
                    mic.parar()  # escuta contínua desligada: o microfone fecha agora
                    drenar(q)
                    print("Escuta contínua desligada. Microfone fechado.")
                if continuo and chave and mic.stream is None and time.time() > mic_em:
                    mic_em = time.time() + 30
                    if mic.tentar(chave):
                        a.sem_escuta_aberta = escuta_aberta_original
                        print("Microfone ligado. Diga 'Ei guardião', espere o bipe e fale.")
                if not continuo:
                    a.sem_escuta_aberta = not (chave and mic.existe())
                if a.cerebro and not achar_claude() and time.time() > claude_em:
                    claude_em = time.time() + 30
                    threading.Thread(target=lambda: achar_claude(refazer=True), daemon=True).start()  # a conferência executa o Claude: fora do laço do áudio
                agora_saude = {"mic": (mic.stream is not None) if continuo else bool(chave and mic.existe()), "groq": bool(chave), "claude": bool(a.cerebro and achar_claude()), "voz": voz_ok}
                if agora_saude != saude:
                    saude = agora_saude
                    bus.emitir("saude", **saude)
            if a.cerebro and time.time() > olhar_em:  # a pessoa ligou o modo sessão nas preferências: o Claude Code já começa a abrir
                olhar_em = time.time() + 5
                ligada = modo_sessao()
                if ligada and not sessao_ligada:
                    threading.Thread(target=lambda: guardiao_sessao.preparar(arquivo_prompt_sessao()), daemon=True).start()
                sessao_ligada = ligada

            comando = None
            try:
                comando = bus.comandos.get_nowait()
            except queue.Empty:
                pass
            if PROPOSTA and time.time() - PROPOSTA["quando"] > VALIDADE_PROPOSTA:
                resolver_proposta("")  # descarta a proposta velha e avisa a tela
            if comando:
                tipo, valor = comando
                if tipo == "saudacao":
                    if a.cerebro and not a.sem_saudacao and pode_saudar(valor):
                        conversar(a, q, modelo, chave, piso, texto_digitado=pedido_saudacao(), saudacao=True)
                    else:
                        bus.portao_saudacao.set()
                elif tipo == "checkin":  # aviso de tempo do modo execução: fala a pergunta e abre o microfone para a resposta
                    if a.cerebro:
                        fala = str((valor or {}).get("texto") or "")
                        dizer(fala, a)
                        lembrar("(aviso de tempo da tarefa em execução)", fala)
                        drenar(q)
                        bus.emitir("estado", v="aguardando")
                        continuar(a, q, modelo, chave, piso, bool(v2.CHECKIN))
                elif tipo == "dizer":  # frase fixa pedida pela tela (resposta aos botões do aviso de tempo)
                    if a.cerebro and valor:
                        dizer(str(valor), a)
                        lembrar("(resposta pelos botões da tela)", str(valor))
                        drenar(q)
                        bus.emitir("estado", v="aguardando")
                elif tipo == "roteiro":
                    if a.cerebro:
                        continuar(a, q, modelo, chave, piso, iniciar_roteiro(a))
                elif tipo == "completo":  # pedido ao guardião completo feito pela tela (botão Montar o dia)
                    if a.cerebro:
                        fala = ("Vou montar isso com calma e te aviso quando terminar." if iniciar_completo(str(valor))
                                else "Ainda estou montando o pedido anterior. Te aviso quando terminar.")
                        dizer(fala, a)
                        lembrar(str(valor), fala)
                        drenar(q)
                        bus.emitir("estado", v="aguardando")
                elif tipo == "completo_fim":  # o guardião completo terminou: ele conta o resultado e, se perguntou algo, o microfone abre
                    if a.cerebro:
                        fala = str((valor or {}).get("fala") or "")
                        dizer(fala, a)
                        lembrar(f"(resultado do guardião completo para o pedido: {(valor or {}).get('pedido')})", fala)
                        drenar(q)
                        bus.emitir("estado", v="aguardando")
                        continuar(a, q, modelo, chave, piso, fala.rstrip().endswith("?"))
                elif tipo in ("ditar", "acionar") and not (mic.stream is not None or (chave and mic.existe())):  # botão do microfone sem microfone: explica, em vez de ficar esperando uma fala
                    bus.emitir("aviso", texto=AVISO_SEM_MIC if chave else AVISO_SEM_CHAVE, erro=False)
                    bus.emitir("estado", v="aguardando")
                elif tipo == "ditar":
                    ditar(q, chave, piso, valor)
                elif tipo == "conversa":  # a tela pediu uma conversa nova ou voltou a uma anterior
                    trocar_conversa((valor or {}).get("id") if (valor or {}).get("acao") == "abrir" else None)
                    bus.emitir("estado", v="aguardando")
                elif tipo == "sessao_fala":  # a sessão falou sozinha (um agente terminou o que fazia em segundo plano)
                    if a.cerebro and (valor or {}).get("texto"):
                        fala = extrair_diretivas(str(valor["texto"]))[0]
                        dizer(fala, a)
                        guardiao_sessao.anotar(str(valor.get("conversa")), "g", fala)
                        drenar(q)
                        bus.emitir("estado", v="aguardando")
                        continuar(a, q, modelo, chave, piso, fala.rstrip().endswith("?"))
                elif tipo == "permissao":
                    pass  # clique atrasado num pedido de permissão que já foi resolvido
                else:
                    conversar(a, q, modelo, chave, piso, texto_digitado=valor if tipo == "perguntar" else None)
                rec = reconhecedor(modelo)
                print("Aguardando 'Ei guardião'...")
                continue
            if dado is None or not continuo:  # sem a escuta contínua nada é analisado fora de uma gravação por botão
                continue

            rms = rms_de(dado)
            bus.emitir("nivel", mic=nivel_mic(rms))
            ativou = False
            if rec.AcceptWaveform(dado):
                resultado = json.loads(rec.Result())
                if a.debug and resultado.get("text"):
                    print("   (ouvi:", resultado["text"], ")")
                ativou = chamou(resultado)
            elif a.debug:
                parcial = json.loads(rec.PartialResult()).get("partial", "")
                if parcial:
                    print("   (ouvindo:", parcial, ")", end="\r")
            if not ativou and rms < piso * 2:
                piso = 0.99 * piso + 0.01 * rms
            if not ativou:
                continue

            if a.cerebro and modo_sessao():  # a pessoa leva alguns segundos para falar: a sessão do Claude Code já abre (ou segue aberta, sem custo)
                threading.Thread(target=lambda: guardiao_sessao.preparar(arquivo_prompt_sessao()), daemon=True).start()
            conversar(a, q, modelo, chave, piso)
            rec = reconhecedor(modelo)
            print("Aguardando 'Ei guardião'...")
    finally:
        mic.parar()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEncerrado.")
