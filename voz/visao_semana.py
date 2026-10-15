"""Visão da semana: o guardião nunca planeja um dia sem enxergar os outros.

Calcula, sem rede e sem Claude, a semana inteira (hoje até daqui a 7 dias): o plano de cada dia, quanto sobra de tempo (e quanto desse
tempo é horário nobre), o que cada bloco deve e as tarefas do ClickUp que ainda não têm lugar em plano nenhum. Vai no contexto da sessão
(guardiao_voz.contexto_proximos_dias) e alimenta a conferência de semana (conferencia_plano.conferir_semana).

Pasta operacional esperada: plano_do_dia.json, planos\\plano_AAAA-MM-DD.json e resumo_clickup.json."""
import json
import os
import re
from datetime import date, datetime, timedelta

# Padrões (a rotina de quem estreou o roteador). Cada pessoa tem a sua em config.json, rotina: chegada, horario_nobre e
# parar_por_dia. aplicar_rotina() troca estes valores ao importar; o que faltar no config fica no padrão e vira pendência (checar_config.py).
CHEGADA = 8 * 60 + 40
NOBRE_MANHA = (8 * 60 + 40, 13 * 60)
NOBRE_NOITE_INICIO = 18 * 60
PARAR_PADRAO = {0: 19 * 60, 1: 19 * 60 + 20, 2: 19 * 60 + 20, 3: 19 * 60 + 20, 4: 19 * 60 + 20}
_PADRAO = (CHEGADA, NOBRE_MANHA, NOBRE_NOITE_INICIO)
PARAR_CONFIG = {}  # rotina.parar_por_dia da pessoa: vale acima do perfil e do padrão
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
DIA_POR_NOME = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "sáb": 5, "dom": 6}
HORIZONTE_DIAS = 7


def aplicar_rotina(cfg):
    """Lê do config.json a rotina da pessoa (chegada, horário nobre, hora de parar por dia). Campo ausente ou inválido: fica o padrão."""
    global CHEGADA, NOBRE_MANHA, NOBRE_NOITE_INICIO
    CHEGADA, NOBRE_MANHA, NOBRE_NOITE_INICIO = _PADRAO
    rotina = (cfg or {}).get("rotina") or {}
    try:
        if rotina.get("chegada"):
            CHEGADA = hm(rotina["chegada"])
    except (ValueError, TypeError):
        pass
    faixas = rotina.get("horario_nobre")
    if isinstance(faixas, list) and faixas:
        try:
            primeira = faixas[0]
            NOBRE_MANHA = (hm(primeira[0]), hm(primeira[1]) if str(primeira[1]).lower() != "fim" else 24 * 60)
            NOBRE_NOITE_INICIO = hm(faixas[1][0]) if len(faixas) > 1 else 24 * 60
        except (ValueError, TypeError, IndexError):
            pass
    PARAR_CONFIG.clear()
    for chave, valor in (rotina.get("parar_por_dia") or {}).items():
        d = DIA_POR_NOME.get(str(chave).strip().lower()[:3])
        try:
            if d is not None:
                PARAR_CONFIG[d] = hm(valor)
        except (ValueError, TypeError):
            pass


def hm(texto):
    h, m = str(texto).split(":")[:2]
    return int(h) * 60 + int(m)


