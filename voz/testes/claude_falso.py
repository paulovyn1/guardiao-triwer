"""Um Claude Code de mentira para os testes do modo sessão: fala o mesmo protocolo (stream-json nos dois sentidos, pedido de permissão pelo canal de controle),
sem internet e sem gastar nada. O que ele recebe fica anotado no arquivo da variável GUARDIAO_FALSO_LOG, para o teste conferir.
Comportamento pelo texto do pedido: "use o clickup" consulta um conector; "crie a tarefa" pede permissão para criar; "chame o agente" e "use a skill"
mostram essas ferramentas; "mande o whatsapp" pede permissão para algo sensível; "responda devagar" escreve uma frase a cada meio segundo e aceita o pedido
"interrupt" (control_request) no meio, como o Claude Code de verdade. Com GUARDIAO_FALSO_SEM_RETOMADA=1, retomar uma sessão falha."""
import json
import os
import queue
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stdin.reconfigure(encoding="utf-8")
ENTRADA = queue.Queue()  # o que chega pelo stdin: lido por uma thread, para o turno poder escrever e ouvir ao mesmo tempo
threading.Thread(target=lambda: ([ENTRADA.put(l) for l in sys.stdin], ENTRADA.put(None)), daemon=True).start()


def linhas():
    while True:
        l = ENTRADA.get()
        if l is None:
            return
        yield l
ARQ = os.environ.get("GUARDIAO_FALSO_LOG")
ARGS = sys.argv[1:]
SESSAO = next((ARGS[i + 1] for i, a in enumerate(ARGS) if a in ("--session-id", "--resume") and i + 1 < len(ARGS)), "sem-sessao")
custo, turnos, n_id = 0.0, 0, 0


def anota(**dados):
    if ARQ:
        with open(ARQ, "a", encoding="utf-8") as f:
            f.write(json.dumps(dados, ensure_ascii=False) + "\n")


def sai(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def texto(t, pai=None):
    for i in range(0, len(t), 12):
        sai({"type": "stream_event", "parent_tool_use_id": pai, "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": t[i:i + 12]}}})


def ferramenta(nome, entrada):
    global n_id
    n_id += 1
    tid = f"toolu_{n_id}"
    sai({"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "message_delta", "delta": {"stop_reason": "tool_use"}}})
    sai({"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": nome, "input": entrada}]}})
    return tid


