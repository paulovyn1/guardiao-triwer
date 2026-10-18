"""Revisor do plano (2026-10-15): só roda em dia muito apertado ou replanejamento; o prompt leva as regras, as campanhas e o horizonte e NÃO leva a conversa
de quem montou; resposta ilegível ou falha do Claude nunca bloqueia o plano; problemas viram frases com o item."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import revisor as rv

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


oper, mem = tempfile.mkdtemp(), tempfile.mkdtemp()
os.makedirs(os.path.join(mem, "campanhas"))
with open(os.path.join(mem, "aprendizados.md"), "w", encoding="utf-8") as f:
    f.write("- Relatório de post só 24h depois da postagem | o relatório está depois de 24h?\n")
with open(os.path.join(mem, "perfil.md"), "w", encoding="utf-8") as f:
    f.write("# Perfil\nO que é importante: caixa com data.\n")
with open(os.path.join(mem, "campanhas", "venda-x.md"), "w", encoding="utf-8") as f:
    f.write("---\nnome: Venda X\nslug: venda-x\ntipo: venda-publica\nstatus: em-execucao\nimportancia: alta\ndata_inicio: 2026-10-01\ndata_fim: 2026-10-31\n---\n"
            "## 1. Ficha\n- O que é e objetivo: vender o produto X no sábado 31 a quem vem do Instagram.\n")
cfg = {"pessoa": {"nome": "Ana"}, "pastas": {"memoria": mem}, "rotina": {"chegada": "08:40", "fim": "19:30"}}
dia = date(2026, 10, 29)

folgado = {"data": "2026-10-29", "blocos": [{"id": "b1", "inicio": "09:00", "fim": "10:00", "titulo": "Copy do post"}], "fixos": []}
cheio = {"data": "2026-10-29", "blocos": [{"id": "b1", "inicio": "08:40", "fim": "19:00", "titulo": "Tudo"}], "fixos": []}
confere("dia folgado e sem replanejamento: não roda", rv.deve_revisar(folgado, dia, oper, cfg) is None)
confere("dia muito apertado: roda", "apertado" in (rv.deve_revisar(cheio, dia, oper, cfg) or ""))
confere("replanejamento: roda", rv.deve_revisar(folgado, dia, oper, cfg, replanejar=True) == "replanejamento")
confere("pedido direto: roda", rv.deve_revisar(folgado, dia, oper, cfg, forcar=True) == "pedido direto")
confere("dossiê com tarefa atrasada conta como replanejamento", "replanejamento" in (rv.deve_revisar(folgado, dia, oper, cfg, dossie="1 tarefa(s) atrasada(s) precisam de lugar") or ""))

prompt = rv.montar_prompt(folgado, dia, "teste", oper, cfg)
confere("o prompt leva aprendizados, perfil, campanha com objetivo e o plano", all(x in prompt for x in ("24h depois da postagem", "caixa com data", "Venda X", "vender o produto X", "Copy do post")))
confere("o prompt diz que o revisor não montou o plano e leva os 12 itens", "NÃO montou" in prompt and "12. O horizonte" in prompt)

saida = 'texto\n```json\n{"itens": [{"n": 1, "ok": true}, {"n": 8, "ok": false, "motivo": "Relatório às 16h40 no dia do post"}, {"n": 3, "ok": false}]}\n```'
p = rv.interpretar(saida)
confere("reprovação com motivo vira problema; reprovação sem motivo é ignorada", len(p) == 1 and "Item 8" in p[0] and "16h40" in p[0], p)
confere("resposta ilegível não bloqueia", rv.interpretar("não sei") == [] and rv.interpretar('{"itens": ') == [] and rv.interpretar(None) == [])
confere("revisar devolve os problemas do executor", len(rv.revisar(folgado, dia, "t", oper, cfg, executar=lambda pr, o: saida)) == 1)


def quebra(pr, o):
    raise RuntimeError("sem Claude")


confere("falha ao chamar o Claude: lista vazia, o plano segue", rv.revisar(folgado, dia, "t", oper, cfg, executar=quebra) == [])
confere("o texto de correção cita o arquivo e os problemas", "plano_x.json" in rv.texto_da_correcao(["a"], "plano_x.json") and "- a" in rv.texto_da_correcao(["a"], "plano_x.json"))
sys.exit(1 if falhas else 0)
