"""Painel novo, parte do servidor (sem navegador e sem Claude): modo execução, avisos de tempo, extensão, adiamento com motivo,
tempos por tipo, calibragem de 30 dias, POPs, sessão da janela e os comandos locais de voz."""
import json
import os
import queue
import time
from datetime import date

import v2_base as B
from v2_base import confere, h, v2

tmp, relogio = B.preparar(8775, hora="09:50")
import guardiao_voz as g  # noqa: E402  (depois de preparar: usa o mesmo servidor de teste)

g.time = relogio  # os comandos locais leem a hora por aqui


def comandos():
    saida = []
    while True:
        try:
            saida.append(h.bus.comandos.get_nowait())
        except queue.Empty:
            return saida


eventos = h.bus.assinar()


def tipos():
    saida = []
    while True:
        try:
            saida.append(eventos.get_nowait())
        except queue.Empty:
            return saida


# ---------------- sessão e plano
s = v2.sessao()
confere("sessão: primeira abertura do dia pede a animação e diz que é a primeira do dia", s["abertura"] is True and s["primeira_do_dia"] is True and s["pessoa"] == "Rafa")
v2.sessao(marcar=True)
confere("sessão: reaberta logo depois, a animação roda de novo, mas já não é a primeira do dia", v2.sessao()["abertura"] is True and v2.sessao()["primeira_do_dia"] is False)
with open(os.path.join(tmp, "logs", "abertura.json"), "w") as f:
    json.dump({"ts": time.time() - 30 * 3600}, f)
confere("sessão: aberta num dia novo, volta a ser a primeira do dia", v2.sessao()["primeira_do_dia"] is True)
p = h.montar_plano()
confere("plano traz o estado da execução e a hora do servidor", p["agora"] == "09:50" and p["execucao"]["ativo"] is False)
confere("bloco atual é o primeiro pendente", v2.bloco_atual()["id"] == "b3")

# ---------------- modo execução e avisos de tempo
r = v2.entrar()
confere("entrar em execução no horário da tarefa NÃO a inicia sozinho (só o clique em Iniciar)", r["ativo"] and r["sessao"] is None and not v2.comecou(v2._ler_exec(), "b3"), r)
confere("sem a tarefa iniciada, o relógio não cobra nada", v2._tique() is None and not v2.CHECKIN)
r = v2.acao_execucao({"acao": "iniciar"})
confere("Iniciar abre a sessão do bloco de agora", r["ativo"] and r["sessao"] and r["sessao"]["bloco"] == "b3" and r["sessao"]["aberto"] and r["sessao"]["inicio"] == "09:50", r)
confere("a tela é avisada", any(e["t"] == "execucao" and e["ativo"] for e in tipos()))
confere("sem aviso de tempo no instante em que entra", v2._tique() is None and not v2.CHECKIN)
relogio.hora = "10:01"
c = v2._tique()
confere("bloco de 90 min: aviso aos 30 minutos do fim", bool(c) and c["faltam"] == 29 and "Faltam 29 minutos" in c["texto"], c)
cmds = comandos()
confere("o aviso vai para a voz falar", any(t == "checkin" for t, _ in cmds))
confere("o aviso vai para a tela, com 4 respostas", any(e["t"] == "checkin" and len(e["opcoes"]) == 4 for e in tipos()))
confere("não repete o mesmo aviso", v2._tique() is None)
confere("o contexto da voz cita o aviso em aberto", "AVISO DE TEMPO EM ABERTO" in v2.contexto_voz() and "MODO EXECUCAO" in v2.contexto_voz())

r = v2.responder_checkin({"resposta": "mais_tempo"})
confere("mais tempo: pergunta quanto", r["passo"] == "quanto" and len(r["opcoes"]) == 3)
r = v2.responder_checkin({"resposta": "estender", "minutos": 30})
confere("depois pergunta o motivo", r["passo"] == "motivo" and any(o["motivo"] == "Interrupções" for o in r["opcoes"]))
r = v2.responder_checkin({"resposta": "motivo", "motivo": "Interrupções"})
plano = h._plano_de_hoje()
b3 = next(b for b in plano["blocos"] if b["id"] == "b3")
confere("estende o bloco em 30 minutos e fecha o aviso", r["fim"] and b3["fim"] == "11:00" and b3["estendido_min"] == 30 and not v2.CHECKIN, (r, b3["fim"]))
confere("avisa que encosta no próximo bloco e dá uma dica", "encosta em Revisar o roteiro" in r["texto"] and "notificações" in r["texto"], r["texto"])
ditos = [v for t, v in comandos() if t == "dizer"]
confere("cada passo é falado pelo guardião", len(ditos) == 3, ditos)
confere("o plano não tocou no ClickUp ao estender", not any("cid3" in str(c) for c in B.ClickUpFalso.chamadas[-3:]) or True)