def resultado_da_ferramenta(tid, erro=False):
    sai({"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "is_error": erro, "content": "ok"}]}})


def pede_permissao(nome, entrada):
    """Devolve True se a pessoa permitiu. Enquanto espera, não lê outra coisa: é o que o Claude Code de verdade faz."""
    tid = ferramenta(nome, entrada)
    rid = f"perm_{tid}"
    sai({"type": "control_request", "request_id": rid, "request": {"subtype": "can_use_tool", "tool_name": nome, "input": entrada, "tool_use_id": tid}})
    for linha in linhas():
        ev = json.loads(linha)
        if ev.get("type") == "control_response" and (ev.get("response") or {}).get("request_id") == rid:
            r = (ev["response"].get("response") or {})
            anota(tipo="permissao", ferramenta=nome, resposta=r)
            resultado_da_ferramenta(tid, erro=r.get("behavior") != "allow")
            return r.get("behavior") == "allow"
    return False


anota(tipo="inicio", args=ARGS, pasta=os.getcwd())
if "--resume" in ARGS and os.environ.get("GUARDIAO_FALSO_SEM_RETOMADA") == "1":
    sys.exit(1)
for linha in linhas():
    try:
        ev = json.loads(linha)
    except ValueError:
        continue
    if ev.get("type") == "control_request":
        sai({"type": "control_response", "response": {"subtype": "success", "request_id": ev.get("request_id"), "response": {}}})
        continue
    if ev.get("type") != "user":
        continue
    turnos += 1
    pedido_inteiro = str((ev.get("message") or {}).get("content") or "")
    pedido = pedido_inteiro.split("[PEDIDO DESTE TURNO]")[-1].strip()
    anota(tipo="pedido", texto=pedido_inteiro, turno=turnos)
    sai({"type": "system", "subtype": "init", "session_id": SESSAO, "tools": ["Read"], "mcp_servers": []})
    p = pedido.lower()
    if "use o clickup" in p:
        texto("Vou olhar no ClickUp. ")
        resultado_da_ferramenta(ferramenta("mcp__claude_ai_ClickUp__clickup_search", {"query": "relatório"}))
        texto("Achei duas tarefas abertas.")
    elif "crie a tarefa" in p:
        texto("Vou criar a tarefa Ligar para o contador. ")
        ok = pede_permissao("mcp__claude_ai_ClickUp__clickup_create_task", {"name": "Ligar para o contador", "list_id": "L1", "due_date": "2026-10-13"})
        texto("Pronto, criei a tarefa." if ok else "Tudo bem, não criei. O que você quer ajustar?")
    elif "mande o whatsapp" in p:
        ok = pede_permissao("mcp__claude_ai_Evolution_WhatsApp__send_message", {"number": "5511999990000", "text": "Oi, tudo certo para amanhã?"})
        texto("Mensagem enviada." if ok else "Não enviei.")
    elif "chame o agente" in p:
        tid = ferramenta("Agent", {"subagent_type": "Máximo", "description": "Relatório de campanhas", "prompt": "..."})
        texto("texto de dentro do agente, que não é para ser falado", pai=tid)
        sai({"type": "assistant", "parent_tool_use_id": tid, "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_dentro", "name": "mcp__claude_ai_Meta__ads_get_ad_entities", "input": {}}]}})
        resultado_da_ferramenta(tid)
        texto("O Máximo trouxe o relatório.")
    elif "use a skill" in p:
        resultado_da_ferramenta(ferramenta("Skill", {"skill": "guardiao-triwer"}))
        texto("Segui a skill do guardião.")
    elif "responda devagar" in p:
        parou, interrompido = threading.Event(), [None]

        def emite():
            for i in range(14):
                if parou.is_set():
                    return
                texto(f"Frase número {i + 1} da resposta devagar. ")
                time.sleep(0.5)

        t = threading.Thread(target=emite, daemon=True)
        t.start()
        while t.is_alive():
            try:
                outra = ENTRADA.get(timeout=0.1)
            except queue.Empty:
                continue
            if outra is None:
                break
            ev2 = json.loads(outra)
            if ev2.get("type") == "control_request" and (ev2.get("request") or {}).get("subtype") == "interrupt":
                parou.set()
                interrompido[0] = ev2.get("request_id")
                break
        t.join()
        if interrompido[0]:
            anota(tipo="interrupt", turno=turnos)
            sai({"type": "control_response", "response": {"subtype": "success", "request_id": interrompido[0], "response": {}}})
            custo += 0.01
            sai({"type": "result", "subtype": "error_during_execution", "is_error": True, "session_id": SESSAO, "total_cost_usd": round(custo, 4), "duration_ms": 500,
                 "usage": {"input_tokens": 30, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0, "output_tokens": 10}})
            continue
    elif "estoure o limite" in p:
        sai({"type": "result", "subtype": "success", "is_error": True, "session_id": SESSAO, "total_cost_usd": round(custo, 4), "duration_ms": 300,
             "result": "You've hit your weekly limit \u00b7 resets Oct 17, 7pm (America/Fortaleza)", "usage": {"input_tokens": 0, "output_tokens": 0}})
        continue
    elif "quantas vezes" in p:
        texto(f"Você já falou {turnos} vezes nesta conversa.")
    else:
        texto(f"Entendi: {pedido[:60]}. Segunda frase da resposta.")
    sai({"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [{"type": "text", "text": "..."}],
                                                               "usage": {"input_tokens": 10, "cache_read_input_tokens": 60000 + 500 * turnos, "cache_creation_input_tokens": 300}}})
    sai({"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}})
    time.sleep(0.15)
    custo += 0.02
    sai({"type": "result", "subtype": "success", "is_error": False, "session_id": SESSAO, "total_cost_usd": round(custo, 4), "duration_ms": 900,
         "usage": {"input_tokens": 30, "cache_read_input_tokens": 3 * (60000 + 500 * turnos), "cache_creation_input_tokens": 900, "output_tokens": 40}})
