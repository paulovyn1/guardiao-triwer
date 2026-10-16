"""Ações rápidas sem o Claude e replanejamento automático (decisões de produto de 13/10/2026). Sem Claude, sem áudio, ClickUp falso.
- "Concluí" fecha a tarefa de agora; na dúvida de qual tarefa é, pergunta antes ("concluo X?") e o sim ou o não valem.
- "Me dá mais 20 minutos", "preciso de mais meia hora": dá o tempo à tarefa de agora; sem motivo na frase, pergunta o motivo e a resposta é anotada.
- "Adia isso", "deixa pra amanhã": adia a tarefa de agora; com dia marcado ou citando outra tarefa, o Claude cuida.
- Replanejar: só quando o atraso passa de 30 minutos e o resto do dia não tem folga; no máximo uma proposta a cada 90 minutos."""
import json
import os
from datetime import date

import v2_base as B
from v2_base import confere, h, v2

tmp, relogio = B.preparar(8777, hora="09:50")
import guardiao_voz as g  # noqa: E402

g.time = relogio


def estado(bid):
    return ({b["id"]: b for b in h._registro_de_hoje().get("blocos", [])}.get(bid) or {}).get("estado")


def eventos(tipo):
    caminho = os.path.join(tmp, "calibragem", "eventos.jsonl")
    if not os.path.exists(caminho):
        return []
    return [e for e in (json.loads(x) for x in open(caminho, encoding="utf-8") if x.strip()) if e.get("tipo") == tipo]


def plano():
    return json.load(open(os.path.join(tmp, "plano_do_dia.json"), encoding="utf-8"))


# ---------------- concluir: direto quando é claro, pergunta na dúvida ----------------
relogio.hora = "10:20"
r = g.comando_local("Terminei as campanhas da clínica.")
confere("concluí citando a tarefa de agora: fecha direto, sem perguntar", r and r["fala"].startswith("Feito às") and estado("b3") == "feito", r)
r = g.comando_local("Concluí o relatório da Loja Nativa.")
confere("concluí citando outra tarefa: pergunta antes, sem fechar nada", r and r["fala"] == "Só para confirmar: concluo Fechar o relatório mensal da Loja Nativa?"
        and estado("b5") != "feito" and estado("b4") != "feito", r)
r = g.comando_local("sim")
confere("o sim fecha a tarefa da pergunta, e não a de agora", r and r["fala"].startswith("Feito às") and estado("b5") == "feito" and estado("b4") != "feito", r)
r = g.comando_local("Terminei aquela parte que eu estava fazendo antes do intervalo")
confere("concluí longo que não cita nada da tarefa de agora: pergunta", r and r["fala"] == "Só para confirmar: concluo Revisar o roteiro do vídeo da Padaria Sol?", r)
r = g.comando_local("não")
confere("o não não fecha nada", r == {"fala": "Certo, não fechei nada."} and estado("b4") != "feito", r)
confere("pergunta respondida não vale de novo", g.comando_local("sim") is None)

# ---------------- mais tempo ----------------
fim_antes = next(b for b in plano()["blocos"] if b["id"] == "b4")["fim"]
r = g.comando_local("Me dá mais 20 minutos porque o cliente pediu um ajuste no roteiro")
b4 = next(b for b in plano()["blocos"] if b["id"] == "b4")
confere("mais 20 minutos com motivo: estende a tarefa de agora e não pergunta nada", r and r["fala"].startswith("Mais 20 minutos para Revisar o roteiro") and not r["fala"].endswith("?")
        and h._min(b4["fim"]) == max(h._min(fim_antes), h._min("10:20")) + 20, (r, fim_antes, b4["fim"]))
confere("o motivo da frase vai para a calibragem", eventos("extensao") and eventos("extensao")[-1].get("motivo", "").startswith("o cliente pediu"), eventos("extensao")[-1:])
r = g.comando_local("Preciso de mais meia hora")
confere("mais meia hora sem motivo: estende 30 e pergunta o motivo", r and "Mais 30 minutos" in r["fala"] and r["fala"].endswith("Qual foi o motivo?"), r)
r = g.comando_local("A revisão está maior do que eu pensava")
confere("a resposta seguinte é anotada como motivo", r == {"fala": "Anotado."} and eventos("motivo_extensao")[-1]["motivo"] == "A revisão está maior do que eu pensava", eventos("motivo_extensao")[-1:])
confere("'mais dois detalhes' não é pedido de tempo", g.comando_local("me fala mais dois detalhes disso") is None)
r = g.comando_local("me dá mais uma hora")
confere("mais uma hora = 60 minutos", r and "Mais 60 minutos" in r["fala"], r)
g.PENDENTE_LOCAL = None

# ---------------- adiar ----------------
r = g.comando_local("Adia isso porque estou sem energia agora")
confere("adia a tarefa de agora com o motivo da frase, sem perguntar", r == {"fala": "Adiei Revisar o roteiro do vídeo da Padaria Sol."} and estado("b4") == "adiado"
        and eventos("adiamento")[-1].get("motivo") == "estou sem energia agora", (r, eventos("adiamento")[-1:]))
r = g.comando_local("deixa pra amanhã")
confere("deixa pra amanhã sem motivo: adia a próxima e pergunta o motivo", r and r["fala"].startswith("Adiei Gravar os stories") and r["fala"].endswith("Qual foi o motivo?") and estado("b6") == "adiado", r)
r = g.comando_local("Concluí a ligação para o contador")
confere("se em vez do motivo vem outro pedido, a pergunta cai e o pedido é atendido", r and r["fala"].startswith("Feito às") and estado("b7") == "feito" and g.PENDENTE_LOCAL is None, r)
confere("adiar com dia marcado fica com o Claude (é remarcar)", g.comando_local("adia isso pra sexta") is None)