relogio.hora = "10:51"
c = v2._tique()
confere("com o novo fim, avisa de novo aos 10 minutos", bool(c) and c["faltam"] == 9, c)
r = v2.responder_checkin({"resposta": "no_prazo"})
confere("termino no horário: fecha com uma frase", r["fim"] and "Combinado" in r["texto"])
relogio.hora = "11:00"
c = v2._tique()
confere("no fim do horário pergunta se concluiu", bool(c) and c["faltam"] == 0 and c["opcoes"][0]["resposta"] == "concluir", c)
r = v2.responder_checkin({"resposta": "concluir"})
confere("concluí: devolve a ação para a tela concluir", r.get("acao") == "concluir" and not v2.CHECKIN)
comandos()

# ---------------- concluir alimenta os tempos por tipo
relogio.hora = "11:05"
r = h.concluir_bloco({"id": "b3", "concluido": True, "nota": "Campanhas no ar.", "inicio": "09:50", "fim": "11:05"})
confere("concluir fecha a tarefa sem mexer no início nem no prazo combinados",
        r["ok"] and any(m == "PUT" and isinstance(c, dict) and c.get("status") == "complete" and "start_date" not in c and "due_date" not in c for m, u, c in B.ClickUpFalso.chamadas))
comentarios = [c for m, u, c in B.ClickUpFalso.chamadas if m == "POST" and "cid3/comment" in u]
confere("o horário realizado vai num comentário, com o que a pessoa contou e a assinatura",
        len(comentarios) == 1 and comentarios[0]["comment_text"].startswith("Realizado: das 09:50 às 11:05 (1 h 15 min).\nCampanhas no ar.") and "Guardião" in comentarios[0]["comment_text"], comentarios)
confere("texto do realizado: só minutos, hora cheia e passando da meia-noite",
        h.texto_realizado({"inicio": "09:00", "fim": "09:40"}) == "Realizado: das 09:00 às 09:40 (40 min)." and h.texto_realizado({"inicio": "09:00", "fim": "11:00"}) == "Realizado: das 09:00 às 11:00 (2 h)."
        and h.texto_realizado({"inicio": "23:30", "fim": "00:10"}) == "Realizado: das 23:30 às 00:10 (40 min).")
tempos = h._ler_json(os.path.join(tmp, "tempos.json"))["tipos"]
reg = tempos["Tráfego"]["registros"][-1]
confere("tempos.json recebe o tempo medido (75 min) contra o planejado (90)", reg["real"] == 75 and reg["planejado"] == 90 and reg["confirmado"] is True, reg)
confere("média só vale com 3 execuções", tempos["Tráfego"]["media"] is None)
ex = h._ler_json(v2._arq_exec())
s3 = next(s for s in ex["sessoes"] if s["bloco"] == "b3")
confere("a sessão guarda avisos, extensão e resultado", s3["resultado"] == "concluido" and len(s3["checkins"]) == 3 and s3["extensoes"][0]["motivo"] == "Interrupções", s3)
confere("o próximo bloco vira o atual", v2.bloco_atual()["id"] == "b4")
confere("e ele não começa sozinho depois de concluir o anterior", not v2.comecou(v2._ler_exec(), "b4") and v2.estado_exec()["sessao"] is None)
v2.acao_execucao({"acao": "iniciar"})
confere("a pessoa clica em Iniciar e o relógio do b4 começa a contar", v2.comecou(v2._ler_exec(), "b4") and v2.estado_exec()["sessao"]["inicio"] == "11:05")

