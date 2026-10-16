"""Mantém sempre gerados os planos dos próximos 3 dias de trabalho (planos\\plano_AAAA-MM-DD.json), para a pessoa ter noção do que vem.

Quem decide é a conta: faltou o arquivo de um dos próximos DIAS_A_FRENTE dias úteis (rotina.dias_trabalho do config.json), gera. Ao concluir o dia, o
primeiro dia útil seguinte já existe e a janela anda um dia: o plano novo entra no fim. Nunca sobrescreve plano existente (o gerar_plano.ps1 também não).
Gera pelo mesmo caminho do plano de hoje (gerar_plano.ps1 -Data -Saida): plano base por código e, só se o dia pede decisão, o Claude.
Roda num laço de fundo do servidor da voz (a cada 15 min) e na hora que uma tarefa é concluída (pedir()). Falha de um dia espera 1 h para tentar de novo."""
import os
import subprocess
import threading
import time
from datetime import date, timedelta

import rota_agenda as ra
import visao_semana as vs

OPER = ra.OPER
DIAS_A_FRENTE = 3
PAUSA_FALHA = 3600  # segundos entre tentativas do mesmo dia que não gerou
LACO_SEGUNDOS = 900
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


def gerar(dia, oper=OPER):
    """Gera o plano de um dia com o gerar_plano.ps1. Devolve True se o arquivo existe depois."""
    destino = os.path.join(oper, "planos", f"plano_{dia.isoformat()}.json")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(oper, "gerar_plano.ps1"),
                        "-Data", dia.isoformat(), "-Saida", destino],
                       cwd=oper, timeout=TIMEOUT_GERAR, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.exists(destino)


def rodar_uma_vez(oper=OPER, cfg=None, hoje=None, gerador=gerar, agora=None):
    """Gera os planos que faltam, um de cada vez (o mais próximo primeiro). Devolve os dias gerados."""
    agora = agora if agora is not None else time.time()
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
    finally:
        _TRAVA.release()
    return feitos


def pedir():
    """Acorda o laço agora (uma tarefa foi concluída: o dia pode ter acabado e a janela andou)."""
    _EVENTO.set()


def _laco():
    time.sleep(60)  # deixa o servidor subir antes da primeira rodada
    while True:
        try:
            rodar_uma_vez()
        except Exception:
            pass
        _EVENTO.wait(timeout=LACO_SEGUNDOS)
        _EVENTO.clear()


def iniciar():
    threading.Thread(target=_laco, daemon=True, name="manter_planos").start()