def fmt(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def duracao(minutos):
    return f"{minutos // 60}h{minutos % 60:02d}" if minutos >= 60 else f"{minutos}min"


def _json(caminho):
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def hora_de_parar(dia, memoria=None):
    """Hora de parar do dia (minutos). Vale rotina.parar_por_dia do config.json; sem ele, "Segunda: ... para às 19h" e "Terça a sexta: ... 19h20"
    do perfil; sem os dois, o padrão."""
    if dia.weekday() in PARAR_CONFIG:
        return PARAR_CONFIG[dia.weekday()]
    parar = PARAR_PADRAO.get(dia.weekday(), 19 * 60 + 20)
    try:
        with open(os.path.join(memoria, "perfil.md"), encoding="utf-8-sig") as f:
            perfil = f.read()
        if dia.weekday() == 0:
            m = re.search(r"Segunda:[^.\n]*?para às (\d{1,2})h(\d{2})?", perfil)
        else:
            m = re.search(r"Terça a sexta:[^.\n]*?(\d{1,2})h(\d{2})?", perfil)
        if m:
            parar = int(m.group(1)) * 60 + int(m.group(2) or 0)
    except (OSError, TypeError):
        pass
    return parar


def carregar_planos(oper, hoje=None):
    """{AAAA-MM-DD: plano} de hoje em diante. O plano de hoje vem de plano_do_dia.json; os outros, de planos\\."""
    hoje = hoje or date.today()
    iso = hoje.isoformat()
    planos = {}
    pasta = os.path.join(oper, "planos")
    try:
        nomes = sorted(os.listdir(pasta))
    except OSError:
        nomes = []
    for n in nomes:
        m = re.match(r"plano_(\d{4}-\d{2}-\d{2})\.json$", n)
        if m and m.group(1) >= iso:
            p = _json(os.path.join(pasta, n))
            if isinstance(p, dict):
                planos[m.group(1)] = p
    hoje_plano = _json(os.path.join(oper, "plano_do_dia.json"))
    if isinstance(hoje_plano, dict) and str(hoje_plano.get("data") or "") >= iso:
        planos[str(hoje_plano["data"])] = hoje_plano
    return planos


def pre_planos_do_clickup(oper, planos, hoje=None):
    """Dias sem plano gravado: o que já está agendado no ClickUp (data e hora) vira o pré-plano daquele dia.
    É a semana que foi montada antes (no Claude Code ou à mão) e que o guardião precisa respeitar."""
    hoje = hoje or date.today()
    limite = (hoje + timedelta(days=HORIZONTE_DIAS)).isoformat()
    resumo = _json(os.path.join(oper, "resumo_clickup.json")) or {}
    em_plano = {b.get("clickup_id") for p in planos.values() for b in (p.get("blocos") or []) if b.get("clickup_id")}
    pre = {}
    for t in resumo.get("tarefas") or []:
        dia = str(t.get("prazo") or "")
        if t.get("aprovar") or t.get("id") in em_plano or dia in planos or not (hoje.isoformat() <= dia <= limite):
            continue
        p = pre.setdefault(dia, {"data": dia, "status": "pré-planejado no ClickUp", "origem": "clickup", "blocos": [], "sem_hora": []})
        bloco = {"titulo": t.get("nome"), "clickup_id": t.get("id"), "frente": t.get("lista") or "?"}
        if t.get("inicio") and t.get("fim"):
            p["blocos"].append(dict(bloco, inicio=t["inicio"], fim=t["fim"]))
        else:
            p["sem_hora"].append(bloco)
    return pre


def planos_da_semana(oper, hoje=None):
    """Planos gravados mais os pré-planos do ClickUp para os dias sem plano."""
    planos = carregar_planos(oper, hoje)
    planos.update(pre_planos_do_clickup(oper, planos, hoje))
    return planos


def _intervalos(plano, ignorar=()):
    lista = []
    for b in (plano.get("blocos") or []):
        if b.get("id") in ignorar:
            continue
        try:
            lista.append((hm(b["inicio"]), hm(b["fim"])))
        except (KeyError, ValueError, TypeError):
            pass
    for f in (plano.get("fixos") or []):
        try:
            lista.append((hm(f["inicio"]), hm(f["fim"])))
        except (KeyError, ValueError, TypeError):
            pass
    return sorted(lista)


def _livre_em(janela, ocupados):
    """Minutos livres dentro de janela (ini, fim) descontando os intervalos ocupados (que podem se sobrepor)."""
    ini, fim = janela
    if fim <= ini:
        return 0
    livre, cursor = 0, ini
    for a, b in ocupados:
        if b <= cursor:
            continue
        if a >= fim:
            break
        livre += max(0, min(a, fim) - cursor)
        cursor = max(cursor, b)
    livre += max(0, fim - cursor)
    return livre


def livre_do_dia(plano, dia, memoria=None, a_partir_de=None, ignorar=()):
    """(livre_total, livre_nobre) em minutos, do início do dia (ou de a_partir_de) até a hora de parar."""
    parar = hora_de_parar(dia, memoria)
    ini = max(CHEGADA, a_partir_de or 0)
    ocupados = _intervalos(plano or {}, ignorar)
    total = _livre_em((ini, parar), ocupados)
    nobre = _livre_em((max(ini, NOBRE_MANHA[0]), NOBRE_MANHA[1]), ocupados) + _livre_em((max(ini, NOBRE_NOITE_INICIO), parar), ocupados)
    return total, nobre


def _chave(bloco):
    """Identidade de um bloco entre planos: o id da tarefa no ClickUp ou, sem ele, o título normalizado."""
    return bloco.get("clickup_id") or re.sub(r"\s+", " ", str(bloco.get("titulo") or "").lower()).strip()


def texto(oper, memoria=None, hoje=None, agora_min=None, feitos_hoje=(), incluir_hoje=True):
    """A semana em texto compacto, para o contexto da sessão. Sem incluir_hoje, começa amanhã (o plano de hoje vai à parte e muda a cada turno)."""
    hoje = hoje or date.today()
    aplicar_rotina(_json(os.path.join(oper, "config.json")))  # relida a cada vez: a pessoa pode ter acabado de completar a rotina
    planos = carregar_planos(oper, hoje)
    pre = pre_planos_do_clickup(oper, planos, hoje)
    resumo = _json(os.path.join(oper, "resumo_clickup.json")) or {}
    tarefas = resumo.get("tarefas") or []
    limite = hoje + timedelta(days=HORIZONTE_DIAS)
    linhas = ["VISÃO DA SEMANA (" + ("" if incluir_hoje else "de amanhã em diante; hoje está no PLANO DE HOJE. ") + "Calculada com o que está gravado; leia inteira antes de mexer em qualquer dia):"]
    ids_em_plano = set()
    if not incluir_hoje:
        ids_em_plano.update(b.get("clickup_id") for b in (planos.get(hoje.isoformat()) or {}).get("blocos") or [] if b.get("clickup_id"))
    for i in range(0 if incluir_hoje else 1, HORIZONTE_DIAS + 1):
        dia = hoje + timedelta(days=i)
        iso = dia.isoformat()
        plano = planos.get(iso) or pre.get(iso)
        if dia.weekday() >= 5 and not plano:
            continue
        parar = hora_de_parar(dia, memoria)
        cab = f"{DIAS[dia.weekday()]} {dia:%d/%m} (para às {fmt(parar)})"
        if not plano:
            linhas.append(f"{cab}: nada gravado nem agendado no ClickUp. Dia livre para planejar.")
            continue
        if plano.get("origem") == "clickup":
            ids_em_plano.update(b["clickup_id"] for b in plano["blocos"] + plano["sem_hora"])
        total, nobre = livre_do_dia(plano, dia, memoria, agora_min if i == 0 else None, feitos_hoje if i == 0 else ())
        linhas.append(f"{cab} [{plano.get('status') or '?'}]: livre {duracao(total)}, dos quais {duracao(nobre)} em horário nobre")
        for b in sorted(plano.get("blocos") or [], key=lambda x: x.get("inicio") or ""):
            if b.get("clickup_id"):
                ids_em_plano.add(b["clickup_id"])
            extra = []
            if b.get("prazo_final"):
                extra.append(f"prazo final {b['prazo_final']}")
            if b.get("reserva_post"):
                extra.append(f"reserva do post de {b['reserva_post']}")
            if i == 0 and b.get("id") in feitos_hoje:
                extra.append("feito")
            linhas.append(f"  {b.get('inicio')}-{b.get('fim')} {b.get('titulo')} ({b.get('frente') or '?'})" + (f" [{'; '.join(extra)}]" if extra else ""))
        for f in plano.get("fixos") or []:
            linhas.append(f"  {f.get('inicio')}-{f.get('fim')} {f.get('titulo')} (fixo)")
        for b in plano.get("sem_hora") or []:
            linhas.append(f"  sem hora: {b.get('titulo')} ({b.get('frente')})")
    sem_lugar = []
    for t in tarefas:
        prazo = str(t.get("prazo") or "")
        primeiro = hoje if incluir_hoje else hoje + timedelta(days=1)
        if t.get("id") in ids_em_plano or t.get("aprovar") or not (primeiro.isoformat() <= prazo <= limite.isoformat()):
            continue
        sem_lugar.append(f"{prazo} {t.get('inicio') or ''} | {t.get('nome')} ({t.get('lista', '')}) id {t.get('id')}")
    if sem_lugar:
        linhas.append("TAREFAS DO CLICKUP AGENDADAS EM DIA QUE JÁ TEM PLANO, MAS FORA DELE (decida: entra no plano, muda de dia ou foi substituída; nunca fica esquecida):")
        linhas += sem_lugar[:25]
    linhas.append(REGRAS_DA_SEMANA)
    return "\n".join(linhas)


REGRAS_DA_SEMANA = (
    "COMO USAR A SEMANA (valem em todo pedido que mexe em horário):\n"
    "0. Tarefa nova, ou tarefa que muda de dia: rode ANTES o roteador (powershell -ExecutionPolicy Bypass -File onde_cabe.ps1 -Minutos N -Tipo pesado|design|leve "
    "-Prazo AAAA-MM-DD -Frente X -Titulo \"...\" [-DependeDias N] [-Estender AAAA-MM-DD=HH:MM só se ela autorizou], na pasta operacional). "
    "Ele faz a conta e diz o nível: 1 = só o plano de hoje; 2 = esta visão da semana; 3 = o horizonte que ele imprime. Leia só o que o nível pede, "
    "use o horário 1 que ele recomenda e, se escolher outro, diga por quê. Se ele trouxer ALERTAS, diga a ela o que importa para a decisão em uma frase.\n"
    "1. Mexer num dia é mexer na semana. Tarefa que sai de um dia entra em outro na MESMA resposta (grave primeiro o plano do dia que recebe, depois o do dia que perde). "
    "Nunca \"refaço a sexta depois\". Dia \"pré-planejado no ClickUp\" é a semana já combinada com ela: respeite o que está lá e, se mexer, grave o plano completo daquele dia.\n"
    "2. Tarefa nova com prazo: ponha \"prazo_final\" (AAAA-MM-DD) no bloco e encaixe no último horário bom que ainda cumpre o prazo com 1 dia útil de folga. "
    "Tarefa de agência ou operacional com folga não ocupa horário nobre (8h40 às 13h e depois das 18h) de dia cheio: vai para o fim do dia ou para perto do prazo. "
    "O horário nobre é do que é importante e urgente (campanha com data, post do dia, stories da campanha).\n"
    "3. Toda proposta diz a consequência em uma frase: o que sai de lugar nos outros dias por causa desta mudança.\n"
    "4. Etapas do mesmo tipo vão na ordem das datas de postagem: o design do post que sai primeiro vem antes. Post fixo (seg, qua, sex) nunca sai por dedução; só se ela mandar.\n"
    "5. Bloco que muda de dia mantém o \"prazo_final\" que já tinha.\n"
    "6. Antes de mostrar uma proposta, confira a semana inteira contra ela: cada post de seg, qua e sex tem copy e design antes do dia dele, "
    "cada prazo final é cumprido e nada pré-planejado sumiu. O servidor nega a gravação em que uma tarefa some da semana, passa do prazo final "
    "ou toma o horário nobre de um dia cheio sendo tarefa com folga."
)


aplicar_rotina(_json(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")))
