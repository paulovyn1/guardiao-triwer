"""Preferências no servidor: padrão, validação, gravação, evento e o que o cérebro faz com elas. Sem navegador e sem Claude."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import limpeza_teste  # noqa: E402,F401
import hud_servidor as h  # noqa: E402
import guardiao_voz as g  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


tmp = tempfile.mkdtemp(prefix="gv_oper_prefs_")
h.OPER = tmp
h.ARQ_PREFS = os.path.join(tmp, "preferencias.json")
g.SAUDACAO_ARQ = os.path.join(tmp, "logs", "saudacao.json")
fila = h.bus.assinar()

p = h.preferencias()
confere("sem arquivo, tudo vem no padrão (sons ligados, volume 70%, saudação e microfone aberto ligados)", p == h.PREFS_PADRAO and p["sons"] and p["volume"] == 0.7 and p["saudacao"] and p["escuta_aberta"], p)

r = h.salvar_preferencias({"saudacao": False, "volume": 0.35})
confere("salvar muda só o que veio e devolve tudo", r["saudacao"] is False and r["volume"] == 0.35 and r["sons"] is True and set(r) == set(h.PREFS_PADRAO), r)
confere("o arquivo guarda e outra leitura devolve igual", json.load(open(h.ARQ_PREFS, encoding="utf-8")) == r and h.preferencias() == r)
eventos = []
while not fila.empty():
    eventos.append(fila.get_nowait())
confere("salvar avisa as telas abertas (evento 'preferencias' com tudo)", eventos and eventos[-1]["t"] == "preferencias" and eventos[-1]["saudacao"] is False and eventos[-1]["volume"] == 0.35, eventos)

r = h.salvar_preferencias({"volume": 7})
confere("volume acima de 1 vira 1", r["volume"] == 1.0, r)
r = h.salvar_preferencias({"volume": -3})
confere("volume abaixo de 0 vira 0", r["volume"] == 0.0, r)
r = h.salvar_preferencias({"volume": True, "sons": "sim", "som_toques": 0, "inventada": 1, "saudacao": True})
confere("tipo errado e chave desconhecida são ignorados (não apagam o que estava salvo)", r["volume"] == 0.0 and r["sons"] is True and r["som_toques"] is True and "inventada" not in r and r["saudacao"] is True, r)
with open(h.ARQ_PREFS, "w", encoding="utf-8") as f:
    f.write("{ isto não é json")
confere("arquivo estragado volta ao padrão sem derrubar nada", h.preferencias() == h.PREFS_PADRAO)
with open(h.ARQ_PREFS, "w", encoding="utf-8") as f:
    json.dump({"sons": False, "volume": "alto", "som_digitacao": "não", "saudacao": False}, f)
p = h.preferencias()
confere("valores inválidos no arquivo caem no padrão, os válidos ficam", p["sons"] is False and p["saudacao"] is False and p["volume"] == 0.7 and p["som_digitacao"] is True, p)

# ---- o cérebro obedece
h.salvar_preferencias({"sons": True, "saudacao": False, "escuta_aberta": False})
confere("saudação desligada: não saúda, nem forçando", g.pode_saudar(False) is False and g.pode_saudar(True) is False)
h.salvar_preferencias({"saudacao": True})
confere("saudação ligada: saúda na primeira vez", g.pode_saudar() is True)
g.registrar_saudacao("Bom dia!")
confere("saudação ligada: continua respeitando as 3 horas", g.pode_saudar() is False and g.pode_saudar(True) is True)

turnos = []
g.atender = lambda *x, **k: turnos.append(k) or True


class A:
    sem_escuta_aberta = False


g.conversar(A(), None, None, None, 0)
confere("microfone aberto desligado: só uma rodada, mesmo o guardião esperando resposta", len(turnos) == 1, len(turnos))
h.salvar_preferencias({"escuta_aberta": True})
turnos.clear()
g.conversar(A(), None, None, None, 0)
confere("microfone aberto ligado: segue até o limite de 12 seguimentos", len(turnos) == 13, len(turnos))

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
