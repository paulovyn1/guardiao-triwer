"""Anexos da conversa, parte do servidor (sem navegador e sem Claude): subir um arquivo, a fila que espera a próxima pergunta, nome seguro, tipos, limites,
miniatura só de imagem, remover, a pergunta que segue ao Claude com o caminho de cada anexo (e a fala transcrita de áudio e vídeo) e o que não gasta o anexo
(comando da tela). Os arquivos ficam na pasta operacional e os antigos são apagados."""
import argparse
import os
import queue
import time

import requests

import v2_base as B
from v2_base import confere, h

PORTA = 8802
tmp, relogio = B.preparar(PORTA, hora="09:50")
import anexos  # noqa: E402
import guardiao_voz as g  # noqa: E402

URL = f"http://localhost:{PORTA}"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a02d4b390000000049454e44ae426082")
fila = h.bus.assinar()


def eventos(tipo):
    saida = []
    while True:
        try:
            ev = fila.get_nowait()
        except queue.Empty:
            return [e for e in saida if e["t"] == tipo]
        saida.append(ev)


def subir(nome, dados, mime="application/octet-stream"):
    return requests.post(f"{URL}/anexo", params={"nome": nome}, data=dados, headers={"Content-Type": mime}, timeout=20).json()


# ---------- subir e listar ----------
r = subir("print da tela.png", PNG, "image/png")
item = r.get("item") or {}
confere("subir um print: o arquivo é gravado na pasta anexos da pasta operacional e entra na fila", r.get("ok") and item["tipo"] == "imagem" and item["nome"] == "print da tela.png"
        and os.path.isfile(os.path.join(tmp, "anexos", time.strftime("%Y-%m-%d"), f"{item['id']}_print da tela.png")), r)
confere("o servidor avisa a tela da fila", any(e["itens"] and e["itens"][0]["id"] == item["id"] for e in eventos("anexos")))
lista = requests.get(f"{URL}/anexos", timeout=5).json()["itens"]
confere("GET /anexos lista o que espera a próxima pergunta, sem mostrar o caminho do arquivo", [i["id"] for i in lista] == [item["id"]] and "caminho" not in lista[0], lista)

# ---------- nome seguro e tipos ----------
r = subir("..\\..\\Windows\\evil<>:|?*.png", PNG, "image/png")
nome_gravado = os.path.basename(anexos.REGISTRO[r["item"]["id"]]["caminho"])
confere("nome com caminho e caracteres que o Windows recusa vira só um nome seguro, dentro da pasta de anexos",
        r["ok"] and ".." not in r["item"]["nome"] and not any(c in r["item"]["nome"] for c in '<>:"/\\|?*') and anexos.REGISTRO[r["item"]["id"]]["caminho"].startswith(os.path.join(tmp, "anexos")), (r, nome_gravado))
tipos, ids = {}, {}
for nome, mime in (("contrato.pdf", "application/pdf"), ("notas.md", "text/markdown"), ("reuniao.mp3", "audio/mpeg"), ("video.mp4", "video/mp4"), ("planilha.xlsx", "application/vnd.ms-excel"), ("foto", "image/jpeg")):
    rr = subir(nome, PNG if nome == "foto" else b"conteudo " + nome.encode(), mime)
    tipos[nome] = (rr["item"]["tipo"], rr["item"].get("aviso")) if rr.get("ok") else rr
    ids[nome] = rr.get("item", {}).get("id")
confere("tipos: PDF, texto, áudio, vídeo e imagem sem extensão (pelo tipo do arquivo)", [tipos[n][0] for n in ("contrato.pdf", "notas.md", "reuniao.mp3", "video.mp4", "foto")] == ["pdf", "texto", "audio", "video", "imagem"], tipos)
confere("planilha do Office entra, com o aviso de que o Claude não abre direto", tipos["planilha.xlsx"][0] == "outro" and "PDF" in tipos["planilha.xlsx"][1], tipos["planilha.xlsx"])
anexos.PENDENTES.clear()  # a fila de cada trecho do teste começa vazia
confere("imagem sem extensão ganha .png no nome", subir("colado", PNG, "image/png")["item"]["nome"] == "colado.png")

# ---------- limites ----------
confere("arquivo vazio é recusado com o motivo", subir("vazio.txt", b"")["ok"] is False and "vazio" in subir("vazio.txt", b"")["erro"])
try:
    anexos.salvar("grande.bin", b"0" * (anexos.LIMITE + 1))
    grande = "aceitou"
except ValueError as e:
    grande = str(e)
confere("arquivo acima de 25 MB é recusado", "25 MB" in grande, grande)
anexos.PENDENTES.clear()
while len(anexos.PENDENTES) < anexos.MAXIMO_NA_FILA:
    subir("extra.txt", b"x")
cheio = subir("mais um.txt", b"x")
confere("no máximo 8 anexos por mensagem", cheio["ok"] is False and "8" in cheio["erro"], cheio)

# ---------- miniatura ----------
pedido = requests.get(f"{URL}/anexo/{item['id']}", timeout=5)
confere("a miniatura de imagem sai com o tipo certo e sem adivinhação do navegador", pedido.status_code == 200 and pedido.headers["Content-Type"] == "image/png" and pedido.headers.get("X-Content-Type-Options") == "nosniff" and pedido.content == PNG)
pdf_id = ids["contrato.pdf"]
anexos.PENDENTES.clear()
anexos.PENDENTES.append(anexos.REGISTRO[pdf_id])  # um PDF esperando na fila, para o teste de remover
confere("só imagem tem miniatura: PDF, id inventado e tentativa de sair da pasta dão 404",
        requests.get(f"{URL}/anexo/{pdf_id}", timeout=5).status_code == 404 and requests.get(f"{URL}/anexo/inventado", timeout=5).status_code == 404
        and requests.get(f"{URL}/anexo/..%2F..%2Fconfig.json", timeout=5).status_code == 404)

