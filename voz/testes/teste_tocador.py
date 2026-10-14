"""O tocador da voz (tocador.py, 0.9): muda a velocidade sem mudar o tom, toca numa saída só da placa de som de verdade (com silêncio, para não
fazer barulho), diz a posição no áudio original mesmo depois de trocar a velocidade e para quando mandam."""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import tocador  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


TAXA = 24000


def tom(segundos, freq=200.0):
    t = np.arange(int(TAXA * segundos)) / TAXA
    return (0.3 * np.sin(2 * np.pi * freq * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)


def freq_dominante(x):
    esp = np.abs(np.fft.rfft(x[:TAXA * 4]))
    return np.argmax(esp) * TAXA / (2 * (len(esp) - 1))


# ---------------- esticar: duração muda, tom não ----------------
x = tom(20)
for fator in (1.5, 2.0):
    t0 = time.time()
    y = tocador.esticar(x, fator, TAXA)
    gasto = time.time() - t0
    confere(f"{fator}x: a duração cai para 1/{fator} ({len(y) / TAXA:.2f} s de 20 s)", abs(len(y) / TAXA - 20 / fator) < 0.1, len(y) / TAXA)
    confere(f"{fator}x: o tom continua o mesmo (sem voz de esquilo)", abs(freq_dominante(y) - 200) < 3, freq_dominante(y))
    confere(f"{fator}x: rápido o bastante para trocar no meio da fala (menos de 1 s para 20 s de áudio)", gasto < 1.0, gasto)
confere("1x devolve o mesmo áudio", np.array_equal(tocador.esticar(x[:1000], 1.0, TAXA), x[:1000]))
confere("áudio vazio ou curtíssimo não quebra", len(tocador.esticar(np.zeros(0), 2.0, TAXA)) == 0 and len(tocador.esticar(np.zeros(100), 2.0, TAXA)) == 50)
confere("as velocidades oferecidas são 1, 1,5 e 2", tocador.VELOCIDADES == (1.0, 1.5, 2.0))

# ---------------- tocar de verdade (silêncio): posição, troca de velocidade e parada ----------------
try:
    import sounddevice as sd
    sd.query_devices(kind="output")
    tem_saida = True
except Exception as erro:
    tem_saida = False
    print("  (sem saída de som neste computador: a parte de tocar foi pulada:", erro, ")")

if tem_saida:
    silencio = np.zeros(TAXA * 3, dtype=np.float32)  # 3 s
    t = tocador.Tocador(silencio, TAXA)
    t.iniciar()
    time.sleep(1.0)
    p1 = t.posicao() / TAXA
    confere("tocando: a posição anda no ritmo do relógio (cerca de 1 s depois de 1 s)", 0.6 < p1 < 1.4, p1)
    t.mudar_velocidade(2.0)
    time.sleep(0.5)
    p2 = t.posicao() / TAXA
    confere("depois de trocar para 2x, meio segundo vale cerca de 1 s do áudio original", 1.5 < p2 < 2.4, p2)
    acabou = t.esperar(3.0)
    confere("e termina antes do tempo normal (3 s em 1x)", acabou and t.posicao() == len(silencio), t.posicao())
    t = tocador.Tocador(silencio, TAXA)
    t.iniciar()
    time.sleep(0.3)
    inicio = time.time()
    t.parar()
    confere("parar corta na hora", t.fim.is_set() and time.time() - inicio < 0.5)
    t = tocador.Tocador(silencio[:TAXA // 2], TAXA, fator=1.5)
    t.iniciar()
    confere("nascer já acelerado (o áudio inteiro esticado antes de tocar) também toca até o fim", t.esperar(2.0) and t.posicao() == TAXA // 2, t.posicao())

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
