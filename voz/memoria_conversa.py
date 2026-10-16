# A memória do guardião no modo rápido (a "conversa com memória" desligada, que é o padrão). Cada fala é uma chamada nova ao Claude, que não lembra de nada:
# quem lembra é este módulo, que guarda as trocas em arquivo e as devolve junto de cada pergunta.
#   - as últimas 10 trocas, guardadas em logs: sobrevivem a reinício e a horas de intervalo (dentro do mesmo dia);
#   - um resumo do dia, que o próprio Claude (modelo leve, uma chamada curta) atualiza quando a pessoa fica uns minutos sem falar;
#   - zera no "nova conversa", e o resumo vale só no dia em que foi feito.
# Arquivo: conversas\memoria_rapida.json, na pasta operacional. Tudo fica neste computador.
import json
import os
import threading
import time

import hud_servidor as h

TROCAS_NO_PROMPT = 10          # quantas trocas vão junto de cada pergunta
TROCAS_GUARDADAS = 40          # quantas ficam no arquivo (as que passam de 10 só servem para o resumo)
LACUNA = 3 * 3600              # sem falar por tanto tempo, a conversa recomeça (o mesmo prazo da conversa nova do modo sessão)
OCIOSO_PARA_RESUMIR = 300      # segundos sem falar antes de gastar uma chamada com o resumo
MINIMO_NOVAS = 4               # só vale resumir quando houve pelo menos tantas trocas novas
MAXIMO_RESUMO = 900            # caracteres
ESPERA_DEPOIS_DE_FALHA = 600   # se o resumo falhar, tenta de novo daqui a tanto
_trava = threading.RLock()
_cache = None
_resumindo = False
_nao_antes_de = 0.0

PEDIDO_DO_RESUMO = (
    "Você mantém o resumo da conversa de hoje entre uma pessoa e o assistente de gestão de projetos dela. Atualize o resumo com as trocas novas.\n"
    "Escreva em até 110 palavras, em frases curtas, em português do Brasil, sem travessão, sem lista numerada e sem comentar o que está fazendo. Guarde só o que ajuda "
    "a continuar a conversa depois: decisões tomadas, tarefas e prazos citados (com os nomes, dias e horários exatos), combinados e pendências, e preferências que a "
    "pessoa disse. Não invente nada que não esteja nas trocas. Se nada importante foi dito, devolva o resumo anterior sem mudar. Se não há resumo anterior e nada "
    "importante foi dito, responda exatamente: (nada importante)")


def _arquivo():
    return os.path.join(h.OPER, "conversas", "memoria_rapida.json")


def _hoje():
    return time.strftime("%Y-%m-%d")


def _vazio():
    return {"dia": _hoje(), "trocas": [], "resumo": "", "resumo_ate": 0.0}


