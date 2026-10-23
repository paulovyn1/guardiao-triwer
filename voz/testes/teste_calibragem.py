"""Calibragem (0.11.0), sem navegador e sem Claude: natureza da tarefa, quando um tempo vale para a média, a migração do tempos.json antigo
(por frente) para o novo (por natureza), a margem do roteador sem reunião, conclusão que não conta duas vezes, atraso para começar,
tarefa principal no registro do dia, eventos sem repetição e as tarefas novas com a origem."""
import json
import os
import tempfile

import v2_base as B
from v2_base import confere, h, v2

import calibragem_motor as cm  # noqa: E402
import rota_agenda as ra  # noqa: E402

# ---------------- natureza da tarefa
casos = [
    ("Copy da página de vendas, parte 1", "Conteúdo", "copy"),
    ("Revisar o roteiro do vídeo da Padaria Sol", "Conteúdo", "revisao"),
    ("Design do post de aquecimento", "Conteúdo", "criacao"),
    ("Montar as campanhas de tráfego da Clínica Vitta", "Tráfego", "trafego"),
    ("Reunião com o cliente", "", "reuniao"),
    ("Encontro ao vivo com os alunos da turma", "Turma VIP", "reuniao"),
    ("Responder grupos dos clientes da agência (manhã)", "Guardião", "atendimento"),
    ("Avisos com o link do Zoom da turma (1 na quarta, 3 na quinta)", "Turma VIP", "operacional"),
    ("Decidir o funil de aquisição da agência", "Agência", "decisao"),
    ("Folga para imprevistos e fechamento do dia", "Guardião", "folga"),
    ("Almoço", "", "folga"),
    ("Pagar o boleto do contador", "", "financeiro"),
    ("Implementar o login do app", "", "dev"),
    ("Gravar os stories da semana", "Conteúdo", "criacao"),
    ("Criar material de aula e disparar para a base", "Aulas", "copy"),
    ("Subir na estratosfera play - AULA #103", "Aulas", "operacional"),
    ("Montar a estratégia do lançamento", "", "decisao"),
    ("Algo sem pista nenhuma", "Atendimento", "atendimento"),
    ("Coisa qualquer", "", "geral"),
]
erradas = [(t, cm.inferir_natureza(t, f), e) for t, f, e in casos if cm.inferir_natureza(t, f) != e]
confere(f"natureza deduzida do título (e da frente quando o título não diz nada): {len(casos)} casos", not erradas, erradas)
confere("a natureza escrita no plano vale, com apelido aceito (design vira criação), e uma desconhecida cai na deduzida",
        cm.natureza_do_bloco({"titulo": "Qualquer", "natureza": "copy"}) == "copy" and cm.natureza_do_bloco({"titulo": "Qualquer", "natureza": "Design"}) == "criacao"
        and cm.natureza_do_bloco({"titulo": "Responder o direct", "natureza": "xyz"}) == "atendimento")

# ---------------- quando um tempo vale para a média
confere("tempo medido no modo execução vale", cm.tempo_confiavel(30, 7, True, False))
confere("sem medir e sem a pessoa informar, não vale", not cm.tempo_confiavel(30, 30, False, False))
confere("1 minuto informado é o horário sugerido aceito sem mexer: não vale", not cm.tempo_confiavel(5, 1, False, True))
confere("informado com menos de 25% do previsto não vale (2 de 25)", not cm.tempo_confiavel(25, 2, False, True))
confere("informado com mais de 4 vezes o previsto não vale (130 de 30)", not cm.tempo_confiavel(30, 130, False, True))
confere("informado e plausível vale (25 de 30, e 3 de uma tarefa de 5)", cm.tempo_confiavel(30, 25, False, True) and cm.tempo_confiavel(5, 3, False, True))

# ---------------- migração do tempos.json antigo, com os casos reais que contaminavam a margem
velho = tempfile.mkdtemp(prefix="gv_tempos_")
os.makedirs(os.path.join(velho, "registros"))