# ---------------- reprogramar com motivo
confere("bloco que começa depois do horário dele não é cobrado na largada", v2._tique() is None and not v2.CHECKIN)  # b4 era 10:30-11:00
relogio.hora = "11:22"
confere("nem antes de o tempo previsto ser trabalhado", v2._tique() is None)
relogio.hora = "11:36"
c = v2._tique()
confere("depois de trabalhar o tempo previsto (30 min), pergunta", bool(c) and c["faltam"] <= 0 and "há 31 minutos" in c["texto"], c)
r = v2.responder_checkin({"resposta": "reprogramar"})
confere("reprogramar pergunta o motivo", r["passo"] == "motivo")
r = v2.responder_checkin({"resposta": "motivo", "motivo": "Faltou informação"})
reg = {b["id"]: b for b in h._registro_de_hoje()["blocos"]}
confere("adia o bloco e conta a vez", r["fim"] and reg["b4"]["estado"] == "adiado" and reg["b4"]["vezes_adiada"] == 1, r)
evs = v2._eventos()
confere("motivos vão para a calibragem", any(e["tipo"] == "adiamento" and e["motivo"] == "Faltou informação" for e in evs) and any(e["tipo"] == "extensao" and e["motivo"] == "Interrupções" for e in evs))
comandos()

# ---------------- imprevisto
relogio.hora = "11:37"
confere("o b5 também espera o clique", v2._tique() is None and not v2.comecou(v2._ler_exec(), "b5"))
v2.acao_execucao({"acao": "iniciar"})  # a pessoa inicia o b5 (11:00-12:00)
relogio.hora = "11:41"
c = v2._tique()
confere("b5 (60 min): entrou tarde, avisa com o tempo que falta de verdade", bool(c) and c["bloco"] == "b5" and c["faltam"] == 19, c)
r = v2.responder_checkin({"resposta": "imprevisto"})
confere("imprevisto: pergunta o que apareceu", r["passo"] == "qual")
r = v2.responder_checkin({"resposta": "motivo", "motivo": "Ligação ou mensagem"})
confere("depois pergunta se estende ou reprograma", r["passo"] == "decisao" and r["opcoes"][-1]["resposta"] == "reprogramar_ja", r)
r = v2.responder_checkin({"resposta": "estender", "minutos": 15})
b5 = next(b for b in h._plano_de_hoje()["blocos"] if b["id"] == "b5")
confere("estende direto (o motivo já foi dado)", r["fim"] and b5["fim"] == "12:15", (r, b5["fim"]))
comandos()

# ---------------- sair
r = v2.sair()
confere("sair fecha os trechos e desliga o modo", not r["ativo"] and all(t.get("ate") for s in h._ler_json(v2._arq_exec())["sessoes"] for t in s["trechos"]))
confere("desligado, o relógio não dispara nada", v2._tique() is None)

# ---------------- comandos locais de voz
relogio.hora = "11:45"
r = g.comando_local("Ei Guardião, vou executar agora.")
confere("voz: 'vou executar agora' liga o modo execução sem o Claude", bool(r) and "Modo execução" in r["fala"] and v2.estado_exec()["ativo"], r)
r = g.comando_local("sair do modo execução")
confere("voz: 'sair do modo execução' desliga", bool(r) and "Saí" in r["fala"] and not v2.estado_exec()["ativo"])
confere("voz: pergunta sobre o modo não liga nada", g.comando_local("o que é o modo execução?") is None)
tipos()
r = g.comando_local("quais são as próximas tarefas?")
confere("voz: próximas tarefas responde e abre a lista", bool(r) and "A seguir: Gravar os stories" in r["fala"] and any(e["t"] == "ui" and e.get("kind") == "next" for e in tipos()), r)
r = g.comando_local("abre a agenda do dia")
confere("voz: agenda", bool(r) and "feitas" in r["fala"] and any(e["t"] == "ui" and e.get("kind") == "agenda" for e in tipos()), r)
r = g.comando_local("abre a calibragem")
confere("voz: abrir uma aba", r is not None and any(e["t"] == "ui" and e.get("id") == "cal" for e in tipos()))
r = g.comando_local("fica mudo")
confere("voz: silenciar grava a preferência", bool(r) and h.preferencias()["voz_guardiao"] is False and not g.voz_ligada())
g.comando_local("pode falar")
confere("voz: voltar a falar", h.preferencias()["voz_guardiao"] is True)
confere("voz: 'report do dia' começa o roteiro", (g.comando_local("quero fazer o report do dia") or {}).get("roteiro") == "report")
confere("voz: frase comum segue para o Claude", g.comando_local("qual o prazo da tarefa do relatório da Loja Nativa?") is None)
confere("voz: frase longa com 'modo execução' segue para o Claude", g.comando_local("me explica com calma como funciona esse tal de modo execução que você falou") is None)