# ---------------- replanejar: atraso acima de 30 minutos e dia sem folga ----------------
hoje = date.today().isoformat()


def gravar(blocos, fim_dia):
    with open(os.path.join(tmp, "plano_do_dia.json"), "w", encoding="utf-8") as f:
        json.dump({"data": hoje, "status": "aprovado", "fixos": [], "blocos": blocos, "fim_do_dia": fim_dia}, f, ensure_ascii=False)


blocos = [B.bloco(21, "09:00", "12:00", "Montar a campanha de novembro"), B.bloco(22, "12:00", "16:30", "Gravar as aulas do módulo 3")]
gravar(blocos, "16:30")
relogio.hora = "12:20"
av = v2.avaliar_atraso()
confere("20 minutos de atraso não replanejam, mesmo com o dia cheio", av["atraso"] == 20 and not av["precisa"], av)
relogio.hora = "12:40"
av = v2.avaliar_atraso()
confere("40 minutos de atraso num dia todo fechado: replaneja", av["atraso"] == 40 and av["folga"] < 0 and av["precisa"], av)
gravar(blocos, "18:30")
av = v2.avaliar_atraso()
confere("40 minutos de atraso com folga no fim do dia: não replaneja", av["atraso"] == 40 and av["folga"] >= 0 and not av["precisa"], av)
gravar([B.bloco(21, "09:00", "12:00", "Montar a campanha de novembro"), B.bloco(22, "14:00", "16:30", "Gravar as aulas do módulo 3")], "16:30")
av = v2.avaliar_atraso()
confere("o intervalo livre antes da próxima tarefa absorve o atraso", not av["precisa"] and av["folga"] >= 0, av)

gravar(blocos, "16:30")
# O supervisor só avisa e pergunta se ela quer replanejar (decisão de 16/10): nunca chama iniciar_completo.
pedidos = []
g.iniciar_completo = lambda pedido: pedidos.append(pedido) or True
fila_av = g.bus.assinar()


def avisos():
    saida = []
    while not fila_av.empty():
        e = fila_av.get_nowait()
        if e.get("t") == "aviso":
            saida.append(e)
    return saida


g.SUPERVISOR.update(dia=None, vezes=0, ultimo=0.0)
ok1 = g.supervisionar(agora=1000.0)
av1 = avisos()
confere("o supervisor avisa uma vez, dizendo o atraso e até quando o dia vai, e pergunta se ela quer replanejar (sem chamar iniciar_completo)",
        ok1 is True and pedidos == [] and len(av1) == 1 and "40 minutos" in av1[0]["texto"] and "16:30" in av1[0]["texto"] and "Quer que eu replaneje" in av1[0]["texto"]
        and eventos("replanejamento_sugerido"), (pedidos, av1))
confere("e não repete antes de 90 minutos", g.supervisionar(agora=1000.0 + 60 * 60) is False and avisos() == [] and g.SUPERVISOR["vezes"] == 1)
confere("depois de 90 minutos avisa de novo", g.supervisionar(agora=1000.0 + 91 * 60) is True and len(avisos()) == 1 and g.SUPERVISOR["vezes"] == 2)
g.SUPERVISOR.update(vezes=g.SUPERVISOR_MAX_DIA, ultimo=0.0)
confere(f"o limite de {g.SUPERVISOR_MAX_DIA} avisos por dia vale", g.SUPERVISOR_MAX_DIA == 3 and g.supervisionar(agora=900000.0) is False and avisos() == [])
confere("o intervalo é de 90 minutos", g.SUPERVISOR_INTERVALO == 90 * 60, g.SUPERVISOR_INTERVALO)
confere("em nenhum momento o supervisor pediu o guardião completo", pedidos == [], pedidos)
with open(os.path.join(tmp, "plano_do_dia.json"), encoding="utf-8") as f:
    p = json.load(f)
p["status"] = "sugerido"
with open(os.path.join(tmp, "plano_do_dia.json"), "w", encoding="utf-8") as f:
    json.dump(p, f, ensure_ascii=False)
g.SUPERVISOR.update(dia=None, vezes=0, ultimo=0.0)
confere("plano ainda não aprovado (por exemplo, a proposta esperando revisão): não avisa de novo", g.supervisionar(agora=50000.0) is False and avisos() == [])

# ---------------- modo rápido lê as regras locais (extensões e aprendizados), não só o perfil ----------------
pasta_skill = os.path.join(tmp, ".claude", "skills", "guardiao-triwer")
os.makedirs(pasta_skill, exist_ok=True)
with open(os.path.join(pasta_skill, "extensoes-teste.md"), "w", encoding="utf-8") as f:
    f.write("Regra de teste: tarefa de conteúdo sempre como subtarefa da mãe.")
with open(os.path.join(tmp, "memoria", "aprendizados.md"), "w", encoding="utf-8") as f:
    f.write("Quando eu disser carrossel, entenda post de feed.")
prompt = g.prompt_sistema()
confere("o prompt do modo rápido leva o perfil, as extensões e os aprendizados", "PERFIL:" in prompt and "Regra de teste: tarefa de conteúdo" in prompt
        and "entenda post de feed" in prompt and "[extensoes-teste.md]" in prompt)
confere("e continua estável (o mesmo prompt na chamada seguinte)", g.prompt_sistema() == prompt)

raise SystemExit(0 if B.placar() else 1)
