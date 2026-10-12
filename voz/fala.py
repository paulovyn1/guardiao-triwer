# Prepara o texto para ser FALADO: horários, números, siglas e marcas viram palavras que a voz lê direito.
# O texto que aparece na tela continua o original; só o que vai para a voz passa por aqui.
# As pronúncias especiais ficam em pronuncias.json (você pode editar: "como está escrito": "como deve soar").
import json
import os
import re
from urllib.parse import unquote

from num2words import num2words

BASE = os.path.dirname(os.path.abspath(__file__))
ARQ_PRONUNCIAS = os.path.join(BASE, "pronuncias.json")
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

_cache = {"mtime": None, "dados": {}}


def _extenso(valor, feminino=False):
    s = num2words(int(valor), lang="pt_BR")
    if feminino:
        s = re.sub(r"\bum\b", "uma", s)
        s = re.sub(r"\bdois\b", "duas", s)
    return s


def _pronuncias():
    try:
        mtime = os.path.getmtime(ARQ_PRONUNCIAS)
    except OSError:
        return {}
    if _cache["mtime"] != mtime:
        with open(ARQ_PRONUNCIAS, encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
        _cache["mtime"] = mtime
    return _cache["dados"]


def _hora(m):
    h = int(m.group(1))
    mi = m.group(2)
    if h > 24:
        return m.group(0)
    if not mi or int(mi) == 0:
        return f"{_extenso(h, True)} {'hora' if h == 1 else 'horas'}"
    mi = int(mi)
    if mi > 59:
        return m.group(0)
    if mi == 30:
        return f"{_extenso(h, True)} e meia"
    return f"{_extenso(h, True)} e {_extenso(mi)}"


def _decimal(m):
    esq, dire = m.group(1), m.group(2)
    prefixo = "zero " if dire.startswith("0") and int(dire) != 0 else ""
    return f"{_extenso(esq)} vírgula {prefixo}{_extenso(dire)}"


def _dinheiro(m):
    simbolo = m.group(1)
    inteiro = int(m.group(2).replace(".", ""))
    centavos = m.group(3)
    moeda = "reais" if simbolo == "R$" else "dólares"
    if inteiro == 1:
        moeda = moeda[:-1] if moeda == "dólares" else "real"
    saida = f"{_extenso(inteiro)} {moeda}"
    if centavos and int(centavos) > 0:
        saida += f" e {_extenso(centavos)} centavos"
    return saida


def _data(m):
    dia, mes = int(m.group(1)), int(m.group(2))
    if not (1 <= dia <= 31 and 1 <= mes <= 12):
        return m.group(0)
    saida = f"{_extenso(dia)} de {MESES[mes - 1]}"
    if m.group(3):
        ano = int(m.group(3))
        saida += f" de {_extenso(ano + 2000 if ano < 100 else ano)}"
    return saida


LINK_COM_TITULO = re.compile(r"\[([^\]\n]+)\]\(\s*((?:https?://|www\.)[^)\s]+)\s*\)", re.I)
PAGINA_SEM_NOME = {"watch", "view", "edit", "index", "home", "file", "share", "open", "post", "posts", "status", "page", "doc", "docs", "app", "login", "v2"}
ENDERECO = re.compile(r"(?:https?://|www\.)[^\s<>\"'\])]+", re.I)


def _endereco_falado(url):
    """Um endereço dito em voz alta: só o domínio e, no máximo, o nome da página. O resto (https, barras, códigos) não é lido."""
    resto = re.sub(r"^https?://", "", url.strip(), flags=re.I)
    dominio, _, caminho = resto.partition("/")
    dominio = re.sub(r"^www\.", "", dominio.split("@")[-1].split(":")[0], flags=re.I).lower()
    if dominio.endswith("clickup.com"):  # tarefa ou documento citado sem título
        return "um link do ClickUp"
    pagina = ""
    ultimo = re.split(r"[?#]", caminho)[0].strip("/").split("/")[-1]
    if ultimo:
        nome = re.sub(r"[-_+.]+", " ", re.sub(r"\.(html?|php|aspx?|pdf)$", "", unquote(ultimo), flags=re.I)).strip()
        # só vale se tiver cara de nome: nada de código, número solto ou sequência comprida
        if nome and nome.lower() not in PAGINA_SEM_NOME and len(nome) <= 40 and len(nome.split()) <= 6 and re.search(r"[a-zà-ú]{3,}", nome, re.I) and not re.search(r"[a-zà-ú]\d|\d[a-zà-ú]|\d{3,}", nome, re.I):
            pagina = nome
    falado = dominio.replace(".", " ponto ")
    return f"{falado}, página {pagina}" if pagina else falado


def _links_para_fala(t):
    """Link com título vira só o título (é assim que chegam as tarefas do ClickUp); endereço solto vira o domínio."""
    t = LINK_COM_TITULO.sub(lambda m: _endereco_falado(m.group(1)) if ENDERECO.fullmatch(m.group(1).strip()) else m.group(1), t)
    t = re.sub(r"\]\(\s*(?:https?://|www\.)[^)\s]*\s*\)?", "", t)  # metade final de um link que foi cortado entre duas frases

    def solto(m):
        url = m.group(0)
        fim = re.search(r"[.,;:!?]+$", url)
        return _endereco_falado(url[:fim.start()] if fim else url) + (fim.group(0) if fim else "")
    t = ENDERECO.sub(solto, t)
    return re.sub(r"\[(?=[^\]]*$)|(?<![^\s(])\]", "", t)  # colchete que sobrou da outra metade


def normalizar_para_fala(texto):
    t = _links_para_fala(texto)
    # marcações de texto que não devem ser lidas
    t = re.sub(r"[*_`#>]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = t.replace("—", ", ").replace("–", ", ").replace("&", " e ").replace("+", " mais ")
    # marcas, siglas e nomes com pronúncia própria (os mais longos primeiro)
    for chave in sorted(_pronuncias(), key=len, reverse=True):
        t = re.sub(r"(?<!\w)" + re.escape(chave) + r"(?!\w)", _pronuncias()[chave], t, flags=re.IGNORECASE)
    # dinheiro, data, hora, minutos, porcentagem, milhar, decimal e número solto
    t = re.sub(r"(R\$|US\$)\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?", _dinheiro, t)
    t = re.sub(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])", _data, t)
    t = re.sub(r"(?<![\d,.])(\d{1,2})\s?[h:](\d{2})?(?![\w])", _hora, t)
    t = re.sub(r"(\d+)\s?min(?:utos?)?\b", lambda m: f"{_extenso(m.group(1))} {'minuto' if int(m.group(1)) == 1 else 'minutos'}", t)
    t = re.sub(r"(\d+(?:,\d+)?)\s?%", lambda m: (_decimal(re.match(r"(\d+),(\d+)", m.group(1))) if "," in m.group(1) else _extenso(m.group(1))) + " por cento", t)
    t = re.sub(r"\d{1,3}(?:\.\d{3})+", lambda m: _extenso(m.group(0).replace(".", "")), t)
    t = re.sub(r"(\d+),(\d+)", _decimal, t)
    t = re.sub(r"\d+", lambda m: _extenso(m.group(0)), t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    exemplos = [
        "Hoje é sábado, 10 de outubro, 18h54, e você está no último bloco do dia, que vai até as 19h: aprovar os planos de domingo, das 15h às 18h, e de segunda, das 14h às 16h30.",
        "A reunião da última quinta é às 18h, dura 2h ou 3h, e a próxima é 29/10. Faltam 30 min.",
        "O CPL ficou em R$ 12,50 com ROAS 0,645 e 20% de conversão no ClickUp e no ManyChat.",
        "O plano usa 7,6 mil tokens e custa US$ 0,46, sai por R$ 1.500 ao mês. Abra a Loja Nativa às 9h.",
        "Criei a tarefa [Post do desafio de outubro](https://app.clickup.com/t/86exemplo1). A página está em https://cpl.triwer.com.br/inscricao-aberta?utm=1.",
    ]
    for e in exemplos:
        print(e)
        print("  ->", normalizar_para_fala(e))
