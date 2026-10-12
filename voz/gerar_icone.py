# Gera o ícone do Guardião a partir de um desenho só: a letra G feita do anel da bolinha, com o núcleo no centro.
# Flat, duas cores: cartão escuro com a marca dourada, que se lê tanto num fundo claro quanto num escuro.
# Saídas: guardiao.ico (atalho da área de trabalho), hud2\icone.ico (janela e barra de tarefas), hud2\icone.svg e os PNG do celular.
# Só precisa do numpy. Rodar de novo depois de mexer no desenho: python gerar_icone.py
import math
import os
import struct
import zlib

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
OBSIDIANA = (11, 12, 15)
OURO = (227, 185, 100)
BRONZE = (111, 83, 34)
TAMANHOS_ICO = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def medidas(n):
    """O desenho numa grade de 64. Nos tamanhos pequenos o traço engrossa e a marca ocupa mais do cartão, para não virar um borrão."""
    if n <= 24:
        return {"raio": 19.0, "traco": 6.4, "nucleo": 6.0, "barra": 45.0, "meio": 32.0, "canto": 15.0, "borda": 2.0}
    return {"raio": 17.5, "traco": 4.5, "nucleo": 5.4, "barra": 43.5, "meio": 29.5, "canto": 14.0, "borda": 1.1}


def _grade(n):
    k = 64.0 / n
    y, x = np.mgrid[0:n, 0:n]
    return (x + 0.5) * k, (y + 0.5) * k, n / 64.0


def _disco(x, y, s, cx, cy, r):
    return np.clip(0.5 - (np.hypot(x - cx, y - cy) - r) * s, 0, 1)


def _caixa(x, y, s, meio, canto):
    qx, qy = np.abs(x - 32) - (meio - canto), np.abs(y - 32) - (meio - canto)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - canto
    return np.clip(0.5 - d * s, 0, 1)


def _segmento(x, y, s, x0, y0, x1, y1, traco):
    dx, dy = x1 - x0, y1 - y0
    t = np.clip(((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy), 0, 1)
    return np.clip(0.5 - (np.hypot(x - (x0 + t * dx), y - (y0 + t * dy)) - traco / 2) * s, 0, 1)


def _arco(x, y, s, raio, fim, traco):
    """Arco do leste (0 grau) até `fim` graus, no sentido horário, com as pontas redondas."""
    dentro = (np.degrees(np.arctan2(y - 32, x - 32)) % 360) <= fim
    pontas = [(32 + raio * math.cos(math.radians(g)), 32 + raio * math.sin(math.radians(g))) for g in (0, fim)]
    d = np.where(dentro, np.abs(np.hypot(x - 32, y - 32) - raio), np.minimum(*[np.hypot(x - px, y - py) for px, py in pontas]))
    return np.clip(0.5 - (d - traco / 2) * s, 0, 1)


ABERTURA = 316  # o anel para aqui: o vão no alto, à direita, é o que faz dele um G


def desenhar(n, trato="escuro"):
    """Devolve a imagem RGBA n x n. Tratos: 'escuro' (o padrão), 'ouro' (cartão dourado, marca escura), 'solto' (só a marca) e 'cheio' (sem cantos, para o celular recortar)."""
    x, y, s = _grade(n)
    m = medidas(n)
    marca = np.maximum.reduce([_arco(x, y, s, m["raio"], ABERTURA, m["traco"]), _segmento(x, y, s, 32 + m["raio"], 32, m["barra"], 32, m["traco"]), _disco(x, y, s, 32, 32, m["nucleo"])])
    img = np.zeros((n, n, 4))
    if trato == "solto":
        img[..., :3], img[..., 3] = (178, 132, 49), marca
    else:
        cartao = np.ones((n, n)) if trato == "cheio" else _caixa(x, y, s, m["meio"], m["canto"])
        fundo, cor = (OURO, OBSIDIANA) if trato == "ouro" else (OBSIDIANA, OURO)
        img[..., :3], img[..., 3] = fundo, cartao
        if trato == "escuro":  # filete de bronze na borda: o cartão não some num fundo preto
            filete = (cartao * (1 - _caixa(x, y, s, m["meio"] - m["borda"], m["canto"] - m["borda"])))[..., None]
            img[..., :3] = img[..., :3] * (1 - filete) + np.array(BRONZE) * filete
        img[..., :3] = img[..., :3] * (1 - marca[..., None]) + np.array(cor) * marca[..., None]
    img[..., 3] *= 255
    return np.clip(np.round(img), 0, 255).astype(np.uint8)


def png(img):
    def pedaco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    alt, larg = img.shape[:2]
    bruto = b"".join(b"\x00" + img[i].tobytes() for i in range(alt))
    return b"\x89PNG\r\n\x1a\n" + pedaco(b"IHDR", struct.pack(">IIBBBBB", larg, alt, 8, 6, 0, 0, 0)) + pedaco(b"IDAT", zlib.compress(bruto, 9)) + pedaco(b"IEND", b"")


def ico(trato="escuro"):
    imagens = [png(desenhar(t, trato)) for t in TAMANHOS_ICO]
    cabecalho, pos = struct.pack("<HHH", 0, 1, len(imagens)), 6 + 16 * len(imagens)
    for t, dados in zip(TAMANHOS_ICO, imagens):
        cabecalho += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(dados), pos)
        pos += len(dados)
    return cabecalho + b"".join(imagens)


def svg():
    m = medidas(256)
    cor = lambda c: "#%02x%02x%02x" % c  # noqa: E731
    fx, fy = 32 + m["raio"] * math.cos(math.radians(ABERTURA)), 32 + m["raio"] * math.sin(math.radians(ABERTURA))
    lado, ini, b = 2 * m["meio"], 32 - m["meio"], m["borda"]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            f'<rect x="{ini}" y="{ini}" width="{lado}" height="{lado}" rx="{m["canto"]}" fill="{cor(BRONZE)}"/>'
            f'<rect x="{ini + b}" y="{ini + b}" width="{lado - 2 * b}" height="{lado - 2 * b}" rx="{m["canto"] - b}" fill="{cor(OBSIDIANA)}"/>'
            f'<path d="M{32 + m["raio"]} 32A{m["raio"]} {m["raio"]} 0 1 1 {fx:.2f} {fy:.2f}M{32 + m["raio"]} 32H{m["barra"]}" fill="none" stroke="{cor(OURO)}" stroke-width="{m["traco"]}" stroke-linecap="round"/>'
            f'<circle cx="32" cy="32" r="{m["nucleo"]}" fill="{cor(OURO)}"/></svg>\n')


if __name__ == "__main__":
    hud2 = os.path.join(AQUI, "hud2")
    saidas = {os.path.join(AQUI, "guardiao.ico"): ico(), os.path.join(hud2, "icone.ico"): ico(), os.path.join(hud2, "icone.svg"): svg().encode("utf-8"),
              os.path.join(hud2, "icone-192.png"): png(desenhar(192)), os.path.join(hud2, "icone-512.png"): png(desenhar(512)),
              os.path.join(hud2, "icone-mascara-512.png"): png(desenhar(512, "cheio")), os.path.join(hud2, "icone-180.png"): png(desenhar(180, "cheio"))}
    for caminho, dados in saidas.items():
        with open(caminho, "wb") as f:
            f.write(dados)
        print("gerado:", os.path.relpath(caminho, AQUI), len(dados), "bytes")
