"""Escuta do microfone, sem microfone: a gravação não corta fala longa, espera a pausa de quem pensa, ignora estalo,
cancela com Esc ou clique, e as frases que o Whisper inventa no silêncio não chegam à tela. Sem Groq e sem Claude."""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import guardiao_voz as g  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe != "" and not ok else ""))


class Relogio:
    """O tempo anda 0,1 s a cada bloco de áudio entregue, como no microfone de verdade."""

    def __init__(self):
        self.t = 1000.0

    def __getattr__(self, nome):
        return getattr(time, nome)

    def time(self):
        return self.t


def bloco(volume):
    return struct.pack("<" + "h" * g.BLOCO, *([volume, -volume] * (g.BLOCO // 2)))


VOZ, SILENCIO, BAIXO = bloco(2000), bloco(20), bloco(200)


class Fila:
    def __init__(self, relogio, roteiro, ao_entregar=None):
        self.relogio, self.itens, self.n, self.ao_entregar = relogio, list(roteiro), 0, ao_entregar

    def get(self, timeout=None):  # o microfone de mentira nunca atrasa: entrega um bloco a cada chamada
        self.relogio.t += 0.1
        self.n += 1
        if self.ao_entregar:
            self.ao_entregar(self.n)
        return self.itens.pop(0) if self.itens else SILENCIO


def gravar(roteiro, ao_bloco=None, ao_entregar=None):
    relogio = Relogio()
    g.time = relogio
    fila = Fila(relogio, roteiro, ao_entregar)
    g.esc_apertado = lambda: False
    audio = g.gravar(fila, 80.0, ao_bloco)
    return audio, fila.n


def segundos(audio):
    return len(audio) / 2 / g.SR


g.bus.emitir = lambda *a, **k: None

# ---- fala longa não é mais cortada ----
audio, n = gravar([SILENCIO] * 5 + [VOZ] * 300)  # 30 s falando sem parar
confere("30 s de fala seguida são gravados inteiros (antes o teto era de 14 s)", audio is not g.CANCELADO and audio and 29.5 <= segundos(audio) <= 31.5, audio and segundos(audio))

audio, n = gravar([VOZ] * 60 + [SILENCIO] * 20 + [VOZ] * 80)  # 6 s, pausa de 2 s para pensar, mais 8 s
confere("pausa de 2 s no meio de uma fala longa não encerra a escuta (antes encerrava com 1 s)", audio and segundos(audio) >= 15.5, audio and segundos(audio))

audio, n = gravar([VOZ] * 60 + [SILENCIO] * 40)
confere("depois de uma fala longa, a escuta encerra com cerca de 2,4 s de silêncio", audio and 83 <= n <= 87, n)
confere("o silêncio das pontas não vai para a transcrição", audio and 5.9 <= segundos(audio) <= 6.6, audio and segundos(audio))

audio, n = gravar([SILENCIO] * 3 + [VOZ] * 6 + [SILENCIO] * 30)  # um "sim"
confere("resposta curta encerra rápido, com cerca de 1,2 s de silêncio", audio and 20 <= n <= 23, n)

audio, n = gravar([VOZ] * 40 + [BAIXO] * 30 + [VOZ] * 30)  # trecho falado baixo no meio
confere("trecho falado mais baixo ainda conta como voz", audio and segundos(audio) >= 9.5, audio and segundos(audio))

# o texto ao vivo andando segura a escuta mesmo com o volume baixo
textos = iter(["oi"] * 30 + [f"oi palavra {i}" for i in range(60)] + ["fim"] * 200)
audio, n = gravar([VOZ] * 30 + [bloco(130)] * 60 + [SILENCIO] * 60, ao_bloco=lambda dado, falando: next(textos))
confere("enquanto o texto ao vivo muda, a pessoa ainda está falando", audio and n >= 110, n)

# ---- ninguém falou ----
audio, n = gravar([SILENCIO] * 200)
confere("sem ninguém falar, desiste em 7 s e não devolve áudio", audio is None and 70 <= n <= 72, (audio, n))
audio, n = gravar([SILENCIO] * 10 + [VOZ] + [SILENCIO] * 20 + [VOZ] * 2 + [SILENCIO] * 200)
confere("estalo ou tecla (menos de 0,3 s de som) não conta como fala", audio is None, n)

# ---- cancelar ----
audio, n = gravar([VOZ] * 300, ao_entregar=lambda i: g.bus.cancelar_escuta.set() if i == 25 else None)
confere("clique no microfone durante a escuta cancela na hora", audio is g.CANCELADO and n == 25, n)
relogio = Relogio()
g.time = relogio
fila = Fila(relogio, [VOZ] * 300)
g.esc_apertado = lambda: fila.n >= 12
confere("Esc durante a escuta cancela na hora", g.gravar(fila, 80.0) is g.CANCELADO and fila.n == 12, fila.n)
g.bus.cancelar_escuta.set()
audio, n = gravar([VOZ] * 10 + [SILENCIO] * 30)
confere("um pedido de cancelar antigo não derruba a escuta seguinte", audio is not g.CANCELADO and audio, audio)

# ---- bipe do Windows: só para quem está sem o painel ----
bipes = []
g.winsound.Beep = lambda f, ms: bipes.append(f)
g.bus.assinantes.clear()
confere("sem painel aberto, o bipe do Windows avisa a hora de falar", g.bipe(880, 120) is True and bipes == [880], bipes)
painel = g.bus.assinar()
confere("com o painel aberto, nada de bipe do Windows: o som é o do painel", g.bipe(880, 120) is False and g.bipe(440, 90) is False and bipes == [880], bipes)
g.bus.sair(painel)

# ---- frases inventadas pelo Whisper ----
for frase in ["Legenda por Sônia Ruberti", "Legendas pela comunidade Amara.org", "Legenda Adriana Zanotto".replace("Legenda ", "Legenda por "), "Legendado por Fulano de Tal",
              "Obrigado por assistir!", "Transcrição e Legendas pela comunidade Amara.org", "♪♪", "Tradução e legendas por Maria Silva", "  ", "",
              "[Música]", "(Aplausos)", "Se inscreva no canal e ative o sininho!", "Até a próxima!", "Obrigado por ter assistido.", "Até o próximo vídeo!"]:
    confere(f"frase inventada some: '{frase}'", g.limpar_alucinacao(frase) == "", g.limpar_alucinacao(frase))
for frase in ["Coloca a legenda por cima do vídeo e me avisa.", "Revisa as pendências de sábado e domingo.", "Obrigado, pode aprovar.", "Sim.",
              "A legenda de hoje ficou boa?", "Preciso da tradução do contrato da Marina até sexta.",
              "Toca uma música para mim.", "Até a próxima reunião, move isso para sexta.", "Se inscreva na lista de espera do curso hoje."]:
    confere(f"fala de verdade fica igual: '{frase}'", g.limpar_alucinacao(frase) == frase, g.limpar_alucinacao(frase))
confere("frase inventada no fim de uma fala de verdade é cortada", g.limpar_alucinacao("Move a reunião para as três. Legendas pela comunidade Amara.org") == "Move a reunião para as três",
        g.limpar_alucinacao("Move a reunião para as três. Legendas pela comunidade Amara.org"))

# ---- a prévia não manda silêncio para o Groq ----
enviados = []
g.transcrever = lambda wav, chave: (enviados.append(len(wav)) or "texto", 0.1)
g.time = time
previa = g.PreviaGroq("chave")
for _ in range(80):
    previa.alimentar(SILENCIO, False)
confere("antes da fala começar, a prévia não envia nada e guarda só um resto curto de áudio", not enviados and len(previa.blocos) <= 6, (enviados, len(previa.blocos)))
previa.alimentar(VOZ, True)
previa.ultimo = time.time() - 10
for _ in range(30):
    previa.alimentar(VOZ, True)
time.sleep(0.3)
confere("com a fala em andamento, a prévia volta a enviar", len(enviados) >= 1, enviados)

# ---- ruído transcrito como palavra (o "Mãe." do relatório da instalação)
confere("'Mãe.' dita em 0,6 s é ruído", not g.fala_confiavel("Mãe.", 0.6))
confere("'Obrigado.' dito em 0,9 s (o que o Whisper inventa no silêncio) é ruído", not g.fala_confiavel("Obrigado.", 0.9))
confere("palavra de até 3 letras fora da lista é ruído ('Ah', 'Né')", not g.fala_confiavel("Ah.", 0.5) and not g.fala_confiavel("Né?", 0.7))
confere("'Sim.', 'Não.', 'Ok.' e 'Pare.' valem", all(g.fala_confiavel(x, 0.6) for x in ("Sim.", "Não.", "Ok.", "Pare.", "Oi.")))
confere("comando de uma palavra só vale ('Plano.', 'Hoje?', 'Pendências.')", all(g.fala_confiavel(x, 0.8) for x in ("Plano.", "Hoje?", "Pendências.")))
confere("duas palavras ou mais valem sempre, mesmo curtas ('Obrigado, valeu')", g.fala_confiavel("Obrigado, valeu", 0.9) and g.fala_confiavel("Nova conversa", 0.8))
confere("uma palavra falada devagar (mais de 1,5 s) vale: a pessoa quis dizer", g.fala_confiavel("Mãe.", 2.0))
confere("uma palavra longa e desconhecida vale (nome de pessoa, de tarefa)", g.fala_confiavel("Marina.", 0.9))

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
