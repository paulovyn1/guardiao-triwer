"""Mantém sempre gerados os planos dos próximos 3 dias de trabalho (planos\\plano_AAAA-MM-DD.json), para a pessoa ter noção do que vem.

Quem decide é a conta: faltou o arquivo de um dos próximos DIAS_A_FRENTE dias úteis (rotina.dias_trabalho do config.json), gera. Ao concluir o dia, o
primeiro dia útil seguinte já existe e a janela anda um dia: o plano novo entra no fim. Nunca sobrescreve plano existente (o gerar_plano.ps1 também não).
Gera pelo mesmo caminho do plano de hoje (gerar_plano.ps1 -Data -Saida): plano base por código e, só se o dia pede decisão, o Claude.
REVISÃO: plano futuro que ainda é só sugerido é refeito quando o que o alimenta muda (tarefas do dia no ClickUp, o que ficou atrasado e rola
para ele, marcos das campanhas sem lugar), no máximo a cada 3 h por dia. Isso cobre o começo do dia (o ClickUp é relido às 9h) e a conclusão
do plano de hoje (o que sobrou rola para o próximo). Plano já APROVADO nunca é refeito sozinho: só passa pela conferência e o resultado vai para o log.
Roda num laço de fundo do servidor da voz (a cada 15 min) e na hora que uma tarefa é concluída (pedir()). Falha de um dia espera 1 h para tentar de novo."""
import hashlib
import json
import os
import subprocess
import threading
import time
from datetime import date, timedelta

import plano_base as pb
import rota_agenda as ra
import visao_semana as vs

OPER = ra.OPER
DIAS_A_FRENTE = 3
PAUSA_FALHA = 3600  # segundos entre tentativas do mesmo dia que não gerou
LACO_SEGUNDOS = 900
REVISAO_PAUSA = 3 * 3600  # segundos mínimos entre duas revisões do mesmo dia
RESUMO_VELHO = 900  # o resumo do ClickUp é relido se tiver mais que isto
TIMEOUT_GERAR = 900
_NOMES = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
_EVENTO = threading.Event()
_TRAVA = threading.Lock()
_TENTATIVAS = {}


def _cfg(oper):
    return vs._json(os.path.join(oper, "config.json")) or {}


def dias_de_trabalho(cfg):
    nomes = ((cfg.get("rotina") or {}).get("dias_trabalho")) or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    return {_NOMES[n] for n in nomes if n in _NOMES} or {0, 1, 2, 3, 4}


def proximos_dias(hoje, cfg, n=DIAS_A_FRENTE):
    """Os próximos n dias de trabalho depois de hoje."""
    uteis, d = [], hoje + timedelta(days=1)
    trabalho = dias_de_trabalho(cfg)
    while len(uteis) < n:
        if d.weekday() in trabalho:
            uteis.append(d)
        d += timedelta(days=1)
    return uteis


def faltando(hoje=None, oper=OPER, cfg=None, n=DIAS_A_FRENTE):
    """Dias entre os próximos n de trabalho que ainda não têm plano (nem em planos\\ nem como plano_do_dia.json)."""
    hoje = hoje or date.today()
    cfg = cfg if cfg is not None else _cfg(oper)
    atual = (vs._json(os.path.join(oper, "plano_do_dia.json")) or {}).get("data")
    return [d for d in proximos_dias(hoje, cfg, n)
            if not os.path.exists(os.path.join(oper, "planos", f"plano_{d.isoformat()}.json")) and atual != d.isoformat()]


def gerar(dia, oper=OPER, refazer=False):
    """Gera (ou, com refazer, regera) o plano de um dia com o gerar_plano.ps1. Devolve True se o arquivo existe depois."""
    destino = os.path.join(oper, "planos", f"plano_{dia.isoformat()}.json")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    comando = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(oper, "gerar_plano.ps1"),
               "-Data", dia.isoformat(), "-Saida", destino] + (["-Forcar", "-Replanejar"] if refazer else [])
    try:
        subprocess.run(comando, cwd=oper, timeout=TIMEOUT_GERAR, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.exists(destino)


def atualizar_resumo(oper=OPER):
    """Relê o ClickUp (sem Claude) se o resumo estiver velho: concluir tarefa não o atualiza, e a revisão depende dele."""
    arquivo = os.path.join(oper, "resumo_clickup.json")
    try:
        if time.time() - os.path.getmtime(arquivo) < RESUMO_VELHO:
            return
    except OSError:
        pass
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(oper, "ler_clickup.ps1")],
                       cwd=oper, timeout=180, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass


