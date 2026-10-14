# Modo sessão: a conversa com o guardião vira uma sessão normal do Claude Code, com os conectores, as skills e os agentes da pasta da pessoa.
# Um processo do Claude Code fica aberto enquanto a conversa dura (entrada e saída em stream-json), para não pagar a partida a cada fala.
# Aqui ficam: a lista de conversas (para voltar a uma anterior), o processo, as regras de permissão e os nomes que a tela mostra
# quando o guardião usa um conector, uma skill ou um agente. Quem fala e ouve continua sendo o guardiao_voz.py.
#
# Arquivos (pasta operacional\conversas): indice.json (as conversas), <id>.jsonl (o que foi dito, para reabrir na tela)
# e permissoes.json (o que a pessoa mandou permitir sempre).
import glob
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid

import conferencia_plano as cp
import hud_servidor as h
from hud_servidor import _config, _ler_json, bus

SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# O Claude Code (e os conectores que ele abre, que herdam a prioridade) roda abaixo do normal: ele passa quase todo o tempo esperando a rede e quase não sente,
# mas na partida os conectores gastam toda a CPU, e a voz (que é gerada neste computador) ficava mais lenta do que a fala, com pausas entre as frases.
FLAGS_CLAUDE = SEM_JANELA | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x00004000)
COMANDO = None  # os testes trocam por um Claude de mentira (lista com o comando); sem isso vale comando_do_claude()
MODELO_PADRAO = os.environ.get("GUARDIAO_MODELO") or "claude-sonnet-5-5"
PRAZO_PERMISSAO = 150  # segundos esperando o sim ou o não; sem resposta, a ação é negada
PRAZO_SILENCIO = 600   # sem nenhum sinal do Claude por tanto tempo, o turno é dado como perdido
_trava = threading.RLock()


# ---------------- onde está o Claude Code ----------------
# O nome "claude" puro não basta no Windows: quem instalou por npm tem um claude.cmd, que o CreateProcess não abre
# (FileNotFoundError) e que, chamado por caminho completo, o cmd.exe corta na primeira quebra de linha do pedido.
# Aqui se acha o claude.exe de verdade, se confere que ele executa e todo o programa chama por este caminho.

AVISO_SEM_CLAUDE = "Não achei o Claude Code neste computador. É ele que pensa por mim. Instale em claude.com/claude-code, entre com a sua conta e abra o guardião de novo."
_CLAUDE = {"comando": None, "versao": "", "erro": "", "de": ""}
_trava_claude = threading.Lock()


def _real_do_atalho(atalho):
    """O que um claude.cmd do npm de fato executa: ['...\\claude.exe'] ou, nas versões antigas, [node, '...\\cli.js']. Vazio se não achar."""
    base = os.path.dirname(os.path.abspath(atalho))
    try:
        with open(atalho, encoding="utf-8", errors="replace") as f:
            texto = f.read()
    except OSError:
        texto = ""
    alvos = [os.path.normpath(os.path.join(base, rel)) for rel in re.findall(r'%dp0%\\([^"\r\n]+?\.(?:exe|js))"', texto, re.I)]
    pacote = os.path.join(base, "node_modules", "@anthropic-ai", "claude-code")
    alvos += [os.path.join(pacote, "bin", "claude.exe"), os.path.join(pacote, "cli.js")]
    for alvo in alvos:
        if not os.path.isfile(alvo):
            continue
        if alvo.lower().endswith(".exe"):
            return [alvo]
        node = shutil.which("node") or os.path.join(base, "node.exe")
        if os.path.isfile(node):
            return [node, alvo]
    return []


def _candidatos():
    """Onde procurar, do mais provável ao menos: o que o terminal da pessoa usa (PATH), o instalador oficial, o npm e a extensão do VS Code."""
    forcado = os.environ.get("GUARDIAO_CLAUDE", "").strip().strip('"')
    if forcado:
        yield forcado
    achado = shutil.which("claude")
    if achado:
        yield achado
    casa = os.path.expanduser("~")
    yield os.path.join(casa, ".local", "bin", "claude.exe")
    yield os.path.join(os.environ.get("APPDATA") or os.path.join(casa, "AppData", "Roaming"), "npm", "claude.cmd")
    yield from sorted(glob.glob(os.path.join(casa, ".vscode", "extensions", "anthropic.claude-code-*", "resources", "native-binary", "claude.exe")), reverse=True)


def _como_chamar(caminho):
    if not os.path.isfile(caminho):
        return []
    return _real_do_atalho(caminho) if caminho.lower().endswith((".cmd", ".bat")) else [caminho]


