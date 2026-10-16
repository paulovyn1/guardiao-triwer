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
fila = h.bus.assinar()

p = h.preferencias()
confere("sem arquivo, tudo vem no padrão (sons ligados, volume 70%, voz em 1x, execução ao abrir e microfone aberto ligados)",
        p == h.PREFS_PADRAO and p["sons"] and p["volume"] == 0.7 and p["voz_velocidade"] == 1.0 and p["execucao_ao_abrir"] and p["escuta_aberta"], p)
confere("saíram as opções de animação de abertura, saudação e vidro (0.9)", not {"abertura_animada", "saudacao", "vidro", "abrir_em_execucao"} & set(p), sorted(p))

r = h.salvar_preferencias({"execucao_ao_abrir": False, "volume": 0.35})
confere("salvar muda só o que veio e devolve tudo", r["execucao_ao_abrir"] is False and r["volume"] == 0.35 and r["sons"] is True and set(r) == set(h.PREFS_PADRAO), r)
confere("o arquivo guarda e outra leitura devolve igual", json.load(open(h.ARQ_PREFS, encoding="utf-8")) == r and h.preferencias() == r)
r = h.salvar_preferencias({"provedor_ia": "codex"})
confere("troca para Codex e persiste no mesmo arquivo", r["provedor_ia"] == "codex" and h.preferencias()["provedor_ia"] == "codex")
r = h.salvar_preferencias({"provedor_ia": "desconhecido"})
confere("provedor desconhecido não substitui a escolha", r["provedor_ia"] == "codex")
r = h.salvar_preferencias({"provedor_ia": "claude"})
confere("voltar ao Claude preserva as outras preferências", r["provedor_ia"] == "claude" and r["volume"] == 0.35)
eventos = []
while not fila.empty():
    eventos.append(fila.get_nowait())
confere("salvar avisa as telas abertas (evento 'preferencias' com tudo)", eventos and eventos[-1]["t"] == "preferencias" and eventos[-1]["execucao_ao_abrir"] is False and eventos[-1]["volume"] == 0.35, eventos)

r = h.salvar_preferencias({"volume": 7})
confere("volume acima de 1 vira 1", r["volume"] == 1.0, r)
r = h.salvar_preferencias({"volume": -3})
confere("volume abaixo de 0 vira 0", r["volume"] == 0.0, r)
r = h.salvar_preferencias({"volume": True, "sons": "sim", "som_toques": 0, "inventada": 1, "saudacao": False, "execucao_ao_abrir": True})
confere("tipo errado e chave desconhecida são ignorados (não apagam o que estava salvo)", r["volume"] == 0.0 and r["sons"] is True and r["som_toques"] is True and "inventada" not in r and "saudacao" not in r and r["execucao_ao_abrir"] is True, r)
for v, esperado in ((1.5, 1.5), (2, 2.0), (1, 1.0), (3, 1.0), (True, 1.0), ("2", 1.0)):
    h.salvar_preferencias({"voz_velocidade": 1.0})
    r = h.salvar_preferencias({"voz_velocidade": v})
    confere(f"velocidade da voz {v!r}: fica {esperado}", r["voz_velocidade"] == esperado, r["voz_velocidade"])
confere("a voz lê a velocidade das preferências", g.velocidade_voz() == 1.0)
h.salvar_preferencias({"voz_velocidade": 2})
confere("e troca quando a pessoa troca", g.velocidade_voz() == 2.0)
with open(h.ARQ_PREFS, "w", encoding="utf-8") as f:
    f.write("{ isto não é json")
confere("arquivo estragado volta ao padrão sem derrubar nada", h.preferencias() == h.PREFS_PADRAO)
with open(h.ARQ_PREFS, "w", encoding="utf-8") as f:
    json.dump({"sons": False, "volume": "alto", "som_digitacao": "não", "abrir_em_execucao": False, "saudacao": False}, f)
p = h.preferencias()
confere("valores inválidos no arquivo caem no padrão, os válidos ficam", p["sons"] is False and p["volume"] == 0.7 and p["som_digitacao"] is True, p)
confere("a opção antiga abrir_em_execucao (que nascia desligada) é ignorada: a execução ao abrir vem ligada", p["execucao_ao_abrir"] is True and "abrir_em_execucao" not in p, p)

# ---- o cérebro obedece
h.salvar_preferencias({"sons": True, "escuta_aberta": False})

turnos = []
g.atender = lambda *x, **k: turnos.append(k) or True


class A:
    sem_escuta_aberta = False


g.conversar(A(), None, None, None, 0)
confere("microfone aberto desligado: só uma rodada, mesmo o guardião esperando resposta", len(turnos) == 1, len(turnos))
h.salvar_preferencias({"escuta_aberta": True})
turnos.clear()
g.conversar(A(), None, None, None, 0)
confere("microfone aberto ligado, mas escuta contínua desligada (padrão): só uma rodada", len(turnos) == 1, len(turnos))
h.salvar_preferencias({"mic_sempre_ligado": True})
turnos.clear()
g.conversar(A(), None, None, None, 0)
confere("microfone aberto ligado: segue até o limite de 12 seguimentos", len(turnos) == 13, len(turnos))

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
