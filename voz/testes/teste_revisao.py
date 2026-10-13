"""Cérebro do guardião na revisão do plano: marcas, permissões, aprovação com "sim", saudação, microfone aberto. Sem Claude, sem áudio, sem navegador."""
import argparse
import json
import os
import queue
import sys
import tempfile
import threading
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


tmp = tempfile.mkdtemp(prefix="gv_oper_rev_")
h.OPER = tmp
g.SAUDACAO_ARQ = os.path.join(tmp, "logs", "saudacao.json")
hoje = date.today().isoformat()
caminho = os.path.join(tmp, "plano_do_dia.json")


def bloco(i, ini, fim, titulo, **extra):
    return {"id": f"b{i}", "inicio": ini, "fim": fim, "titulo": titulo, "dono": "Rafa Lima", "frente": "Teste",
            "descricao": f"Descrição {i}", "primeiro_passo": f"Passo {i}", "por_que_agora": f"Motivo {i}", **extra}


def gravar_plano(status="sugerido"):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"data": hoje, "status": status, "fixos": [], "blocos": [
            bloco(1, "09:00", "09:30", "Primeira", clickup_id="cid1"), bloco(2, "10:00", "11:00", "Segunda", lista_id="L1")]}, f, ensure_ascii=False)


def plano():
    return json.load(open(caminho, encoding="utf-8"))


with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"pessoa": {"nome": "Rafa Lima", "artigo": "o"}, "clickup": {"user_id": "1", "listas": [{"id": "L1", "nome": "Rotineiras"}]}}, f)
gravar_plano()
fila = h.bus.assinar()


def eventos():
    saida = []
    while not fila.empty():
        saida.append(fila.get_nowait())
    return saida


# ---- as marcas novas são reconhecidas e não vazam para a fala
t = "{{revisao:inicio}} {{foco:b1}} Das 9h às 9h30, Primeira. {{mover:b2|15:00-16:00}} Movi a segunda. {{aprovar}} Posso aprovar o plano?"
limpo, dirs = g.extrair_diretivas(t)
confere("extrair reconhece revisao, foco, mover e aprovar", [d[0] for d in dirs] == ["revisao", "foco", "mover", "aprovar"] and "{{" not in limpo, (limpo, dirs))
confere("mascarar protege as marcas novas contra cortes de frase", "15:00" not in g.mascarar(t) and g.mascarar("{{adicionar:titulo=A. B|inicio=10:00|fim=10:30}}").count(".") == 0)

# ---- permissões: fora da revisão, o ajuste só vale se a frase pedir
g.executar_diretivas([("mover", "b2|15:00-16:00")], "o que eu tenho amanhã?")
confere("fora da revisão, 'o que eu tenho amanhã' não mexe no plano", plano()["blocos"][1]["inicio"] == "10:00")
eventos()
g.executar_diretivas([("mover", "b2|15:00-16:00")], "move a segunda para as três da tarde")
confere("fora da revisão, pedir para mover move", plano()["blocos"][1]["inicio"] == "15:00")
ev = eventos()
confere("o ajuste emite plano_editado e plano, e destaca o bloco (foco)", [e["t"] for e in ev] == ["foco", "plano_editado", "plano"], [e["t"] for e in ev])
confere("o resultado do ajuste vai para o guardião saber na próxima fala", any("mover 'Segunda' ok" in x for x in g.AVISOS_AO_MODELO), g.AVISOS_AO_MODELO)
sit = g.situacao_plano()
confere("situacao_plano traz o status, lista o resultado e limpa a lista", "sugerido" in sit and "mover 'Segunda' ok" in sit and g.AVISOS_AO_MODELO == [], sit)
g.executar_diretivas([("mover", "b1|15:30-16:30")], "move a primeira para as 15:30")
ev = eventos()
confere("choque de horário: o evento do ajuste carrega o conflito (a tela avisa) e fica anotado para o modelo", any(e["t"] == "plano_editado" and e["conflitos"] for e in ev) and any("ATENÇÃO" in x for x in g.AVISOS_AO_MODELO), [e["t"] for e in ev])
g.AVISOS_AO_MODELO.clear()
g.executar_diretivas([("mover", "b1|09:00-09:30")], "move a primeira para as 9h")
eventos()

