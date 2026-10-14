# Toca a fala do guardião de uma vez só, sem buraco entre as frases, e muda a velocidade no meio sem mudar o tom da voz.
#
# Por que tocar de uma vez: com o computador ocupado, gerar a próxima frase enquanto a anterior toca deixava a fala picotada
# (pedido de 14/10/2026: a voz só sai com o áudio da resposta inteira pronto).
# Velocidade: a voz já nasce na velocidade escolhida (o Kokoro gera mais rápido sem mudar o tom). Se a pessoa troca a velocidade
# no meio da fala, o que falta tocar é esticado ou encolhido aqui (WSOLA: pedaços curtos sobrepostos, alinhados pela semelhança),
# também sem voz de esquilo.
import threading

import numpy as np

try:
    import sounddevice as sd
except Exception:  # testes sem placa de som
    sd = None

VELOCIDADES = (1.0, 1.5, 2.0)


def esticar(x, fator, taxa=24000):
    """Muda a duração do áudio sem mudar o tom. fator > 1 acelera (1.5 = 50% mais rápido); fator < 1 desacelera."""
    x = np.asarray(x, dtype=np.float32)
    if abs(fator - 1.0) < 0.01 or len(x) == 0:
        return x.copy()
    n = max(256, int(0.040 * taxa))      # janela de 40 ms
    hs = n // 2                           # passo de saída
    ha = hs * fator                       # passo de entrada
    tol = max(16, int(0.010 * taxa))      # procura do melhor encaixe: 10 ms para cada lado
    if len(x) < n + 2 * tol + hs:
        idx = np.clip((np.arange(int(len(x) / fator)) * fator).astype(int), 0, len(x) - 1)
        return x[idx]
    janela = np.hanning(n).astype(np.float32)
    tamanho = int(len(x) / fator) + n
    y = np.zeros(tamanho, dtype=np.float32)
    peso = np.zeros(tamanho, dtype=np.float32)
    pos_in, pos_out, delta = 0.0, 0, 0
    passo = 4  # a procura do encaixe é feita num sinal com 1 de cada 4 amostras: o mesmo resultado, bem mais rápido
    while True:
        ini = int(pos_in) + delta
        if ini < 0:
            ini = 0
        if ini + n > len(x) or pos_out + n > tamanho:
            break
        y[pos_out:pos_out + n] += x[ini:ini + n] * janela
        peso[pos_out:pos_out + n] += janela
        natural = x[ini + hs:ini + hs + n]  # o que viria depois deste pedaço se nada mudasse
        pos_in += ha
        pos_out += hs
        base = int(pos_in)
        lo, hi = max(0, base - tol), min(len(x) - n, base + tol)
        if hi <= lo or len(natural) < n:
            delta = 0
            continue
        regiao = x[lo:hi + n][::passo]
        corr = np.correlate(regiao, natural[::passo], mode="valid")
        delta = lo + int(np.argmax(corr)) * passo - base
    usado = max(1, pos_out)
    y = y[:usado + hs]
    peso = peso[:usado + hs]
    return y / np.maximum(peso, 1e-3)


class Tocador:
    """Toca um áudio inteiro numa saída só. posicao() diz onde está, em amostras do áudio original (para sincronizar o texto),
    mesmo depois de mudar a velocidade."""

    def __init__(self, amostras, taxa, fator=1.0):
        self.orig = np.asarray(amostras, dtype=np.float32)
        self.taxa = int(taxa)
        self.trava = threading.Lock()
        self.base = 0          # onde, no áudio original, começa o pedaço que está tocando
        self.fator = 1.0
        self.buf = self.orig
        self.p = 0             # posição dentro do pedaço que está tocando
        self.fim = threading.Event()
        self.stream = None
        if abs(fator - 1.0) >= 0.01:
            self.buf, self.fator = esticar(self.orig, fator, self.taxa), float(fator)

    def _callback(self, saida, frames, tempo, status):
        with self.trava:
            pedaco = self.buf[self.p:self.p + frames]
            n = len(pedaco)
            saida[:n, 0] = pedaco
            self.p += n
        if n < frames:
            saida[n:, 0] = 0
            raise sd.CallbackStop

    def iniciar(self):
        if sd is None or len(self.orig) == 0:
            self.fim.set()
            return
        # latência alta de propósito: um bloco maior aguenta o computador ocupado sem engasgar
        self.stream = sd.OutputStream(samplerate=self.taxa, channels=1, dtype="float32", callback=self._callback, latency="high",
                                      finished_callback=self.fim.set)
        self.stream.start()

    def posicao(self):
        with self.trava:
            return min(len(self.orig), self.base + int(self.p * self.fator))

    def mudar_velocidade(self, fator):
        """Troca a velocidade do que falta tocar. fator é relativo ao áudio original (1.5 = 50% mais rápido que ele)."""
        fator = float(fator)
        with self.trava:
            if abs(fator - self.fator) < 0.01:
                return
            inicio = self.base + int(self.p * self.fator)
        novo = esticar(self.orig[inicio:], fator, self.taxa)  # fora da trava: o som continua tocando enquanto calcula
        with self.trava:
            agora = self.base + int(self.p * self.fator)
            pular = max(0, int((agora - inicio) / fator))  # o que tocou enquanto calculava não se repete
            self.buf, self.base, self.p, self.fator = novo, inicio, pular, fator

    def nivel(self, janela_seg=0.05):
        """Volume de agora (0 a 1), para a bolinha reagir à voz."""
        i = self.posicao()
        trecho = self.orig[i:i + int(self.taxa * janela_seg)]
        if not len(trecho):
            return 0.0
        return float(min(1.0, np.sqrt(np.mean(np.square(trecho))) / 0.2))

    def parar(self):
        try:
            if self.stream is not None:
                self.stream.abort()
                self.stream.close()
        except Exception:
            pass
        self.fim.set()

    def esperar(self, timeout=None):
        return self.fim.wait(timeout)
