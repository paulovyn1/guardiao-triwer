"""Classes de tarefa (2026-10-15): fixa, prazo máximo, estabelecida pelo guardião e sugestão. Só sugestão é replanejada à vontade; fixa não muda; prazo máximo nunca vai
para depois; o que o guardião marcou fica; o config da pessoa troca listas e tags."""
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conferencia_plano as cp
import travas as tv

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


t = lambda **x: dict(dict(id="T", nome="Algo", prazo="2026-10-30", inicio=None, fim=None, lista="Conteúdos", tags=[]), **x)
confere("reunião (lista Reuniões Gerais, como o Hotseat) é fixa", tv.classe(t(lista="Reuniões Gerais")) == tv.FIXA)
confere("tag 'fixo' também", tv.classe(t(tags=["Fixo"])) == tv.FIXA)
confere("tag de prazo máximo ou de cliente é limite", tv.classe(t(tags=["prazo máximo"])) == tv.LIMITE and tv.classe(t(tags=["cliente"])) == tv.LIMITE)
confere("tarefa citada na tabela de marcos da campanha é limite", tv.classe(t(id="17tnabc1234x"), marcos={"17tnabc1234x"}) == tv.LIMITE)
confere("tarefa criada pelo guardião é estabelecida", tv.classe(t(criada_pelo_guardiao=True)) == tv.ESTABELECIDA)
mov = {"T": {"data": "2026-10-30", "inicio": "09:00", "fim": "10:00"}}
confere("tarefa que o guardião moveu ao aprovar é estabelecida enquanto a data bate; se mudaram a data, volta a ser sugestão",
        tv.classe(t(inicio="09:00", fim="10:00"), agendadas=mov) == tv.ESTABELECIDA and tv.classe(t(inicio="11:00", fim="12:00"), agendadas=mov) == tv.SUGESTAO)
confere("automação do ClickUp (copy/design sem marca) é sugestão", tv.classe(t(nome="[DESIGN] Post - Oct 14 2026 (America/Sao_Paulo)")) == tv.SUGESTAO)
confere("o config da pessoa troca as listas e tags", tv.classe(t(lista="Minhas calls"), {"rotina": {"travas": {"listas_fixas": ["Minhas calls"]}}}) == tv.FIXA
        and tv.classe(t(lista="Reuniões Gerais"), {"rotina": {"travas": {"listas_fixas": ["Minhas calls"]}}}) == tv.SUGESTAO)

oper = tempfile.mkdtemp()
tv.registrar_agendada(oper, "X1", "2026-10-16", "09:00", "09:30")
confere("o registro do que o guardião marcou persiste", tv.carregar_agendadas(oper)["X1"]["fim"] == "09:30")

# conferência: fixa não muda, prazo máximo nunca depois, antes pode
fixa = {"F": t(id="F", prazo="2026-10-19", inicio="09:00", fim="14:00", lista="Reuniões Gerais")}
mesmo = {"blocos": [{"id": "a", "inicio": "09:00", "fim": "14:00", "titulo": "Hotseat", "clickup_id": "F"}]}
movido = {"blocos": [{"id": "a", "inicio": "15:00", "fim": "20:00", "titulo": "Hotseat", "clickup_id": "F"}]}
confere("fixa no mesmo dia e horário passa; movida é barrada", cp.conferir_travas(mesmo, date(2026, 10, 19), fixa, {}, None) == []
        and len(cp.conferir_travas(movido, date(2026, 10, 19), fixa, {}, None)) == 1 and len(cp.conferir_travas(mesmo, date(2026, 10, 20), fixa, {}, None)) == 1)
lim = {"L": t(id="L", prazo="2026-10-30", tags=["prazo máximo"], nome="Página de vendas do Halloween")}
pl = lambda: {"blocos": [{"id": "a", "inicio": "09:00", "fim": "11:00", "titulo": "Página de vendas do Halloween", "clickup_id": "L"}]}
confere("prazo máximo: fazer antes (28) passa; no dia (30) passa; depois (31) é barrado",
        cp.conferir_travas(pl(), date(2026, 10, 28), lim, {}, None) == [] and cp.conferir_travas(pl(), date(2026, 10, 30), lim, {}, None) == []
        and len(cp.conferir_travas(pl(), date(2026, 10, 31), lim, {}, None)) == 1)
sys.exit(1 if falhas else 0)
