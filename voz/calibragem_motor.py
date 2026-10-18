# Calibragem: o que o guardião aprende com o uso. Tudo aqui é regra local, sem chamar o Claude.
#   natureza da tarefa   o tipo de trabalho (copy, reunião, operacional...), separado da frente (o projeto). O tempo real é medido por natureza.
#   tempo confiável      quando um tempo vale para a média e para a margem do roteador (medido no modo execução ou informado pela pessoa).
#   tempos.json v2       a média por natureza; o arquivo antigo (por frente) é migrado uma vez, descartando o que não foi medido de verdade.
#   resumo do dia        o que o report mostra: planejado e feito, a tarefa principal, foco medido, o que entrou fora do plano.
#   perfil               calibragem\perfil_comportamento.json: o que se repete nos últimos dias, com o nível de cada achado
#                        (hipótese, provável, confirmado pela pessoa, negado) e a regra que o plano deve seguir.
#   seção do plano       calibragem\calibragem_para_o_plano.md: só o provável e o confirmado, em poucas linhas, para o plano usar.
# Não importa o hud_servidor: o roteador e o plano base também usam este módulo.
import json
import os
import re
import shutil
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta

NATUREZAS = {
    "copy": "Copy e texto",
    "criacao": "Design e vídeo",
    "trafego": "Tráfego e anúncios",
    "decisao": "Decisão e estratégia",
    "reuniao": "Reunião",
    "atendimento": "Atendimento e mensagens",
    "operacional": "Operacional",
    "dev": "Desenvolvimento e automação",
    "financeiro": "Financeiro",
    "revisao": "Revisão e aprovação",
    "estudo": "Estudo",
    "geral": "Geral",
}
SEM_TEMPO = "folga"  # pausa, almoço e folga para imprevistos: não é trabalho, não entra na média
ALIASES = {"design": "criacao", "video": "criacao", "edicao": "criacao", "texto": "copy", "estrategia": "decisao", "anuncios": "trafego",
           "ads": "trafego", "automacao": "dev", "desenvolvimento": "dev", "mensagens": "atendimento", "aprovacao": "revisao", "rotina": "operacional"}
SEM_MEDIA = {"reuniao", SEM_TEMPO}
REPLANEJAMENTO = ("replanejamento_automatico", "replanejamento_sugerido")  # antes da 0.11.0 o supervisor replanejava sozinho; agora só sugere  # reunião dura o que foi marcado: não ensina nada sobre estimativa nem entra na margem

FOLGA = re.compile(r"\b(folga|pausa|almoco|intervalo|descanso|respiro)\b|^reserva\b")
# a ordem importa: a primeira regra que casa decide ("Revisar o roteiro" é revisão, "Design do criativo" é criação)
REGRAS = [
    ("reuniao", r"reuni|\bcall\b|mentoria|\bencontro\b|\blive\b|apresentacao|entrevista|\bdaily\b|aula ao vivo"),
    ("financeiro", r"pagament|\bpagar\b|boleto|nota fiscal|\bnf\b|financeir|cobranca|fatura|imposto|contador|concilia|recebiment"),
    ("revisao", r"revis|aprova|\bconferir\b|feedback|corrigir|correcao"),
    ("criacao", r"design|\barte\b|thumb|\bcapa\b|carrossel|edicao|editar"),
    ("trafego", r"trafego|campanha|anuncio|\bads\b|publicos?\b|pixel|criativos"),
    ("dev", r"codigo|\bapp\b|implementa|\bbug|deploy|\bsite\b|automac|\bn8n\b|manychat|integrac|\bapi\b|programa[rc]|interface|supabase|banco de dados"),
    ("atendimento", r"respond|\bgrupos?\b|whatsapp|\bdirect\b|\bdms?\b|mensage|atendiment|suporte|duvidas|comentarios"),
    ("copy", r"copy|roteiro|legenda|\btexto|e-?mail|headline|manifesto|escrever|redac|artigo|substack|\bcarta\b|pitch|briefing|material"),
    ("criacao", r"video|gravar|gravac|stories|reels|\bfotos?\b|criativo|\bpost\b"),
    ("decisao", r"decid|decis|estrateg|planej|ideia|brainstorm|definir|escolher|pensar|posicionament|oferta|funil"),
    ("estudo", r"estud|curso|aprender|\bler\b|leitura|pesquis"),
    ("operacional", r"subir|agendar|enviar|disparar|aviso|configur|cadastr|liberar|organizar|upload|publicar|postar|triagem|atualizar|preencher|relatorio|lancar|acesso"),
]
REGRAS = [(n, re.compile(r)) for n, r in REGRAS]

MIN_MEDIDO = 3        # sessão de menos de 3 minutos no modo execução é clique em Iniciar só para concluir, não trabalho medido
CURTO_DEMAIS = 0.25   # tempo informado abaixo de 25% do previsto (em tarefa de 10 min ou mais) não entra na média
LONGO_DEMAIS = 4.0    # nem acima de 4 vezes o previsto sem ter sido medido
VERSAO_TEMPOS = 2


def _norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def inferir_natureza(titulo, frente=""):
    """Natureza pelo título (e pela frente, se o título não disser nada). Bloco de folga, pausa ou almoço devolve "folga"."""
    t = _norm(titulo)
    if FOLGA.search(t):
        return SEM_TEMPO
    for texto in (t, _norm(frente)):
        for nome, regra in REGRAS:
            if regra.search(texto):
                return nome
    return "geral"


def natureza_do_bloco(bloco):
    """A natureza que o plano escreveu no bloco (campo "natureza"), ou a deduzida do título quando falta ou não é uma das conhecidas."""
    bloco = bloco or {}
    n = _norm(bloco.get("natureza"))
    n = ALIASES.get(n, n)
    if n in NATUREZAS or n == SEM_TEMPO:
        return n
    return inferir_natureza(bloco.get("titulo"), bloco.get("frente"))


def rotulo(natureza):
    return NATUREZAS.get(natureza) or ("Folga" if natureza == SEM_TEMPO else str(natureza or "Geral"))


def tempo_confiavel(planejado, minutos, medido, informado):
    """O tempo vale para a média? Medido no modo execução: vale. Sem medir, só se a pessoa informou o horário e o número é plausível
    (marcar como feito depois deixava 1 ou 2 minutos "confirmados" e derrubava a margem do roteador)."""
    if not minutos or minutos < 1:
        return False
    if medido:
        return True
    if not informado or minutos <= 1:
        return False
    if planejado and planejado >= 10 and minutos < CURTO_DEMAIS * planejado:
        return False
    if planejado and minutos > LONGO_DEMAIS * planejado:
        return False
    return True