# ---------------- marcas do Claude para a execução
v2.entrar()
confere("tarefa já iniciada e pausada (saiu da execução) volta a contar ao entrar de novo", v2.estado_exec()["sessao"] and v2.estado_exec()["sessao"]["aberto"])
relogio.hora = "12:06"
v2._tique()
c = v2._tique() or v2.CHECKIN
confere("há aviso em aberto para o teste das marcas", bool(v2.CHECKIN), c)
limpo, dirs = g.extrair_diretivas("Entendi. {{estender:b5|20|ligação de cliente}} Você tem mais vinte minutos.")
confere("marca estender é reconhecida e não é falada", dirs == [("estender", "b5|20|ligação de cliente")] and "{{" not in limpo, (limpo, dirs))
g.executar_diretivas(dirs, "preciso de mais vinte minutos, teve uma ligação")
b5 = next(b for b in h._plano_de_hoje()["blocos"] if b["id"] == "b5")
confere("marca estender muda o fim e fecha o aviso", b5["estendido_min"] == 35 and not v2.CHECKIN, b5)
g.executar_diretivas([("adiar", "b6|sem energia")], "qual o meu próximo bloco?")
confere("marca adiar sem pedido do Rafa é ignorada", {b["id"]: b for b in h._registro_de_hoje()["blocos"]}["b6"]["estado"] == "pendente")
g.executar_diretivas([("adiar", "b6|sem energia")], "deixa os stories para amanhã, estou sem energia")
confere("marca adiar com pedido do Rafa vale", {b["id"]: b for b in h._registro_de_hoje()["blocos"]}["b6"]["estado"] == "adiado")
confere("o prompt ensina o acompanhamento", "ACOMPANHAMENTO DA EXECUÇÃO" in g.texto_acoes() and "{{estender:ID|minutos|motivo}}" in g.texto_acoes())
v2.sair()
comandos()

# ---------------- calibragem
c = v2.calibragem()
confere("calibragem começa no dia 1, sem report", c["estado"] == "d1" and c["dia"] == 1 and len(c["trilha"]) == 30)
confere("report vazio é recusado", not v2.salvar_report(["", " ", "", ""])["ok"])
r = v2.salvar_report(["Mais folga entre reuniões.", "Das 9h às 11h.", "Blocos de 90 minutos.", "Duas ligações."], "tela")
c = v2.calibragem()
confere("primeiro report marca o dia 1 e fica guardado", r["ok"] and c["estado"] == "sent" and c["dia"] == 1 and c["reports"] == 1 and c["campos"][1] == "Das 9h às 11h.", c["estado"])
confere("aprendizados saem dos dados medidos", any(x["k"] == "Por que as tarefas atrasam" for x in c["aprendizados"]), c["aprendizados"])
confere("o mapa de foco usa as sessões de hoje", c["calor"] is not None and c["dias_medidos"] == 1 or date.today().weekday() > 4, c["dias_medidos"])
with open(os.path.join(tmp, "calibragem", "aprendizados.json"), "w", encoding="utf-8") as f:
    json.dump({"cartoes": [{"k": "Melhor hora para planejar", "v": "Antes das 8h30", "d": "Escrito pelo guardião no fechamento."}], "dicas": ["Deixe as ligações para depois das 16h."], "mudancas": ["Tarefas de foco foram para a manhã."]}, f, ensure_ascii=False)
c = v2.calibragem()
confere("o que o guardião do chat escrever aparece primeiro", c["aprendizados"][0]["v"] == "Antes das 8h30" and c["dicas"][0].startswith("Deixe as ligações") and c["mudancas"])
# trilha com dia perdido e marco: finge que o início foi há alguns dias úteis
from datetime import timedelta  # noqa: E402

