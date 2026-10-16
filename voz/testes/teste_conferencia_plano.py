"""Conferência do plano (2026-10-14): campanha encerrada sai da exigência, gravação sem leitura é negada, sobreposição e removido voltando são barrados."""
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conferencia_plano as cp

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


mem = tempfile.mkdtemp()
os.makedirs(os.path.join(mem, "campanhas"))


def campanha(slug, ini, fim, status):
    with open(os.path.join(mem, "campanhas", slug + ".md"), "w", encoding="utf-8") as f:
        f.write(f"---\nnome: {slug}\nslug: {slug}\ndata_inicio: {ini}\ndata_fim: {fim}\nstatus: {status}\n---\n# x\n")


hoje = date(2026, 10, 14)
campanha("viva", "2026-10-08", "2026-11-03", "em-execucao")
campanha("acabou", "2026-10-01", "2026-10-13", "em-execucao")
campanha("encerrada", "2026-10-01", "2026-11-03", "concluida")
campanha("longe", "2026-12-01", "2026-12-10", "planejando")
campanha("proxima", "2026-10-28", "2026-10-30", "planejando")
confere("só as campanhas que pesam hoje", sorted(cp.campanhas_ativas(mem, hoje)) == ["proxima", "viva"])
confere("Read da nota conta", cp.slug_lido("Read", {"file_path": "C:/x/campanhas/viva.md"}, mem) == "viva")
confere("ler_campanha.ps1 conta", cp.slug_lido("PowerShell", {"command": "powershell -File ler_campanha.ps1 -Slug proxima"}, mem) == "proxima")
confere("outro Read não conta", cp.slug_lido("Read", {"file_path": "C:/x/perfil.md"}, mem) is None)
confere("plano de hoje é arquivo de plano", cp.eh_arquivo_de_plano("D:/a/plano_do_dia.json") and cp.eh_arquivo_de_plano("D:/a/planos/plano_2026-10-15.json"))
confere("outro json não é", not cp.eh_arquivo_de_plano("D:/a/resumo_clickup.json"))

bom = {"agenda_impoe": "roteiro até 21/10", "fixos": [], "blocos": [{"id": "b1", "inicio": "16:55", "fim": "17:40", "titulo": "Material de aula"}]}
confere("plano limpo passa", cp.conferir(bom) == [])
confere("sem agenda_impoe barra", any("agenda_impoe" in p for p in cp.conferir({"blocos": []})))
sobre = dict(bom, blocos=bom["blocos"] + [{"id": "b2", "inicio": "17:30", "fim": "17:50", "titulo": "Stories"}])
confere("sobreposição barra", any("sobrepõe" in p for p in cp.conferir(sobre)))
confere("bloco já feito não conta na sobreposição", cp.conferir(sobre, feitos={"b2"}) == [])
volta = dict(bom, blocos=bom["blocos"] + [{"id": "b7", "inicio": "18:00", "fim": "18:15", "titulo": "Aprovações do Caio (1 do Davi)"}])
confere("removido não volta", any("Caio" in p for p in cp.conferir(volta, {"removidos": ["Aprovações do Caio"]})))