# ---- revisão aberta: qualquer ajuste vale e o microfone reabre
confere("revisão começa fechada", not g.revisao_ativa())
g.executar_diretivas([("revisao", "inicio")], "bora revisar")
confere("{{revisao:inicio}} abre a revisão", g.revisao_ativa())
g.executar_diretivas([("remover", "b2")], "esse bloco não vai dar")
confere("na revisão, remover vale", all(b["id"] != "b2" for b in plano()["blocos"]))
g.executar_diretivas([("desfazer", "")], "volta como estava")
confere("desfazer traz o bloco de volta", any(b["id"] == "b2" for b in plano()["blocos"]))
g.executar_diretivas([("adicionar", "titulo=Ligar para a Débora|inicio=16:00|fim=16:15|lista=rotineiras")], "inclui uma ligação para a Débora às 16h")
novo = next((b for b in plano()["blocos"] if b["titulo"] == "Ligar para a Débora"), None)
confere("adicionar cria o bloco com lista", novo and novo["lista_id"] == "L1", novo)
g.REVISAO["ultimo"] -= 1300
confere("revisão parada há mais de 20 min se encerra sozinha", not g.revisao_ativa())

# ---- aprovar: explícito executa, vago propõe e espera o sim
chamadas = []
g.agir = lambda tipo, *a, **k: chamadas.append((tipo, a, k)) or {"ok": True, "criadas": 1}
eventos()
g.executar_diretivas([("aprovar", "")], "pode aprovar o plano")
time.sleep(0.2)
confere("'pode aprovar' aprova direto (sem pergunta)", chamadas and chamadas[0][0] == "aprovar" and g.PROPOSTA is None, chamadas)
chamadas.clear()
g.executar_diretivas([("aprovar", "")], "tá bom assim")
confere("'tá bom assim' só propõe: nada é aprovado e a tela mostra a proposta", not chamadas and g.PROPOSTA and g.PROPOSTA["tipo"] == "aprovar" and any(e["t"] == "proposta" and e.get("tipo") == "aprovar" for e in eventos()))
confere("proposta de aprovar: 'sim' e 'ok' confirmam", g.resolver_proposta("sim") == "sim" and g.resolver_proposta("ok") == "sim" and g.resolver_proposta("pode aprovar") == "sim" and g.resolver_proposta("tá bom, pode aprovar") == "sim")
confere("proposta de aprovar: 'pode mover a reunião' NÃO aprova (é outro pedido)", g.resolver_proposta("pode mover a reunião para as 16h") == "outro")
confere("proposta de aprovar: 'não' recusa e 'não, muda a hora' é outro pedido", g.resolver_proposta("não") == "nao" and g.resolver_proposta("não, muda a hora") == "outro")
confere("proposta de aprovar: conversa solta também vira 'outro'", g.resolver_proposta("e como está o tempo hoje") == "outro")
g.PROPOSTA["quando"] -= 400
ev_antes = eventos()
confere("proposta velha expira e avisa a tela", g.resolver_proposta("sim") is None and g.PROPOSTA is None and any(e["t"] == "proposta_fim" and e["resultado"] == "expirada" for e in eventos()))
gravar_plano("aprovado")
chamadas.clear()
g.executar_diretivas([("aprovar", "")], "aprova")
time.sleep(0.1)
confere("com o plano já aprovado, {{aprovar}} não faz nada e avisa", not chamadas and any(e["t"] == "aviso" for e in eventos()))
g.executar_diretivas([("mover", "b2|12:00-13:00")], "move a segunda")
confere("depois de aprovado, mover pela voz é recusado", plano()["blocos"][1]["inicio"] == "10:00" and any("FALHOU" in x for x in g.AVISOS_AO_MODELO))
g.AVISOS_AO_MODELO.clear()
gravar_plano()

