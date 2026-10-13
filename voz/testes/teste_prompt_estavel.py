"""Prompt estável (cache do Claude): o prompt de sistema não muda de um turno para o outro e tudo que muda vai junto da pergunta. Sem Claude e sem navegador."""
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
import guardiao_voz as g  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {str(detalhe)[:300]}" if detalhe and not ok else ""))


tmp = tempfile.mkdtemp(prefix="gv_oper_estavel_")
h.OPER = g.OPER = tmp
os.makedirs(os.path.join(tmp, "memoria"))
os.makedirs(os.path.join(tmp, "planos"))
os.makedirs(os.path.join(tmp, "registros"))
os.makedirs(os.path.join(tmp, "logs"))
with open(os.path.join(tmp, "memoria", "perfil.md"), "w", encoding="utf-8") as f:
    f.write("# Perfil de teste\n- almoço às 12:00\n")
hoje = date.today().isoformat()
amanha = date.fromordinal(date.today().toordinal() + 1).isoformat()
with open(os.path.join(tmp, "planos", f"plano_{amanha}.json"), "w", encoding="utf-8") as f:
    json.dump({"blocos": [{"id": "b1", "inicio": "09:00", "fim": "09:30", "titulo": "Bloco de amanhã"}]}, f, ensure_ascii=False)


def gravar_plano(status):
    blocos = [{"id": f"b{i}", "inicio": f"{7 + i:02d}:00", "fim": f"{7 + i:02d}:30", "titulo": f"Tarefa {i}", "dono": "Rafa", "frente": "Teste", "descricao": "d", "primeiro_passo": "p",
               "por_que_agora": "q", "clickup_id": f"cid{i}"} for i in range(1, 5)]
    with open(os.path.join(tmp, "plano_do_dia.json"), "w", encoding="utf-8") as f:
        json.dump({"data": hoje, "status": status, "fixos": [], "blocos": blocos}, f, ensure_ascii=False)


class Relogio:
    def __init__(self, hora):
        self.hora = hora

    def strftime(self, fmt, t=None):
        if t is None and fmt == "%d/%m/%Y %H:%M":
            return f"14/10/2026 {self.hora}"
        return time.strftime(fmt, t) if t is not None else time.strftime(fmt)

    def __getattr__(self, n):
        return getattr(time, n)


def zerar():
    g.CONVERSA.clear()
    g.AVISOS_AO_MODELO.clear()
    g.PROPOSTA = None
    g.REVISAO = None


DINAMICOS = ["Agora sao", "STATUS DO PLANO DE HOJE:", "TAREFAS CONHECIDAS (id", "CONVERSA RECENTE", "PROPOSTA PENDENTE", "RESULTADO DOS SEUS"]

# ---------------- modo antigo: nada muda
g.PROMPT_ESTAVEL = False
gravar_plano("aprovado")
zerar()
antigo = g.prompt_sistema()
confere("modo antigo: o prompt de sistema continua com o relógio, o status, os ids e o plano", all(x in antigo for x in ["Agora sao", "STATUS DO PLANO DE HOJE:", "TAREFAS CONHECIDAS (id", "PLANO DE HOJE:"]))
confere("modo antigo: a mensagem é só a pergunta", g.mensagem_do_turno("oi") == "oi" and g.contexto_do_turno() == "")
confere("modo antigo: o texto das ações continua dizendo 'abaixo'", "TAREFAS CONHECIDAS abaixo" in antigo)

# ---------------- modo estável com o plano aprovado
g.PROMPT_ESTAVEL = True
g.PLANO_NO_CONTEXTO = "sugerido"
gravar_plano("aprovado")
zerar()
g.time = Relogio("10:20")
s1 = g.prompt_sistema()
m1 = g.mensagem_do_turno("o que é a tarefa 2?")
confere("estável: o prompt de sistema não tem nada que muda a cada turno", not any(x in s1 for x in DINAMICOS), [x for x in DINAMICOS if x in s1])
PRECISA = ["DESTAQUES E AÇÕES NA TELA", "PERFIL:", "PLANO DE HOJE:", "Bloco de amanhã", "CONTEXTO DESTE MOMENTO"]
confere("estável: tem as regras, o perfil, o plano aprovado e os planos dos próximos dias", all(x in s1 for x in PRECISA), [x for x in PRECISA if x not in s1])
confere("estável: o texto das ações não diz mais 'abaixo'", "TAREFAS CONHECIDAS abaixo" not in s1 and "TAREFAS CONHECIDAS;" in s1)
confere("estável: a mensagem traz relógio, status e ids antes do pedido, e o pedido vai por último",
        m1.startswith("[CONTEXTO DESTE MOMENTO") and "Agora sao 14/10/2026 10:20." in m1 and "STATUS DO PLANO DE HOJE:" in m1 and "TAREFAS CONHECIDAS (id" in m1 and m1.endswith("[PEDIDO DESTE TURNO]\no que é a tarefa 2?"), m1[:200])
confere("estável: com o plano aprovado, o plano de hoje fica fora da mensagem", "PLANO DE HOJE:\n{" not in m1)