def _executa(comando):
    """Roda `claude --version` de verdade. Devolve (versão, erro): achar o arquivo não prova que ele executa."""
    try:
        r = subprocess.run(comando + ["--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                           stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired) as erro:
        return "", str(erro)
    saida = (r.stdout or r.stderr or "").strip()
    return (saida.splitlines()[0] if saida else ""), ("" if r.returncode == 0 else f"saiu com código {r.returncode}: {saida[:200]}")


def comando_do_claude(refazer=False):
    """Como chamar o Claude Code: a lista que abre qualquer comando (['C:\\...\\claude.exe']). Vazia se nenhum candidato executa.
    O resultado fica guardado; refazer=True procura de novo (a pessoa pode ter instalado o Claude Code com o guardião aberto)."""
    if COMANDO:
        return list(COMANDO)
    guardado = _CLAUDE["comando"]
    if guardado is not None and not refazer:  # sem cadeado: o laço do microfone chama isto a cada poucos segundos e não pode esperar uma procura lenta
        return list(guardado)
    with _trava_claude:
        if _CLAUDE["comando"] is not None and not refazer:
            return list(_CLAUDE["comando"])
        erros, vistos = [], set()
        for candidato in _candidatos():
            if candidato.lower() in vistos:
                continue
            vistos.add(candidato.lower())
            cmd = _como_chamar(candidato)
            if not cmd:
                continue
            versao, erro = _executa(cmd)
            if not erro:
                _CLAUDE.update(comando=cmd, versao=versao, erro="", de=candidato)
                return list(cmd)
            erros.append(f"{candidato}: {erro}")
        _CLAUDE.update(comando=[], versao="", erro="; ".join(erros), de="")
        return []


def estado_do_claude():
    """Para a tela e o diagnóstico: o que foi achado, a versão e, se nada executou, por quê."""
    comando_do_claude()
    return {"ok": bool(_CLAUDE["comando"]), "comando": list(_CLAUDE["comando"] or []), "versao": _CLAUDE["versao"], "erro": _CLAUDE["erro"], "de": _CLAUDE["de"]}


class ErroDeConta(RuntimeError):
    """O Claude Code respondeu, mas a conta não deixa: sem login, limite de uso, servidor sobrecarregado, ou ele nem está instalado.
    A mensagem já vem em português e diz o que fazer; quem recebe pode falá-la como está. Tentar de novo por outro caminho falharia igual."""


_MESES_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def quando_o_limite_volta(texto):
    """'... resets Oct 17, 7pm (America/Fortaleza)' vira 'em 17 de outubro, às 19h'; '... resets 3pm' vira 'às 15h'. Vazio se não entender."""
    m = re.search(r"\breset(?:s)?(?:\s+at|\s+on)?\s+(?:([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(?:at\s+)?)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", texto or "", re.I)
    if not m:
        return ""
    mes, dia, hora, minuto, ampm = m.groups()
    h24 = int(hora) % 12 + (12 if ampm.lower() == "pm" else 0)
    quando = f"às {h24}h" + (minuto if minuto and minuto != "00" else "")
    if mes and dia and mes.lower() in _MESES_EN:
        return f"em {int(dia)} de {_MESES_PT[_MESES_EN[mes.lower()] - 1]}, {quando}"
    return quando


def explicar_erro_do_claude(texto):
    """O texto de erro que o Claude Code devolve vira uma frase que a pessoa entende e sabe resolver. Vazio se não for um erro de conta conhecido."""
    t = (texto or "").lower()
    if re.search(r"not logged in|/login|invalid api key|authentication|oauth token|token has expired|please run", t):
        return "O Claude Code não está conectado à sua conta. Abra o Claude Code, entre com a sua conta e fale comigo de novo."
    if "overloaded" in t or "529" in t:
        return "O Claude está sobrecarregado agora. Tente de novo em instantes."
    if re.search(r"hit your|usage limit|rate limit|limit reached|reached your|out of (extra )?usage|quota", t):
        volta = quando_o_limite_volta(texto)
        quando = f"Ele volta {volta}." if volta else "Tente de novo mais tarde."
        if "weekly" in t:
            return f"Você atingiu o limite semanal do seu plano do Claude. {quando} Até lá não consigo responder."
        return f"Você atingiu o limite de uso do seu plano do Claude. {quando}"
    return ""


def erro_de_conta(texto):
    """A ErroDeConta para o texto de erro do Claude Code (explicado em português, ou o texto como veio se não for conhecido)."""
    return ErroDeConta(explicar_erro_do_claude(texto) or f"O Claude Code respondeu com erro: {str(texto or 'sem detalhes').strip()[:160]}")


def arquivo_de_erro():
    """Para onde vai o que o Claude Code escreve na saída de erro: logs\\claude_erro.log (apagado quando passa de 200 KB). Sem isso,
    um problema de login ou de versão não deixa rastro nenhum."""
    try:
        pasta = os.path.join(h.OPER, "logs")
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, "claude_erro.log")
        if os.path.exists(caminho) and os.path.getsize(caminho) > 200_000:
            os.remove(caminho)
        return open(caminho, "ab")
    except OSError:
        return subprocess.DEVNULL


def _pasta():
    return os.path.join(h.OPER, "conversas")  # lida a cada uso: os testes trocam a pasta operacional


def configuracao():
    """Bloco sessao do config.json: pasta (onde o Claude Code roda, com as skills e os agentes da pessoa), modelo, esforco
    ("low" por padrão: medido, a primeira frase sai em 3,5 a 4,6 s, contra 5 a 14 s no padrão do Claude Code; "padrao" usa o do Claude Code),
    fecha_apos_min (processo parado se fecha sozinho) e nova_conversa_apos_horas (depois de tanto tempo sem conversa, começa uma nova)."""
    c = _config().get("sessao") or {}
    pasta = str(c.get("pasta") or "").strip()

    def numero(chave, padrao):
        try:
            return max(0.0, float(c.get(chave)))
        except (TypeError, ValueError):
            return padrao
    return {"pasta": pasta if pasta and os.path.isdir(pasta) else h.OPER, "modelo": str(c.get("modelo") or "").strip() or MODELO_PADRAO,
            "esforco": "" if str(c.get("esforco") or "").strip().lower() in ("padrao", "padrão", "default") else str(c.get("esforco") or "low").strip(), "ociosa": numero("fecha_apos_min", 15) * 60, "nova_apos": numero("nova_conversa_apos_horas", 3) * 3600}


# ---------------- as conversas ----------------

def _agora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _segundos(iso):
    try:
        return time.mktime(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return 0.0


def _indice():
    d = _ler_json(os.path.join(_pasta(), "indice.json")) or {}
    return {"atual": d.get("atual"), "conversas": [c for c in d.get("conversas") or [] if isinstance(c, dict) and c.get("id")]}


def _gravar(nome, dados):
    os.makedirs(_pasta(), exist_ok=True)
    tmp = os.path.join(_pasta(), nome + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(_pasta(), nome))


def _achar(ind, cid):
    return next((c for c in ind["conversas"] if c["id"] == cid), None)


def nova():
    """Começa uma conversa nova (contexto limpo). As anteriores continuam na lista."""
    with _trava:
        ind = _indice()
        ind["conversas"] = [c for c in ind["conversas"] if c.get("turnos")]  # conversa que nem chegou a ter uma fala não fica guardada
        c = {"id": str(uuid.uuid4()), "titulo": "", "criada": _agora(), "ultima": _agora(), "turnos": 0, "iniciada": False, "contexto": 0}
        ind["conversas"].append(c)
        ind["atual"] = c["id"]
        _gravar("indice.json", ind)
        return c


def atual(criar=True):
    """A conversa em andamento. Sem nenhuma, ou se a última ficou parada por mais de nova_conversa_apos_horas, começa outra."""
    with _trava:
        ind = _indice()
        c = _achar(ind, ind.get("atual"))
        vencida = bool(c and c.get("turnos") and time.time() - _segundos(c.get("ultima")) > configuracao()["nova_apos"] > 0)
        if c and not vencida:
            return c
        return nova() if criar else None


def abrir(cid):
    """Volta a uma conversa anterior. Devolve a conversa ou None se ela não existe."""
    with _trava:
        ind = _indice()
        c = _achar(ind, cid)
        if not c:
            return None
        ind["atual"] = c["id"]
        c["ultima"] = _agora()  # reaberta agora: não vence na próxima fala
        _gravar("indice.json", ind)
        return c


def _atualizar(cid, **campos):
    with _trava:
        ind = _indice()
        c = _achar(ind, cid)
        if c:
            c.update(campos)
            _gravar("indice.json", ind)
        return c


def anotar(cid, quem, texto):
    """Guarda uma fala ('u' = a pessoa, 'g' = o guardião) para a conversa poder ser reaberta na tela. A primeira fala da pessoa vira o título."""
    texto = str(texto or "").strip()
    if not texto:
        return
    os.makedirs(_pasta(), exist_ok=True)
    with _trava:
        with open(os.path.join(_pasta(), cid + ".jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"q": quem, "t": texto, "em": _agora()}, ensure_ascii=False) + "\n")
        ind = _indice()
        c = _achar(ind, cid)
        if c:
            c["ultima"] = _agora()
            if quem == "u":
                c["turnos"] = int(c.get("turnos") or 0) + 1
                if not c.get("titulo"):
                    c["titulo"] = texto[:70] + ("…" if len(texto) > 70 else "")
            _gravar("indice.json", ind)


def mensagens(cid, limite=40):
    saida = []
    try:
        with open(os.path.join(_pasta(), os.path.basename(str(cid)) + ".jsonl"), encoding="utf-8") as f:
            for linha in f:
                try:
                    m = json.loads(linha)
                except ValueError:
                    continue
                if m.get("q") in ("u", "g") and m.get("t"):
                    saida.append({"q": m["q"], "t": m["t"], "em": m.get("em")})
    except OSError:
        pass
    return saida[-limite:]


def resumo():
    """O que a tela precisa saber das conversas: a atual e as anteriores (as mais recentes primeiro)."""
    ind = _indice()
    c = _achar(ind, ind.get("atual"))
    lista = [x for _, x in sorted(((i, x) for i, x in enumerate(ind["conversas"]) if x.get("turnos")), key=lambda p: (str(p[1].get("ultima")), p[0]), reverse=True)][:40]
    limpa = lambda x: {"id": x["id"], "titulo": x.get("titulo") or "Conversa nova", "ultima": x.get("ultima"), "turnos": int(x.get("turnos") or 0), "contexto": int(x.get("contexto") or 0)}  # noqa: E731
    return {"atual": limpa(c) if c else None, "lista": [limpa(x) for x in lista], "pronta": bool(_proc and _proc.viva() and _proc.pronta.is_set()),
            "pasta": os.path.basename(configuracao()["pasta"].rstrip("\\/"))}


def avisar_tela(troca=False):
    bus.emitir("conversa", troca=bool(troca), **resumo())


# ---------------- nomes que a tela mostra quando o guardião usa uma ferramenta ----------------

LIVRES = {"Read", "Glob", "Grep", "LS", "Skill", "ToolSearch", "TodoWrite", "Task", "Agent", "WebSearch", "WebFetch", "NotebookRead", "ListMcpResourcesTool",
          "ReadMcpResourceTool", "ReadMcpResourceDirTool", "TaskOutput", "BashOutput", "TaskStop", "KillShell", "ListAgents", "ReadNotifications"}
NEGADAS = {"AskUserQuestion": "No painel de voz não existe essa ferramenta. Faça a pergunta em voz alta, em uma frase curta, e espere a resposta.",
           "EnterPlanMode": "No painel de voz não existe modo de planejamento. Diga o plano em poucas frases.",
           "ExitPlanMode": "No painel de voz não existe modo de planejamento. Diga o plano em poucas frases."}
P_LEITURA = {"get", "list", "search", "read", "find", "query", "fetch", "filter", "resolve", "lookup", "show", "describe", "whoami", "status", "view", "count", "aggregate", "preview",
             "check", "suggest", "recommend", "explore", "help", "guide", "summarize", "wait", "context", "metadata", "schema", "info", "details", "balance", "transactions", "display"}
P_SENSIVEL = {"send", "reply", "forward", "post", "publish", "delete", "trash", "pay", "buy", "purchase", "deploy", "invite", "share", "execute", "run", "apply", "activate", "boost",
              "respond", "merge", "pause", "unpause", "cancel", "restore", "reset", "spam", "untrash", "promote", "rollback", "transfer"}
VERBOS = [("create", "criar"), ("update", "alterar"), ("edit", "alterar"), ("set", "alterar"), ("delete", "apagar"), ("trash", "apagar"), ("remove", "remover"), ("send", "enviar"),
          ("reply", "responder"), ("respond", "responder"), ("forward", "encaminhar"), ("post", "publicar"), ("publish", "publicar"), ("add", "adicionar"), ("move", "mover"),
          ("upload", "enviar"), ("execute", "executar"), ("run", "executar"), ("apply", "aplicar"), ("activate", "ativar"), ("generate", "gerar"), ("comment", "comentar em"),
          ("merge", "juntar"), ("start", "iniciar"), ("stop", "parar"), ("attach", "anexar"), ("share", "compartilhar"), ("invite", "convidar"), ("deploy", "publicar"),
          ("pause", "pausar"), ("copy", "copiar"), ("duplicate", "duplicar"), ("label", "etiquetar"), ("cancel", "cancelar"), ("boost", "impulsionar"), ("export", "exportar")]
OBJETOS = {"task": "uma tarefa", "tasks": "tarefas", "comment": "um comentário", "message": "uma mensagem", "event": "um evento", "page": "uma página", "pages": "páginas",
           "file": "um arquivo", "draft": "um rascunho", "email": "um e-mail", "list": "uma lista", "folder": "uma pasta", "document": "um documento", "doc": "um documento",
           "reminder": "um lembrete", "tag": "uma etiqueta", "campaign": "uma campanha", "ad": "um anúncio", "design": "um design", "database": "uma base", "thread": "uma conversa",
           "flow": "um fluxo", "workflow": "um fluxo", "field": "um campo", "image": "uma imagem", "video": "um vídeo", "entry": "um registro", "record": "um registro",
           "dependency": "uma dependência", "link": "um vínculo", "creative": "um criativo", "audience": "um público", "sql": "um comando no banco", "migration": "uma migração",
           "project": "um projeto", "attachment": "um anexo", "channel": "um canal", "subscriber": "um contato", "entity": "um item", "set": "um conjunto", "view": "uma visão"}
ROTULOS = {"name": "Nome", "title": "Título", "summary": "Título", "subject": "Assunto", "to": "Para", "number": "Para", "recipient": "Para", "cc": "Cópia", "description": "Descrição",
           "markdown_description": "Descrição", "content": "Texto", "text": "Texto", "message": "Mensagem", "body": "Texto", "comment_text": "Comentário", "due_date": "Prazo",
           "start_date": "Início", "start": "Início", "end": "Fim", "status": "Status", "priority": "Prioridade", "assignees": "Responsáveis", "attendees": "Convidados",
           "file_path": "Arquivo", "command": "Comando", "url": "Endereço", "query": "Consulta"}
NA = {"Meta": "na Meta", "Vercel": "na Vercel"}


def nome_conector(servidor):
    s = re.sub(r"^(claude_ai_|plugin_[^_]+_)", "", str(servidor)).replace("_", " ").replace("-", " ").strip()
    return (s[:1].upper() + s[1:]) if s else "conector"


def _mcp(nome):
    m = re.match(r"mcp__(.+?)__(.+)$", nome)
    return (m.group(1), m.group(2), [p for p in re.split(r"[_\-]+", m.group(2).lower()) if p]) if m else None


def _frase_da_acao(palavras):
    """'criar uma tarefa' a partir do nome da ferramenta (clickup_create_task). Sem verbo conhecido, devolve vazio."""
    for i, p in enumerate(palavras):
        verbo = next((pt for en, pt in VERBOS if en == p), None)
        if not verbo:
            continue
        objeto = ""
        for q in palavras[i + 1:]:
            if q in ("to", "from", "in", "on", "for", "by", "with"):
                break
            objeto = OBJETOS.get(q, objeto)
        return f"{verbo} {objeto}".strip() if objeto else (verbo if not verbo.endswith(" em") else "comentar")
    return ""


def atividade(nome, entrada):
    """(tipo, rotulo) do que o guardião está fazendo, para a tela: conector, skill, agente, arquivo, web ou comando. None = não vale mostrar."""
    entrada = entrada or {}
    m = _mcp(nome)
    if m:
        conector = nome_conector(m[0])
        return "conector", ("Consultando " if set(m[2]) & P_LEITURA and not set(m[2]) & P_SENSIVEL else "Usando ") + ("a " if conector in NA else "o ") + conector
    if nome == "Skill":
        return "skill", "Usando a skill " + str(entrada.get("skill") or entrada.get("command") or "").split(":")[-1]
    if nome in ("Task", "Agent"):
        quem = str(entrada.get("subagent_type") or "").strip()
        return "agente", ("Chamando o agente " + quem) if quem and quem != "general-purpose" else "Chamando um agente"
    if nome in ("Read", "Glob", "Grep", "LS", "NotebookRead"):
        return "arquivo", "Lendo arquivos"
    if nome in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return "arquivo", "Escrevendo " + (os.path.basename(str(entrada.get("file_path") or "")) or "um arquivo")
    if nome in ("Bash", "PowerShell"):
        return "comando", "Rodando um comando"
    if nome == "WebSearch":
        return "web", "Pesquisando na web"
    if nome == "WebFetch":
        return "web", "Abrindo uma página"
    if nome == "ToolSearch":
        return "conector", "Procurando a ferramenta certa"
    return None


# ---------------- permissões ----------------

def _sempre():
    return set((_ler_json(os.path.join(_pasta(), "permissoes.json")) or {}).get("sempre") or [])


def permitir_sempre(nome):
    with _trava:
        _gravar("permissoes.json", {"sempre": sorted(_sempre() | {nome})})


def _dentro(caminho, pasta):
    try:
        return os.path.commonpath([os.path.normcase(os.path.abspath(caminho)), os.path.normcase(os.path.abspath(pasta))]) == os.path.normcase(os.path.abspath(pasta))
    except ValueError:
        return False


def _pasta_memoria():
    return (_config().get("pastas") or {}).get("memoria") or os.path.join(h.OPER, "memoria")


def _pastas_do_guardiao():
    return [h.OPER, (_config().get("pastas") or {}).get("memoria") or os.path.join(h.OPER, "memoria")]


def _script_do_guardiao(comando):
    """O comando só roda um script .ps1 da pasta operacional (ler_campanha, anotar_campanha...), sem emendar outro comando?"""
    c = str(comando or "").strip()
    if not re.match(r"^powershell(\.exe)?\s", c, re.I) or re.search(r"[;|&><`]|\$\(", c):
        return False
    m = re.search(r"-File\s+(\"[^\"]+\"|'[^']+'|\S+)", c, re.I)
    return bool(m and m.group(1).strip("\"'").lower().endswith(".ps1") and _dentro(m.group(1).strip("\"'"), h.OPER))


def classificar(nome, entrada):
    """O que fazer com o pedido de uso de uma ferramenta: ('permitir' | 'negar' | 'perguntar', sensivel, motivo).
    Ler é livre. Escrever nas pastas do próprio guardião é livre. O resto pergunta; o que envia, apaga ou publica pergunta sempre."""
    entrada = entrada or {}
    if nome in NEGADAS:
        return "negar", False, NEGADAS[nome]
    if nome in LIVRES:
        return "permitir", False, ""
    m = _mcp(nome)
    if m and m[1] == "clickup_create_task" and not entrada.get("parent") and h.lista_conteudos_id() and str(entrada.get("list_id") or "") == h.lista_conteudos_id() and h.eh_etapa_de_post(entrada.get("name")):
        return "negar", False, ("Etapa de post (copy, design, manychat, roteiro) nunca nasce solta: crie como subtarefa, com o campo parent apontando para a tarefa mãe do post "
                                "(posts_maes.json na pasta operacional). Se a mãe não existe, não crie nada: diga isso à pessoa.")
    if m:
        palavras = set(m[2])
        if palavras & P_SENSIVEL:
            return "perguntar", True, ""
        if nome in _sempre() or (palavras & P_LEITURA and not any(en in palavras for en, _ in VERBOS)):
            return "permitir", False, ""
        return "perguntar", False, ""
    if nome in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        caminho = str(entrada.get("file_path") or entrada.get("notebook_path") or "")
        return ("permitir" if caminho and any(_dentro(caminho, p) for p in _pastas_do_guardiao()) else "perguntar"), False, ""
    if nome in ("Bash", "PowerShell"):
        return ("permitir" if _script_do_guardiao(entrada.get("command")) else "perguntar"), True, ""
    return "perguntar", True, ""


def _valor(v):
    texto = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:220] + ("…" if len(texto) > 220 else "")


def descrever(nome, entrada):
    """Como o pedido aparece para a pessoa: título do cartão, a pergunta falada e as linhas com os dados."""
    entrada = entrada or {}
    m = _mcp(nome)
    if m:
        conector = nome_conector(m[0])
        onde = NA.get(conector, "no " + conector)
        frase = _frase_da_acao(m[2]) or ("usar " + m[1].replace("_", " ").replace("-", " "))
        titulo, kicker = f"{frase[:1].upper()}{frase[1:]} {onde}", conector
    elif nome in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        arq = os.path.basename(str(entrada.get("file_path") or entrada.get("notebook_path") or "")) or "um arquivo"
        frase, titulo, kicker = f"gravar o arquivo {arq}", f"Gravar o arquivo {arq}", "Arquivo neste computador"
        entrada = {"file_path": entrada.get("file_path") or entrada.get("notebook_path"), "content": entrada.get("content") or entrada.get("new_string")}
    elif nome in ("Bash", "PowerShell"):
        frase, titulo, kicker = "rodar um comando neste computador", "Rodar um comando neste computador", "Comando"
        entrada = {"command": entrada.get("command"), "description": entrada.get("description")}
    else:
        frase, titulo, kicker = f"usar a ferramenta {nome}", f"Usar a ferramenta {nome}", "Ferramenta"
    conhecidas = [(ROTULOS[k], _valor(v)) for k, v in entrada.items() if k in ROTULOS and v not in (None, "", [], {})]
    outras = [(k.replace("_", " ").capitalize(), _valor(v)) for k, v in entrada.items()  # códigos internos (list_id, task_id...) não dizem nada para a pessoa
              if k not in ROTULOS and v not in (None, "", [], {}) and not isinstance(v, bool) and not re.search(r"(^|_)id$", k)]
    pergunta = f"Posso {frase}{' ' + NA.get(nome_conector(m[0]), 'no ' + nome_conector(m[0])) if m else ''}?"
    return {"titulo": titulo, "kicker": kicker, "pergunta": pergunta, "linhas": [list(x) for x in (conhecidas + outras)[:7]]}


# ---------------- o processo do Claude Code ----------------

class Processo:
    """Um Claude Code aberto para uma conversa. As falas entram pelo stdin e os eventos saem pelo stdout, uma linha de JSON por vez."""

    def __init__(self, conversa, arquivo_prompt):
        cfg = configuracao()
        self.conversa = conversa["id"]
        self.modelo = cfg["modelo"]
        base = comando_do_claude()
        if not base:
            raise ErroDeConta(AVISO_SEM_CLAUDE)
        cmd = base + ["--print", "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--input-format", "stream-json",
                         "--permission-prompt-tool", "stdio", "--model", self.modelo, "--append-system-prompt-file", arquivo_prompt]
        cmd += ["--resume", self.conversa] if conversa.get("iniciada") else ["--session-id", self.conversa]
        if cfg["esforco"]:
            cmd += ["--effort", cfg["esforco"]]
        for pasta in _pastas_do_guardiao():  # o plano e a memória ficam à mão mesmo quando a sessão roda em outra pasta
            if os.path.isdir(pasta) and not _dentro(pasta, cfg["pasta"]):
                cmd += ["--add-dir", pasta]
        env = dict(os.environ)
        env.pop("CLAUDECODE", None)
        erro = arquivo_de_erro()
        self.proc = subprocess.Popen(cmd, cwd=cfg["pasta"], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=erro, text=True, encoding="utf-8",
                                     errors="replace", bufsize=1, creationflags=FLAGS_CLAUDE)
        if erro is not subprocess.DEVNULL:
            erro.close()  # o processo filho tem a própria cópia
        self.fila = queue.Queue()
        self.pronta = threading.Event()
        self.em_turno = False
        self.resultados_atrasados = 0  # turnos que acabaram de falar mas ainda não mandaram o fecho (uso e custo)
        self.custo = 0.0
        self.solto = ""  # texto que chegou fora de um turno (um agente que terminou em segundo plano, por exemplo)
        self.fechou = False
        self.descartar = False  # a fala foi interrompida: o que ainda chegar desse turno não é para dizer
        self.respostas = {}  # respostas aos pedidos de controle que o guardião faz (estado dos conectores)
        self.aquecida = threading.Event()  # os conectores terminaram de ligar
        self.contexto = 0  # tamanho da conversa na última chamada ao Claude (o fecho do turno soma todas as chamadas, o que não serve para isso)
        self.usado_em = time.time()
        self.lidas = set()  # campanhas lidas desde que o plano foi gravado pela última vez
        self.rota = False  # o roteador da agenda (onde_cabe.ps1) rodou desde a última gravação do plano
        self.gravou_plano = False
        self.escrita = threading.Lock()
        threading.Thread(target=self._ler, daemon=True).start()
        self._manda({"type": "control_request", "request_id": "inicio", "request": {"subtype": "initialize", "hooks": None}})

    def viva(self):
        return not self.fechou and self.proc.poll() is None

    def _manda(self, obj):
        with self.escrita:
            self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()

    def _ler(self):
        try:
            for linha in self.proc.stdout:
                try:
                    ev = json.loads(linha)
                except ValueError:
                    continue
                tipo = ev.get("type")
                if tipo == "assistant" and not ev.get("parent_tool_use_id"):
                    uso = (ev.get("message") or {}).get("usage") or {}
                    self.contexto = sum(uso.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")) or self.contexto
                if tipo == "assistant":
                    for bloco in (ev.get("message") or {}).get("content") or []:
                        if isinstance(bloco, dict) and bloco.get("type") == "tool_use":
                            slug = cp.slug_lido(str(bloco.get("name") or ""), bloco.get("input"), _pasta_memoria())
                            if slug:
                                self.lidas.add(slug)
                            if bloco.get("name") in ("Bash", "PowerShell") and "onde_cabe" in str((bloco.get("input") or {}).get("command") or "").lower():
                                self.rota = True
                if tipo == "control_response":
                    r = ev.get("response") or {}
                    self.respostas[str(r.get("request_id"))] = r.get("response") or {}
                    self.pronta.set()
                elif tipo == "control_request":
                    threading.Thread(target=self._permissao, args=(ev,), daemon=True).start()
                elif self.em_turno:
                    self.fila.put(ev)
                else:
                    self._fora_de_turno(ev)
        except (OSError, ValueError):
            pass
        self.fechou = True
        self.pronta.set()
        self.fila.put({"type": "_fim"})

    def _fora_de_turno(self, ev):
        """Sem turno em andamento chegam o fecho do turno anterior (uso e custo) e, às vezes, uma fala que o Claude começa sozinho
        (um agente em segundo plano terminou): essa fala vira um comando para o guardião dizer."""
        tipo = ev.get("type")
        if self.descartar:  # turno interrompido (a pessoa fechou a janela): nada do que sobrou vira fala
            if tipo == "result":
                self.descartar, self.solto = False, ""
                self._fechar_turno(ev, contar=False)
            return
        if tipo == "stream_event" and not ev.get("parent_tool_use_id"):
            e = ev.get("event") or {}
            if e.get("type") == "content_block_delta" and (e.get("delta") or {}).get("type") == "text_delta":
                self.solto += e["delta"].get("text", "")
        elif tipo == "result":
            texto, self.solto = self.solto.strip(), ""
            self._fechar_turno(ev, contar=not texto)
            if texto:
                bus.comandos.put(("sessao_fala", {"texto": texto, "conversa": self.conversa}))

    def conectores_ligados(self):
        """Quantos conectores já estão ligados (None se o Claude Code não respondeu)."""
        rid = f"mcp_{time.time():.3f}"
        try:
            self._manda({"type": "control_request", "request_id": rid, "request": {"subtype": "mcp_status"}})
        except (OSError, ValueError):
            return None
        fim = time.time() + 5
        while time.time() < fim and rid not in self.respostas:
            time.sleep(0.1)
        resposta = self.respostas.pop(rid, None)
        if resposta is None:
            return None
        servidores = next((v for v in resposta.values() if isinstance(v, list)), [])
        return sum(1 for x in servidores if isinstance(x, dict) and x.get("status") == "connected")

    def aquecer(self, limite=40):
        """Espera a contagem de conectores ligados parar de mudar (3 leituras iguais) ou o limite de tempo. Uma fala que chegue antes não espera."""
        fim, anterior, iguais = time.time() + limite, None, 0
        while time.time() < fim and self.viva() and not self.em_turno and iguais < 3:
            n = self.conectores_ligados()
            if n is None:
                break
            iguais = iguais + 1 if n == anterior else 0
            anterior = n
            time.sleep(1.5)
        self.aquecida.set()

    def interromper(self):
        """Pede ao Claude Code que pare a resposta em andamento (testado: ele devolve o fecho do turno em milésimos e aceita a fala seguinte)."""
        self.descartar = True
        try:
            self._manda({"type": "control_request", "request_id": f"int_{time.time():.3f}", "request": {"subtype": "interrupt"}})
        except (OSError, ValueError):
            self.descartar = False

    def _responde(self, ev, permitir, mensagem=""):
        resposta = {"behavior": "allow", "updatedInput": (ev.get("request") or {}).get("input") or {}} if permitir else {"behavior": "deny", "message": mensagem or "A pessoa não autorizou."}
        try:
            self._manda({"type": "control_response", "response": {"subtype": "success", "request_id": ev.get("request_id"), "response": resposta}})
        except (OSError, ValueError):
            pass

    def _permissao(self, ev):
        r = ev.get("request") or {}
        if r.get("subtype") != "can_use_tool":
            try:
                self._manda({"type": "control_response", "response": {"subtype": "error", "request_id": ev.get("request_id"), "error": "pedido não atendido pelo guardião"}})
            except (OSError, ValueError):
                pass
            return
        nome, entrada = str(r.get("tool_name") or ""), r.get("input") or {}
        regra, sensivel, motivo = classificar(nome, entrada)
        if regra == "permitir":
            barrado = self._barrar_plano(nome, entrada)
            if barrado:
                return self._responde(ev, False, barrado)
        if regra == "permitir":
            return self._responde(ev, True)
        if regra == "negar" or not self.em_turno:
            return self._responde(ev, False, motivo or "Não há ninguém para autorizar agora. Diga o que pretende fazer e espere a pessoa pedir.")
        pedido = dict(descrever(nome, entrada), id=str(ev.get("request_id")), ferramenta=nome, sempre=bool(_mcp(nome)) and not sensivel, espera=threading.Event(), decisao=None)
        self.fila.put({"type": "_permissao", "pedido": pedido})
        if not pedido["espera"].wait(PRAZO_PERMISSAO):
            pedido["decisao"] = ("nao", "A pessoa não respondeu ao pedido de permissão. Não execute; diga que ficou sem resposta.")
        decisao, mensagem = pedido["decisao"] or ("nao", "")
        if decisao == "sempre" and pedido["sempre"]:
            permitir_sempre(nome)
        self._responde(ev, decisao in ("sim", "sempre"), mensagem or "A pessoa não autorizou. Não tente de novo nem por outro caminho; pergunte o que ajustar.")

    def _barrar_plano(self, nome, entrada):
        """Gravar o plano exige ter lido as campanhas ativas e um plano sem contradição. Devolve o motivo da negação, ou "" se pode gravar."""
        if nome not in ("Write", "Edit", "MultiEdit"):
            return ""
        caminho = str(entrada.get("file_path") or "")
        if not cp.eh_arquivo_de_plano(caminho):
            return ""
        faltam = [c for c in cp.campanhas_ativas(_pasta_memoria()) if c not in self.lidas]
        if faltam:
            return ("Não grave o plano ainda: você não leu a agenda inteira. Leia estas campanhas ativas e só depois grave "
                    f"(powershell -File ler_campanha.ps1 -Slug <slug>, na pasta operacional): {', '.join(faltam)}. "
                    "Depois de ler, ponha no plano o campo \"agenda_impoe\" com uma frase do que a agenda impõe a este dia.")
        plano = cp.texto_do_plano(entrada) if nome == "Write" else None
        if plano is not None:
            registro = h._registro_de_hoje().get("blocos", [])
            feitos = {b.get("id") for b in registro if b.get("estado") in ("feito", "adiado")}
            anterior = _ler_json(caminho)
            problemas = cp.conferir(plano, anterior, feitos)
            problemas += self._conferir_semana(plano, caminho, anterior, feitos)
            problemas += self._exigir_rota(plano, caminho, anterior)
            if problemas:
                return "O plano não pode ser gravado assim. Corrija e grave de novo:\n- " + "\n- ".join(problemas)
        self.gravou_plano = True
        return ""

    def _exigir_rota(self, plano, caminho, anterior):
        """Editar um plano já gravado pondo nele uma tarefa que não estava naquele dia (nova ou vinda de outro dia) exige o roteador antes:
        é ele que faz a conta de onde cabe. Montar um dia do zero não exige (a conferência de semana já vale)."""
        if self.rota or not (anterior or {}).get("blocos"):
            return []
        try:
            import visao_semana as vs
            dia = cp.data_do_plano(caminho, plano)
            pre = vs.pre_planos_do_clickup(h.OPER, vs.carregar_planos(h.OPER)).get(dia.isoformat()) or {}
            ja = {cp._chave_bloco(b) for b in (anterior.get("blocos") or []) + (pre.get("blocos") or []) + (pre.get("sem_hora") or [])}
            novas = [b.get("titulo") for b in plano.get("blocos") or [] if cp._chave_bloco(b) not in ja]
        except Exception as erro:
            print("  Exigência do roteador falhou:", erro)
            return []
        if not novas:
            return []
        return [f"Entrou neste dia o que não estava nele ({'; '.join(map(str, novas[:3]))}). Antes de gravar, rode o roteador da agenda "
                "(powershell -ExecutionPolicy Bypass -File onde_cabe.ps1 -Minutos N -Tipo pesado|design|leve -Prazo AAAA-MM-DD -Frente X -Titulo \"...\", na pasta operacional) "
                "e siga o nível e o horário que ele indicar, ou diga a ela por que não."]

    def _conferir_semana(self, plano, caminho, anterior, feitos):
        """O plano de um dia não pode quebrar os outros: tarefa não some, prazo final vale, nobre é do importante (conferencia_plano.conferir_semana)."""
        try:
            import visao_semana as vs
            dia = cp.data_do_plano(caminho, plano)
            outros = vs.planos_da_semana(h.OPER)  # inclui o pré-plano do ClickUp nos dias sem plano gravado
            resumo = _ler_json(os.path.join(h.OPER, "resumo_clickup.json")) or {}
            pendentes = {t.get("id") for t in resumo.get("tarefas") or []} if resumo.get("tarefas") is not None else None
            return cp.conferir_semana(plano, dia, anterior, outros, pendentes, feitos, _pasta_memoria())
        except Exception as erro:  # a conferência nunca pode impedir o guardião de gravar por um defeito dela
            print("  Conferência de semana falhou:", erro)
            return []

    def turno(self, mensagem):
        """Manda a fala e devolve o que acontece, na ordem: ('texto', pedaço), ('ferramenta', dados), ('permissao', pedido) e, no fim, ('fim', evento).
        Quem recebe um pedido de permissão precisa chamar decidir(pedido, 'sim' | 'sempre' | 'nao', mensagem)."""
        if not self.viva():
            raise RuntimeError("a sessão do Claude Code fechou")
        self._esperar_fecho_da_interrupcao()
        if self.gravou_plano:  # o plano mudou no turno anterior: refazer exige ler a agenda de novo
            self.lidas.clear()
            self.rota = False
            self.gravou_plano = False
        self.em_turno = True
        self.usado_em = time.time()
        try:
            try:
                self._manda({"type": "user", "message": {"role": "user", "content": mensagem}, "parent_tool_use_id": None, "session_id": self.conversa})
            except (OSError, ValueError):
                raise RuntimeError("a sessão do Claude Code fechou") from None
            _atualizar(self.conversa, iniciada=True)  # a partir daqui a sessão existe no Claude Code: da próxima vez é retomada, não criada
            while True:
                try:
                    ev = self.fila.get(timeout=PRAZO_SILENCIO)
                except queue.Empty:
                    raise RuntimeError("a sessão do Claude Code parou de responder") from None
                tipo = ev.get("type")
                if tipo == "_fim":
                    raise RuntimeError("a sessão do Claude Code fechou")
                if tipo == "_permissao":
                    yield "permissao", ev["pedido"]
                elif tipo == "result":
                    if self.descartar:  # este é o fecho de uma interrupção (a pessoa fechou a janela): chega como erro, mas não é um erro de verdade
                        ev["_interrompido"] = True
                    self.descartar = False  # e ele acabou de ser consumido aqui: o turno seguinte não precisa esperar por ele
                    if self.resultados_atrasados > 0:  # fecho de um turno anterior que chegou só agora
                        self._fechar_turno(ev)
                        continue
                    self._fechar_turno(ev, contar=False)
                    yield "fim", ev
                    return
                elif tipo == "stream_event" and not ev.get("parent_tool_use_id"):
                    e = ev.get("event") or {}
                    if e.get("type") == "content_block_delta" and (e.get("delta") or {}).get("type") == "text_delta":
                        yield "texto", e["delta"].get("text", "")
                    elif e.get("type") == "message_delta" and (e.get("delta") or {}).get("stop_reason") in ("end_turn", "stop_sequence", "max_tokens", "refusal"):
                        # a resposta acabou de ser escrita: a conversa segue já, e o fecho (uso e custo) é lido quando chegar
                        self.resultados_atrasados += 1
                        yield "fim", None
                        return
                elif tipo == "assistant":
                    for bloco in (ev.get("message") or {}).get("content") or []:
                        if bloco.get("type") == "tool_use":
                            a = atividade(str(bloco.get("name") or ""), bloco.get("input"))
                            if a:
                                yield "ferramenta", {"fase": "inicio", "id": bloco.get("id"), "tipo": a[0], "rotulo": a[1], "dentro": bool(ev.get("parent_tool_use_id"))}
                elif tipo == "user":
                    conteudo = (ev.get("message") or {}).get("content")
                    for bloco in conteudo if isinstance(conteudo, list) else []:
                        if isinstance(bloco, dict) and bloco.get("type") == "tool_result":
                            yield "ferramenta", {"fase": "fim", "id": bloco.get("tool_use_id"), "erro": bool(bloco.get("is_error"))}
        finally:
            self.em_turno = False
            self.usado_em = time.time()

    def _esperar_fecho_da_interrupcao(self):
        """Depois de uma interrupção o Claude Code manda o fecho do turno interrompido. Ele precisa chegar (e ser descartado) antes da fala
        seguinte, senão seria lido como o fim dela. Normalmente leva milésimos; se não vier em 3 s, segue assim mesmo."""
        fim = time.time() + 3
        while self.descartar and time.time() < fim:
            try:
                ev = self.fila.get(timeout=0.1)  # com o turno ainda marcado como aberto, o fecho cai aqui em vez de em _fora_de_turno
            except queue.Empty:
                continue
            if ev.get("type") == "result":
                self.descartar = False
                self._fechar_turno(ev, contar=False)
            elif ev.get("type") == "_fim":
                self.fila.put(ev)
                break
        self.descartar = False
        guardados = []
        while True:  # o que sobrou do turno antigo na fila
            try:
                ev = self.fila.get_nowait()
            except queue.Empty:
                break
            if ev.get("type") == "_fim":
                guardados.append(ev)
        for ev in guardados:
            self.fila.put(ev)

    def _fechar_turno(self, ev, contar=True):
        if contar:
            self.resultados_atrasados = max(0, self.resultados_atrasados - 1)
        total = float(ev.get("total_cost_usd") or 0)
        ev["_custo_do_turno"] = max(0.0, total - self.custo)  # o total vem acumulado desde que o processo abriu
        self.custo = max(self.custo, total)
        _atualizar(self.conversa, iniciada=True, **({"contexto": self.contexto} if self.contexto else {}))
        for f in list(AO_FECHAR_TURNO):
            try:
                f(self, ev)
            except Exception:
                pass

    def fechar(self):
        try:
            self.proc.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            self.proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            self.proc.kill()


AO_FECHAR_TURNO = []  # funções chamadas com (processo, evento result) a cada turno fechado: o guardiao_voz registra o uso em logs\modelos.jsonl
_proc = None
_vigia = None


def interromper():
    """A pessoa fechou a janela no meio da resposta: o turno em andamento para."""
    p = _proc
    if p and p.viva() and p.em_turno:
        p.interromper()


def decidir(pedido, decisao, mensagem=""):
    pedido["decisao"] = (decisao, mensagem)
    pedido["espera"].set()


def _fechar_processo():
    global _proc
    with _trava:
        p, _proc = _proc, None
    if p:
        p.fechar()


def _vigiar():
    while True:
        time.sleep(30)
        p = _proc
        if p and p.viva() and not p.em_turno:
            cfg = configuracao()
            # Com a janela do painel aberta a sessão fica de pé até a conversa vencer (nova_conversa_apos_horas): assim a primeira fala depois de
            # um intervalo não paga a partida do Claude Code e dos conectores de novo (uns 20 s). Sem janela, fecha logo (fecha_apos_min).
            limite = max(cfg["ociosa"], cfg["nova_apos"]) if bus.assinantes else cfg["ociosa"]
            if cfg["ociosa"] > 0 and time.time() - p.usado_em > limite:
                _fechar_processo()  # a conversa continua guardada: a próxima fala reabre o processo no mesmo ponto


def processo(arquivo_prompt):
    """O processo da conversa atual, aberto se preciso. Trocou de conversa ou o processo caiu: abre outro."""
    global _proc, _vigia
    with _trava:
        c = atual()
        if _proc and _proc.viva() and _proc.conversa == c["id"]:
            return _proc
        antigo, _proc = _proc, None
    if antigo:
        antigo.fechar()
    with _trava:
        _proc = Processo(c, arquivo_prompt)
        if _vigia is None:
            _vigia = threading.Thread(target=_vigiar, daemon=True)
            _vigia.start()
        return _proc


def preparar(arquivo_prompt):
    """Deixa o processo aberto antes da primeira fala (ao abrir o app), para a conversa começar sem a espera da partida."""
    try:
        p = processo(arquivo_prompt)
        p.pronta.wait(60)
        avisar_tela()
        p.aquecer()
    except (OSError, ValueError):
        pass


def turno(mensagem, arquivo_prompt):
    """Um turno na conversa atual. Se a conversa guardada não puder ser retomada, o turno acontece numa conversa nova."""
    p = processo(arquivo_prompt)
    p.pronta.wait(60)
    time.sleep(0.05)
    if not p.viva():  # a sessão guardada não existe mais no Claude Code (pasta trocada, histórico apagado): segue numa nova
        _fechar_processo()
        nova()
        avisar_tela(troca=True)
        p = processo(arquivo_prompt)
        p.pronta.wait(60)
        if not p.viva():
            raise RuntimeError("o Claude Code não abriu")
    yield from p.turno(mensagem)


def trocar(cid=None):
    """Conversa nova (sem id) ou volta a uma anterior. O processo da conversa antiga é fechado; o da nova abre na próxima fala."""
    c = abrir(cid) if cid else nova()
    if c:
        _fechar_processo()
        avisar_tela(troca=True)
    return c


def encerrar():
    _fechar_processo()
