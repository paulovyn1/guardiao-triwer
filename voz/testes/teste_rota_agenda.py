"""Roteador da agenda (2026-10-14): nível 1 só quando cabe hoje num espaço contínuo do tipo certo; nível 2 quando cabe na semana antes da data segura
(direto ou tirando um leve do nobre); nível 3 quando a semana não comporta ou o prazo passa da semana. Margem do tempos.json, prazo sem folga,
extensão autorizada, dia de marco crítico por último, alertas e marcos lidos das tabelas das campanhas."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rota_agenda as ra

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


oper, mem = tempfile.mkdtemp(), tempfile.mkdtemp()
os.makedirs(os.path.join(oper, "planos"))
os.makedirs(os.path.join(mem, "campanhas"))
hoje = date(2026, 10, 14)  # quarta


def grava(nome, dados):
    with open(os.path.join(oper, nome), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)


def b(i, ini, fim, titulo, frente="Conteúdo", **x):
    return dict(id=i, inicio=ini, fim=fim, titulo=titulo, frente=frente, **x)


grava("config.json", {"rotina": {"almoco": "13:00", "fixos_semana": [{"dias": [0, 1, 2, 3, 4], "inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}]}})
grava("tempos.json", {"tipos": {}})
# hoje: livre 15:00-16:00 e 18:00-19:20
grava("plano_do_dia.json", {"data": "2026-10-14", "blocos": [b("b1", "08:40", "13:00", "Copy grande"), b("b2", "14:00", "15:00", "Design X"),
                                                            b("b3", "16:00", "18:00", "Stories e mensagens")],
                            "fixos": [{"inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}]})
# quinta lotada no nobre, com um leve (aprovações) no nobre e tarde livre 14:00-16:00
grava("planos/plano_2026-10-15.json", {"data": "2026-10-15", "blocos": [b("c1", "08:40", "10:40", "Copy A"), b("c2", "10:40", "11:20", "Aprovações do Vitor", "Agência"),
                                                                       b("c3", "11:20", "13:00", "Roteiro B"), b("c4", "16:00", "18:00", "Design C"), b("c5", "18:00", "19:20", "Aula")],
                                       "fixos": [{"inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}]})
grava("resumo_clickup.json", {"tarefas": [{"id": "x1abc23456", "nome": "Copy do post de segunda", "prazo": "2026-10-16", "inicio": "08:40", "fim": "13:00", "lista": "Conteúdos"},
                                          {"id": "x2abc23456", "nome": "Design do post de segunda", "prazo": "2026-10-16", "inicio": "14:00", "fim": "18:00", "lista": "Conteúdos"},
                                          {"id": "x3abc23456", "nome": "Decidir o bônus", "prazo": "2026-10-20", "lista": "Estratégia"}]})
with open(os.path.join(mem, "campanhas", "lanc.md"), "w", encoding="utf-8") as f:
    f.write("---\nslug: lanc\ndata_inicio: 2026-10-10\ndata_fim: 2026-11-20\nstatus: em-execucao\nimportancia: critica\n---\n# Lanc\n## 2. Estado\n| Data | x |\n|---|---|\n| Sex 30 | não é marco |\n"
            "## 3. Marcos e tarefas\n| Data | Marco ou tarefa | Dono | ClickUp |\n|---|---|---|---|\n| Ter 20 | Decidir o bônus | Milena | x3abc23456 |\n"
            "| Qua 4/11 | Abertura do carrinho | Milena | a criar |\n| Seg 9/11 | Live de vendas | Paulo | x9abc23456 |\n\n| Mãe (ClickUp) | Data | Itens |\n|---|---|---|\n"
            "| Página no ar (y1abc23456) | qua 28 | copy e design |\n## 4. Decisões\n- 2026-10-12 | Algo decidido | x\n")
ra.OPER = oper


def rota(minutos, tipo, prazo=None, frente="", agora=14 * 60 + 50, estender=None, depende=0):
    ra.ESTENDER.clear()
    ra.ESTENDER.update(estender or {})
    return ra.decidir(minutos, tipo, prazo, frente, "t", hoje=hoje, agora=agora, depende_dias=depende, oper=oper, memoria=mem)


r = rota(40, "leve")
confere("nível 1: leve de 40 min cabe hoje às 15:00", r["nivel"] == 1 and r["candidatos"][0]["inicio"] == 15 * 60, r)
r = rota(60, "pesado", date(2026, 10, 14))
confere("nível 1: pesado vai para a noite de hoje (nobre), não para a tarde", r["nivel"] == 1 and r["candidatos"][0]["inicio"] >= 18 * 60, r)
r = rota(60, "pesado", agora=19 * 60)
confere("depois das 19h não cabe hoje: sai do nível 1", r["nivel"] != 1)
r = rota(30, "pesado", date(2026, 10, 16), "Conteúdo", agora=19 * 60)
confere("nível 2: tira o leve do nobre de quinta para a tarde (preferência dela)", r["nivel"] == 2 and "tirando o leve" in r["candidatos"][0]["como"] and r["candidatos"][0]["dia"] == date(2026, 10, 15), r)
r = rota(90, "pesado", date(2026, 10, 16), "Agência", agora=19 * 60)
confere("sem nobre até a data segura: usa a tarde livre antes do prazo em vez de hora extra", r["nivel"] == 2 and "FORA DO NOBRE" in r["candidatos"][0]["como"]
        and r["candidatos"][0]["dia"] <= date(2026, 10, 16), r)
r = rota(300, "pesado", date(2026, 10, 16), "Agência", agora=19 * 60)
confere("tarefa que não cabe nem fora do nobre: nível 3 com horizonte", r["nivel"] == 3 and "HORIZONTE" in r.get("horizonte", ""), r)
r = rota(270, "pesado", date(2026, 10, 16), "Agência", agora=19 * 60, estender={date(2026, 10, 16): 23 * 60 + 30})
confere("extensão autorizada na sexta: cabe no dia do prazo, marcado SEM FOLGA", r["nivel"] == 2 and "SEM FOLGA" in r["candidatos"][0]["como"], r)
r = rota(90, "pesado")
confere("margem padrão 1,2 sem 3 registros: 90 vira 110", r["precisa"] == 110 and r["margem"] == 1.2)
r = rota(120, "pesado", date(2026, 11, 10), "Conteúdo", depende=3)
confere("prazo além da semana: nível 3, data segura de trás para frente (10/11 - 3 - 1 = 04/11)", r["nivel"] == 3 and r["data_segura"] == date(2026, 11, 4), r)
confere("dia de marco crítico (04/11) vai para o fim da fila", r["candidatos"] and r["candidatos"][0]["dia"] != date(2026, 11, 4) and all(not c["critico"] for c in r["candidatos"][:1]), r["candidatos"])
m = ra.marcos(oper, mem, hoje, date(2026, 11, 30))
nomes = [x[2] for x in m]
confere("marcos: só a seção 3, com colunas pelo cabeçalho", "Decidir o bônus" in nomes and "Abertura do carrinho" in nomes and "Página no ar" in nomes and "não é marco" not in nomes and "Algo decidido" not in nomes, m)
confere("marco: data do ClickUp quando o id está no resumo, do texto quando não", (date(2026, 10, 20), "Decidir o bônus") in [(x[0], x[2]) for x in m] and (date(2026, 10, 28), "Página no ar") in [(x[0], x[2]) for x in m], m)
confere("marco: mês certo pelo dia da semana (qua 28 = 28/10)", any(x[0] == date(2026, 10, 28) for x in m))
al = ra.alertas(ra.vs.planos_da_semana(oper, hoje), hoje, {}, mem, oper)
confere("alerta: quinta cheia é avisada", any("15/10" in a and ("ocupado" in a or "nobre" in a) for a in al), al)
confere("alerta: marco da Milena sem horário a 6 dias é avisado", any("Decidir o bônus" in a for a in al), al)
confere("alerta: marco do Paulo não vira alerta dela", not any("Live de vendas" in a for a in al), al)
confere("tipo: design vem antes de copy no título", ra.tipo_de("Design | Copy de segunda") == "design" and ra.tipo_de("Copy | X") == "pesado" and ra.tipo_de("Aprovações do Vitor") == "leve")
texto = ra.texto(rota(40, "leve"))
confere("texto diz o nível e o que ler", texto.startswith("ROTA") and "nível 1" in texto)
# janela é preferência (Milena, 2026-10-14): copy com prazo não atrasa por falta de nobre; leve só vai ao nobre sem outro espaço
r = rota(60, "pesado", date(2026, 10, 15), "Conteúdo", agora=19 * 60)
confere("copy de post com prazo amanhã e nobre lotado: vai para a tarde, não passa do prazo", r["candidatos"] and r["candidatos"][0]["dia"] <= date(2026, 10, 15)
        and "FORA DO NOBRE" in r["candidatos"][0]["como"], r)
r = rota(60, "pesado", date(2026, 10, 30), "Conteúdo", agora=19 * 60)
confere("copy sem pressa e semana com nobre livre mais à frente: espera o nobre, não vai para a tarde", r["candidatos"] and "FORA DO NOBRE" not in r["candidatos"][0]["como"], r)
r = rota(40, "leve")
confere("leve prefere a tarde mesmo com a noite nobre livre", r["candidatos"][0]["inicio"] == 15 * 60, r)
r = rota(70, "leve", agora=19 * 60)
confere("leve sem espaço fora do nobre na semana só entra no nobre marcado", all(("NO NOBRE" in c["como"]) == ra._no_nobre(c["inicio"]) for c in r["candidatos"]), r)
# não cabe: dizer e oferecer saídas com números (Milena, 2026-10-14)
r = rota(300, "pesado", date(2026, 10, 16), "Agência", agora=19 * 60)
t = ra.texto(r)
confere("não cabe: o texto manda dizer e oferece negociar prazo, eliminar, simplificar, delegar, tirar outra coisa",
        "NÃO CABE BEM" in t and "negociar novo prazo" in t and "eliminar" in t and "versão mais simples" in t and "delegar" in t, t)
confere("não cabe: a data para negociar é depois do prazo", r.get("cabe_em") and r["cabe_em"]["dia"] > date(2026, 10, 16), r.get("cabe_em"))
confere("cabe bem: sem a lista de saídas", "NÃO CABE BEM" not in ra.texto(rota(40, "leve")))
grava("planos/plano_2026-10-19.json", {"data": "2026-10-19", "blocos": [b("s1", "08:40", "13:00", "Manhã cheia"), b("s2", "14:00", "19:00", "Tarde cheia")], "fixos": [{"inicio": "13:00", "fim": "14:00", "titulo": "Almoço"}]})
al = ra.alertas(ra.vs.planos_da_semana(oper, hoje), hoje, {}, mem, oper)
confere("desequilíbrio: dia no limite com outro folgado vira alerta", any("Desequilíbrio" in a for a in al), al)
r = rota(400, "pesado", date(2026, 10, 23), "Conteúdo", agora=19 * 60)
partes = r["candidatos"]
confere("tarefa longa que não cabe num dia: dividida em partes de 1 h ou mais até a data segura, somando o tempo todo",
        r["nivel"] in (2, 3) and len(partes) >= 2 and all(c["fim"] - c["inicio"] >= 60 for c in partes) and sum(c["fim"] - c["inicio"] for c in partes) >= r["precisa"]
        and all(c["dia"] <= r["data_segura"] for c in partes) and "parte 1 de" in partes[0]["como"], r)
# correções de 14/10 à noite: zona morta, hoje a partir de agora, fim de semana
ra.vs.aplicar_rotina({"rotina": {"zona_morta": [["16:00", "18:00"]]}})
fora = ra.janelas("pesado", 19 * 60 + 20, fora=True)
confere("zona morta: pesado fora do nobre nunca cai entre 16h e 18h", all(b <= 16 * 60 or a >= 18 * 60 for a, b in fora), fora)
confere("zona morta: leve continua podendo", ra.janelas("leve", 19 * 60 + 20, fora=True) == [(ra.vs.CHEGADA, 19 * 60 + 20)])
ra.vs.aplicar_rotina({})
p_hoje = {"blocos": [], "fixos": []}
confere("ocupação de hoje conta só a partir de agora", ra.ocupacao(p_hoje, hoje, mem, 19 * 60)[1] == 20 and ra.ocupacao(p_hoje, hoje, mem)[1] > 600)
sys.exit(1 if falhas else 0)
