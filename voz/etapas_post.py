"""Etapas de post (copy, design, manychat, relatório): quem decide a data é o GUARDIÃO, não o ClickUp (decisão da Milena, 2026-10-15).

As tarefas de copy e de design nascem de uma automação do ClickUp, com um prazo que é só SUGESTÃO. O guardião replaneja sempre: a etapa termina antes da
data de postagem e entra na agenda do melhor jeito (copies juntas, designs juntos, copy antes do design de cada post). Exceção: tarefa fixa (reunião, aula,
compromisso com hora marcada por outra pessoa), que mantém a data do ClickUp. Aprovado o plano, a data nova vai para o ClickUp.

Regras de data de cada tipo:
- copy, design, manychat: terminam até o fim do DIA ANTERIOR ao da postagem (limite). Sem a data do post (nem pela tarefa mãe, nem pelo título), o prazo do
  ClickUp vira o limite, por falta de informação melhor;
- relatório: nunca antes de 24h da postagem (abre no dia seguinte), sem limite.
Este módulo só classifica e calcula datas; não decide o horário (isso é do plano)."""
import re
import unicodedata
from datetime import date, timedelta

COPY = re.compile(r"^\s*(\[?copy\]?\b|roteiro\b|legenda\b)", re.I)
DESIGN = re.compile(r"^\s*(\[?design\]?\b|arte\b)", re.I)
MANYCHAT = re.compile(r"^\s*\[?manychat\b", re.I)
RELATORIO = re.compile(r"^\s*\[?(preencher relat|relat[oó]rio\b)", re.I)
POSTA_NO_TITULO = re.compile(r"posta\w*\s+(?:(?:seg|ter|qua|qui|sex|s[aá]b|dom)\w*\s+)?(\d{1,2})\b|\bdo dia (\d{1,2})\b", re.I)


def _norm(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def tipo_da_etapa(nome):
    n = str(nome or "")
    if RELATORIO.match(n):
        return "relatorio"
    if MANYCHAT.match(n):
        return "manychat"
    if COPY.match(n):
        return "copy"
    if DESIGN.match(n):
        return "design"
    return None


def _data(txt):
    try:
        return date.fromisoformat(str(txt or "")[:10])
    except ValueError:
        return None


def _mae_da_etapa(tarefa, maes):
    for m in maes or []:
        if any(e.get("id") == tarefa.get("id") for e in m.get("etapas") or []):
            return m
    return None


def _post_pela_mae(tarefa, maes):
    m = _mae_da_etapa(tarefa, maes)
    return _data(m.get("prazo")) if m else None


def _post_pelo_titulo(tarefa):
    m = POSTA_NO_TITULO.search(str(tarefa.get("nome") or ""))
    sugerida = _data(tarefa.get("prazo"))
    if not m or not sugerida:
        return None
    dia = int(m.group(1) or m.group(2))
    for meses in (0, 1):  # o dia citado é do mesmo mês da sugestão ou do seguinte
        ano, mes = sugerida.year + (sugerida.month - 1 + meses) // 12, (sugerida.month - 1 + meses) % 12 + 1
        try:
            candidata = date(ano, mes, dia)
        except ValueError:
            continue
        if candidata >= sugerida:
            return candidata
    return None


def info(tarefa, maes=()):
    """Dados da etapa de post ou None (tarefa que não é etapa: segue como está). Chaves: id, titulo, tipo, post, limite, abre, sugestao."""
    tipo = tipo_da_etapa(tarefa.get("nome"))
    if not tipo or tarefa.get("aprovar"):
        return None
    post = _post_pela_mae(tarefa, maes) or _post_pelo_titulo(tarefa)
    sugestao = _data(tarefa.get("prazo"))
    limite = abre = None
    if tipo == "relatorio":
        abre = post + timedelta(days=1) if post else None
    else:
        limite = post - timedelta(days=1) if post else sugestao
    mae = _mae_da_etapa(tarefa, maes)
    return {"id": tarefa.get("id"), "titulo": tarefa.get("nome"), "tipo": tipo, "post": post, "limite": limite, "abre": abre, "sugestao": sugestao,
            "mae": mae.get("id") if mae else None}


def datas_por_mae(tarefas, maes=()):
    """{id da mãe: {"copy": data, "design": data}} com as datas que o ClickUp tem hoje (para achar copy depois do design do mesmo post)."""
    saida = {}
    for t in tarefas or []:
        e = info(t, maes)
        d = _data(t.get("prazo"))
        if e and e["mae"] and e["tipo"] in ("copy", "design") and d:
            saida.setdefault(e["mae"], {})[e["tipo"]] = d
    return saida


def violacao(e, tarefa, por_mae=None):
    """Por que a data de uma etapa não serve (texto) ou None. Vale para o que o guardião marcou ANTES de existirem estas regras: a data dele não é prova de que está certa."""
    if not e:
        return None
    prazo = _data(tarefa.get("prazo"))
    if not prazo:
        return None
    if e["limite"] and prazo > e["limite"]:
        return f"passa do limite da postagem (post de {e['post']:%d/%m}, terminar até {e['limite']:%d/%m})" if e["post"] else f"passa do limite ({e['limite']:%d/%m})"
    if e["abre"] and prazo < e["abre"]:
        return f"relatório antes de 24h da postagem (só a partir de {e['abre']:%d/%m})"
    pares = (por_mae or {}).get(e["mae"]) or {}
    if e["tipo"] == "copy" and pares.get("design") and pares["design"] < prazo:
        return f"a copy ({prazo:%d/%m}) vem depois do design do mesmo post ({pares['design']:%d/%m})"
    if e["tipo"] == "design" and pares.get("copy") and pares["copy"] > prazo:
        return f"o design ({prazo:%d/%m}) vem antes da copy do mesmo post ({pares['copy']:%d/%m})"
    return None


def replanejar(e, classe, tarefa, por_mae=None):
    """A etapa é do guardião replanejar? Sempre quando o prazo do ClickUp é só sugestão; e também quando a data que o guardião já tinha marcado (ESTABELECIDA)
    quebra uma regra (violacao): ele marcou antes das travas existirem, então a data dele passa pela mesma conferência."""
    if not e:
        return False
    if classe == "sugestao":
        return True
    return classe == "estabelecida" and violacao(e, tarefa, por_mae) is not None


def pendentes(tarefas, maes=()):
    """Etapas de post das tarefas abertas, ordenadas pelo limite (as sem limite por último)."""
    saida = [i for i in (info(t, maes) for t in tarefas or []) if i]
    return sorted(saida, key=lambda i: (i["limite"] or date.max, i["tipo"], str(i["titulo"])))


def regras_texto():
    """Texto curto para o dossiê do plano."""
    return ("REGRAS DAS ETAPAS DE POST (quem manda na data é você; o prazo do ClickUp é só sugestão da automação):\n"
            "- Copy, design e manychat terminam até o fim do dia ANTERIOR à postagem. Relatório só 24h depois da postagem, em 5 minutos.\n"
            "- Encaixe na agenda do melhor jeito: copies juntas num bloco, designs juntos em outro, e a copy de um post sempre antes do design dele. "
            "Copy cai na faixa nobre; design simples na faixa de recarga.\n"
            "- Cada etapa entra em UM dia só (com o clickup_id dela). O que não couber hoje vai para outro dia dentro do limite; diga no aviso.\n"
            "- Se não há espaço até o limite, diga qual post está em risco e o que sai para abrir espaço.")