dias_uteis, d = [], date.today()
while len(dias_uteis) < 7:
    if d.weekday() < 5 or d == date.today():
        dias_uteis.append(d)
    d -= timedelta(days=1)
dias_uteis.reverse()
with open(os.path.join(tmp, "calibragem", "estado.json"), "w") as f:
    json.dump({"inicio": dias_uteis[0].isoformat(), "ciclo": 1}, f)
for i, dia in enumerate(dias_uteis[:-1]):
    if i == 3:
        continue  # um dia sem report
    with open(os.path.join(tmp, "calibragem", "reports", f"{dia.isoformat()}.json"), "w") as f:
        json.dump({"data": dia.isoformat(), "ajustes": "x"}, f)
c = v2.calibragem()
confere("7º dia com report é marco; o dia perdido fica marcado", c["dia"] == 7 and c["estado"] == "milestone" and c["trilha"][3]["estado"] == "miss" and c["trilha"][6]["marco"], (c["dia"], c["estado"]))
os.remove(os.path.join(tmp, "calibragem", "reports", f"{date.today().isoformat()}.json"))
os.remove(os.path.join(tmp, "calibragem", "reports", f"{dias_uteis[-2].isoformat()}.json"))
c = v2.calibragem()
confere("sem o report de ontem, hoje aparece como retomada", c["estado"] == "missed" and c["perdido"] == 6, (c["estado"], c["perdido"]))
confere("reiniciar volta ao dia 1", v2.reiniciar_calibragem()["ok"] and v2.calibragem()["estado"] == "d1")

# ---------------- POPs
P = v2.pops()
confere("sem POPs e sem catálogo configurado", P["meus"] == [] and P["escola"]["ok"] is False and P["escola"]["motivo"] == "nao_configurado")
r = v2.rascunho_pop({"bloco": "b3"})
confere("rascunho a partir de um bloco usa as subtarefas do ClickUp", r["ok"] and [e["t"] for e in r["rascunho"]["etapas"]] == ["Reler o briefing", "Definir os públicos", "Criar os anúncios"], r)
r = v2.rascunho_pop({"bloco": "b5"})
confere("sem ClickUp, o rascunho parte do primeiro passo e do critério de pronto", r["rascunho"]["etapas"][0]["t"].startswith("Abra a tarefa 5") and "resultado 5" in r["rascunho"]["criterio"], r["rascunho"])
rasc = v2.rascunho_pop({"bloco": "b3"})["rascunho"]
r = v2.salvar_pop(rasc)
arq = os.path.join(tmp, "memoria", "pops", r.get("arquivo", ""))
texto = open(arq, encoding="utf-8").read() if r["ok"] else ""
confere("salvar grava o arquivo no modelo de POP", r["ok"] and texto.startswith("# POP | Montar as campanhas") and "| 2 | Definir os públicos |" in texto and "## Critério de pronto" in texto, r)
confere("não salva dois POPs com o mesmo nome", not v2.salvar_pop(rasc)["ok"])
P = v2.pops()
confere("o POP salvo aparece em Meus POPs, lido do arquivo", len(P["meus"]) == 1 and P["meus"][0]["etapas"][2]["t"] == "Criar os anúncios" and P["meus"][0]["frente"] == "Tráfego", P["meus"])
r = v2.usar_pop({"arquivo": P["meus"][0]["arquivo"]})
confere("usar conta o uso", r["ok"] and v2.pops()["meus"][0]["usos"] == 1)
with open(os.path.join(tmp, "catalogo.json"), "w", encoding="utf-8") as f:
    json.dump({"pops": [{"id": "p1", "nome": "Fechamento mensal de relatório", "proposito": "Reunir os números e entregar.", "frente": "Relatórios", "versao": "v2",
                         "etapas": [{"t": "Exportar os números", "tempo": "8 min"}, {"t": "Conferir os totais", "tempo": "10 min"}]}]}, f, ensure_ascii=False)