# ---------- remover ----------
caminho_pdf = anexos.REGISTRO[pdf_id]["caminho"]
eventos("anexos")
r = requests.post(f"{URL}/anexos", json={"id": pdf_id}, timeout=5).json()
confere("remover tira da fila, apaga o arquivo e avisa a tela", r["ok"] and pdf_id not in [i["id"] for i in anexos.lista()] and not os.path.exists(caminho_pdf) and eventos("anexos"))
confere("remover um id que não existe não dá erro", requests.post(f"{URL}/anexos", json={"id": "nada"}, timeout=5).json()["ok"] is False)

# ---------- arquivos antigos ----------
velha = os.path.join(tmp, "anexos", "2020-01-01")
os.makedirs(velha, exist_ok=True)
open(os.path.join(velha, "velho.png"), "wb").write(PNG)
os.utime(velha, (time.time() - 40 * 86400,) * 2)
anexos.PENDENTES.clear()
subir("novo.txt", b"novo")
confere("arquivos de mais de 14 dias são apagados", not os.path.exists(velha))

# ---------- a pergunta que segue ao Claude ----------
anexos.PENDENTES.clear()
a1 = subir("print.png", PNG, "image/png")["item"]
a2 = subir("proposta.pdf", b"%PDF-1.4 teste", "application/pdf")["item"]
a3 = subir("recado.mp3", b"ID3....", "audio/mpeg")["item"]
anexos.transcrever = lambda item, chave: "oi, aqui é o cliente falando do prazo" if chave else ""
itens = list(anexos.PENDENTES)
msg = anexos.compor("o que acha disso?", itens, "chave", "claude")
confere("a pergunta leva o caminho de cada imagem e PDF e manda abrir com a ferramenta Read", msg.startswith("o que acha disso?") and "Read" in msg and anexos.REGISTRO[a1["id"]]["caminho"] in msg and anexos.REGISTRO[a2["id"]]["caminho"] in msg, msg)
confere("áudio e vídeo vão como a fala transcrita, sem caminho", "oi, aqui é o cliente falando do prazo" in msg and anexos.REGISTRO[a3["id"]]["caminho"] not in msg, msg)
confere("sem a chave da transcrição o guardião é avisado de que não deu", "não consegui transcrever" in anexos.compor("x", [anexos.REGISTRO[a3["id"]]], "", "claude"))
confere("no Codex a pergunta diz que anexo não é lido aqui", "não lê anexos" in anexos.compor("x", itens, "chave", "codex") and anexos.REGISTRO[a1["id"]]["caminho"] not in anexos.compor("x", itens, "chave", "codex"))
confere("sem anexo a pergunta segue igual", anexos.compor("só texto", [], "chave", "claude") == "só texto")

# ---------- no guardião: o anexo vai com a próxima pergunta, uma vez só ----------
capturado = []


def responder_falso(pergunta, voz, texto_usuario=None, **k):
    capturado.append({"pergunta": pergunta, "texto_usuario": texto_usuario, "modelo": k.get("modelo"), "motivo": k.get("motivo")})
    return 0.1, 0.2, "Vi o print."


g.responder_falando = responder_falso
g.preferencias = lambda: {"voz_guardiao": True, "sessao": False, "escuta_aberta": True, "provedor_ia": "claude"}
g.provedor_ia = lambda: "claude"
g.chave_groq = lambda: "chave"
args = argparse.Namespace(cerebro=True, voz="kokoro", voz_kokoro="pm_santa", voz_nome="", sem_preview=True, previa_local=True, sem_escuta_aberta=False)
eventos("anexos"), eventos("anexos_enviados")
g.atender(args, queue.Queue(), None, None, 0, texto_digitado="tutorial")
confere("comando da tela (o tutorial) não gasta o anexo: ele continua esperando a pergunta de verdade", len(anexos.PENDENTES) == 3 and not capturado)
g.atender(args, queue.Queue(), None, None, 0, texto_digitado="o que tem nesse print?")
c = capturado[-1]
confere("a pergunta vai ao Claude com os anexos e usa o modelo completo", "o que tem nesse print?" in c["pergunta"] and anexos.REGISTRO[a1["id"]]["caminho"] in c["pergunta"] and c["modelo"] == g.MODELO_PADRAO and c["motivo"] == "tem anexo", c)
confere("o texto que a pessoa escreveu segue limpo para as regras de intenção (sem o bloco dos anexos)", c["texto_usuario"] == "o que tem nesse print?", c["texto_usuario"])
confere("a fila esvazia e a tela é avisada do que foi enviado", not anexos.PENDENTES and any(e["nomes"] == ["print.png", "proposta.pdf", "recado.mp3"] for e in eventos("anexos_enviados")))
g.atender(args, queue.Queue(), None, None, 0, texto_digitado="e agora sem anexo?")
confere("a pergunta seguinte segue sem anexo", capturado[-1]["pergunta"] == "e agora sem anexo?", capturado[-1])

ok = B.placar()
raise SystemExit(0 if ok else 1)