def recalcular(t):
    """Média (só com 3 registros confirmados), média planejada e a razão de uma natureza. A razão (mediana de real sobre planejado dos
    confirmados) é o que vale para ajustar estimativa: tarefas da mesma natureza têm tamanhos diferentes, a média em minutos não."""
    regs = t.get("registros") or []
    validos = [r for r in regs if r.get("confirmado")]
    t["media"] = round(sum(r["real"] for r in validos) / len(validos)) if len(validos) >= 3 else None
    t["media_planejado"] = round(sum(r["planejado"] for r in regs) / len(regs)) if regs else None
    razoes = sorted(r["real"] / r["planejado"] for r in validos if r.get("planejado"))
    t["razao"] = round(razoes[len(razoes) // 2] if len(razoes) % 2 else (razoes[len(razoes) // 2 - 1] + razoes[len(razoes) // 2]) / 2, 2) if len(razoes) >= 3 else None
    return t


def media_da_tarefa(tipos, titulo, minimo=3):
    """A média em minutos da mesma tarefa repetida (o mesmo assunto, com palavras um pouco diferentes), com 3 registros confirmados ou mais."""
    chave = _chave_titulo(titulo)
    if not chave:
        return None
    reais = [r["real"] for t in (tipos or {}).values() for r in (t.get("registros") or []) if r.get("confirmado") and _chave_titulo(r.get("titulo")) == chave]
    return int(round(sum(reais) / len(reais))) if len(reais) >= minimo else None


def somar(dados, natureza, registro, maximo=10):
    """Acrescenta um registro ao tempos.json (já carregado) na natureza certa. Folga não entra."""
    if natureza == SEM_TEMPO:
        return dados
    dados["versao"] = VERSAO_TEMPOS
    t = dados.setdefault("tipos", {}).setdefault(natureza, {"rotulo": rotulo(natureza), "registros": [], "media": None})
    t["rotulo"] = rotulo(natureza)
    t.setdefault("registros", []).append(registro)
    t["registros"] = t["registros"][-maximo:]
    recalcular(t)
    return dados


def _gravar(caminho, obj):
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)


def _ler(caminho):
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _medicoes(oper):
    """{(data, título): [minutos medidos]} das sessões do modo execução, para saber se um registro antigo foi medido de verdade."""
    saida = {}
    pasta = os.path.join(oper, "registros")
    try:
        nomes = os.listdir(pasta)
    except OSError:
        return saida
    for nome in nomes:
        m = re.match(r"execucao_(\d{4}-\d{2}-\d{2})\.json$", nome)
        d = _ler(os.path.join(pasta, nome)) if m else None
        for s in (d or {}).get("sessoes") or []:
            if s.get("resultado") == "concluido" and s.get("minutos") is not None:
                saida.setdefault((m.group(1), s.get("titulo")), []).append(int(s["minutos"]))
    return saida


def migrar_tempos(oper):
    """tempos.json antigo (por frente) vira o novo (por natureza), uma vez. Cada registro é reclassificado pelo título; o que não foi medido
    de verdade perde o "confirmado"; folga sai; registro repetido (a mesma tarefa concluída duas vezes) conta uma vez.
    O arquivo antigo fica em calibragem\\tempos_antes_da_v2.json. Devolve True se migrou."""
    caminho = os.path.join(oper, "tempos.json")
    dados = _ler(caminho)
    if not isinstance(dados, dict) or dados.get("versao") == VERSAO_TEMPOS:
        return False
    antigos = dados.get("tipos") or {}
    medicoes = _medicoes(oper)
    novo = {"versao": VERSAO_TEMPOS, "migrado_em": time.strftime("%Y-%m-%d"), "tipos": {}}
    todos, vistos = [], set()
    for frente, t in antigos.items():
        for r in (t or {}).get("registros") or []:
            if not isinstance(r, dict) or r.get("real") is None or r.get("planejado") is None:
                continue
            chave = (r.get("data"), r.get("titulo"), r.get("real"), r.get("planejado"))
            if chave in vistos:
                continue
            vistos.add(chave)
            todos.append((frente, r))
    todos.sort(key=lambda fr: str(fr[1].get("data") or ""))
    for frente, r in todos:
        natureza = inferir_natureza(r.get("titulo"), frente)
        medido = any(m >= MIN_MEDIDO and abs(m - int(r["real"])) <= 1 for m in medicoes.get((r.get("data"), r.get("titulo")), []))
        confirmado = bool(r.get("confirmado")) and tempo_confiavel(r["planejado"], r["real"], medido, True)
        somar(novo, natureza, {"data": r.get("data"), "titulo": r.get("titulo"), "frente": frente, "planejado": r["planejado"], "real": r["real"],
                               "confirmado": confirmado, "medido": medido})
    pasta_cal = os.path.join(oper, "calibragem")
    os.makedirs(pasta_cal, exist_ok=True)
    copia = os.path.join(pasta_cal, "tempos_antes_da_v2.json")
    if not os.path.exists(copia):
        shutil.copyfile(caminho, copia)
    _gravar(caminho, novo)
    return True


def garantir_tempos(oper):
    """Chamado antes de ler ou somar no tempos.json: migra o formato antigo uma vez. Nunca levanta erro."""
    try:
        return migrar_tempos(oper)
    except Exception as erro:  # a calibragem nunca pode derrubar o guardião
        print("  (não consegui migrar o tempos.json:", erro, ")")
        return False


# ======================= o que o guardião mostra, aprende e aplica =======================

ATRAPALHOU = ["Subestimei o tempo", "Interrupções", "Faltou informação", "Me distraí", "Sem energia", "Depende de outra pessoa",
              "Imprevistos e tarefas fora do plano", "Reunião demais", "Demorei para começar", "O plano não coube no dia"]
AJUDOU = ["Tarefa clara, com primeiro passo", "Comecei cedo", "Dia com pouca reunião", "Modo execução e foco", "Notificações desligadas",
          "Um agente fez e eu revisei", "Pausas no meio do dia", "Boa noite de sono"]
RESPOSTAS = ("sim", "nao", "as_vezes")
FAIXAS = (("manha", "de manhã", 0, 12 * 60), ("tarde", "à tarde", 12 * 60, 17 * 60), ("noite", "à noite", 17 * 60, 24 * 60))
DIAS_NOME = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
PESADAS = ("copy", "decisao", "criacao", "trafego", "dev", "estudo")  # sem tarefa principal marcada, a primeira destas faz o papel
JANELA = 42           # dias olhados para aprender
JANELA_REPETIDAS = 14
MIN_DADOS = 3         # abaixo disso é hipótese: não vira regra nem pergunta
REPERGUNTAR_APOS = 5  # achado negado volta a ser perguntado se ganhar 5 dados novos
PAUSA_PERGUNTA = 3    # dias sem repetir a mesma pergunta
MAX_LINHAS_PLANO = 12
REGRA_DO_MOTIVO = {
    "Interrupções": "No bloco de foco, notificações fechadas e uma folga curta logo depois dele.",
    "Faltou informação": "Antes de um bloco que depende de informação de alguém, uma tarefa curta de pedir o que falta.",
    "Me distraí": "Tarefa longa em trechos de 25 minutos com pausa.",
    "Depende de outra pessoa": "Cobrar quem falta um dia antes do bloco, não no dia.",
    "Imprevistos e tarefas fora do plano": "Folga reservada no horário em que os imprevistos costumam chegar.",
    "Demorei para começar": "Primeira ação de cada bloco pequena e física, para começar no horário.",
    "Reunião demais": "Reuniões agrupadas, com dias protegidos sem reunião.",
    "O plano não coube no dia": "Plano com uma tarefa a menos e folga no fim do dia.",
}
REGRA_DO_AJUDOU = {
    "Tarefa clara, com primeiro passo": "Todo bloco de criação ou decisão nasce com um primeiro passo concreto e pequeno.",
    "Comecei cedo": "A primeira tarefa pesada logo na chegada, sem aquecimento.",
    "Dia com pouca reunião": "Reuniões agrupadas no mesmo dia, para proteger os outros.",
    "Modo execução e foco": "Lembrar de entrar em execução e de clicar em Iniciar em cada tarefa.",
    "Notificações desligadas": "No bloco de foco, lembrar de fechar as notificações antes de começar.",
    "Um agente fez e eu revisei": "Quando der, propor que um agente de IA faça a primeira versão e a pessoa revise.",
    "Pausas no meio do dia": "Pausa curta entre blocos longos.",
    "Boa noite de sono": "Nada de trabalho depois da hora de parar.",
}
_PALAVRAS_VAZIAS = {"de", "da", "do", "das", "dos", "com", "o", "a", "os", "as", "e", "para", "pra", "na", "no", "nas", "nos", "em", "um", "uma", "ao", "aos", "que", "por"}


def _minutos_hm(hhmm):
    try:
        hh, mm = str(hhmm).split(":")[:2]
        return int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        return None


def _faixa(minuto):
    for chave, nome, ini, fim in FAIXAS:
        if minuto is not None and ini <= minuto < fim:
            return chave, nome
    return None, None


def _nome_faixa(chave):
    return next((n for c, n, _, _ in FAIXAS if c == chave), chave)


def _mediana(valores):
    v = sorted(valores)
    if not v:
        return None
    meio = len(v) // 2
    return v[meio] if len(v) % 2 else (v[meio - 1] + v[meio]) / 2


def _fmt(m):
    m = int(round(m or 0))
    return f"{m} min" if m < 60 else (f"{m // 60}h" if m % 60 == 0 else f"{m // 60}h{m % 60:02d}")


def _curto(t, n=60):
    t = str(t or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0]


def _pasta_cal(oper):
    return os.path.join(oper, "calibragem")


def registro(oper, iso):
    return _ler(os.path.join(oper, "registros", f"registro_{iso}.json")) or {}


def execucao(oper, iso):
    return _ler(os.path.join(oper, "registros", f"execucao_{iso}.json")) or {}


def report(oper, iso):
    return _ler(os.path.join(_pasta_cal(oper), "reports", f"{iso}.json"))


def eventos(oper, desde_iso, ate_iso=None):
    saida = []
    try:
        with open(os.path.join(_pasta_cal(oper), "eventos.jsonl"), encoding="utf-8") as f:
            for linha in f:
                try:
                    ev = json.loads(linha)
                except ValueError:
                    continue
                d = str(ev.get("data") or "")
                if d >= desde_iso and (ate_iso is None or d <= ate_iso):
                    saida.append(ev)
    except OSError:
        pass
    return saida


def _plano_de(oper, iso):
    p = _ler(os.path.join(oper, "planos", f"plano_{iso}.json"))
    if p:
        return p
    p = _ler(os.path.join(oper, "plano_do_dia.json"))
    return p if p and p.get("data") == iso else None


def _trabalhado(sessao):
    total = 0
    for t in sessao.get("trechos") or []:
        a, b = _minutos_hm(t.get("de")), _minutos_hm(t.get("ate"))
        if a is not None and b is not None:
            total += max(0, (b - a) % 1440)
    return total


def _blocos_de_trabalho(reg):
    return [b for b in reg.get("blocos") or [] if not b.get("fixo") and (b.get("natureza") or natureza_do_bloco(b)) != SEM_TEMPO]


def _principal(blocos):
    """A tarefa principal do dia: a marcada no plano; sem marca, a primeira tarefa pesada (deduzida)."""
    marcada = next((b for b in blocos if b.get("principal")), None)
    if marcada:
        return marcada, False
    pesadas = sorted((b for b in blocos if (b.get("natureza") or natureza_do_bloco(b)) in PESADAS),
                     key=lambda b: _minutos_hm((b.get("planejado") or {}).get("inicio") or b.get("inicio")) or 0)
    return (pesadas[0], True) if pesadas else (None, False)


def resumo_do_dia(oper, dia=None):
    """O que o report do dia mostra, montado só com o que o app gravou: a pessoa lê, não digita."""
    dia = dia or date.today()
    iso = dia.isoformat()
    reg = registro(oper, iso)
    blocos = _blocos_de_trabalho(reg)
    feitas = [b for b in blocos if b.get("estado") == "feito"]
    principal, deduzida = _principal(blocos)
    foco = sum(_trabalhado(s) for s in execucao(oper, iso).get("sessoes") or [])
    evs = eventos(oper, iso, iso)
    novas = [t for e in evs if e.get("tipo") == "tarefas_novas" for t in (e.get("tarefas") or [])]
    n_novas = sum(int(e.get("quantidade") or 0) for e in evs if e.get("tipo") == "tarefas_novas")
    imprevistos = [e for e in evs if e.get("tipo") == "imprevisto_encaixado"]
    motivo_do_bloco = {e.get("bloco"): e.get("motivo") for e in evs if e.get("tipo") == "adiamento" and e.get("motivo")}
    motivos = Counter(e["motivo"] for e in evs if e.get("motivo") and e.get("tipo") in ("adiamento", "extensao", "motivo", "imprevisto"))
    estouros = [e for e in evs if e.get("tipo") == "conclusao" and e.get("confirmado") and e.get("natureza") not in SEM_MEDIA
                and (e.get("desvio") or 0) >= max(10, 0.2 * (e.get("planejado") or 0))]
    atrasos = [e["atraso"] for e in evs if e.get("tipo") == "inicio_bloco" and isinstance(e.get("atraso"), (int, float))]
    atraso = _mediana(atrasos)
    replanejou = any(e.get("tipo") in REPLANEJAMENTO for e in evs)
    reunioes = sum(int((b.get("planejado") or {}).get("minutos") or 0) for b in blocos if (b.get("natureza") or natureza_do_bloco(b)) == "reuniao")
    detectados = {m for m in motivos if m in ATRAPALHOU}
    if n_novas + len(imprevistos) >= 3:
        detectados.add("Imprevistos e tarefas fora do plano")
    if atraso is not None and atraso > 15:
        detectados.add("Demorei para começar")
    if replanejou:
        detectados.add("O plano não coube no dia")
    if reunioes >= 180:
        detectados.add("Reunião demais")
    amanha = None
    p = _plano_de(oper, (dia + timedelta(days=1)).isoformat())
    if p:
        primeiros = sorted((b for b in p.get("blocos") or [] if _minutos_hm(b.get("inicio")) is not None), key=lambda b: _minutos_hm(b["inicio"]))
        if primeiros:
            amanha = {"inicio": primeiros[0]["inicio"], "titulo": primeiros[0].get("titulo")}
    r = {"data": iso, "tem_plano": bool(blocos), "planejadas": len(blocos), "feitas": len(feitas),
         "adiadas": [{"titulo": b.get("titulo"), "motivo": motivo_do_bloco.get(b.get("id"))} for b in blocos if b.get("estado") == "adiado"],
         "principal": {"titulo": principal.get("titulo"), "feita": principal.get("estado") == "feito", "deduzida": deduzida} if principal else None,
         "foco_min": foco, "novas": n_novas + len(imprevistos), "novas_titulos": [_curto(t.get("nome"), 50) for t in novas][:5] + [_curto(e.get("titulo"), 50) for e in imprevistos][:3],
         "origens": [{"lista": k, "n": n} for k, n in Counter(t.get("lista") or "?" for t in novas).most_common(3)],
         "estouros": [{"titulo": e.get("titulo"), "planejado": e.get("planejado"), "real": e.get("real")} for e in estouros][:3],
         "atraso_mediano": round(atraso) if atraso is not None else None, "amanha": amanha,
         "detectados": [c for c in ATRAPALHOU if c in detectados]}
    r["frase"] = frase_do_resumo(r)
    return r


def frase_do_resumo(r):
    """O resumo em poucas frases, para a voz falar antes das perguntas do report."""
    if not r.get("tem_plano"):
        return "Hoje não teve plano aprovado."
    partes = [f"Hoje você fez {r['feitas']} de {r['planejadas']} tarefas"]
    pr = r.get("principal")
    if pr:
        partes[0] += ", e a principal saiu" if pr["feita"] else f", e a principal, {_curto(pr['titulo'], 50)}, ficou para depois"
    partes[0] += "."
    if r.get("foco_min", 0) >= 10:
        partes.append(f"{_fmt(r['foco_min'])} de foco medido.")
    if r.get("novas"):
        partes.append(f"Entraram {r['novas']} {'tarefa' if r['novas'] == 1 else 'tarefas'} fora do plano.")
    if r.get("amanha"):
        partes.append(f"Amanhã começa às {r['amanha']['inicio']} com {_curto(r['amanha']['titulo'], 50)}.")
    return " ".join(partes)


def _confirmacoes(oper):
    return _ler(os.path.join(_pasta_cal(oper), "confirmacoes.json")) or {}


def registrar_resposta(oper, achado_id, resposta, n=None, texto=None):
    """Guarda a resposta da pessoa à hipótese do dia (sim, não, às vezes)."""
    if resposta not in RESPOSTAS or not achado_id:
        return False
    c = _confirmacoes(oper)
    c[achado_id] = {"resposta": resposta, "data": date.today().isoformat(), "n": n, "texto": texto}
    os.makedirs(_pasta_cal(oper), exist_ok=True)
    _gravar(os.path.join(_pasta_cal(oper), "confirmacoes.json"), c)
    return True


def marcar_perguntado(oper, achado_id):
    c = _confirmacoes(oper)
    item = c.setdefault(achado_id, {})
    item["perguntado_em"] = date.today().isoformat()
    os.makedirs(_pasta_cal(oper), exist_ok=True)
    _gravar(os.path.join(_pasta_cal(oper), "confirmacoes.json"), c)


def _nivel(achado, conf):
    if achado.get("tipo") == "estimativa":
        return "medido"
    c = conf.get(achado["id"]) or {}
    resp = c.get("resposta")
    if resp == "sim":
        return "confirmado"
    if resp == "nao" and achado["n"] < int(c.get("n") or 0) + REPERGUNTAR_APOS:
        return "negado"
    return "provavel" if achado["n"] >= MIN_DADOS else "hipotese"


def _chave_titulo(titulo):
    """O mesmo assunto com palavras um pouco diferentes ("Aviso 2 com o link..." e "Avisos com o link...") cai na mesma chave."""
    palavras = [p for p in re.sub(r"[^a-z ]", " ", _norm(titulo)).split() if p not in _PALAVRAS_VAZIAS and len(p) > 1]
    palavras = [p[:-1] if len(p) > 3 and p.endswith("s") else p for p in palavras]
    return " ".join(palavras[:4])


def perfil(oper, hoje=None, cfg=None):
    """O que se repete nos últimos JANELA dias. Cada achado traz o que foi visto (texto), o que o plano deve fazer (regra), quantos dados o
    sustentam (n) e o nível. Só o provável e o confirmado chegam ao plano; o provável vira a pergunta do report."""
    hoje = hoje or date.today()
    desde = (hoje - timedelta(days=JANELA)).isoformat()
    ontem = (hoje - timedelta(days=1)).isoformat()
    evs = eventos(oper, desde)
    conf = _confirmacoes(oper)
    dias, cumprimento = [], {}
    for i in range(1, JANELA + 1):
        d = hoje - timedelta(days=i)
        reg = registro(oper, d.isoformat())
        blocos = _blocos_de_trabalho(reg)
        if blocos:
            dias.append(d)
            cumprimento[d.isoformat()] = (sum(1 for b in blocos if b.get("estado") == "feito"), len(blocos))
    reports = {d.isoformat(): report(oper, d.isoformat()) for d in dias}
    reports = {k: v for k, v in reports.items() if v and v.get("versao") == 2}
    achados, acoes = [], []

    # tempo real por natureza (fato medido: não precisa de confirmação)
    garantir_tempos(oper)
    tempos = (_ler(os.path.join(oper, "tempos.json")) or {}).get("tipos") or {}
    naturezas, por_tarefa = {}, {}
    for nome, t in tempos.items():
        recalcular(t)
        conf_regs = [r for r in t.get("registros") or [] if r.get("confirmado")]
        naturezas[nome] = {"rotulo": t.get("rotulo") or rotulo(nome), "confirmados": len(conf_regs), "razao": t.get("razao"), "media_planejado": t.get("media_planejado")}
        for r in conf_regs:
            por_tarefa.setdefault(_chave_titulo(r.get("titulo")), []).append(r)
        razao = t.get("razao")
        if nome in SEM_MEDIA or not razao or len(conf_regs) < MIN_DADOS or 0.8 < razao < 1.2:
            continue
        pct = round(abs(razao - 1) * 100 / 5) * 5
        achados.append({"id": f"estimativa:{nome}", "tipo": "estimativa", "n": len(conf_regs),
                        "texto": f"{rotulo(nome)} costuma levar {pct}% {'a mais' if razao > 1 else 'a menos'} do que o planejado.",
                        "regra": f"Planeje {rotulo(nome).lower()} com {pct}% {'a mais' if razao > 1 else 'a menos'} de tempo."})
    for chave, regs in por_tarefa.items():  # a mesma tarefa repetida: aqui a média em minutos vale
        if chave and len(regs) >= MIN_DADOS:
            media = round(sum(r["real"] for r in regs) / len(regs))
            planejado = round(sum(r["planejado"] for r in regs) / len(regs))
            if planejado and abs(media - planejado) / planejado >= 0.2:
                exemplo = _curto(regs[-1].get("titulo"), 50)
                achados.append({"id": f"tarefa:{chave}", "tipo": "estimativa", "n": len(regs), "texto": f"\"{exemplo}\" leva {_fmt(media)}; o plano dá {_fmt(planejado)}.",
                                "regra": f"Reserve {_fmt(media)} para \"{exemplo}\"."})

    # atraso para começar: por natureza e faixa do dia
    por_nf = {}
    for e in evs:
        if e.get("tipo") == "inicio_bloco" and isinstance(e.get("atraso"), (int, float)) and e.get("natureza") not in SEM_MEDIA:
            faixa, _ = _faixa(_minutos_hm(e.get("planejado")))
            if faixa:
                por_nf.setdefault(e["natureza"], {}).setdefault(faixa, []).append(e["atraso"])
    faixas_atraso = {}
    for nat, por_faixa in por_nf.items():
        med = {f: (_mediana(v), len(v)) for f, v in por_faixa.items()}
        faixas_atraso[nat] = {f: {"mediana": round(m), "n": n} for f, (m, n) in med.items()}
        ruins = [(f, m, n) for f, (m, n) in med.items() if m >= 20 and n >= 2]
        boas = [(f, m, n) for f, (m, n) in med.items() if m <= 5 and n >= 2]
        if ruins and boas:
            f, m, n = max(ruins, key=lambda x: x[1])
            boa = min(boas, key=lambda x: x[1])[0]
            achados.append({"id": f"faixa:{nat}:{f}", "tipo": "faixa", "n": n,
                            "texto": f"Você costuma demorar para começar {rotulo(nat).lower()} {_nome_faixa(f)} (cerca de {_fmt(m)} depois do horário) e começa no horário {_nome_faixa(boa)}.",
                            "regra": f"Ponha {rotulo(nat).lower()} {_nome_faixa(boa)} sempre que der."})

    # o que mais é adiado
    planejadas_nat, adiadas_nat = Counter(), Counter()
    for d in dias:
        for b in _blocos_de_trabalho(registro(oper, d.isoformat())):
            nat = b.get("natureza") or natureza_do_bloco(b)
            planejadas_nat[nat] += 1
            adiadas_nat[nat] += 1 if (b.get("estado") == "adiado" or int(b.get("vezes_adiada") or 0) > 0) else 0
    for nat, k in adiadas_nat.items():
        if nat not in SEM_MEDIA and k >= MIN_DADOS and k / max(1, planejadas_nat[nat]) >= 0.4:
            achados.append({"id": f"adia:{nat}", "tipo": "adiamento", "n": k,
                            "texto": f"{rotulo(nat)} é o que você mais adia ({k} de {planejadas_nat[nat]} nos últimos dias).",
                            "regra": f"{rotulo(nat)} sempre com um primeiro passo de 10 minutos e hora marcada na melhor faixa do dia."})
    adiadas_titulo = Counter(e.get("titulo") for e in evs if e.get("tipo") == "adiamento" and e.get("titulo"))
    concluidas = {e.get("titulo") for e in evs if e.get("tipo") == "conclusao"}
    for titulo, k in adiadas_titulo.most_common():
        if k >= 2 and titulo not in concluidas:
            acoes.append(f"\"{_curto(titulo, 50)}\" já foi adiada {k} vezes: comece por um primeiro passo de 10 minutos.")

    # motivos citados quando a tarefa não termina
    motivos = Counter()
    sem_energia = Counter()
    for e in evs:
        if e.get("motivo") and e.get("tipo") in ("adiamento", "extensao", "motivo", "imprevisto"):
            motivos[e["motivo"]] += 1
            if _norm(e["motivo"]) == "sem energia":
                f, _ = _faixa(_minutos_hm(e.get("hora")))
                if f:
                    sem_energia[f] += 1
    for f, k in sem_energia.items():
        if k >= MIN_DADOS:
            achados.append({"id": f"energia_faixa:{f}", "tipo": "energia", "n": k, "texto": f"Falta energia {_nome_faixa(f)} ({k} vezes nos últimos dias).",
                            "regra": f"{_nome_faixa(f).capitalize()}, só tarefa leve ou operacional."})
    for m, k in motivos.most_common():
        if m in REGRA_DO_MOTIVO and k >= MIN_DADOS:
            achados.append({"id": f"motivo:{_norm(m)}", "tipo": "motivo", "n": k, "texto": f"\"{m}\" é o motivo que mais aparece quando uma tarefa não termina ({k} vezes).",
                            "regra": REGRA_DO_MOTIVO[m]})
    atrapalhou = Counter(c for r in reports.values() for c in set(r.get("atrapalhou") or []))  # o que a pessoa marcou no report
    for m, k in atrapalhou.most_common():
        if m in REGRA_DO_MOTIVO and k >= MIN_DADOS and not any(a["id"] == f"motivo:{_norm(m)}" for a in achados):
            achados.append({"id": f"motivo:{_norm(m)}", "tipo": "motivo", "n": k, "texto": f"\"{m}\" aparece em {k} dos seus reports.", "regra": REGRA_DO_MOTIVO[m]})

    # imprevistos e tarefas fora do plano por dia da semana
    fora = Counter()
    horas_fora = Counter()
    minutos_fora = Counter()
    for e in evs:
        if e.get("tipo") in ("tarefas_novas", "imprevisto_encaixado") and e.get("data") <= ontem:
            dsem = date.fromisoformat(e["data"]).weekday()
            fora[dsem] += int(e.get("quantidade") or 1)
            h = _minutos_hm(e.get("hora"))
            if h is not None:
                horas_fora[(dsem, h // 60)] += 1
            if e.get("tipo") == "imprevisto_encaixado":
                minutos_fora[dsem] += 30
    dias_por_semana = Counter(d.weekday() for d in dias)
    semana = {}
    for dsem, n_dias in dias_por_semana.items():
        media = fora[dsem] / n_dias
        semana[DIAS_NOME[dsem]] = {"dias": n_dias, "fora_do_plano": round(media, 1)}
        if n_dias >= 2 and media >= 2:
            hora = max((hh for (ds, hh) in horas_fora if ds == dsem), key=lambda hh: horas_fora[(dsem, hh)], default=None)
            folga = min(90, max(15, int(round(max(media * 15, minutos_fora[dsem] / n_dias) / 15.0)) * 15))
            achados.append({"id": f"folga:{dsem}", "tipo": "folga", "n": n_dias,
                            "texto": f"Às {DIAS_NOME[dsem]}s entram em média {media:.0f} tarefas ou imprevistos fora do plano" + (f", mais perto das {hora}h." if hora is not None else "."),
                            "regra": f"Às {DIAS_NOME[dsem]}s, reserve {folga} min de folga" + (f" perto das {hora}h." if hora is not None else " no meio do dia.")})

    # energia e o que ajudou, dos reports
    energia_dia = {}
    for iso, r in reports.items():
        if isinstance(r.get("energia"), (int, float)):
            energia_dia.setdefault(date.fromisoformat(iso).weekday(), []).append(r["energia"])
    for dsem, v in energia_dia.items():
        media = sum(v) / len(v)
        semana.setdefault(DIAS_NOME[dsem], {})["energia"] = round(media, 1)
        if len(v) >= MIN_DADOS and media <= 2.5:
            achados.append({"id": f"energia_dia:{dsem}", "tipo": "energia", "n": len(v), "texto": f"Às {DIAS_NOME[dsem]}s sua energia costuma ser baixa (média {media:.1f} de 5).",
                            "regra": f"Às {DIAS_NOME[dsem]}s, tarefa pesada só no começo do dia e uma tarefa a menos no plano."})
    bons = [iso for iso, (f, p) in cumprimento.items() if p >= 3 and f / p >= 0.8 and iso in reports]
    for chip in AJUDOU:
        k = sum(1 for iso in bons if chip in (reports[iso].get("ajudou") or []))
        if k >= MIN_DADOS and k / max(1, len(bons)) >= 0.6:
            achados.append({"id": f"ajudou:{_norm(chip)}", "tipo": "ajudou", "n": k, "texto": f"Nos seus dias bons quase sempre aparece: {chip.lower()}.", "regra": REGRA_DO_AJUDOU[chip]})

    # o que entra fora do plano e se repete (vira proposta de rotina no fechamento da semana)
    desde_rep = (hoje - timedelta(days=JANELA_REPETIDAS)).isoformat()
    grupos = {}
    for e in evs:
        if e.get("data") < desde_rep:
            continue
        titulos = [t.get("nome") for t in (e.get("tarefas") or [])] if e.get("tipo") == "tarefas_novas" else ([e.get("titulo")] if e.get("tipo") == "imprevisto_encaixado" else [])
        for t in titulos:
            chave = _chave_titulo(t)
            if chave:
                g = grupos.setdefault(chave, {"titulos": [], "dias": set(), "listas": Counter(), "horas": Counter()})
                g["titulos"].append(t)
                g["dias"].add(e["data"])
                if e.get("tipo") == "tarefas_novas":
                    g["listas"][next((x.get("lista") for x in e.get("tarefas") or [] if x.get("nome") == t), None) or "?"] += 1
                h = _minutos_hm(e.get("hora"))
                if h is not None:
                    g["horas"][h // 60] += 1
    repetidas = []
    for chave, g in grupos.items():
        if len(g["titulos"]) >= MIN_DADOS:
            hora = g["horas"].most_common(1)[0][0] if g["horas"] else None
            exemplo = Counter(g["titulos"]).most_common(1)[0][0]
            repetidas.append({"chave": chave, "exemplo": exemplo, "vezes": len(g["titulos"]), "dias": len(g["dias"]), "hora": hora,
                              "lista": g["listas"].most_common(1)[0][0] if g["listas"] else None})
            perto = f" perto das {hora}h" if hora is not None else ""
            achados.append({"id": f"rotina:{chave}", "tipo": "rotina", "n": len(g["titulos"]),
                            "texto": f"\"{_curto(exemplo, 50)}\" entrou {len(g['titulos'])} vezes fora do plano em {JANELA_REPETIDAS} dias.",
                            "pergunta": f"\"{_curto(exemplo, 50)}\" entrou {len(g['titulos'])} vezes fora do plano nas últimas duas semanas. Isso vai continuar aparecendo?",
                            "regra": f"Reserve um horário para \"{_curto(exemplo, 50)}\"{perto}, antes de a tarefa aparecer; no fechamento da semana, proponha virar bloco fixo na semana-base ou POP."})
    fora_semana = sum(int(e.get("quantidade") or 1) for e in evs if e.get("tipo") in ("tarefas_novas", "imprevisto_encaixado") and e.get("data") >= (hoje - timedelta(days=7)).isoformat())
    if fora_semana >= 8:
        acoes.append(f"Entraram {fora_semana} tarefas fora do plano nos últimos 7 dias. No fechamento, revise o que se repete e o que dá para prever.")

    for a in achados:
        a["nivel"] = _nivel(a, conf)
        c = conf.get(a["id"]) or {}
        if c.get("resposta"):
            a["resposta"] = c["resposta"]
        if a["tipo"] == "estimativa":
            a["pergunta"] = None
        elif not a.get("pergunta"):
            a["pergunta"] = f"Percebi uma coisa: {a['texto'][0].lower()}{a['texto'][1:]} Isso é verdade?"
    ordem = {"confirmado": 0, "medido": 1, "provavel": 2, "hipotese": 3, "negado": 4}
    achados.sort(key=lambda a: (ordem.get(a["nivel"], 9), -a["n"]))
    feitos = sum(f for f, _ in cumprimento.values())
    planejados = sum(p for _, p in cumprimento.values())
    return {"gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"), "janela_dias": JANELA, "dias_com_plano": len(dias),
            "cumprimento": round(feitos / planejados, 2) if planejados else None, "naturezas": naturezas, "atraso_por_faixa": faixas_atraso,
            "semana": semana, "motivos": [{"motivo": m, "vezes": k} for m, k in motivos.most_common(6)], "repetidas": repetidas,
            "achados": achados, "acoes": acoes[:4]}


def secao_do_plano(p):
    """As poucas linhas que o plano recebe: só o medido, o provável e o confirmado. Vazio quando ainda não há nada firme."""
    linhas = []
    for a in p.get("achados") or []:
        if a["nivel"] in ("confirmado", "medido", "provavel"):
            marca = {"confirmado": "confirmado por ela", "medido": "medido", "provavel": f"provável, {a['n']} dados"}[a["nivel"]]
            linhas.append(f"- [{a['id']}] {a['regra']} ({marca})")
    for acao in p.get("acoes") or []:
        linhas.append(f"- {acao}")
    if not linhas:
        return ""
    linhas = linhas[:MAX_LINHAS_PLANO]
    return ("CALIBRAGEM (o que o guardião aprendeu com o uso; vale acima do palpite e abaixo do que a pessoa disser hoje. "
            "O provável é ajuste leve e sempre dito no por_que_agora. Bloco que aplica uma linha leva \"aprendizado\": \"<id entre colchetes>\"):\n" + "\n".join(linhas))


def pode_gravar(oper):
    """A pasta é uma pasta operacional de verdade? A pasta da skill (no clone ou instalada) tem o SKILL.md: ali a calibragem só lê, nunca grava."""
    return not os.path.exists(os.path.join(oper, "SKILL.md"))


def atualizar_perfil(oper, forcar=False, hoje=None):
    """Recalcula o perfil uma vez por dia (ou quando chamado com forcar, como depois do report) e grava a seção do plano em arquivo."""
    caminho = os.path.join(_pasta_cal(oper), "perfil_comportamento.json")
    atual = _ler(caminho)
    hoje = hoje or date.today()
    if atual and not forcar and str(atual.get("gerado_em", "")).startswith(hoje.isoformat()):
        return atual
    try:
        p = perfil(oper, hoje)
    except Exception as erro:  # a calibragem nunca pode derrubar o guardião
        print("  (não consegui recalcular a calibragem:", erro, ")")
        return atual or {}
    if not pode_gravar(oper):
        return p
    os.makedirs(_pasta_cal(oper), exist_ok=True)
    _gravar(caminho, p)
    secao = secao_do_plano(p)
    with open(os.path.join(_pasta_cal(oper), "calibragem_para_o_plano.md"), "w", encoding="utf-8") as f:
        f.write(secao or "CALIBRAGEM: ainda sem nada firme. O guardião precisa de mais dias de uso para afirmar alguma coisa.\n")
    return p


def hipotese_do_dia(oper, p=None, hoje=None):
    """Uma pergunta por dia, no máximo: o achado provável com mais dados que ainda não foi respondido nem perguntado nos últimos dias."""
    p = p or atualizar_perfil(oper)
    hoje = hoje or date.today()
    conf = _confirmacoes(oper)
    for a in p.get("achados") or []:
        if a["nivel"] != "provavel" or not a.get("pergunta"):
            continue
        c = conf.get(a["id"]) or {}
        if c.get("resposta") in ("sim", "as_vezes") and a["n"] < int(c.get("n") or 0) + REPERGUNTAR_APOS:
            continue
        perguntado = c.get("perguntado_em")
        if perguntado and perguntado != hoje.isoformat() and (hoje - date.fromisoformat(perguntado)).days < PAUSA_PERGUNTA:
            continue
        return {"id": a["id"], "texto": a["pergunta"], "n": a["n"]}
    return None


def registrar_mudancas(oper, plano, p=None):
    """Plano aprovado com blocos que aplicam um aprendizado ("aprendizado": "<id>"): vira "O que mudou no plano" na tela, sem o Claude escrever nada."""
    p = p or atualizar_perfil(oper)
    por_id = {a["id"]: a for a in p.get("achados") or []}
    linhas = []
    for b in plano.get("blocos") or []:
        ids = b.get("aprendizado")
        for i in ([ids] if isinstance(ids, str) else (ids or [])):
            a = por_id.get(i)
            if a:
                linhas.append({"data": plano.get("data") or date.today().isoformat(), "id": i, "regra": a["regra"], "titulo": b.get("titulo"), "inicio": b.get("inicio")})
    if linhas:
        os.makedirs(_pasta_cal(oper), exist_ok=True)
        with open(os.path.join(_pasta_cal(oper), "mudancas.jsonl"), "a", encoding="utf-8") as f:
            for linha in linhas:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return linhas


# ---------------- o report falado: a resposta livre vira os mesmos toques da tela ----------------

FALA_ATRAPALHOU = {
    "Subestimei o tempo": r"subestim|demorou mais|levou mais tempo|nao deu tempo|faltou tempo",
    "Interrupções": r"interromp|interrup|ligac|ligaram|mensage|notifica",
    "Faltou informação": r"faltou informac|sem informac|faltou dado|nao tinha a informac",
    "Me distraí": r"distra|celular|rede social|instagram|procrastin|enrolei",
    "Sem energia": r"cansad|sem energia|sono|exaust|desanim|esgotad",
    "Depende de outra pessoa": r"depend|esperando (o|a|resposta)|aguardando",
    "Imprevistos e tarefas fora do plano": r"imprevist|urgen|apareceu|tarefa nova|pedido novo|pediram",
    "Reunião demais": r"reuni|\bcall",
    "Demorei para começar": r"demorei (para|pra) comecar|comecei tarde|custei (a|para|pra) comecar",
    "O plano não coube no dia": r"nao coube|muita coisa|plano grande|dia cheio|apertado",
}
FALA_AJUDOU = {
    "Tarefa clara, com primeiro passo": r"\bclar|primeiro passo|sabia o que fazer",
    "Comecei cedo": r"\bcedo\b|comecei logo",
    "Dia com pouca reunião": r"sem reuni|pouca reuni|nenhuma reuni",
    "Modo execução e foco": r"\bfoco|modo execu|cronometr|iniciar",
    "Notificações desligadas": r"notifica|celular longe|nao perturbe|silencio",
    "Um agente fez e eu revisei": r"agente|claude|\bia\b|automac",
    "Pausas no meio do dia": r"pausa|intervalo|descans",
    "Boa noite de sono": r"dormi|noite de sono",
}
_NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5}


def chips_da_fala(texto, qual):
    """A fala do report vira os chips da tela ("atrapalhou" ou "ajudou"). "Nada" e "nenhum" devolvem a lista vazia."""
    t = _norm(texto)
    regras = FALA_ATRAPALHOU if qual == "atrapalhou" else FALA_AJUDOU
    return [chip for chip, r in regras.items() if re.search(r, t)]


def energia_da_fala(texto):
    t = _norm(texto)
    m = re.search(r"\b([1-5])\b", t)
    if m:
        return int(m.group(1))
    for palavra, n in _NUMEROS.items():
        if re.search(rf"\b{palavra}\b", t):
            return n
    return None


def resposta_da_fala(texto):
    """Sim, não ou às vezes, para a hipótese do dia. None se a fala não responde."""
    t = _norm(texto)
    if re.search(r"as vezes|depende|mais ou menos|um pouco|em parte", t):
        return "as_vezes"
    if re.search(r"^(nao|nem)\b|nao e (bem )?(isso|verdade)|errado|de jeito nenhum", t):
        return "nao"
    if re.search(r"^(sim|e sim|exato|isso|verdade|com certeza|claro|aham|uhum)\b|e verdade|isso mesmo|faz sentido", t):
        return "sim"
    return None


def registrar_evento(oper, tipo, **extra):
    """Uma linha no eventos.jsonl, no mesmo formato do painel. Para o guardião do chat (fechamento da semana, rotina aceita)."""
    agora = datetime.now()
    linha = {"ts": agora.strftime("%Y-%m-%d %H:%M:%S"), "data": agora.strftime("%Y-%m-%d"), "hora": agora.strftime("%H:%M"), "tipo": tipo,
             **{k: v for k, v in extra.items() if v is not None}}
    os.makedirs(_pasta_cal(oper), exist_ok=True)
    with open(os.path.join(_pasta_cal(oper), "eventos.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return linha


def ultimas_mudancas(oper, n=4):
    try:
        with open(os.path.join(_pasta_cal(oper), "mudancas.jsonl"), encoding="utf-8") as f:
            linhas = [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError):
        return []
    saida = []
    for m in reversed(linhas):
        texto = f"{m['data'][8:10]}/{m['data'][5:7]}: {_curto(m.get('titulo'), 50)}" + (f" às {m['inicio']}" if m.get("inicio") else "") + f". {m.get('regra')}"
        if texto not in saida:
            saida.append(texto)
        if len(saida) >= n:
            break
    return saida


def main(argv=None):
    """Para o guardião do chat, sem abrir o painel:
    python calibragem_motor.py --perfil                     recalcula e mostra o que a calibragem já sabe (a seção do plano e o que se repete)
    python calibragem_motor.py --fechamento                 registra que o fechamento da semana foi feito
    python calibragem_motor.py --rotina-aceita "<id>"       a pessoa aceitou transformar o que se repete em rotina (bloco fixo, POP ou reserva)"""
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--oper", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--perfil", action="store_true")
    ap.add_argument("--fechamento", action="store_true")
    ap.add_argument("--rotina-aceita", dest="rotina")
    a = ap.parse_args(argv)
    if a.fechamento:
        registrar_evento(a.oper, "fechamento_semanal")
        print("fechamento da semana registrado")
    if a.rotina:
        registrar_evento(a.oper, "rotina_aceita", id=a.rotina)
        registrar_resposta(a.oper, a.rotina, "sim")
        print(f"rotina aceita: {a.rotina}")
    if a.perfil or not (a.fechamento or a.rotina):
        p = atualizar_perfil(a.oper, forcar=True)
        print(secao_do_plano(p) or "CALIBRAGEM: ainda sem nada firme.")
        for r in p.get("repetidas") or []:
            print(f"- se repete fora do plano: \"{r['exemplo']}\" ({r['vezes']} vezes em {r['dias']} dias" + (f", perto das {r['hora']}h" if r.get("hora") is not None else "")
                  + (f", lista {r['lista']}" if r.get("lista") else "") + f") id rotina:{r['chave']}")
        for x in p.get("achados") or []:
            if x["nivel"] == "hipotese":
                print(f"- hipótese ({x['n']} dados, ainda não vale): {x['texto']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