# conferência de semana (2026-10-14): tarefa não some, prazo final vale, nobre é do importante
qui = date(2026, 10, 15)
base = {"agenda_impoe": "x", "fixos": [{"inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}], "blocos": [
    {"id": "b1", "inicio": "08:50", "fim": "09:50", "titulo": "Edição de segunda", "frente": "Conteúdo", "clickup_id": "c1"},
    {"id": "b2", "inicio": "09:50", "fim": "13:00", "titulo": "Roteiro", "frente": "Rebranding"},
    {"id": "b3", "inicio": "19:45", "fim": "21:15", "titulo": "Página do Carlos", "frente": "Agência", "prazo_final": "2026-10-16"}]}
confere("semana: plano intacto passa", cp.conferir_semana(base, qui, base, {}, {"c1"}) == [])
sumiu = dict(base, blocos=base["blocos"][1:])
confere("semana: copy que some sem ir para outro dia barra", any("não está em nenhum outro dia" in p for p in cp.conferir_semana(sumiu, qui, base, {}, {"c1"})))
confere("semana: copy movida para sexta passa", cp.conferir_semana(sumiu, qui, base, {"2026-10-16": {"blocos": [base["blocos"][0]]}}, {"c1"}) == [])
confere("semana: tarefa já concluída no ClickUp pode sair", cp.conferir_semana(sumiu, qui, base, {}, set()) == [])
confere("semana: removido a pedido pode sair", cp.conferir_semana(dict(sumiu, removidos=["Edição de segunda"]), qui, base, {}, {"c1"}) == [])
manha = dict(base, blocos=[dict(base["blocos"][2], inicio="09:50", fim="11:20"), dict(base["blocos"][1], inicio="11:20", fim="13:00"), base["blocos"][0]])
manha["blocos"][2] = dict(base["blocos"][0], inicio="08:40", fim="09:50")
confere("semana: agência com folga no nobre cheio barra", any("horário nobre" in p for p in cp.conferir_semana(manha, qui, base, {}, {"c1"})))
vazio = {"agenda_impoe": "x", "blocos": [dict(base["blocos"][2], inicio="09:00", fim="10:30")]}
confere("semana: agência no nobre de manhã vazia passa", not any("horário nobre" in p for p in cp.conferir_semana(vazio, qui, None, {}, set())))
confere("semana: depois do prazo final barra", any("depois do prazo final" in p for p in cp.conferir_semana(base, date(2026, 10, 19), None, {}, {"c1"})))
sem_prazo = dict(base, blocos=base["blocos"][:2] + [{k: v for k, v in base["blocos"][2].items() if k != "prazo_final"}])
confere("semana: prazo final não pode sumir ao mudar", any("prazo_final" in p for p in cp.conferir_semana(sem_prazo, qui, base, {}, {"c1"})))
confere("data do plano pelo arquivo", cp.data_do_plano("D:/x/planos/plano_2026-10-16.json", {}) == date(2026, 10, 16))

# visão da semana: pré-plano do ClickUp nos dias sem plano gravado
import json
import visao_semana as vs
oper = tempfile.mkdtemp()
os.makedirs(os.path.join(oper, "planos"))
with open(os.path.join(oper, "planos", "plano_2026-10-15.json"), "w", encoding="utf-8") as f:
    json.dump(base, f)
with open(os.path.join(oper, "resumo_clickup.json"), "w", encoding="utf-8") as f:
    json.dump({"tarefas": [{"id": "c9", "nome": "Gravação de segunda", "prazo": "2026-10-16", "inicio": "11:00", "fim": "13:00", "lista": "Conteúdos"},
                           {"id": "c1", "nome": "Edição de segunda", "prazo": "2026-10-15", "lista": "Conteúdos"},
                           {"id": "c7", "nome": "Esquecida", "prazo": "2026-10-15", "inicio": "15:00", "fim": "16:00", "lista": "Conteúdos"}]}, f)
t = vs.texto(oper, mem, hoje=date(2026, 10, 15))
confere("visão: sexta sem plano mostra o pré-plano do ClickUp", "Sex 16/10" in t and "pré-planejado no ClickUp" in t and "11:00-13:00 Gravação de segunda" in t)
confere("visão: tarefa do dia fora do plano aparece para decidir", "Esquecida" in t and "c1" not in t.split("FORA DELE")[1].split("COMO USAR")[0])
confere("visão: livre e nobre calculados", "Qui 15/10" in t and "horário nobre" in t)
com_c9 = dict(base, blocos=base["blocos"] + [{"id": "b9", "titulo": "Gravação de segunda", "clickup_id": "c9", "inicio": "15:00", "fim": "16:00"}])
confere("semana: tarefa que já está no pré-plano de outro dia pode sair", cp.conferir_semana(base, qui, com_c9, vs.planos_da_semana(oper, qui), {"c1", "c9"}) == [])

# regras que viraram conta (2026-10-14)
qua = date(2026, 10, 14)
maes = [{"id": "m15", "nome": "Post de quinta sobre vendas", "prazo": "2026-10-15", "etapas": [{"id": "c15"}, {"id": "d15"}]},
        {"id": "m16", "nome": "Post de sexta sobre desejo", "prazo": "2026-10-16", "etapas": [{"id": "d16"}]},
        {"id": "m19", "nome": "Post de segunda sobre marketing", "prazo": "2026-10-19", "etapas": [{"id": "d19"}]}]
def pl(*blocos):
    return {"blocos": list(blocos), "fixos": [{"inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}]}
def bl(i, ini, titulo, cid=None, **x):
    return dict(id=i, inicio=ini, fim=ini[:3] + "59", titulo=titulo, clickup_id=cid, **x)
almoco = [{"dias": [0, 1, 2, 3, 4], "inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}]
confere("regras: plano certo passa", cp.conferir_regras(pl(bl("a", "09:00", "Copy | Post de quinta sobre vendas", "c15"), bl("b", "14:00", "Design | Post de quinta sobre vendas", "d15")), qua, {}, maes, almoco) == [])
confere("regras: design antes da copy do mesmo post é barrado", any("A copy vem antes" in x for x in cp.conferir_regras(
    pl(bl("a", "09:00", "Design | Post de quinta sobre vendas", "d15"), bl("b", "11:00", "Copy | Post de quinta sobre vendas", "c15")), qua, {}, maes, almoco)))
erro_de_ontem = cp.conferir_regras(pl(bl("a", "14:00", "Design | Post de segunda sobre marketing", "d19")), qua,
                                   {"2026-10-15": pl(bl("b", "16:00", "Design | Post de sexta sobre desejo", "d16"))}, maes, almoco)
confere("regras: design do post de segunda antes do de sexta é barrado (erro de 14/10)", any("ordem das datas de postagem" in x for x in erro_de_ontem), erro_de_ontem)
confere("regras: na ordem certa entre dias, passa", cp.conferir_regras(pl(bl("a", "14:00", "Design | Post de sexta sobre desejo", "d16")), qua,
        {"2026-10-15": pl(bl("b", "16:00", "Design | Post de segunda sobre marketing", "d19"))}, maes, almoco) == [])
confere("regras: almoço que some é barrado, e só para quem tem almoço na rotina",
        any("almoço" in x for x in cp.conferir_regras({"blocos": [], "fixos": []}, qua, {}, [], almoco)) and cp.conferir_regras({"blocos": [], "fixos": []}, qua, {}, [], []) == [])
confere("regras: post chamado por letra é barrado", any("por letra" in x for x in cp.conferir_regras(pl(bl("a", "09:00", "Copy do carrossel B")), qua, {}, [], almoco)))
alternado = pl(bl("a", "09:00", "Copy | Post de quinta sobre vendas", "c15"), bl("b", "10:00", "Design | Post de sexta sobre desejo", "d16"), bl("c", "11:00", "Copy | outra coisa qualquer"))
confere("regras: copy, design, copy só é barrado com a regra pessoal ligada",
        cp.conferir_regras(alternado, qua, {}, maes, almoco) == [] and any("Agrupe" in x for x in cp.conferir_regras(alternado, qua, {}, maes, almoco, lote=True)))
# tarefa movida no ClickUp de um dia planejado para um dia pré-planejado não é "tarefa que some" (14/10)
oper2 = tempfile.mkdtemp()
os.makedirs(os.path.join(oper2, "planos"))
with open(os.path.join(oper2, "planos", "plano_2026-10-15.json"), "w", encoding="utf-8") as f:
    json.dump({"blocos": [{"id": "b1", "inicio": "11:00", "fim": "11:30", "titulo": "Encaixar ideias", "clickup_id": "e1"}]}, f)
with open(os.path.join(oper2, "resumo_clickup.json"), "w", encoding="utf-8") as f:
    json.dump({"tarefas": [{"id": "e1", "nome": "Encaixar ideias", "prazo": "2026-10-16", "inicio": "09:00", "fim": "09:40"}]}, f)
semana = vs.planos_da_semana(oper2, date(2026, 10, 14))
antes15 = semana["2026-10-15"]
confere("tarefa que o ClickUp já pôs na sexta aparece no pré-plano da sexta", any(b.get("clickup_id") == "e1" for b in semana.get("2026-10-16", {}).get("blocos", [])), semana.get("2026-10-16"))
confere("e sair da quinta não é barrado", cp.conferir_semana({"blocos": []}, date(2026, 10, 15), antes15, semana, {"e1"}) == [])
sem_consumo = pl(bl("a", "09:00", "Pensar ideias e DOPA da semana"), bl("b", "10:00", "Rascunho do Substack (só a ideia)"))
com_consumo = pl(bl("c", "08:30", "Consumo com a pergunta"), bl("a", "09:00", "Pensar ideias e DOPA da semana"))
confere("regra pessoal: ideia sem consumo antes é barrada só com a regra ligada",
        cp.conferir_regras(sem_consumo, qua, {}, [], almoco) == [] and len(cp.conferir_regras(sem_consumo, qua, {}, [], almoco, consumo_antes_de_ideia=True)) == 2
        and cp.conferir_regras(com_consumo, qua, {}, [], almoco, consumo_antes_de_ideia=True) == [])

maes_rel = [{"id": "m1", "nome": "Postar várias vezes não adianta NADA", "prazo": "2026-10-15", "etapas": [{"id": "r1"}]}]
rel = {"blocos": [{"id": "x", "inicio": "16:40", "fim": "17:05", "titulo": "Preencher relatório do Postar várias vezes não adianta NADA", "clickup_id": "r1"}]}
confere("relatório no mesmo dia do post é barrado; no dia seguinte passa (caso real 15/10)",
        len(cp.conferir_regras(rel, date(2026, 10, 15), {}, maes_rel, [])) == 1 and cp.conferir_regras(rel, date(2026, 10, 16), {}, maes_rel, []) == [])

# alavancas: campanha pública de venda que termina em até 3 dias exige bloco que traga gente
mem_a = tempfile.mkdtemp()
os.makedirs(os.path.join(mem_a, "campanhas"))


def campanha(slug, tipo, fim, extra=""):
    with open(os.path.join(mem_a, "campanhas", slug + ".md"), "w", encoding="utf-8") as f:
        f.write(f"---\nnome: {slug}\nslug: {slug}\ntipo: {tipo}\nstatus: em-execucao\ndata_inicio: 2026-10-01\ndata_fim: {fim}\n{extra}---\n# {slug}\n")


campanha("venda-x", "venda-publica", "2026-10-31")
sem_alavanca = {"blocos": [{"id": "a", "inicio": "09:00", "fim": "10:00", "titulo": "Decidir o bônus"}], "fixos": []}
com_stories = {"blocos": [{"id": "a", "inicio": "09:00", "fim": "10:00", "titulo": "Stories de aquecimento"}], "fixos": []}
confere("venda pública a 2 dias do fim sem bloco de alavanca é barrada", len(cp.conferir_alavancas(sem_alavanca, date(2026, 10, 29), mem_a)) == 1)
confere("com stories no dia passa", cp.conferir_alavancas(com_stories, date(2026, 10, 29), mem_a) == [])
confere("longe do fim (7 dias) não cobra", cp.conferir_alavancas(sem_alavanca, date(2026, 10, 24), mem_a) == [])
campanha("interna-y", "acao-comercial", "2026-10-31")
os.remove(os.path.join(mem_a, "campanhas", "venda-x.md"))
confere("campanha que não é venda pública não cobra alavanca", cp.conferir_alavancas(sem_alavanca, date(2026, 10, 29), mem_a) == [])
campanha("venda-z", "venda-ao-vivo", "2026-10-31", "alavancas: reels, convite\n")
confere("a lista de alavancas da nota vale no lugar da padrão", len(cp.conferir_alavancas(com_stories, date(2026, 10, 29), mem_a)) == 1
        and cp.conferir_alavancas({"blocos": [{"id": "a", "inicio": "09:00", "fim": "10:00", "titulo": "Reels de convite"}], "fixos": []}, date(2026, 10, 29), mem_a) == [])
campanha("venda-z", "venda-publica", "2026-10-31", "publica: nao\n")
confere("campanha marcada como interna (publica: nao) não cobra", cp.conferir_alavancas(sem_alavanca, date(2026, 10, 29), mem_a) == [])
# erros críticos do plano de 15/10: consumo duplo, tarefa em dois planos, bloco depois do prazo
dois_consumos = {"blocos": [{"id": "a", "inicio": "16:30", "fim": "17:10", "titulo": "Consumo com a pergunta: isso pode virar post?"}],
                 "fixos": [{"inicio": "09:20", "fim": "09:45", "titulo": "Recarga: leitura ou curso, sem tela de trabalho"}]}
confere("dois blocos de consumo/recarga no mesmo dia são barrados; um só passa", len(cp.conferir_consumo(dois_consumos)) == 1
        and cp.conferir_consumo({"blocos": dois_consumos["blocos"], "fixos": []}) == [])
plano_seg = {"blocos": [{"id": "a", "inicio": "15:30", "fim": "17:10", "titulo": "Rascunho do Substack", "clickup_id": "T1"}]}
outros_dup = {"2026-10-16": {"blocos": [{"id": "b3", "inicio": "14:00", "fim": "15:40", "titulo": "Rascunho do Substack", "clickup_id": "T1"}]}}
confere("tarefa que já está no plano de outro dia é barrada", len(cp.conferir_duplicadas(plano_seg, date(2026, 10, 19), outros_dup)) == 1
        and cp.conferir_duplicadas(plano_seg, date(2026, 10, 19), {"2026-10-16": {"blocos": [{"clickup_id": "T1"}]}}) == [])
newsletter = {"T2": {"id": "T2", "prazo": "2026-10-19", "inicio": None, "fim": "09:00"}}
plano_news = {"blocos": [{"id": "a", "inicio": "17:10", "fim": "17:30", "titulo": "Substack - Newsletter", "clickup_id": "T2"}]}
confere("bloco depois do horário limite da tarefa (Substack às 9h, bloco às 17h10) é barrado",
        len(cp.conferir_prazos(plano_news, date(2026, 10, 19), newsletter)) == 1)
confere("o mesmo trabalho na sexta, antes do prazo, passa; e tarefa com início (movível) não é cobrada",
        cp.conferir_prazos({"blocos": [{"id": "a", "inicio": "14:00", "fim": "15:40", "titulo": "Rascunho", "clickup_id": "T2"}]}, date(2026, 10, 16), newsletter) == []
        and cp.conferir_prazos(plano_news, date(2026, 10, 19), {"T2": {"id": "T2", "prazo": "2026-10-19", "inicio": "09:00", "fim": "10:00"}}) == [])
# blocos diários obrigatórios (stories em todo dia de trabalho)
cfg_d = {"rotina": {"dias_trabalho": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                    "blocos_diarios": [{"nome": "stories", "palavras": ["stories", "story"], "excluir": ["cronograma"], "minutos_minimos": 15, "bloco_max_min": 40}]}}
b_ = lambda ini, fim, tit: {"id": "x", "inicio": ini, "fim": fim, "titulo": tit}
segunda_ = date(2026, 10, 19)
confere("dia de trabalho sem stories é barrado", len(cp.conferir_blocos_diarios({"blocos": [b_("09:00", "10:00", "Copy do post")], "fixos": []}, segunda_, cfg_d)) == 1)
confere("com stories de 15 min passa; cronograma de stories (planejar) não conta", cp.conferir_blocos_diarios({"blocos": [b_("17:10", "17:25", "Stories do replay: 3 telas")], "fixos": []}, segunda_, cfg_d) == []
        and len(cp.conferir_blocos_diarios({"blocos": [b_("09:45", "10:45", "Cronograma de stories da semana")], "fixos": []}, segunda_, cfg_d)) == 1)
confere("stories em lote (bloco de 3h) é barrado; vários blocos curtos passam",
        any("blocos menores" in x for x in cp.conferir_blocos_diarios({"blocos": [b_("14:00", "17:00", "Stories do dia")], "fixos": []}, segunda_, cfg_d))
        and cp.conferir_blocos_diarios({"blocos": [b_("10:00", "10:30", "Stories 1"), b_("15:00", "15:30", "Stories 2")], "fixos": []}, segunda_, cfg_d) == [])
confere("sábado não cobra, e sem a regra no config nada é cobrado", cp.conferir_blocos_diarios({"blocos": [], "fixos": []}, date(2026, 10, 17), cfg_d) == []
        and cp.conferir_blocos_diarios({"blocos": [], "fixos": []}, segunda_, {"rotina": {}}) == [])
# stories: mínimo de 10 telas por dia; 3 telas só no dia de captação (1 por semana)
cfg_s2 = {"rotina": {"dias_trabalho": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "stories": {"ativo": True}}}
st_ = lambda ini, fim, tit: {"id": "s", "inicio": ini, "fim": fim, "titulo": tit}
sex = date(2026, 10, 16)
so_replay = {"blocos": [st_("17:10", "17:25", "Stories do replay da sala secreta: 3 telas")], "fixos": []}
confere("sexta só com 3 telas de divulgação (caso real 16/10) é barrada", len(cp.conferir_stories(so_replay, sex, cfg_s2)) == 1)
dez = {"blocos": [st_("10:00", "10:15", "Stories: respostas da caixinha (4 telas)"), st_("14:00", "14:15", "Stories: respostas da caixinha (4 telas)"), st_("17:10", "17:25", "Stories do replay da sala secreta: 3 telas")], "fixos": []}
confere("2 caixinhas (8 telas) + replay (3) = 11 telas passa", cp.conferir_stories(dez, sex, cfg_s2) == [])
normal = {"blocos": [st_("14:00", "14:30", "Stories: sequência normal (8 a 10 telas)")], "fixos": []}
confere("sequência normal de 30 min (8 a 10 telas) sozinha: 10 telas, passa", cp.conferir_stories(normal, sex, cfg_s2) == [])
cap = {"blocos": [st_("14:00", "14:15", "Stories de captação de leads (3 telas)")], "fixos": []}
confere("dia de captação com só 3 telas passa; um segundo dia de captação na mesma semana é barrado",
        cp.conferir_stories(cap, date(2026, 10, 15), cfg_s2) == []
        and len(cp.conferir_stories(cap, sex, cfg_s2, {"2026-10-15": cap})) == 1)
confere("telas de caixinha sem número no título saem da conta (15 min = 4 telas); bloco de 3h é barrado como lote",
        cp.telas_do_bloco(st_("10:00", "10:15", "Responder a caixinha"), cp.config_stories(cfg_s2)) == 4
        and any("blocos menores" in x for x in cp.conferir_stories({"blocos": [st_("14:00", "17:00", "Stories do dia")], "fixos": []}, sex, cfg_s2)))
confere("sem rotina.stories no config nada é cobrado; sábado não cobra", cp.conferir_stories(so_replay, sex, {"rotina": {}}) == [] and cp.conferir_stories({"blocos": []}, date(2026, 10, 17), cfg_s2) == [])
sys.exit(1 if falhas else 0)
