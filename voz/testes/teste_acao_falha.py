"""Ação por voz que não deu certo: o guardião já falou "estou concluindo" quando o resultado chega, então o programa precisa dizer a verdade no fim da resposta.
Cobre a ação que falha (erro do ClickUp, tarefa que não existe, exceção), a ação recusada porque a pessoa não a pediu (ele pergunta e o "sim" vale), a ação que
dá certo (não diz nada), esperar a ação terminar antes de fechar a resposta, e calar quando a pessoa fechou a janela. Sem Claude, sem áudio, sem navegador,
sem ClickUp."""
import json
import os
import sys
import tempfile
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import limpeza_teste  # noqa: E402,F401
import hud_servidor as h  # noqa: E402
limpeza_teste.fixar_relogio(h)
import guardiao_voz as g  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


tmp = tempfile.mkdtemp(prefix="gv_oper_falha_")
h.OPER = tmp
with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"pessoa": {"nome": "Rafa Lima", "artigo": "o"}}, f)
with open(os.path.join(tmp, "plano_do_dia.json"), "w", encoding="utf-8") as f:
    json.dump({"data": date.today().isoformat(), "status": "aprovado", "fixos": [], "blocos": [
        {"id": "pensar", "inicio": "09:00", "fim": "10:00", "titulo": "Pensar nos posts", "dono": "Rafa Lima", "frente": "Teste", "clickup_id": "cid1"}]}, f, ensure_ascii=False)

ditas = []
g.dizer = lambda texto, a: ditas.append(texto)
resposta_do_agir = {"r": {"ok": False, "erro": "O ClickUp não respondeu."}, "demora": 0.0, "levantar": None, "chamadas": []}


def agir_falso(tipo, ref=None, texto=None, dados=None):
    resposta_do_agir["chamadas"].append((tipo, ref, texto))
    time.sleep(resposta_do_agir["demora"])
    if resposta_do_agir["levantar"]:
        raise resposta_do_agir["levantar"]
    return resposta_do_agir["r"]


g.agir = agir_falso


def zerar():
    ditas.clear()
    g.CORRECOES.clear()
    g.AVISOS_AO_MODELO.clear()
    g.CONVERSA.clear()
    resposta_do_agir.update({"r": {"ok": False, "erro": "O ClickUp não respondeu."}, "demora": 0.0, "levantar": None})
    resposta_do_agir["chamadas"].clear()
    g.controle_fala.PARAR.clear()


# ---------------- a ação falha: ele diz que não conseguiu, com o motivo ----------------
zerar()
g.lembrar("terminei o pensar", "Certo, estou concluindo Pensar nos posts.")
g.executar_diretivas([("concluir", "pensar")], "terminei o pensar")
fala = g.falar_correcoes(None, espera=5)
confere("ação que falha: depois da resposta ele diz que não conseguiu, qual tarefa e por quê",
        fala == "Não consegui concluir Pensar nos posts: O ClickUp não respondeu." and ditas == [fala], (fala, ditas))
confere("a ação rodou uma vez, no bloco com nome", resposta_do_agir["chamadas"] == [("concluir", "pensar", None)], resposta_do_agir["chamadas"])
confere("o modelo é avisado de que NÃO deu certo e de que a pessoa já sabe, para não repetir nem afirmar o contrário",
        len(g.AVISOS_AO_MODELO) == 1 and "NÃO deu certo" in g.AVISOS_AO_MODELO[0] and "não repita" in g.AVISOS_AO_MODELO[0], g.AVISOS_AO_MODELO)
confere("a correção entra na conversa, depois do 'estou concluindo' que já tinha sido falado", g.CONVERSA[-1][2].endswith("Não consegui concluir Pensar nos posts: O ClickUp não respondeu."), g.CONVERSA)
confere("dita uma vez, não repete na resposta seguinte", g.falar_correcoes(None, espera=1) == "" and len(ditas) == 1)

# ---------------- erro inesperado dentro da ação ----------------
zerar()
resposta_do_agir["levantar"] = RuntimeError("sem internet")
g.executar_diretivas([("concluir", "pensar")], "terminei o pensar")
fala = g.falar_correcoes(None, espera=5)
confere("exceção na ação também vira 'não consegui', e a thread não morre calada", fala == "Não consegui concluir Pensar nos posts: sem internet.", fala)

# ---------------- a tarefa não existe ----------------
zerar()
resposta_do_agir["r"] = {"ok": False, "erro": "Não achei essa tarefa."}
g.executar_diretivas([("concluir", "fantasma")], "terminei o fantasma")
fala = g.falar_correcoes(None, espera=5)
confere("tarefa que não existe: diz que não achou, sem inventar título", fala == "Não consegui concluir: Não achei essa tarefa.", fala)

# ---------------- deu certo: não diz nada ----------------
zerar()
resposta_do_agir["r"] = {"ok": True, "status": "complete"}
g.executar_diretivas([("concluir", "pensar")], "terminei o pensar")
confere("ação que deu certo: nada a corrigir, nada é dito", g.falar_correcoes(None, espera=5) == "" and not ditas and not g.AVISOS_AO_MODELO)

# ---------------- esperar a ação terminar ----------------
zerar()
resposta_do_agir["demora"] = 1.2
t0 = time.time()
g.executar_diretivas([("concluir", "pensar")], "terminei o pensar")
fala = g.falar_correcoes(None, espera=8)
confere("a resposta só fecha depois da ação terminar (a falha de 1,2 s chega a tempo de ser dita)", fala.startswith("Não consegui concluir") and time.time() - t0 >= 1.1, (fala, time.time() - t0))
zerar()
resposta_do_agir["demora"] = 2.5
g.executar_diretivas([("concluir", "pensar")], "terminei o pensar")
fala = g.falar_correcoes(None, espera=0.5)
confere("se a ação demora demais, não prende a resposta (espera no máximo o limite)", fala == "")
time.sleep(2.3)  # deixa a ação lenta terminar antes do próximo bloco

# ---------------- recusada: a pessoa não pediu ----------------
zerar()
g.executar_diretivas([("concluir", "pensar")], "bom dia, tudo bem?")
confere("ação que a pessoa não pediu não chega a rodar", not resposta_do_agir["chamadas"])
fala = g.falar_correcoes(None, espera=5)
confere("e ele conta que não fez e pergunta se é para fazer",
        fala == "Não fiz nada ainda: você não me pediu para concluir Pensar nos posts. Quer que eu conclua Pensar nos posts?", fala)
confere("o modelo é avisado de que NÃO foi feito", len(g.AVISOS_AO_MODELO) == 1 and "NÃO foi feita" in g.AVISOS_AO_MODELO[0], g.AVISOS_AO_MODELO)
g.CONVERSA[:] = [(time.time(), "bom dia, tudo bem?", "Bom dia! " + fala)]
confere("o 'sim' da pessoa a essa pergunta vale como pedido", g.permitido("concluir", "sim, pode") is True)
confere("mas o sim não libera outra ação", g.permitido("reabrir", "sim, pode") is False)

# ---------------- a pessoa mandou calar (fechou a janela) ----------------
zerar()
g.executar_diretivas([("concluir", "pensar")], "terminei o pensar")
time.sleep(0.3)
g.controle_fala.PARAR.set()
fala = g.falar_correcoes(None, espera=5)
confere("com a janela fechada (fala interrompida) ele não fala depois, e a correção não fica pendurada para a próxima resposta", fala == "" and not ditas and not g.CORRECOES, (fala, ditas, g.CORRECOES))
g.controle_fala.PARAR.clear()

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