# o prompt de sistema não muda com o relógio, a conversa, a proposta, o aviso nem o registro
g.time = Relogio("10:21")
g.lembrar("conclui a tarefa 1", "O que foi feito?")
g.PROPOSTA = {"tipo": "criar", "dados": {"titulo": "x"}, "quando": time.time()}
g.avisar_modelo("Ajuste aplicado")
with open(os.path.join(tmp, "registros", f"registro_{hoje}.json"), "w", encoding="utf-8") as f:
    json.dump({"data": hoje, "blocos": [{"id": "b1", "estado": "feito"}]}, f)
s2 = g.prompt_sistema()
m2 = g.mensagem_do_turno("e agora?")
confere("estável: o prompt de sistema é idêntico no minuto seguinte, com conversa, proposta, aviso e tarefa concluída", s1 == s2, f"{len(s1)} x {len(s2)}")
confere("estável: tudo isso foi parar na mensagem do turno", all(x in m2 for x in ["10:21", "CONVERSA RECENTE", "PROPOSTA PENDENTE", "RESULTADO DOS SEUS", "Ajuste aplicado", "b1 | hoje 08:00-08:30 | Tarefa 1 | feito"]), m2[:400])
confere("estável: o aviso dos ajustes é lido uma vez só (a mensagem consumiu)", not g.AVISOS_AO_MODELO)

# ---------------- o comando do Claude
zerar()
g.avisar_modelo("Aviso único")
cmd, _ = g.comando_claude("qual o prazo?", streaming=False)
mensagem_cmd = cmd[cmd.index("-p") + 1]
arq = cmd[cmd.index("--system-prompt-file") + 1]
sistema_cmd = open(arq, encoding="utf-8").read()
confere("comando: o -p leva o contexto e o pedido; o arquivo de sistema leva o prompt fixo", mensagem_cmd.endswith("[PEDIDO DESTE TURNO]\nqual o prazo?") and "Aviso único" in mensagem_cmd and "Aviso único" not in sistema_cmd and "Agora sao" not in sistema_cmd)
cmd2, _ = g.comando_claude("e depois?", streaming=False)
confere("comando: o aviso aparece só no primeiro turno", "Aviso único" not in cmd2[cmd2.index("-p") + 1])

# ---------------- plano em revisão: o plano vai na mensagem, o prompt de sistema segue igual quando ele muda
gravar_plano("sugerido")
zerar()
g.time = Relogio("08:10")
s_a = g.prompt_sistema()
m_a = g.mensagem_do_turno("vamos revisar")
confere("revisão (plano sugerido): o plano de hoje vai na mensagem e não no prompt de sistema", "PLANO DE HOJE:\n{" in m_a and "PLANO DE HOJE:\n{" not in s_a and "Tarefa 3" in m_a and "Tarefa 3" not in s_a)
r = h.editar_plano("mover", "b3", {"horario": "15:00-15:30"})
s_b = g.prompt_sistema()
m_b = g.mensagem_do_turno("e agora?")
confere("revisão: depois de mover um bloco o prompt de sistema continua idêntico (o cache não se perde) e a mensagem mostra o novo horário", r.get("ok") and s_a == s_b and "15:00" in m_b and "15:00" not in s_b, r)
g.PLANO_NO_CONTEXTO = "nunca"
confere("PLANO_NO_CONTEXTO=nunca: o plano fica sempre no prompt de sistema", "PLANO DE HOJE:\n{" in g.prompt_sistema() and "PLANO DE HOJE:\n{" not in g.mensagem_do_turno("x"))
g.PLANO_NO_CONTEXTO = "sempre"
gravar_plano("aprovado")
confere("PLANO_NO_CONTEXTO=sempre: o plano vai sempre na mensagem, mesmo aprovado", "PLANO DE HOJE:\n{" not in g.prompt_sistema() and "PLANO DE HOJE:\n{" in g.mensagem_do_turno("x"))
g.PLANO_NO_CONTEXTO = "sugerido"

# ---------------- sem plano e saudação
os.remove(os.path.join(tmp, "plano_do_dia.json"))
zerar()
s_sem = g.prompt_sistema()
m_sem = g.mensagem_do_turno("[ABERTURA DO APP.] cumprimente")
confere("sem plano hoje: nada quebra e a mensagem avisa", "(sem plano hoje)" in m_sem or "STATUS DO PLANO DE HOJE: ainda não existe plano" in m_sem, m_sem[:300])
confere("a saudação vai como pedido do turno, depois do contexto", m_sem.endswith("[PEDIDO DESTE TURNO]\n[ABERTURA DO APP.] cumprimente"))

# ---------------- registro de custo com cache
g.registrar_chamada("claude-sonnet-5-5", "teste", {"total_cost_usd": 0.01, "usage": {"input_tokens": 2, "cache_creation_input_tokens": 1300, "cache_read_input_tokens": 6800, "output_tokens": 50}, "duration_ms": 1000})
linha = json.loads(open(os.path.join(tmp, "logs", "modelos.jsonl"), encoding="utf-8").read().splitlines()[-1])
confere("o registro guarda o cache lido e o escrito e o modo do prompt", linha["cache_lido"] == 6800 and linha["cache_escrito"] == 1300 and linha["prompt_estavel"] is True, linha)

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
