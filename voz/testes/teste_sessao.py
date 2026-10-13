"""Modo sessão (0.5.0), sem navegador e sem o Claude de verdade: a conversa como uma sessão do Claude Code num processo que fica aberto,
a lista de conversas (nova, voltar a uma anterior), o pedido de permissão (falado, digitado ou clicado), os avisos de uso de conector,
skill e agente, e a palavra de ativação que só aceita "ei guardião". O Claude Code é o claude_falso.py desta pasta."""
import json
import os
import queue
import sys
import time

from v2_base import confere, h, placar, preparar
import requests

import guardiao_sessao as gs
import guardiao_voz as g

PORTA = 8789
tmp, relogio = preparar(PORTA, hora="09:50")
g.OPER = tmp
AQUI = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(tmp, "claude_falso.log")
os.environ["GUARDIAO_FALSO_LOG"] = LOG
gs.COMANDO = [sys.executable, os.path.join(AQUI, "claude_falso.py")]
URL = f"http://localhost:{PORTA}"
eventos = []
emitir_original = h.bus.emitir


def emitir(tipo, /, **dados):
    eventos.append((tipo, dados))
    emitir_original(tipo, **dados)


h.bus.emitir = emitir


def do_falso(tipo):
    try:
        with open(LOG, encoding="utf-8") as f:
            return [x for x in map(json.loads, f) if x.get("tipo") == tipo]
    except OSError:
        return []


def rodar(pedido, decisao=None):
    """Um turno inteiro pela sessão. Devolve (texto falado, lista de ferramentas, lista de pedidos de permissão)."""
    falas, ferramentas, pedidos = [], [], []
    for tipo, dado in gs.turno(pedido, g.arquivo_prompt_sessao()):
        if tipo == "texto":
            falas.append(dado)
        elif tipo == "ferramenta":
            ferramentas.append(dado)
        elif tipo == "permissao":
            pedidos.append(dado)
            gs.decidir(dado, *(decisao or ("nao", "")))
    return "".join(falas), ferramentas, pedidos