def _carregar():
    global _cache
    if _cache is None:
        try:
            with open(_arquivo(), encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = _vazio()
        for chave, padrao in _vazio().items():
            _cache.setdefault(chave, padrao)
    if _cache["dia"] != _hoje():  # dia novo: o resumo de ontem não vale mais (o plano, o ClickUp e a memória do perfil carregam o que importa)
        _cache = _vazio()
    return _cache


def _gravar():
    try:
        os.makedirs(os.path.dirname(_arquivo()), exist_ok=True)
        provisorio = _arquivo() + ".tmp"
        with open(provisorio, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
        os.replace(provisorio, _arquivo())
    except OSError:
        pass


def esquecer_cache():
    """Para os testes (e para quem trocar a pasta operacional): a próxima leitura vem do arquivo, como depois de um reinício."""
    global _cache, _resumindo, _nao_antes_de
    with _trava:
        _cache, _resumindo, _nao_antes_de = None, False, 0.0


def lembrar(usuario, guardiao, agora=None):
    """Guarda uma troca (o que a pessoa disse e o que o guardião respondeu)."""
    with _trava:
        e = _carregar()
        agora = agora if agora is not None else time.time()
        if e["trocas"] and agora - e["trocas"][-1][0] > LACUNA:
            e["trocas"] = []  # passou da lacuna: a conversa recomeça (o resumo do dia continua)
        e["trocas"].append([agora, str(usuario or ""), str(guardiao or "")])
        del e["trocas"][:-TROCAS_GUARDADAS]
        _gravar()


def recentes(n=TROCAS_NO_PROMPT, agora=None):
    """As últimas n trocas, se a última foi há menos de 3 horas. Cada uma é [horário, o que a pessoa disse, o que o guardião disse]."""
    with _trava:
        e = _carregar()
        agora = agora if agora is not None else time.time()
        if not e["trocas"] or agora - e["trocas"][-1][0] > LACUNA:
            return []
        return [list(t) for t in e["trocas"][-n:]]


def resumo():
    with _trava:
        return str(_carregar().get("resumo") or "")


def zerar():
    """'Nova conversa': esquece as trocas e o resumo."""
    global _cache
    with _trava:
        _cache = _vazio()
        _gravar()


def bloco(nome):
    """O texto que vai junto da pergunta: o resumo do dia (se houver) e as últimas trocas. Vazio se não há nada para lembrar."""
    trocas, texto_resumo = recentes(), resumo()
    partes = []
    if texto_resumo and texto_resumo.strip().lower() != "(nada importante)":
        partes.append("RESUMO DO DIA ATÉ AGORA (resumo automático do que já foi tratado hoje; use para lembrar, e se algo parecer estranho, confirme com a pessoa):\n"
                      + texto_resumo.strip())
    if trocas:
        linhas = []
        for _, u, g in trocas:
            linhas += [f"{nome}: {u}", f"Guardiao: {g}"]
        partes.append("CONVERSA RECENTE (para você entender o que ele quer dizer agora):\n" + "\n".join(linhas))
    return "\n\n".join(partes)


# ---------------- o resumo do dia ----------------

def _precisa_resumir(agora):
    e = _carregar()
    if not e["trocas"] or _resumindo or agora < _nao_antes_de:
        return False
    if agora - e["trocas"][-1][0] < OCIOSO_PARA_RESUMIR:
        return False
    return sum(1 for t in e["trocas"] if t[0] > e["resumo_ate"]) >= MINIMO_NOVAS


def resumir(chamar, nome="Pessoa", agora=None):
    """Atualiza o resumo do dia se a pessoa está parada há uns minutos e houve trocas novas. `chamar(pedido)` faz a pergunta ao Claude e devolve o texto
    (ou None se falhar). Devolve True se o resumo foi atualizado."""
    global _resumindo, _nao_antes_de
    agora = agora if agora is not None else time.time()
    with _trava:
        if not _precisa_resumir(agora):
            return False
        e = _carregar()
        novas = [t for t in e["trocas"] if t[0] > e["resumo_ate"]][-30:]
        anterior = e["resumo"]
        _resumindo = True
    pedido = (f"{PEDIDO_DO_RESUMO}\nO que a pessoa confirmou nas trocas novas (feito, cancelado, mudado) substitui o resumo anterior: não deixe como pendente o que ela já resolveu.\n\nRESUMO ANTERIOR:\n{anterior or '(nenhum)'}\n\nTROCAS NOVAS:\n"
              + "\n".join(f"{nome}: {u}\nGuardiao: {g}" for _, u, g in novas))
    try:
        texto = chamar(pedido)
    except Exception:
        texto = None
    with _trava:
        _resumindo = False
        texto = (texto or "").strip()
        if not texto:
            _nao_antes_de = agora + ESPERA_DEPOIS_DE_FALHA
            return False
        e = _carregar()
        if e["dia"] == _hoje():
            e["resumo"] = texto[:MAXIMO_RESUMO]
            e["resumo_ate"] = novas[-1][0]
            _gravar()
        return True


def vigiar(chamar, nome_da_pessoa, intervalo=30):
    """Uma thread que confere a cada 30 s se é hora de atualizar o resumo. Nunca atrapalha a conversa: a chamada ao Claude é feita aqui, fora dela."""
    def laco():
        while True:
            time.sleep(intervalo)
            try:
                resumir(chamar, nome_da_pessoa() if callable(nome_da_pessoa) else nome_da_pessoa)
            except Exception:
                pass
    threading.Thread(target=laco, daemon=True).start()
