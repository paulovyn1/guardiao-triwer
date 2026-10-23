# Anexos da conversa com o guardião: imagem, PDF, texto, áudio e vídeo. A pessoa anexa (botão do clipe, arrastar para a janela ou colar um print com Ctrl+V),
# o arquivo vai para a pasta anexos\ da pasta operacional e fica esperando a próxima pergunta, escrita ou falada. Quando ela chega, a pergunta segue ao Claude com
# o caminho de cada arquivo (ele abre imagem, PDF e texto com a ferramenta Read) e áudio e vídeo vão antes pelo Groq, que devolve a fala transcrita.
# Nada aqui chama o Claude. Os arquivos ficam só neste computador e são apagados depois de 14 dias.
import os
import re
import threading
import time

LIMITE = 25 * 1024 * 1024      # o mesmo teto do Groq para áudio; PDF e imagem grandes demais o Claude também não lê
MAXIMO_NA_FILA = 8            # anexos por mensagem
GUARDAR_DIAS = 14

IMAGEM = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
PDF = {"pdf"}
TEXTO = {"txt", "md", "csv", "tsv", "json", "xml", "html", "htm", "css", "js", "ts", "tsx", "jsx", "py", "ps1", "sql", "log", "yml", "yaml", "ini", "toml", "sh", "bat", "srt", "vtt", "env", "ipynb"}
AUDIO = {"mp3", "wav", "m4a", "ogg", "oga", "flac", "aac", "mpga", "opus"}
VIDEO = {"mp4", "mov", "webm", "mkv", "avi", "m4v", "mpeg", "mpg"}
MIMES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
ROTULOS = {"imagem": "imagem", "pdf": "PDF", "texto": "arquivo de texto", "audio": "áudio", "video": "vídeo", "outro": "arquivo"}

_trava = threading.Lock()
_seq = [0]
PENDENTES = []   # itens (dicts) na ordem em que foram anexados, esperando a próxima pergunta
REGISTRO = {}    # id -> item, para servir a miniatura e achar o arquivo


def _oper():
    import hud_servidor as h
    return h.OPER


def _pasta():
    return os.path.join(_oper(), "anexos", time.strftime("%Y-%m-%d"))


def tipo_de(nome, mime=""):
    ext = os.path.splitext(str(nome))[1].lower().lstrip(".")
    for tipo, exts in (("imagem", IMAGEM), ("pdf", PDF), ("texto", TEXTO), ("audio", AUDIO), ("video", VIDEO)):
        if ext in exts:
            return tipo
    mime = str(mime or "").lower()
    for prefixo, tipo in (("image/", "imagem"), ("audio/", "audio"), ("video/", "video"), ("text/", "texto")):
        if mime.startswith(prefixo):
            return tipo
    return "pdf" if mime == "application/pdf" else "outro"


def nome_seguro(nome):
    """Só o nome do arquivo (nunca um caminho), sem caractere que o Windows recusa, com no máximo 80 letras e a extensão preservada."""
    base = os.path.basename(str(nome or "").replace("\\", "/")) or "arquivo"
    base = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", base).strip(" .") or "arquivo"
    raiz, ext = os.path.splitext(base)
    return raiz[:80 - len(ext)] + ext


def _limpar_antigos():
    pasta = os.path.join(_oper(), "anexos")
    limite = time.time() - GUARDAR_DIAS * 86400
    try:
        for dia in os.listdir(pasta):
            caminho = os.path.join(pasta, dia)
            if os.path.isdir(caminho) and os.path.getmtime(caminho) < limite:
                for nome in os.listdir(caminho):
                    try:
                        os.remove(os.path.join(caminho, nome))
                    except OSError:
                        pass
                try:
                    os.rmdir(caminho)
                except OSError:
                    pass
    except OSError:
        pass


def publico(item):
    return {k: item[k] for k in ("id", "nome", "tipo", "tamanho", "aviso") if k in item}


def lista():
    with _trava:
        return [publico(i) for i in PENDENTES]