try:
    # ---------------- palavra de ativação: só "ei guardião", no começo da fala ----------------
    def ouvido(*palavras):
        t, saida = 0.5, []
        for p in palavras:
            nome, conf = p if isinstance(p, tuple) else (p, 0.95)
            saida.append({"word": nome, "conf": conf, "start": t, "end": t + 0.3})
            t += 0.35
        return {"text": " ".join(w["word"] for w in saida), "result": saida}

    confere('"ei guardião" aciona', g.chamou(ouvido("ei", "guardião")))
    confere("com um ruído curto antes também", g.chamou(ouvido("[unk]", "ei", "guardião")))
    confere('"ei" dito baixo (certeza 0,45) ainda vale', g.chamou(ouvido(("ei", 0.45), "guardião")))
    confere('a palavra "guardião" sozinha NÃO aciona (era o defeito)', not g.chamou(ouvido("guardião")))
    for frase in (["o", "guardião"], ["do", "guardião"], ["meu", "guardião"], ["eu", "guardião"], ["[unk]", "guardião", "[unk]"], ["ei", "com", "guardião", "[unk]"],
                  ["que", "do", "ei", "guardião"], ["guardiã", "ei", "[unk]"]):
        confere(f"NÃO aciona: {' '.join(frase)}", not g.chamou(ouvido(*frase)))
    lento = ouvido("ei", "guardião")
    lento["result"][1]["start"] += 1.2
    confere('"ei", uma pausa longa e depois "guardião" não aciona', not g.chamou(lento))
    confere("a gramática tem as palavras curtas que tiram o falso acionamento", all(p in json.loads(g.GRAMATICA) for p in ("o", "do", "meu", "eu", "ei guardião", "[unk]")))

    # ---------------- regras de permissão ----------------
    c = gs.classificar
    confere("ler num conector é livre", c("mcp__claude_ai_ClickUp__clickup_get_task", {})[0] == "permitir" and c("mcp__claude_ai_Notion__notion-search", {})[0] == "permitir"
            and c("mcp__claude_ai_Google_Calendar__list_events", {})[0] == "permitir")
    confere("criar ou alterar num conector pergunta, e pode virar 'sempre'", c("mcp__claude_ai_ClickUp__clickup_create_task", {})[:2] == ("perguntar", False)
            and c("mcp__claude_ai_ClickUp__clickup_update_task", {})[:2] == ("perguntar", False))
    antes = gs.h.lista_conteudos_id
    gs.h.lista_conteudos_id = lambda: "L9"
    confere("tarefa na lista de conteúdo sem parent é negada, com a orientação de achar a mãe",
            c("mcp__claude_ai_ClickUp__clickup_create_task", {"list_id": "L9", "name": "Design do post X"})[0] == "negar"
            and "parent" in c("mcp__claude_ai_ClickUp__clickup_create_task", {"list_id": "L9", "name": "Copy | Post X"})[2])
    confere("stories, caixinha e material de aula ficam soltos na lista de conteúdo sem trava",
            all(c("mcp__claude_ai_ClickUp__clickup_create_task", {"list_id": "L9", "name": n})[0] == "perguntar"
                for n in ("Stories da sala secreta: 3 telas", "Caixinha de perguntas", "Material de aula da sala secreta")))
    confere("com parent, ou em outra lista, segue a regra normal (pergunta)",
            c("mcp__claude_ai_ClickUp__clickup_create_task", {"list_id": "L9", "parent": "M1"})[0] == "perguntar"
            and c("mcp__claude_ai_ClickUp__clickup_create_task", {"list_id": "OUTRA"})[0] == "perguntar")
    gs.h.lista_conteudos_id = lambda: ""
    confere("sem lista de conteúdo configurada, a trava não bloqueia nada", c("mcp__claude_ai_ClickUp__clickup_create_task", {})[0] == "perguntar")
    gs.h.lista_conteudos_id = antes
    confere("enviar, apagar, publicar e executar perguntam sempre (sem 'sempre')", all(c(n, {})[:2] == ("perguntar", True) for n in (
        "mcp__claude_ai_Evolution_WhatsApp__send_message", "mcp__claude_ai_Gmail__send_message", "mcp__claude_ai_ClickUp__clickup_delete_task",
        "mcp__claude_ai_Meta__ads_activate_entity", "mcp__claude_ai_Supabase__execute_sql", "mcp__claude_ai_n8n__execute_workflow")))
    confere("ler arquivo, usar skill e chamar agente são livres", all(c(n, {})[0] == "permitir" for n in ("Read", "Glob", "Grep", "Skill", "Agent", "Task", "WebSearch")))
    confere("gravar na memória e na pasta operacional do guardião é livre", c("Write", {"file_path": os.path.join(tmp, "memoria", "estado.md")})[0] == "permitir"
            and c("Edit", {"file_path": os.path.join(tmp, "plano_do_dia.json")})[0] == "permitir")
    confere("gravar em qualquer outro lugar pergunta", c("Write", {"file_path": r"C:\Users\alguem\Documents\nota.txt"})[0] == "perguntar")
    script = os.path.join(tmp, "ler_campanha.ps1")
    confere("rodar um script do próprio guardião é livre", c("PowerShell", {"command": f'powershell -File "{script}" -Slug cpl'})[0] == "permitir")
    confere("comando emendado ou de fora pergunta", c("PowerShell", {"command": f'powershell -File "{script}" -Slug cpl; Remove-Item x'})[0] == "perguntar"
            and c("Bash", {"command": "rm -rf /"})[:2] == ("perguntar", True))
    confere("AskUserQuestion é negada com a orientação de perguntar em voz alta", c("AskUserQuestion", {})[0] == "negar" and "voz alta" in c("AskUserQuestion", {})[2])

    d = gs.descrever("mcp__claude_ai_ClickUp__clickup_create_task", {"name": "Ligar para o contador", "list_id": "L1", "due_date": "2026-10-13"})
    confere("o pedido é descrito em português, com os dados", d["pergunta"] == "Posso criar uma tarefa no ClickUp?" and d["titulo"] == "Criar uma tarefa no ClickUp"
            and ["Nome", "Ligar para o contador"] in d["linhas"] and ["Prazo", "2026-10-13"] in d["linhas"], d)
    confere("outros pedidos também viram frase", gs.descrever("mcp__claude_ai_Evolution_WhatsApp__send_message", {"number": "55", "text": "oi"})["pergunta"] == "Posso enviar uma mensagem no Evolution WhatsApp?"
            and gs.descrever("mcp__claude_ai_ClickUp__clickup_add_tag_to_task", {})["pergunta"] == "Posso adicionar uma etiqueta no ClickUp?"
            and gs.descrever("mcp__claude_ai_ClickUp__clickup_create_task_comment", {})["pergunta"] == "Posso criar um comentário no ClickUp?"
            and gs.descrever("mcp__claude_ai_Meta__ads_create_campaign", {})["pergunta"] == "Posso criar uma campanha na Meta?"
            and gs.descrever("Write", {"file_path": r"C:\x\nota.txt", "content": "oi"})["pergunta"] == "Posso gravar o arquivo nota.txt?",
            gs.descrever("mcp__claude_ai_ClickUp__clickup_add_tag_to_task", {}))
    a = gs.atividade
    confere("a tela recebe o nome do que está sendo usado", a("mcp__claude_ai_ClickUp__clickup_search", {}) == ("conector", "Consultando o ClickUp")
            and a("mcp__claude_ai_ClickUp__clickup_create_task", {}) == ("conector", "Usando o ClickUp") and a("Skill", {"skill": "guardiao-triwer"}) == ("skill", "Usando a skill guardiao-triwer")
            and a("Agent", {"subagent_type": "Máximo"}) == ("agente", "Chamando o agente Máximo") and a("WebSearch", {}) == ("web", "Pesquisando na web")
            and a("Read", {}) == ("arquivo", "Lendo arquivos") and a("TodoWrite", {}) is None, a("mcp__claude_ai_ClickUp__clickup_search", {}))

    # ---------------- a conversa como sessão ----------------
    usos = []
    gs.AO_FECHAR_TURNO.append(lambda p, ev: usos.append(ev.get("_custo_do_turno")))
    c1 = gs.atual()
    fala, ferr, ped = rodar("bom dia")
    inicio = do_falso("inicio")[-1]
    confere("a primeira fala abre o Claude Code com a sessão nova, na pasta certa e com o protocolo de permissão",
            "--session-id" in inicio["args"] and c1["id"] in inicio["args"] and "--resume" not in inicio["args"] and "stdio" in inicio["args"]
            and "--append-system-prompt-file" in inicio["args"] and os.path.normcase(inicio["pasta"]) == os.path.normcase(tmp), inicio)
    confere("a resposta chega como texto", "Entendi: bom dia" in fala and not ferr and not ped, fala)
    prompt = open(g.arquivo_prompt_sessao(), encoding="utf-8").read()
    confere("o prompt da sessão tem as regras do painel de voz, o nome da pessoa e as marcas da tela, sem a marca completo",
            "PASTAS DO GUARDIÃO" in prompt and tmp in prompt and "MODO PAINEL DE VOZ" in prompt and "Guardião do Rafa" in prompt and "{{foco:ID}}" in prompt and "{{completo:" not in prompt and "PERFIL:" in prompt and "<o Fulano>" not in prompt)
    fala2, _, _ = rodar("quantas vezes eu já falei?")
    confere("a segunda fala cai no MESMO processo, que lembra da primeira", "2 vezes" in fala2 and len(do_falso("inicio")) == 1, (fala2, len(do_falso("inicio"))))
    time.sleep(0.6)
    confere("o uso de cada turno é registrado com o custo só daquele turno", len(usos) == 2 and all(abs(u - 0.02) < 1e-6 for u in usos), usos)
    confere("a conversa guarda o tamanho do contexto (o da última chamada, não a soma do turno) e fica marcada como iniciada", 60000 < gs.atual()["contexto"] < 70000 and gs.atual()["iniciada"] is True, gs.atual())

    fala, ferr, _ = rodar("use o clickup para achar o relatório")
    confere("usar um conector avisa a tela no começo e no fim", [f["fase"] for f in ferr] == ["inicio", "fim"] and ferr[0]["rotulo"] == "Consultando o ClickUp" and ferr[0]["tipo"] == "conector"
            and "Vou olhar no ClickUp" in fala and "Achei duas" in fala, ferr)
    fala, ferr, _ = rodar("chame o agente de tráfego")
    confere("chamar um agente avisa a tela, e o que o agente escreve por dentro não é falado", ferr[0]["rotulo"] == "Chamando o agente Máximo" and "de dentro do agente" not in fala
            and "trouxe o relatório" in fala and any(f.get("dentro") and f["rotulo"] == "Consultando a Meta" for f in ferr), (fala, ferr))
    _, ferr, _ = rodar("use a skill do guardião")
    confere("usar uma skill avisa a tela", ferr[0] == dict(ferr[0], tipo="skill", rotulo="Usando a skill guardiao-triwer"), ferr)

    # ---------------- permissão ----------------
    fala, _, ped = rodar("crie a tarefa do contador", ("nao", ""))
    confere("criar tarefa pede permissão e, com o não, nada é feito", len(ped) == 1 and ped[0]["titulo"] == "Criar uma tarefa no ClickUp" and ped[0]["sempre"] is True
            and do_falso("permissao")[-1]["resposta"]["behavior"] == "deny" and "não criei" in fala, (fala, ped and ped[0]["titulo"]))
    fala, _, ped = rodar("crie a tarefa do contador", ("sim", ""))
    r = do_falso("permissao")[-1]["resposta"]
    confere("com o sim, a ferramenta roda com os mesmos dados", r["behavior"] == "allow" and r["updatedInput"]["name"] == "Ligar para o contador" and "criei a tarefa" in fala, r)
    fala, _, ped = rodar("crie a tarefa do contador", ("sempre", ""))
    confere("'permitir sempre' fica guardado", "mcp__claude_ai_ClickUp__clickup_create_task" in gs._sempre() and "criei" in fala)
    fala, _, ped = rodar("crie a tarefa do contador")
    confere("e da próxima vez nem pergunta", not ped and "criei a tarefa" in fala and do_falso("permissao")[-1]["resposta"]["behavior"] == "allow", (ped, fala))
    fala, _, ped = rodar("mande o whatsapp para a Marina", ("sempre", ""))
    confere("mensagem para fora pergunta sempre e não aceita 'sempre'", len(ped) == 1 and ped[0]["sempre"] is False and "send_message" not in " ".join(gs._sempre()), (ped, gs._sempre()))
    fala, _, ped = rodar("mande o whatsapp para a Marina", ("nao", "A pessoa respondeu: muda o texto antes."))
    confere("o recado da pessoa chega ao guardião junto com o não", do_falso("permissao")[-1]["resposta"] == {"behavior": "deny", "message": "A pessoa respondeu: muda o texto antes."}, do_falso("permissao")[-1])

    # ---------------- conversas: nova, lista, voltar ----------------
    gs.anotar(c1["id"], "u", "bom dia, quero ver as pendências de sábado e domingo")
    gs.anotar(c1["id"], "g", "Bom dia. São doze pendências.")
    r = gs.resumo()
    confere("a primeira fala vira o título da conversa", r["atual"]["titulo"].startswith("bom dia, quero ver") and r["atual"]["turnos"] == 1 and len(r["lista"]) == 1, r)
    c2 = gs.trocar()
    confere("conversa nova: outro id, processo antigo fechado e a tela avisada da troca", c2["id"] != c1["id"] and gs._proc is None and eventos[-1][0] == "conversa" and eventos[-1][1]["troca"] is True)
    fala, _, _ = rodar("quantas vezes eu já falei?")
    inicio = do_falso("inicio")[-1]
    confere("a conversa nova começa do zero, em outro processo", "1 vezes" in fala and c2["id"] in inicio["args"] and "--session-id" in inicio["args"], (fala, inicio["args"][-6:]))
    gs.anotar(c2["id"], "u", "outra conversa")
    confere("as duas aparecem na lista, a mais recente primeiro", [x["id"] for x in gs.resumo()["lista"]] == [c2["id"], c1["id"]], gs.resumo()["lista"])
    gs.trocar(c1["id"])
    rodar("voltei")
    inicio = do_falso("inicio")[-1]
    confere("voltar a uma conversa anterior RETOMA a sessão dela no Claude Code", "--resume" in inicio["args"] and c1["id"] in inicio["args"] and "--session-id" not in inicio["args"], inicio["args"][-6:])
    confere("e as falas guardadas voltam para a tela", [m["q"] for m in gs.mensagens(c1["id"])] == ["u", "g"] and "doze pendências" in gs.mensagens(c1["id"])[1]["t"])
    confere("conversa que não existe não abre", gs.trocar("nao-existe") is None and gs.atual()["id"] == c1["id"])
    os.environ["GUARDIAO_FALSO_SEM_RETOMADA"] = "1"
    gs.encerrar()
    fala, _, _ = rodar("ainda está aí?")
    os.environ.pop("GUARDIAO_FALSO_SEM_RETOMADA")
    confere("se a sessão guardada não existe mais no Claude Code, a fala segue numa conversa nova (não trava)", "Entendi: ainda está aí" in fala and gs.atual()["id"] != c1["id"], (fala, gs.atual()["id"]))
    ind = gs._indice()
    gs._achar(ind, gs.atual()["id"]).update(turnos=3, ultima=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 4 * 3600)))
    gs._gravar("indice.json", ind)
    velha = ind["atual"]
    confere("depois de 3 horas parada, a próxima fala abre uma conversa nova sozinha", gs.atual()["id"] != velha)

    # ---------------- rotas da tela ----------------
    r = requests.get(URL + "/conversas").json()
    confere("GET /conversas traz o modo, a conversa atual e a lista", r["modo"] is False and r["atual"]["id"] == gs.atual()["id"] and len(r["lista"]) >= 2 and "pasta" in r, r)
    r = requests.get(URL + "/conversas/mensagens", params={"id": c1["id"]}).json()
    confere("GET /conversas/mensagens traz as falas de uma conversa", len(r["mensagens"]) == 2 and r["mensagens"][0]["q"] == "u")
    while not h.bus.comandos.empty():
        h.bus.comandos.get_nowait()
    requests.post(URL + "/conversas", json={"acao": "nova"})
    requests.post(URL + "/conversas", json={"acao": "abrir", "id": c1["id"]})
    confere("POST /conversas vira comando para o programa de voz", [h.bus.comandos.get_nowait() for _ in range(2)] == [("conversa", {"acao": "nova", "id": ""}), ("conversa", {"acao": "abrir", "id": c1["id"]})])
    h.bus.cancelar_escuta.clear()
    resp = requests.post(URL + "/permissao", json={"decisao": "sempre"})
    confere("POST /permissao entrega o clique e interrompe a escuta", resp.status_code == 202 and h.bus.comandos.get_nowait() == ("permissao", "sempre") and h.bus.cancelar_escuta.is_set())
    confere("decisão desconhecida é recusada", requests.post(URL + "/permissao", json={"decisao": "talvez"}).status_code == 400)
    requests.post(URL + "/preferencias", json={"sessao": True})
    confere("a preferência do modo sessão é guardada e liga o modo", h.preferencias()["sessao"] is True and g.modo_sessao() is True and requests.get(URL + "/conversas").json()["modo"] is True)

    # ---------------- o programa de voz dentro da sessão ----------------
    g._ENVIADO.clear()
    g.FORA_DA_SESSAO.clear()
    conversa = gs.atual()["id"]
    m1 = g.mensagem_da_sessao("o que eu tenho agora?", conversa)
    m2 = g.mensagem_da_sessao("e depois?", conversa)
    confere("a primeira fala leva a hora, o plano e as tarefas conhecidas; a segunda só o que mudou",
            "Agora sao" in m1 and "PLANO DE HOJE" in m1 and "TAREFAS CONHECIDAS" in m1 and m1.endswith("[PEDIDO DESTE TURNO]\no que eu tenho agora?")
            and "Agora sao" in m2 and "PLANO DE HOJE:\n" not in m2 and "TAREFAS CONHECIDAS" not in m2 and "STATUS DO PLANO" in m2.upper() and "guardião completo" not in m2, m2[:300])
    g.lembrar("modo execução", "Modo execução. Foco em Montar as campanhas.")
    m3 = g.mensagem_da_sessao("quanto falta?", conversa)
    m4 = g.mensagem_da_sessao("ok", conversa)
    confere("o que aconteceu no painel fora da sessão entra uma vez na fala seguinte", "FORA DESTA SESSAO" in m3 and "Modo execução. Foco em" in m3 and "FORA DESTA SESSAO" not in m4)
    frases = list(g.frases_da_sessao("use o clickup para achar o relatório"))
    confere("o que ele diz antes de usar o conector sai na hora, e o uso do conector vira evento da tela", frases == ["Vou olhar no ClickUp.", "Achei duas tarefas abertas."]
            and any(t == "ferramenta" and d.get("rotulo") == "Consultando o ClickUp" for t, d in eventos), frases)
    saida = []
    for f in g.frases_da_sessao("mande o whatsapp para a Marina"):
        if isinstance(f, str):
            saida.append(f)
        else:
            saida.append(f[0])
            gs.decidir(f[1], "nao", "")
    confere("o pedido de permissão chega no meio das frases, na ordem", saida == ["permissao", "Não enviei."], saida)

    rapido = []
    turno_original, g.frases_do_claude = gs.turno, lambda p, m=None, motivo="": (rapido.append(motivo) or iter(["Resposta do modo rápido."]))

    def turno_quebrado(*a, **k):
        raise RuntimeError("caiu")
        yield
    gs.turno = turno_quebrado
    frases = list(g.frases_da_sessao("oi"))
    gs.turno = turno_original
    confere("se a sessão falha antes de falar, a resposta sai pelo modo rápido e a tela é avisada", frases == ["Resposta do modo rápido."] and rapido == ["sessão indisponível"]
            and any(t == "aviso" and "modo rápido" in d.get("texto", "") for t, d in eventos), (frases, rapido))

    i = g.interpretar_permissao
    confere("sim, pode, manda e autorizo viram sim", all(i(t, True) == ("sim", "") for t in ("sim", "pode", "pode sim, manda", "autorizo", "ok, pode criar")))
    confere("não e variações viram não", all(i(t, True) == ("nao", "") for t in ("não", "melhor não", "cancela", "deixa pra lá")))
    confere("'pode sempre' só vira sempre quando o pedido aceita", i("pode sempre", True) == ("sempre", "") and i("sim, sempre", False) == ("sim", ""))
    confere("outra resposta nega e leva o que a pessoa disse", i("muda o prazo para sexta e tira o nome do cliente do título antes", True)[0] == "nao"
            and "muda o prazo para sexta" in i("muda o prazo para sexta e tira o nome do cliente do título antes", True)[1] and i("", True) is None)

    # o pedido de permissão do começo ao fim: cartão na tela, pergunta em voz alta e a resposta por clique, por texto e por voz
    ditas, escutas = [], []
    g.dizer = lambda texto, a: ditas.append(texto)
    g.drenar = lambda q: None

    class A:
        sem_escuta_aberta = False
    pedido = dict(gs.descrever("mcp__claude_ai_ClickUp__clickup_create_task", {"name": "Ligar para o contador"}), id="p1", sempre=True)
    h.bus.comandos.put(("permissao", "sempre"))
    del eventos[:]
    r = g.pedir_permissao(A(), None, None, None, 0, pedido, por_voz=False)
    confere("clique em 'permitir sempre': a pergunta é falada, o cartão abre e fecha, e a decisão volta", r == ("sempre", "") and ditas == ["Posso criar uma tarefa no ClickUp?"]
            and [t for t, _ in eventos if t.startswith("permissao")] == ["permissao", "permissao_fim"] and eventos[0][1]["titulo"] == "Criar uma tarefa no ClickUp"
            and [d for t, d in eventos if t == "permissao_fim"][0] == {"id": "p1", "resultado": "permitida", "sempre": True}, (r, eventos[:2]))
    h.bus.comandos.put(("checkin", {"texto": "aviso que não pode se perder"}))
    h.bus.comandos.put(("perguntar", "não, deixa"))
    r = g.pedir_permissao(A(), None, None, None, 0, pedido, por_voz=False)
    confere("resposta digitada vale, e os outros comandos da fila não se perdem", r == ("nao", "") and h.bus.comandos.get_nowait()[0] == "checkin")
    g.escutar = lambda a, q, modelo, chave, piso, seguimento=False, avisar_cancelamento=True: (escutas.append(avisar_cancelamento) or ("pode criar", 0.5, "ok"))
    r = g.pedir_permissao(A(), None, None, None, 0, pedido, por_voz=True)
    confere("resposta falada vale (o microfone abre sozinho depois da pergunta)", r == ("sim", "") and escutas == [False])
    g.escutar = lambda *a, **k: ("", None, "cancelado")
    r = g.pedir_permissao(A(), None, None, None, 0, pedido, por_voz=True)
    confere("Esc durante a pergunta vale como não", r == ("nao", "") and [d for t, d in eventos if t == "permissao_fim"][-1]["resultado"] == "negada")

    # ---------------- 0.5.1: o guardião resolve ele mesmo o que sobra e fala como um só ----------------
    oferta = "Juntei as duas tarefas num bloco só. A tarefa repetida, Revisar e melhorar a interface, continua aberta. Quer que eu conclua essa repetida?"
    g.CONVERSA[:] = [(time.time(), "(resultado do pedido em segundo plano)", oferta)]
    confere("o sim à oferta do próprio guardião libera a ação que ele ofereceu", g.permitido("concluir", "sim, pode") and g.permitido("concluir", "pode"))
    confere("o sim não libera outra ação, e o não continua sendo não", not g.permitido("reabrir", "sim") and not g.permitido("concluir", "não, deixa"))
    g.CONVERSA[:] = [(time.time(), "oi", "Concluí a revisão do roteiro.")]
    confere("sem uma pergunta do guardião, o sim sozinho não libera nada", not g.permitido("concluir", "sim"))
    g.CONVERSA[:] = []
    rapido_txt, completo_txt, sessao_txt = g.texto_acoes(), g.prompt_completo("junta as duas tarefas", "plano_do_dia.json"), open(g.arquivo_prompt_sessao(), encoding="utf-8").read()
    confere("no modo rápido ele encerra tarefa repetida, não manda a pessoa ao ClickUp e não fala em guardião completo",
            "Tarefa repetida, o trabalho segue em" in rapido_txt and "Nunca mande o Rafa ir ao ClickUp" in rapido_txt and "nunca diga guardião completo em voz alta" in rapido_txt)
    confere("o pedido em segundo plano volta oferecendo resolver o que sobrou, sem falar de si mesmo",
            "não mande a pessoa fazer" in completo_txt and "não cite esta execução" in completo_txt and "Ao gravar o plano de hoje" in completo_txt)
    confere("na sessão ele faz pelo conector e sabe gravar o plano de hoje", "Nunca mande o Rafa fazer num conector" in sessao_txt and "PLANO DE HOJE EM ARQUIVO" in sessao_txt
            and '"status": "sugerido"' in sessao_txt and "não fale em guardião completo" in sessao_txt)
    arq_plano = os.path.join(tmp, "plano_do_dia.json")
    plano = json.load(open(arq_plano, encoding="utf-8"))
    plano["status"] = "aprovado"
    json.dump(plano, open(arq_plano, "w", encoding="utf-8"), ensure_ascii=False)
    antes = g.ler_plano()
    confere("plano que ninguém mexeu continua como está", g.conferir_plano(antes) == "igual" and json.load(open(arq_plano, encoding="utf-8"))["status"] == "aprovado")
    plano["blocos"][-1]["titulo"] = "Bloco juntado pela conversa"
    json.dump(plano, open(arq_plano, "w", encoding="utf-8"), ensure_ascii=False)
    confere("plano mudado pela conversa volta para aprovação", g.conferir_plano(antes) == "mudou" and json.load(open(arq_plano, encoding="utf-8"))["status"] == "sugerido")
    antes = g.ler_plano()
    open(arq_plano, "w", encoding="utf-8").write('{"blocos": [{"titulo": "sem id nem hora"}]')
    confere("plano gravado com defeito é desfeito", g.conferir_plano(antes) == "defeito" and g.ler_plano() == antes)

    # comandos falados que a própria máquina resolve
    antes = gs.atual()["id"]
    gs.anotar(antes, "u", "para a conversa não ser descartada")
    confere('"nova conversa" começa outra, sem gastar chamada ao Claude', g.comando_local("Ei guardião, nova conversa") == {"fala": "Conversa nova. Pode falar."} and gs.atual()["id"] != antes)
    del eventos[:]
    confere('"abrir conversas" abre a lista na tela', g.comando_local("abrir conversas") == {"fala": ""} and ("ui", {"cmd": "conversas"}) in eventos
            and g.comando_local("mostra o histórico") == {"fala": ""})
    requests.post(URL + "/preferencias", json={"sessao": False})
    g.CONVERSA[:] = [(time.time(), "a", "b")]
    confere("com o modo sessão desligado, 'nova conversa' só limpa a memória curta", g.comando_local("nova conversa") == {"fala": "Conversa nova. Pode falar."} and g.CONVERSA == [] and g.comando_local("abrir conversas") is None)
finally:
    gs.encerrar()
sys.exit(0 if placar() else 1)