def grava(caminho, obj):
    with open(os.path.join(velho, *caminho.split("/")), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def r(data, titulo, planejado, real, confirmado=True):
    return {"data": data, "titulo": titulo, "planejado": planejado, "real": real, "confirmado": confirmado}


grava("tempos.json", {"tipos": {
    "Guardião": {"registros": [r("2026-10-12", "Folga para imprevistos e fechamento do dia", 30, 1), r("2026-10-15", "Responder grupos dos clientes", 25, 2),
                               r("2026-10-15", "Aviso 2 com o link do Zoom", 5, 1), r("2026-10-15", "Aviso 3 com o link do Zoom", 5, 1), r("2026-10-15", "Aviso 3 com o link do Zoom", 5, 1)]},
    "Turma VIP": {"registros": [r("2026-10-14", "Avisos com o link do Zoom", 20, 20), r("2026-10-15", "Encontro ao vivo com os alunos da turma", 95, 94)]},
    "Atividades": {"registros": [r("2026-10-15", "Avisos com o link do Zoom", 5, 15)]},
    "Aulas": {"registros": [r("2026-10-15", "Subir na estratosfera play", 30, 7), r("2026-10-12", "Agendar a publicação no YouTube", 30, 286, False)]},
}})


def sessao(titulo, minutos):
    return {"titulo": titulo, "resultado": "concluido", "minutos": minutos}


grava("registros/execucao_2026-10-14.json", {"sessoes": [sessao("Avisos com o link do Zoom", 20)]})
grava("registros/execucao_2026-10-15.json", {"sessoes": [sessao("Responder grupos dos clientes", 2), sessao("Avisos com o link do Zoom", 15),
                                                         sessao("Subir na estratosfera play", 7), sessao("Encontro ao vivo com os alunos da turma", 94)]})
confere("o tempos.json antigo é migrado uma vez", cm.migrar_tempos(velho) is True and cm.migrar_tempos(velho) is False)
novo = json.load(open(os.path.join(velho, "tempos.json"), encoding="utf-8"))
tipos = novo["tipos"]
op = {(x["titulo"], x["real"]): x for x in tipos["operacional"]["registros"]}
confere("formato novo: versão 2, por natureza, sem folga", novo["versao"] == 2 and "folga" not in tipos and set(tipos) == {"operacional", "atendimento", "reuniao"}, sorted(tipos))
confere("o medido de verdade continua valendo (20 de 20, 15 de 5, 7 de 30)",
        op[("Avisos com o link do Zoom", 20)]["confirmado"] and op[("Avisos com o link do Zoom", 15)]["confirmado"] and op[("Subir na estratosfera play", 7)]["confirmado"])
confere("1 minuto sem medir e 2 minutos de uma sessão curta deixam de valer",
        not op[("Aviso 2 com o link do Zoom", 1)]["confirmado"] and not tipos["atendimento"]["registros"][0]["confirmado"])
confere("a mesma tarefa repetida no mesmo dia conta uma vez", sum(1 for x in tipos["operacional"]["registros"] if x["titulo"].startswith("Aviso 3")) == 1)
confere("média da natureza com 3 confirmados: (20 + 15 + 7) / 3 = 14", tipos["operacional"]["media"] == 14, tipos["operacional"])
confere("o arquivo antigo fica guardado na calibragem", os.path.exists(os.path.join(velho, "calibragem", "tempos_antes_da_v2.json")))
m, n = ra.margem(velho)
confere("a margem do roteador usa só os confirmados e deixa a reunião de fora (3 razões, não 4)", n == 3 and m == 1.0, (m, n))

# ---------------- o painel: plano com tarefa principal e um bloco de folga
plano = B.PLANO_PADRAO()
plano["blocos"][2]["principal"] = True  # b3, campanhas de tráfego
plano["blocos"].append(B.bloco(8, "15:30", "16:00", "Folga para o que estourar", frente="Rotina"))
tmp, relogio = B.preparar(8781, plano=plano, hora="09:50", feitos=())

p = h.montar_plano()
reg = {b["id"]: b for b in h._registro_de_hoje()["blocos"]}
confere("plano aprovado: o registro do dia nasce com todos os blocos pendentes", len(reg) == 8 and all(b["estado"] == "pendente" for b in reg.values()), list(reg))
confere("o registro traz a natureza e a tarefa principal", reg["b3"]["natureza"] == "trafego" and reg["b3"]["principal"] is True and reg["b8"]["natureza"] == "folga" and reg["b1"]["principal"] is False)
confere("a tela recebe a natureza e a marca de principal", next(b for b in p["hoje"]["blocos"] if b["id"] == "b3")["principal"] is True)

v2.acao_execucao({"acao": "iniciar"})  # b1 (08:00) iniciado às 09:50
ev = [e for e in v2._eventos() if e["tipo"] == "inicio_bloco"]
confere("Iniciar grava o atraso para começar (08:00 contra 09:50 = 110 min), com a natureza", len(ev) == 1 and ev[0]["bloco"] == "b1" and ev[0]["atraso"] == 110 and ev[0]["natureza"] == "atendimento", ev)
v2.sair()
v2.entrar()
confere("sair e voltar não grava outro início", len([e for e in v2._eventos() if e["tipo"] == "inicio_bloco"]) == 1)

relogio.hora = "09:51"
h.concluir_bloco({"id": "b1", "concluido": True, "nota": "", "inicio": "09:50", "fim": "09:51", "nao_confirmado": False})


def tempos():
    return h._ler_json(os.path.join(tmp, "tempos.json"))["tipos"]


t1 = tempos()["atendimento"]["registros"]
confere("Iniciar e concluir no mesmo minuto não é tempo medido: fica fora da média", len(t1) == 1 and t1[0]["confirmado"] is False and t1[0]["medido"] is False, t1)
h.concluir_bloco({"id": "b1", "concluido": True, "nota": "", "inicio": "09:50", "fim": "09:51"})
confere("concluir a mesma tarefa de novo não soma outra vez", len(tempos()["atendimento"]["registros"]) == 1
        and len([e for e in v2._eventos() if e["tipo"] == "conclusao" and e["bloco"] == "b1"]) == 1)

h.concluir_bloco({"id": "b2", "concluido": True, "nota": "", "inicio": "08:30", "fim": "09:00"})
confere("horário informado e plausível vale (30 de 30, operacional)", tempos()["operacional"]["registros"][-1]["confirmado"] is True)
h.concluir_bloco({"id": "b8", "concluido": True, "nota": "", "inicio": "15:30", "fim": "16:00"})
confere("folga concluída não entra no tempos.json", "folga" not in tempos() and any(e["tipo"] == "conclusao" and e["bloco"] == "b8" and e["natureza"] == "folga" for e in v2._eventos()))

relogio.hora = "09:52"
v2.acao_execucao({"acao": "iniciar"})  # agora o atual é o b3, a tarefa principal
relogio.hora = "10:40"
h.concluir_bloco({"id": "b3", "concluido": True, "nota": "", "inicio": "09:52", "fim": "10:40", "nao_confirmado": False})
ini3 = next(e for e in v2._eventos() if e["tipo"] == "inicio_bloco" and e["bloco"] == "b3")
fim3 = next(e for e in v2._eventos() if e["tipo"] == "conclusao" and e["bloco"] == "b3")
confere("a tarefa principal leva a marca no início e na conclusão", ini3.get("principal") is True and ini3["atraso"] == 52 and fim3.get("principal") is True, (ini3, fim3))
confere("trabalho medido de 48 minutos vale", fim3["medido"] is True and fim3["confirmado"] is True and fim3["real"] == 48, fim3)

# ---------------- eventos que não se repetem
b5 = next(b for b in plano["blocos"] if b["id"] == "b5")
a = v2.registrar_evento("replanejamento_automatico", b5, unico_por=600, atraso=40, folga=-20)
b = v2.registrar_evento("replanejamento_automatico", b5, unico_por=600, atraso=41, folga=-21)
confere("o mesmo replanejamento do mesmo bloco não é gravado duas vezes em 10 minutos", a and b is None
        and len([e for e in v2._eventos() if e["tipo"] == "replanejamento_automatico"]) == 1)

import guardiao_voz as g  # noqa: E402

g.OPER = tmp
g.time = relogio
g.SUPERVISOR.update(dia=None, vezes=0, ultimo=0.0)
antes = v2.avaliar_atraso
v2.avaliar_atraso = lambda: {"precisa": False}
g.supervisionar()
v2.avaliar_atraso = antes
confere("reabrir o guardião não zera o limite de replanejamentos do dia (a conta vem da calibragem)", g.SUPERVISOR["vezes"] == 1 and g.SUPERVISOR["ultimo"] > 0, g.SUPERVISOR)

# ---------------- tarefas novas, com a origem
resumo = os.path.join(tmp, "resumo_clickup.json")


def renovar():
    dados = h._ler_json(resumo)
    dados["tarefas"].append({"id": "z9", "prazo": "2026-12-01", "nome": "Enviar o contrato do cliente novo", "lista": "[CAIXA] Baú de Tarefas", "status": "to do"})
    with open(resumo, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    return True


antes_resumo = h.atualizar_resumo_clickup
h.atualizar_resumo_clickup = renovar
h.sincronizar_com_clickup(espaco=0)
h.atualizar_resumo_clickup = antes_resumo
nova = [e for e in v2._eventos() if e["tipo"] == "tarefas_novas"]
confere("tarefa nova fora do plano é gravada com nome, lista e prazo", nova and nova[-1]["tarefas"][0] == {"id": "z9", "nome": "Enviar o contrato do cliente novo",
                                                                                                        "lista": "[CAIXA] Baú de Tarefas", "prazo": "2026-12-01"}, nova)

# ======================= o motor que aprende (vários dias de dados sintéticos) =======================
from datetime import date, timedelta  # noqa: E402

mot = tempfile.mkdtemp(prefix="gv_motor_")
for p in ("registros", "calibragem", os.path.join("calibragem", "reports"), "planos"):
    os.makedirs(os.path.join(mot, p), exist_ok=True)
uteis, d = [], date.today() - timedelta(days=1)
while len(uteis) < 8:
    if d.weekday() < 5:
        uteis.append(d)
    d -= timedelta(days=1)
uteis.reverse()
linhas = []


def ev(dia, hora, tipo, **x):
    linhas.append(json.dumps({"ts": f"{dia.isoformat()} {hora}:00", "data": dia.isoformat(), "hora": hora, "tipo": tipo, **x}, ensure_ascii=False))


for i, dia in enumerate(uteis):
    manha = i < 4  # nos 4 primeiros dias a copy fica de manhã e começa atrasada; nos outros, à tarde e no horário
    ini_copy = "09:00" if manha else "15:00"
    copy_feita = i not in (1, 2)
    blocos = [{"id": "b1", "titulo": "Copy da página de vendas", "natureza": "copy", "principal": True, "estado": "feito" if copy_feita else "adiado",
               "vezes_adiada": 0 if copy_feita else 1, "planejado": {"inicio": ini_copy, "fim": "10:30" if manha else "16:30", "minutos": 90}},
              {"id": "b2", "titulo": "Subir os vídeos da aula", "natureza": "operacional", "estado": "feito", "planejado": {"inicio": "11:00", "fim": "11:30", "minutos": 30}},
              {"id": "b3", "titulo": "Reunião com o cliente", "natureza": "reuniao", "estado": "feito", "planejado": {"inicio": "14:00", "fim": "15:00", "minutos": 60}},
              {"id": "b4", "titulo": "Responder os directs", "natureza": "atendimento", "estado": "feito", "planejado": {"inicio": "17:00", "fim": "17:30", "minutos": 30}}]
    with open(os.path.join(mot, "registros", f"registro_{dia.isoformat()}.json"), "w", encoding="utf-8") as f:
        json.dump({"data": dia.isoformat(), "blocos": blocos}, f, ensure_ascii=False)
    ev(dia, ini_copy, "inicio_bloco", bloco="b1", titulo="Copy da página de vendas", natureza="copy", planejado=ini_copy, atraso=35 if manha else 2)
    ev(dia, "10:15", "tarefas_novas", quantidade=3, tarefas=[{"id": f"z{i}", "nome": f"Aviso {i} com o link do Zoom da turma", "lista": "[CAIXA] Baú", "prazo": None},
                                                             {"id": f"y{i}", "nome": "Pedido do cliente", "lista": "Clientes"}, {"id": f"x{i}", "nome": f"Outra coisa {i}", "lista": "Clientes"}])
    if i < 3:
        ev(dia, "11:20", "extensao", bloco="b2", titulo="Subir os vídeos da aula", natureza="operacional", minutos=15, motivo="Interrupções")
    if copy_feita:
        with open(os.path.join(mot, "calibragem", "reports", f"{dia.isoformat()}.json"), "w", encoding="utf-8") as f:
            json.dump({"data": dia.isoformat(), "versao": 2, "energia": 4, "atrapalhou": [], "ajudou": ["Tarefa clara, com primeiro passo"], "nota": ""}, f, ensure_ascii=False)
with open(os.path.join(mot, "calibragem", "eventos.jsonl"), "w", encoding="utf-8") as f:
    f.write("\n".join(linhas) + "\n")
with open(os.path.join(mot, "tempos.json"), "w", encoding="utf-8") as f:
    json.dump({"versao": 2, "tipos": {"operacional": {"registros": [{"titulo": "Subir os vídeos da aula", "planejado": 30, "real": r, "confirmado": True} for r in (45, 48, 42)]},
                                      "reuniao": {"registros": [{"titulo": "Reunião com o cliente", "planejado": 60, "real": 60, "confirmado": True}] * 3}}}, f)

p = cm.atualizar_perfil(mot, forcar=True)
ach = {a["id"]: a for a in p["achados"]}
confere("tempo real por natureza vira fato medido pela razão (operacional leva 50% a mais), sem precisar de confirmação",
        ach.get("estimativa:operacional", {}).get("nivel") == "medido" and "50% a mais" in ach["estimativa:operacional"]["texto"], list(ach))
confere("a mesma tarefa repetida ganha a média em minutos (45 min)", ach.get("tarefa:subir video aula", {}).get("regra", "").startswith("Reserve 45 min"), list(ach))
confere("reunião não vira achado de estimativa", "estimativa:reuniao" not in ach)
confere("começar copy atrasado de manhã e no horário à tarde vira achado provável, com a regra de mudar de faixa",
        ach.get("faixa:copy:manha", {}).get("nivel") == "provavel" and "à tarde" in ach["faixa:copy:manha"]["regra"], ach.get("faixa:copy:manha"))
confere("motivo citado 3 vezes vira achado com a regra prática", ach.get("motivo:interrupcoes", {}).get("nivel") == "provavel" and "notificações" in ach["motivo:interrupcoes"]["regra"])
confere("o que entra fora do plano e se repete (o aviso do Zoom) vira proposta de rotina", any(a["tipo"] == "rotina" and "Zoom" in a["texto"] for a in p["achados"]) and p["repetidas"], p["repetidas"])
confere("o que aparece nos dias bons vira achado (tarefa clara)", ach.get("ajudou:tarefa clara, com primeiro passo", {}).get("nivel") == "provavel", [a for a in ach if a.startswith("ajudou")])
confere("dia da semana com muita coisa fora do plano pede folga", any(a["tipo"] == "folga" for a in p["achados"]), [a["id"] for a in p["achados"]])
confere("com 2 dados ainda é hipótese: copy adiada 2 vezes não vira regra", "adia:copy" not in ach or ach["adia:copy"]["nivel"] == "hipotese")

secao = cm.secao_do_plano(p)
confere("a seção do plano leva só o medido e o provável, com o id de cada linha", secao.startswith("CALIBRAGEM") and "[estimativa:operacional]" in secao and "[faixa:copy:manha]" in secao
        and len(secao.splitlines()) <= cm.MAX_LINHAS_PLANO + 1, secao)
confere("e fica em arquivo para o plano automático e o guardião do chat", open(os.path.join(mot, "calibragem", "calibragem_para_o_plano.md"), encoding="utf-8").read() == secao)

h1 = cm.hipotese_do_dia(mot, p)
confere("a pergunta do dia é o provável com mais dados (aqui, o que se repete fora do plano), dita como pergunta",
        h1 and h1["id"].startswith("rotina:") and h1["texto"].endswith("Isso vai continuar aparecendo?"), h1)
outra = next(a for a in p["achados"] if a["tipo"] == "faixa")
confere("os outros achados perguntam se é verdade", outra["pergunta"].startswith("Percebi uma coisa:") and outra["pergunta"].endswith("Isso é verdade?"), outra["pergunta"])
confere("semana com 8 ou mais tarefas fora do plano vira uma ação para o fechamento", any("fora do plano nos últimos 7 dias" in x for x in p["acoes"]), p["acoes"])
cm.marcar_perguntado(mot, h1["id"])
confere("no mesmo dia a pergunta é a mesma", cm.hipotese_do_dia(mot, p)["id"] == h1["id"])
cm.registrar_resposta(mot, h1["id"], "sim", n=h1["n"])
p = cm.atualizar_perfil(mot, forcar=True)
ach = {a["id"]: a for a in p["achados"]}
confere("respondida com sim, vira confirmado e vai para o topo", ach[h1["id"]]["nivel"] == "confirmado" and p["achados"][0]["id"] == h1["id"])
h2 = cm.hipotese_do_dia(mot, p)
confere("a próxima pergunta é outra", h2 and h2["id"] != h1["id"], h2)
cm.registrar_resposta(mot, h2["id"], "nao", n=h2["n"])
p = cm.atualizar_perfil(mot, forcar=True)
secao = cm.secao_do_plano(p)
confere("respondida com não, sai do plano e não é perguntada de novo", f"[{h2['id']}]" not in secao and {a["id"]: a for a in p["achados"]}[h2["id"]]["nivel"] == "negado"
        and (cm.hipotese_do_dia(mot, p) or {}).get("id") != h2["id"])
confere("o confirmado aparece no plano marcado como confirmado", f"[{h1['id']}]" in secao and "confirmado por ela" in secao)

plano_mud = {"data": date.today().isoformat(), "blocos": [{"id": "b1", "inicio": "15:00", "fim": "16:30", "titulo": "Copy da página", "aprendizado": "faixa:copy:manha"}]}
cm.registrar_mudancas(mot, plano_mud, p)
mud = cm.ultimas_mudancas(mot)
confere("bloco que aplica um aprendizado vira O que mudou no plano, sem o Claude escrever nada", mud and "Copy da página às 15:00" in mud[0] and "à tarde" in mud[0], mud)

import plano_base as pb  # noqa: E402

doss = pb.dossie(date.today(), {"data": date.today().isoformat(), "blocos": []}, ["teste"], oper=mot, cfg={"pastas": {"memoria": mot}})
confere("o dossiê do plano automático traz a seção CALIBRAGEM", "CALIBRAGEM (o que o guardião aprendeu" in doss and "[faixa:copy:manha]" in doss)

import motor_agenda as ma  # noqa: E402
import revisor_ia  # noqa: E402

confere("o motor da agenda usa o tempo da mesma tarefa repetida (45 min, medido)", ma.estimar({"titulo": "Subir os vídeos da aula"}, oper=mot) == (45, True), ma.estimar({"titulo": "Subir os vídeos da aula"}, oper=mot))
confere("sem medição, o padrão do motor acompanha a razão da natureza (leve 20 min x 1,5 = 30)", ma.estimar({"titulo": "Configurar a planilha de controle"}, oper=mot) == (30, False), ma.estimar({"titulo": "Configurar a planilha de controle"}, oper=mot))
prompt_rev = revisor_ia.montar_prompt({"dias": {}, "julgar": [], "nao_coube": []}, {"pastas": {"operacional": mot}})
confere("o revisor de IA recebe a seção CALIBRAGEM no prompt", "CALIBRAGEM (o que o guardião aprendeu" in prompt_rev and "[faixa:copy:manha]" in prompt_rev)

# a fala do report vira os mesmos toques da tela
confere("energia falada: número ou por extenso", cm.energia_da_fala("acho que quatro") == 4 and cm.energia_da_fala("2") == 2 and cm.energia_da_fala("sei lá") is None)
confere("o que atrapalhou, falado, vira chips", set(cm.chips_da_fala("muita interrupção e reunião demais", "atrapalhou")) == {"Interrupções", "Reunião demais"})
confere("o que ajudou, falado, vira chips", cm.chips_da_fala("o primeiro passo estava claro e eu comecei cedo", "ajudou") == ["Tarefa clara, com primeiro passo", "Comecei cedo"])
confere("sim, não e às vezes", cm.resposta_da_fala("é verdade") == "sim" and cm.resposta_da_fala("não, não é isso") == "nao" and cm.resposta_da_fala("às vezes") == "as_vezes"
        and cm.resposta_da_fala("talvez amanhã") is None)

# ======================= report do dia no painel: convite na hora de parar, voz e calibragem contínua =======================
relogio.hora = "15:40"
confere("antes da hora de parar não convida", v2._tique_report() is None and not v2.CHECKIN)
relogio.hora = "15:55"
c = v2._tique_report()
confere("na hora de parar (fim do plano, 16:00), convida para o report com o resumo do dia", c and c["bloco"] == "report" and c["texto"].startswith("Fim do dia. Hoje você fez")
        and [o["resposta"] for o in c["opcoes"]] == ["report_agora", "report_depois"], c)
confere("convida uma vez só", (v2.CHECKIN and v2._tique_report() is None))
r = g.convite_report_local("vamos")
confere("pela voz, 'vamos' começa o roteiro do report sem o Claude", r == {"roteiro": "report"} and not v2.CHECKIN, r)

ditos = []
antes_dizer = g.dizer
g.dizer = lambda texto, a=None: ditos.append(texto)
g.iniciar_roteiro(None)
confere("o roteiro começa pelo resumo do dia e pergunta a energia", ditos and "Hoje você fez" in ditos[-1] and ditos[-1].endswith("como foi a sua energia hoje?"), ditos[-1:])
for fala in ("quatro", "muita interrupção", "o primeiro passo estava claro"):
    g.tratar_roteiro(fala, None, False)
while g.ROTEIRO and g.ROTEIRO["passos"][g.ROTEIRO["i"]] != "nota":
    g.tratar_roteiro("sim", None, False)
g.tratar_roteiro("pronto", None, False)
g.dizer = antes_dizer
rep = v2._report_de(date.today().isoformat())
confere("o report falado grava os mesmos toques da tela", rep and rep["versao"] == 2 and rep["origem"] == "voz" and rep["energia"] == 4 and rep["atrapalhou"] == ["Interrupções"]
        and rep["ajudou"] == ["Tarefa clara, com primeiro passo"] and rep["resumo"]["planejadas"] == 7, rep)
k = v2.calibragem()
confere("a calibragem mostra o report de hoje e o resumo do dia", k["estado"] == "sent" and k["hoje"]["versao"] == 2 and k["resumo"]["frase"].startswith("Hoje você fez")
        and k["opcoes"]["ajudou"] == cm.AJUDOU)
confere("com o report feito, o convite não volta", v2._tique_report() is None)
r = v2.salvar_report({"energia": 9, "atrapalhou": ["inventado"], "nota": ""}, "tela")
confere("report sem nada válido é recusado (energia fora de 1 a 5 e chip que não existe)", r["ok"] is False, r)

# calibragem contínua: 45 dias de trabalho com report, e o aviso de recalibrar quando a semana-base muda
inicio, dias_cal, d = None, [], date.today()
while len(dias_cal) < 45:
    if d.weekday() < 5 or d == date.today():
        dias_cal.append(d)
    d -= timedelta(days=1)
for dia in dias_cal:
    with open(os.path.join(tmp, "calibragem", "reports", f"{dia.isoformat()}.json"), "w", encoding="utf-8") as f:
        json.dump({"data": dia.isoformat(), "versao": 2, "energia": 3}, f)
semana_base = os.path.join(tmp, "memoria", "semana-base.md")
with open(semana_base, "w", encoding="utf-8") as f:
    f.write("semana nova")
with open(os.path.join(tmp, "calibragem", "estado.json"), "w", encoding="utf-8") as f:
    json.dump({"inicio": dias_cal[-1].isoformat(), "ciclo": 1, "semana_base_mtime": int(os.path.getmtime(semana_base)) - 86400}, f)
k = v2.calibragem()
confere("depois do dia 30 a calibragem continua: conta os dias e a trilha mostra os últimos 30", k["continua"] is True and k["dia"] == 45 and len(k["trilha"]) == 30
        and k["trilha"][-1]["d"] == 45 and k["estado"] == "sent" and k["reports"] == 45, (k["dia"], k["estado"], k["trilha"][-1]))
confere("semana-base mudou depois do começo da calibragem: sugere recalibrar", bool(k["recalibrar"]) and "recomece a calibragem" in k["recalibrar"], k["recalibrar"])

# ======================= estatísticas e conquistas =======================
import conquistas  # noqa: E402
import estatisticas  # noqa: E402

est = estatisticas.calcular(mot)
kp = {k["chave"]: k for k in est["kpis"]}
confere("estatísticas: 4 números no topo, cada um com 8 semanas", set(kp) == {"cumprido", "principal", "precisao", "foco_h"} and all(len(k["serie"]) == 8 for k in est["kpis"]))
semanas_com = [s for s in est["semanas"] if s["dias"]]
confere("plano cumprido e tarefa principal feita saem dos registros do dia", semanas_com and all(s["cumprido"] is not None for s in semanas_com)
        and any(s["principal"] is not None and s["principal"] < 100 for s in semanas_com), semanas_com)
confere("precisão sem tarefa medida fica como pouco dado (nunca inventa número)", all(s["precisao"] is None for s in est["semanas"]))
confere("motivos, atraso por faixa e o que entra fora do plano por dia da semana", est["motivos"][0] == {"motivo": "Interrupções", "vezes": 3}
        and {a["faixa"] for a in est["atraso_por_faixa"]} == {"de manhã", "à tarde"} and all(v == 3 for v in est["fora_por_dia"].values()), (est["motivos"], est["atraso_por_faixa"], est["fora_por_dia"]))
confere("energia contra rendimento, dos reports", est["energia"] and est["energia"][0]["energia"] == 4 and est["energia"][0]["cumprido"] == 100, est["energia"])
confere("entregas só aparecem com 3 tarefas com prazo concluídas", est["entregas"] is None)

c1 = conquistas.calcular(mot, memoria=mot)
cq = {c["id"]: c for c in c1["lista"]}
confere("22 conquistas, com grupo, regra e meta", c1["total"] == 22 and all(c["regra"] and c["meta"] >= 1 for c in c1["lista"]))
confere("na primeira vez, o que já estava cumprido entra sem anúncio (retroativo)", cq["primeiro_report"]["desbloqueada"] and not c1["novas"] and not cq["primeiro_report"]["nova"])
confere("progresso do que falta: 6 de 7 reports, sem desbloquear antes da hora", cq["calib_7"]["progresso"] == 6 and not cq["calib_7"]["desbloqueada"], cq["calib_7"])
confere("conquista de padrão confirmado vem da resposta sim à pergunta do dia", cq["padrao_confirmado"]["desbloqueada"])
with open(os.path.join(mot, "calibragem", "reports", f"{date.today().isoformat()}.json"), "w", encoding="utf-8") as f:
    json.dump({"data": date.today().isoformat(), "versao": 2, "energia": 3}, f)
c2 = conquistas.calcular(mot, memoria=mot)
confere("o sétimo report desbloqueia a Semana calibrada, como novidade", [n["id"] for n in c2["novas"]] == ["calib_7"] and {c["id"]: c for c in c2["lista"]}["calib_7"]["nova"], c2["novas"])
confere("e ela não é anunciada de novo", conquistas.calcular(mot, memoria=mot)["novas"] == [])
with open(os.path.join(mot, "aprendizados.md"), "w", encoding="utf-8") as f:
    f.write("# Aprendizados\n\n## Regras\n- Quando o plano põe copy depois das 14h, mova para a manhã. Teste: toda copy cai na manhã?\n")
confere("a primeira regra escrita no aprendizados.md é conquista", [n["id"] for n in conquistas.calcular(mot, memoria=mot)["novas"]] == ["primeira_regra"])

comandos_antes = []
while not h.bus.comandos.empty():
    comandos_antes.append(h.bus.comandos.get_nowait())
k = v2.calibragem()
confere("a calibragem do painel traz as estatísticas e as conquistas", k["estatisticas"] and len(k["estatisticas"]["kpis"]) == 4 and k["conquistas"]["total"] == 22)
confere("no painel de teste, 45 reports já desbloquearam as de constância até 30 dias", all({c["id"]: c for c in k["conquistas"]["lista"]}[i]["desbloqueada"] for i in ("calib_7", "calib_14", "calib_21", "calib_30")))
with open(os.path.join(tmp, "memoria", "aprendizados.md"), "w", encoding="utf-8") as f:
    f.write("## Regras\n- Quando X, faça Y. Teste: sim?\n")
v2.verificar_conquistas()
ditos = [v for t, v in [h.bus.comandos.get_nowait() for _ in range(h.bus.comandos.qsize())] if t == "dizer"]
confere("conquista nova é dita pela voz, uma vez", "Conquista desbloqueada: Primeira regra." in ditos and v2.verificar_conquistas()["novas"] == [], ditos)

# ======================= mapeamento de rotina (o que entra fora do plano e se repete) =======================
r = v2.salvar_report({"energia": 3, "hipotese": {"id": "rotina:aviso link zoom turma", "texto": "\"Aviso com o link do Zoom\" entrou 8 vezes...", "resposta": "sim"}}, "tela")
confere("responder sim à pergunta de rotina registra a rotina aceita e desbloqueia Rotina mapeada",
        r["ok"] and any(e["tipo"] == "rotina_aceita" and e["id"] == "rotina:aviso link zoom turma" for e in v2._eventos())
        and {c["id"]: c for c in v2.verificar_conquistas()["lista"]}["rotina_mapeada"]["desbloqueada"])
import contextlib  # noqa: E402
import io  # noqa: E402

saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    cm.main(["--oper", mot, "--perfil"])
texto_cli = saida.getvalue()
confere("o guardião do chat vê, sem abrir o painel, a seção do plano e o que se repete com o id para aceitar",
        texto_cli.startswith("CALIBRAGEM") and "se repete fora do plano" in texto_cli and "id rotina:" in texto_cli, texto_cli[:300])
with contextlib.redirect_stdout(io.StringIO()):
    cm.main(["--oper", mot, "--fechamento"])
    cm.main(["--oper", mot, "--rotina-aceita", "rotina:pedido cliente"])
cmot = {c["id"]: c for c in conquistas.calcular(mot, memoria=mot)["lista"]}
confere("fechamento e rotina aceita pelo chat ficam registrados e contam nas conquistas", cmot["semana_fechada"]["desbloqueada"] and cmot["rotina_mapeada"]["desbloqueada"]
        and cm._confirmacoes(mot)["rotina:pedido cliente"]["resposta"] == "sim")
p = cm.atualizar_perfil(mot, forcar=True)
confere("a rotina aceita vira linha confirmada no plano: reserva de horário antes de a tarefa aparecer",
        "[rotina:pedido cliente] Reserve um horário para \"Pedido do cliente\"" in cm.secao_do_plano(p), cm.secao_do_plano(p))

v2.sair()

raise SystemExit(0 if B.placar() else 1)