def assinatura(dia, oper=OPER, cfg=None, hoje=None):
    """Resumo do que alimenta o plano de um dia: suas tarefas no ClickUp, o que está atrasado para ele e os marcos das campanhas sem lugar."""
    cfg = cfg if cfg is not None else _cfg(oper)
    iso = dia.isoformat()
    tarefas = (vs._json(os.path.join(oper, "resumo_clickup.json")) or {}).get("tarefas") or []
    do_dia = sorted((str(t.get("id")), t.get("prazo"), t.get("inicio"), t.get("fim"), t.get("status")) for t in tarefas if t.get("prazo") == iso)
    atrasadas = sorted(str(t.get("id")) for t in tarefas if str(t.get("prazo") or "") < (hoje or date.today()).isoformat() and not t.get("aprovar"))
    try:
        marcos = sorted(pb.marcos_sem_lugar(dia, oper, cfg))
    except Exception:
        marcos = []
    return hashlib.sha1(json.dumps([do_dia, atrasadas, marcos], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _estado(oper):
    return vs._json(os.path.join(oper, "planos", ".revisao.json")) or {}


def _guardar(oper, estado):
    try:
        with open(os.path.join(oper, "planos", ".revisao.json"), "w", encoding="utf-8") as f:
            json.dump(estado, f)
    except OSError:
        pass


def _log(oper, texto):
    try:
        os.makedirs(os.path.join(oper, "logs"), exist_ok=True)
        with open(os.path.join(oper, "logs", "manter_planos.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M ") + texto + "\n")
    except OSError:
        pass


def rodar_uma_vez(oper=OPER, cfg=None, hoje=None, gerador=gerar, agora=None):
    """Gera os planos que faltam, um de cada vez (o mais próximo primeiro). Devolve os dias gerados."""
    agora = agora if agora is not None else time.time()
    hoje = hoje or date.today()
    cfg = cfg if cfg is not None else _cfg(oper)
    feitos = []
    if not _TRAVA.acquire(blocking=False):  # já tem uma rodada em curso
        return feitos
    try:
        for d in faltando(hoje, oper, cfg):
            if d in _TENTATIVAS and agora - _TENTATIVAS[d] < PAUSA_FALHA:
                continue
            _TENTATIVAS[d] = agora
            if gerador(d, oper):
                feitos.append(d)
                _TENTATIVAS.pop(d, None)
                _guardar(oper, {**_estado(oper), d.isoformat(): {"assinatura": assinatura(d, oper, cfg, hoje), "em": agora}})
        revisar(oper, cfg, hoje, gerador, agora)
    finally:
        _TRAVA.release()
    return feitos


def revisar(oper=OPER, cfg=None, hoje=None, gerador=gerar, agora=None):
    """Refaz o plano sugerido de cada um dos próximos dias cuja assinatura mudou. Aprovado: só confere e registra no log. Devolve os dias refeitos."""
    agora = agora if agora is not None else time.time()
    hoje = hoje or date.today()
    cfg = cfg if cfg is not None else _cfg(oper)
    refeitos, estado = [], _estado(oper)
    for d in proximos_dias(hoje, cfg):
        iso = d.isoformat()
        caminho = os.path.join(oper, "planos", f"plano_{iso}.json")
        plano = vs._json(caminho)
        if not isinstance(plano, dict):
            continue
        sig = assinatura(d, oper, cfg, hoje)
        visto = estado.get(iso)
        if not visto:  # plano que já existia antes da revisão: só marca o ponto de partida
            estado[iso] = {"assinatura": sig, "em": agora}
            continue
        if visto.get("assinatura") == sig or agora - float(visto.get("em") or 0) < REVISAO_PAUSA:
            continue
        if plano.get("status") == "aprovado":
            try:
                problemas = pb.conferir_arquivo(caminho, oper, cfg)
            except Exception:
                problemas = []
            _log(oper, f"plano aprovado de {iso}: o ClickUp mudou desde a aprovação" + (f"; a conferência aponta: {' | '.join(problemas)}" if problemas else "; a conferência não aponta nada"))
        elif gerador(d, oper, True):
            _log(oper, f"plano sugerido de {iso} refeito: o que o alimenta mudou")
            refeitos.append(d)
        estado[iso] = {"assinatura": assinatura(d, oper, cfg, hoje), "em": agora}
    _guardar(oper, estado)
    return refeitos


def pedir():
    """Acorda o laço agora (uma tarefa foi concluída: o dia pode ter acabado e a janela andou)."""
    _EVENTO.set()


def _laco():
    time.sleep(60)  # deixa o servidor subir antes da primeira rodada
    while True:
        try:
            import calibragem_semanal
            calibragem_semanal.gerar_se_sabado(OPER)  # sábado: as perguntas da calibragem da semana
        except Exception:
            pass
        try:
            atualizar_resumo()
            rodar_uma_vez()
        except Exception:
            pass
        _EVENTO.wait(timeout=LACO_SEGUNDOS)
        _EVENTO.clear()


def iniciar():
    threading.Thread(target=_laco, daemon=True, name="manter_planos").start()