# ---- saudação
confere("pode saudar na primeira vez", g.pode_saudar())
g.registrar_saudacao("Bom dia, Rafa! Hoje é sábado, 10 de outubro. Quer revisar o plano?")
confere("não repete a saudação em menos de 3 horas, a não ser forçando", not g.pode_saudar() and g.pode_saudar(True))
arq = json.load(open(g.SAUDACAO_ARQ, encoding="utf-8"))
arq["ts"] -= 4 * 3600
json.dump(arq, open(g.SAUDACAO_ARQ, "w", encoding="utf-8"))
confere("depois de 3 horas pode saudar de novo", g.pode_saudar())
pedido = g.pedido_saudacao()
confere("pedido: avisa que não é fala do Rafa, traz data e horário, convida a revisar o plano sugerido", "não é uma fala do Rafa" in pedido and "de outubro" in pedido and "NÃO foi aprovado" in pedido and "revisar o plano" in pedido, pedido)
confere("pedido: lembra a saudação anterior para variar", "Quer revisar o plano?" in pedido)
gravar_plano("aprovado")
confere("pedido com plano aprovado fala do próximo bloco", "já está aprovado" in g.pedido_saudacao() and "próximo bloco" in g.pedido_saudacao())
os.remove(caminho)
confere("pedido sem plano diz que não há plano", "Ainda não existe plano" in g.pedido_saudacao())
gravar_plano()
g.PROPOSTA = {"tipo": "criar", "dados": {}, "quando": time.time()}
confere("com uma proposta esperando, não saúda", not g.pode_saudar(True))
g.PROPOSTA = None

# ---- atender: microfone aberto depois de pergunta
a = argparse.Namespace(cerebro=True, voz="kokoro", voz_kokoro="pm_santa", voz_nome="", sem_preview=True, previa_local=True, sem_escuta_aberta=False)
g.winsound.Beep = lambda *x: (_ for _ in ()).throw(AssertionError("bipe tocou no seguimento"))
g.dizer = lambda *x, **k: None
chamadas_resp = []
modelos_usados = []


def falso_responder(pergunta, voz, texto_usuario=None, acoes=True, portao=None, modelo=None, motivo="", fonte=None, pedir=None, limite_primeira=None, modo="rapido"):
    chamadas_resp.append({"texto_usuario": texto_usuario, "acoes": acoes, "portao": portao is not None})
    modelos_usados.append((modelo, motivo))
    return 1.0, 2.0, FALA[0]


FALA = ["Quer revisar o plano agora?"]
g.responder_falando = falso_responder
g.executar_diretivas = lambda *x, **k: None
q = queue.Queue()
r = g.atender(a, q, None, None, 0, texto_digitado="Isto é um pedido de saudação", saudacao=True)
confere("saudação: não mostra 'você', usa o portão, sem ações, e pede o microfone aberto", r is True and chamadas_resp[-1] == {"texto_usuario": "", "acoes": False, "portao": True} and not any(e["t"] == "voce" for e in eventos()), chamadas_resp)
confere("a saudação vai para o modelo padrão (Sonnet), com o motivo", modelos_usados[-1] == (g.MODELO_PADRAO, "saudação"), modelos_usados)
confere("saudação fica registrada para variar amanhã", "Quer revisar o plano agora?" in json.load(open(g.SAUDACAO_ARQ, encoding="utf-8"))["textos"])
r = g.atender(a, q, None, None, 0, texto_digitado="e agora?")
confere("pergunta digitada nunca abre o microfone sozinho", r is False)
FALA[0] = "Pronto, está feito."
r = g.atender(a, q, None, None, 0, texto_digitado="a saudação já passou")
confere("resposta sem pergunta não reabre o microfone", r is False)
g.REVISAO = {"inicio": time.time(), "ultimo": time.time()}
g.gravar = lambda *x, **k: None
r = g.atender(a, q, None, None, 0, seguimento=True)
confere("seguimento: sem bipe; se ninguém falar, a conversa termina", r is False)
g.REVISAO = None

# ---- conversar: repete enquanto o guardião espera resposta, com limite
turnos = []
sequencia = [True, True, True, False]
g.atender = lambda *x, **k: turnos.append(k) or sequencia[len(turnos) - 1]
g.conversar(a, q, None, None, 0)
confere("conversar repete até o guardião não esperar mais resposta (3 seguimentos)", len(turnos) == 4 and [bool(t.get("seguimento")) for t in turnos] == [False, True, True, True], turnos)
turnos.clear()
sequencia[:] = [True] * 30
g.atender = lambda *x, **k: turnos.append(k) or True
g.conversar(a, q, None, None, 0)
confere("limite de 12 seguimentos seguidos", len(turnos) == 13, len(turnos))
turnos.clear()
a.sem_escuta_aberta = True
g.conversar(a, q, None, None, 0)
confere("--sem-escuta-aberta desliga o microfone aberto", len(turnos) == 1)

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