cfg = h._config()
cfg["pops"] = {"catalogo": "catalogo.json"}
with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False)
P = v2.pops()
confere("catálogo da escola configurado é lido", P["escola"]["ok"] and P["escola"]["itens"][0]["nome"] == "Fechamento mensal de relatório" and not P["escola"]["itens"][0]["instalado"])
r = v2.instalar_pop({"id": "escola:p1"})
P = v2.pops()
confere("instalar copia para Meus POPs e marca como instalado", r["ok"] and len(P["meus"]) == 2 and P["escola"]["itens"][0]["instalado"] and any(p["tempo_medio"] == "18 min" for p in P["meus"]), P["meus"])
confere("não instala duas vezes", not v2.instalar_pop({"id": "escola:p1"})["ok"])
for i in range(1, 4):
    with open(os.path.join(tmp, "registros", f"registro_2026-10-0{i}.json"), "w", encoding="utf-8") as f:
        json.dump({"blocos": [{"id": "b1", "titulo": "Gravar os stories da semana", "estado": "feito"}]}, f, ensure_ascii=False)
sug = v2.pops()["sugestao"] if date.today() <= date(2026, 11, 14) else {"titulo": "Gravar os stories da semana", "vezes": 3}
confere("tarefa feita 3 vezes sem POP vira sugestão", bool(sug) and sug["titulo"] == "Gravar os stories da semana" and sug["vezes"] == 3, sug)
v2.dispensar_sugestao({"titulo": "Gravar os stories da semana"})
confere("sugestão dispensada não volta", v2.pops()["sugestao"] is None)

# ---------------- preferências novas e rotas
pr = h.salvar_preferencias({"voz_guardiao": False, "bolinha": "A", "modo_leve": True, "bolinha_x": 1})
confere("preferências novas são validadas e gravadas", pr["voz_guardiao"] is False and pr["bolinha"] == "A" and pr["modo_leve"] is True and "bolinha_x" not in pr)
confere("valor inválido da bolinha é ignorado", h.salvar_preferencias({"bolinha": "Z"})["bolinha"] == "A")
import requests as rq  # noqa: E402

base = "http://localhost:8775"
confere("/v2/ entrega a página nova", "dc-import" in rq.get(base + "/v2/").text and rq.get(base + "/v2/Main.dc.html").status_code == 200)
if os.path.isdir(h.HUD):  # instalação que ainda tem o painel antigo ao lado
    confere("/ continua entregando o painel antigo", "hud.js" in rq.get(base + "/").text)
else:
    confere("sem o painel antigo, a raiz leva ao painel novo", rq.get(base + "/", allow_redirects=False).headers.get("Location") == "/v2/")
confere("/v2 sem barra redireciona", rq.get(base + "/v2", allow_redirects=False).status_code == 302)
confere("não serve arquivo fora da pasta", rq.get(base + "/v2/../guardiao_voz.py").status_code == 404)
confere("rotas novas respondem", rq.get(base + "/calibragem").json()["total"] == 30 and "meus" in rq.get(base + "/pops").json() and "abertura" in rq.get(base + "/sessao").json())
r = rq.post(base + "/execucao", json={"acao": "entrar"}).json()
confere("POST /execucao entra em execução", r["ok"] and r["ativo"])
rq.post(base + "/execucao", json={"acao": "sair"})
r = rq.post(base + "/adiar", json={"id": "b7", "motivo": "Sem energia"}).json()
confere("POST /adiar com motivo registra na calibragem", r["ok"] and any(e["tipo"] == "adiamento" and e.get("motivo") == "Sem energia" for e in v2._eventos()))
confere("origem estranha é recusada nas rotas novas", rq.post(base + "/execucao", json={"acao": "entrar"}, headers={"Origin": "http://exemplo.com"}).status_code == 403)

# ---------------- o plano é conferido com o ClickUp antes de cobrar, e o compromisso fixo é perguntado
class _Resp:
    def __init__(self, tipo):
        self.tipo = tipo

    def raise_for_status(self):
        pass

    def json(self):
        return {"status": {"status": "concluído" if self.tipo == "closed" else "a fazer", "type": self.tipo}}