def salvar(nome, dados, mime=""):
    """Grava o arquivo, põe na fila da próxima pergunta e devolve o item. Lança ValueError com o motivo em português se não puder."""
    if not dados:
        raise ValueError("O arquivo está vazio.")
    if len(dados) > LIMITE:
        raise ValueError(f"O arquivo passa de {LIMITE // (1024 * 1024)} MB.")
    with _trava:
        if len(PENDENTES) >= MAXIMO_NA_FILA:
            raise ValueError(f"No máximo {MAXIMO_NA_FILA} anexos por mensagem.")
        _seq[0] += 1
        n = _seq[0]
    limpo = nome_seguro(nome)
    tipo = tipo_de(limpo, mime)
    if tipo == "imagem" and "." not in limpo:
        limpo += ".png"
    pasta = _pasta()
    os.makedirs(pasta, exist_ok=True)
    cid = f"a{int(time.time())}{n}"
    caminho = os.path.join(pasta, f"{cid}_{limpo}")
    with open(caminho, "wb") as f:
        f.write(dados)
    item = {"id": cid, "nome": limpo, "tipo": tipo, "tamanho": len(dados), "caminho": caminho, "mime": mime}
    if tipo == "outro":
        item["aviso"] = "O Claude não abre este tipo de arquivo direto. Exporte para PDF ou cole o texto na conversa."
    with _trava:
        PENDENTES.append(item)
        REGISTRO[cid] = item
    _limpar_antigos()
    return item


def remover(cid):
    with _trava:
        achou = next((i for i in PENDENTES if i["id"] == cid), None)
        if achou:
            PENDENTES.remove(achou)
    if achou:
        try:
            os.remove(achou["caminho"])
        except OSError:
            pass
    return bool(achou)


def arquivo(cid):
    """O item para servir a miniatura (só imagem que está registrada), ou None."""
    item = REGISTRO.get(str(cid))
    if item and item["tipo"] == "imagem" and os.path.isfile(item["caminho"]):
        return item
    return None


def consumir():
    """Tira da fila o que foi anexado desde a última pergunta: vai junto com esta."""
    with _trava:
        itens = list(PENDENTES)
        PENDENTES.clear()
    return itens


def nomes(itens):
    return [i["nome"] for i in itens]


def transcrever(item, chave):
    """Áudio ou vídeo pelo Groq (Whisper). Devolve o texto, ou '' se não deu."""
    import requests
    if not chave:
        return ""
    try:
        with open(item["caminho"], "rb") as f:
            r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": "Bearer " + chave},
                              files={"file": (item["nome"], f, item.get("mime") or "application/octet-stream")},
                              data={"model": "whisper-large-v3-turbo", "language": "pt", "response_format": "json", "temperature": "0"}, timeout=180)
        r.raise_for_status()
        return str(r.json().get("text") or "").strip()
    except Exception as erro:
        print("  (não consegui transcrever o anexo", item["nome"], ":", erro, ")")
        return ""


def compor(texto, itens, chave_groq="", provedor="claude"):
    """A pergunta que segue ao Claude: o que a pessoa disse mais a lista dos anexos (caminho de cada um, ou a fala transcrita de áudio e vídeo)."""
    if not itens:
        return texto
    if provedor != "claude":
        return texto + "\n\n[A pessoa anexou arquivos, mas este provedor não lê anexos. Diga que ela pode trocar para o Claude nas Preferências.]"
    linhas = []
    for it in itens:
        rotulo = ROTULOS.get(it["tipo"], "arquivo")
        if it["tipo"] in ("audio", "video"):
            fala = transcrever(it, chave_groq)
            linhas.append(f'- {rotulo} "{it["nome"]}", transcrição do que é dito: "{fala}"' if fala else
                          f'- {rotulo} "{it["nome"]}": não consegui transcrever (sem chave do Groq ou sem fala). Avise a pessoa.')
        else:
            linhas.append(f"- {rotulo}: {it['caminho']}")
    cab = "A pessoa anexou arquivos a esta mensagem. Abra cada um com a ferramenta Read antes de responder (imagem, PDF e texto abrem direto):"
    return f"{texto}\n\n[{cab}\n" + "\n".join(linhas) + "]"