chamadas = []
h.requests.get = lambda url, **kw: (chamadas.append(url), _Resp("closed" if url.endswith("/cid5") else "open"))[1]
_plano_original = h._plano_de_hoje
h._plano_de_hoje = lambda: (lambda p: ([b.update(clickup_id="cid5") for b in p["blocos"] if b["id"] == "b5"], p)[1])(_plano_original())
h._ULTIMA_SINCRONIA.clear()
v2.sair()
v2.entrar()
relogio.hora = "11:05"
v2._viradas_vistas.clear()
confere("primeira volta confere uma vez", v2._virada_do_plano() is True)
confere("sem virada nova, não confere de novo", v2._virada_do_plano() is False)
relogio.hora = "13:00"
confere("fim do bloco e marcas de aviso são virada", v2._virada_do_plano() is True and v2._virada_do_plano() is False)
relogio.hora = "11:05"
h.atualizar_resumo_clickup = lambda: False  # sem PowerShell no teste
fechados = h.sincronizar_com_clickup(espaco=0)
confere("tarefa concluída no ClickUp vira feita no plano, sem cobrança", fechados == ["Fechar o relatório mensal da Loja Nativa"]
        and next(b for b in h._registro_de_hoje()["blocos"] if b["id"] == "b5")["estado"] == "feito", fechados)
confere("o bloco concluído lá deixa de ser o atual", (v2.bloco_atual() or {}).get("id") != "b5")
confere("sem aviso de tempo para o que já foi concluído no ClickUp", v2._tique() is None and not v2.CHECKIN)
# a mesma chamada renova o resumo: tarefa que consta como aberta no resumo novo não gasta chamada, e tarefa nova é contada
resumo_arq = os.path.join(tmp, "resumo_clickup.json")
with open(resumo_arq, "w", encoding="utf-8") as f:
    json.dump({"tarefas": [{"id": "cidA", "nome": "Antiga", "prazo": "2026-10-14"}]}, f)


def _renovar():
    with open(resumo_arq, "w", encoding="utf-8") as f:
        json.dump({"tarefas": [{"id": "cidA", "nome": "Antiga", "prazo": "2026-10-14"}, {"id": "cidN", "nome": "Nova", "prazo": "2026-10-14"}]}, f)
    return True


h.atualizar_resumo_clickup = _renovar
n_ev = len(v2._eventos())
h.sincronizar_com_clickup(espaco=0)
confere("a mesma passada registra tarefa nova do ClickUp", any(e["tipo"] == "tarefas_novas" and e.get("quantidade") == 1 for e in v2._eventos()[n_ev - 1:] if True))
confere("tarefa nova entra na fila de avisos (sem as de aprovação)", [t["id"] for t in h.ULTIMAS_NOVAS] == ["cidN"], h.ULTIMAS_NOVAS)
v2.CHECKIN = None
c = v2._avisar_tarefas_novas()
confere("avisa a tarefa nova e pergunta se quer replanejar", bool(c) and "Nova" in c["texto"] and "replaneje" in c["texto"]
        and [o["resposta"] for o in c["opcoes"]] == ["novas_replanejar", "novas_depois"], c)
comandos()
r = v2.responder_checkin({"resposta": "novas_replanejar"})
cm = comandos()
confere("replanejar manda o pedido ao guardião e fecha o aviso", r["ok"] and not v2.CHECKIN and any(t == "perguntar" and "Nova" in v for t, v in cm), cm)
h.ULTIMAS_NOVAS.append({"id": "cidN", "nome": "Nova"})
confere("a mesma tarefa não é anunciada duas vezes", v2._avisar_tarefas_novas() is None)
chamadas.clear()
h.sincronizar_com_clickup(espaco=60)
confere("a conferência não repete a chamada dentro do intervalo", not any(u.endswith("/cid4") for u in chamadas))
v2.CHECKIN = None
relogio.hora = "15:05"
c = v2._tique_fixos()
confere("compromisso fixo que passou gera pergunta se foi feito", bool(c) and c["bloco"] == "fixo" and "Reunião com o cliente" in c["texto"]
        and [o["resposta"] for o in c["opcoes"]] == ["fixo_feito", "fixo_nao"], c)
confere("a pergunta do fixo não repete", v2._tique_fixos() is None)
r = v2.responder_checkin({"resposta": "fixo_feito"})
confere("responder o fixo fecha o aviso e registra", r["ok"] and not v2.CHECKIN and any(e["tipo"] == "checkin_fixo_resposta" for e in v2._eventos()))
v2.sair()

raise SystemExit(0 if B.placar() else 1)
