"""A IA revisa o rascunho do motor da agenda e devolve INSTRUÇÕES, nunca horário (docs/PRD-motor-agenda.md, Etapa 2).

Uma chamada só, sem ferramentas e sem ler arquivo: tudo que ela precisa vai no prompt, em forma compacta. O motor aplica as instruções e refaz a conta.
Instruções aceitas (JSON, chave "instrucoes"):
  {"acao":"estimar","id":ID,"minutos":N}
  {"acao":"janela","id":ID,"preferir":"manha|tarde|design|leve"}
  {"acao":"prioridade","id":ID,"nivel":1-4}                (1 = primeiro)
  {"acao":"desdobrar","id":ID_ou_titulo,"subtarefas":[{"titulo":..,"minutos":N,"tipo":"pesado|design|leve","dias_antes":N}]}
  {"acao":"perguntar","texto":".."}   (só estender x renegociar, ou decisão de campanha que só ela toma)
  {"acao":"explicar","texto":".."}    (o porquê do plano, em até 3 frases, na voz do guardião)
Instrução inválida é ignorada e registrada."""
import json
import os
import re
import subprocess
import sys
import time
from datetime import date

OPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPO = 240
ACOES = {"estimar", "janela", "prioridade", "desdobrar", "perguntar", "explicar", "feito", "tirar", "imprevisto", "limite", "cancelar", "hoje", "adiar",
         "manter"}
SO_TITULO = {"feito", "tirar", "imprevisto", "limite", "cancelar", "hoje", "adiar", "manter"}

REGRAS = """REGRAS DA AGENDA (o código já aplica as de horário; você só julga):
- Quem decide a agenda é o guardião. Pergunte à pessoa SÓ quando for impossível: até 2h de hora extra a pergunta é "você prefere estender o dia ou renegociar o prazo?"; acima disso, renegociar o prazo com quem combinou. Nunca pergunte onde colocar algo.
- Stories: meta de 45 min por dia, em blocos de até 15 min; só o dia de captação tem pouco stories. Consumo antes das copies, um por dia. Copies juntas, depois designs. Copy antes do design do mesmo post.
- Tarefa sem tempo medido (lista JULGAR): estime pelo título e pelo perfil. Entrega ou marco de campanha sem tarefa: desdobre em subtarefas com tempo e quantos dias antes do prazo cada uma termina.
- Subtarefa de outra pessoa leva "dono" com o nome dela SÓ quando a tarefa, a nota ou a pessoa disseram quem faz. Nunca atribua dono por dedução:
  na dúvida, sem dono (fica com a pessoa) e, se importar, pergunte.
- Use "prioridade" quando a ordem por prazo não reflete o que importa (campanha de venda perto do fim vem antes de tarefa interna).
- Não invente fato, número nem tarefa que não decorra do que está aqui.
- "explicar" é FALADO À PESSOA: 1 ou 2 frases curtas, na primeira pessoa do guardião ("Coloquei a thumb antes da live", "Deixei o design para segunda"),
  sem repetir horários (a lista na tela já mostra) e NUNCA com instruções ao sistema ou ao código ("preserve", "registre", "use as tarefas...").
- "perguntar": no máximo UMA, e só "estender o dia ou renegociar o prazo" ou decisão de campanha que só ela toma. Não pergunte o que ela já fez:
  se ela não disse, não marque como feito."""


def _perfil(memoria):
    try:
        with open(os.path.join(memoria, "perfil.md"), encoding="utf-8-sig") as f:
            return re.sub(r"\n{3,}", "\n\n", f.read())[:1800]
    except (OSError, TypeError):
        return ""


PEDIDO = """PEDIDO DA PESSOA (traduza em instruções; não monte horário, o código monta):
- o que ela diz que já fez: {"acao":"feito","titulo":"..","minutos":N}
- o que ela mandou tirar DESTE DIA (a tarefa continua existindo e vai para outro dia): {"acao":"tirar","titulo":".."}
- o que ela cancelou de vez ("cancela", "não vou mais fazer", "não faz mais sentido"): {"acao":"cancelar","titulo":".."} (a tarefa é fechada no ClickUp ao aprovar)
- compromisso, refeição ou imprevisto com horário que ela disse (ex.: almoço às 14h, reunião de emergência): {"acao":"imprevisto","titulo":"..","inicio":"HH:MM","fim":"HH:MM"}
- tarefa que ela disse que faz HOJE ("posso fazer hoje", "faço isso hoje", "quero ver isso hoje"): {"acao":"hoje","titulo":".."}, uma por tarefa.
  Num dia de folga (fim de semana) SÓ entra hoje o que vier com "hoje"; o resto vai para o próximo dia de trabalho sem pergunta.
- tarefa que ela quer em outro momento ou com outro prazo ("joga mais pra frente", "pronta antes do dia 27"): {"acao":"limite","titulo":"..","ate":"AAAA-MM-DD"}
  (o código acha o melhor dia até essa data; "mais pra frente" sem data: use a data da entrega ligada a ela, se houver, ou 7 dias depois de hoje)
- tarefa que ela adiou para DEPOIS de uma data ("adia", "vai pra semana depois do dia 31", "só a partir de segunda", "não sai semana que vem"):
  {"acao":"adiar","titulo":"..","a_partir":"AAAA-MM-DD"} com o PRIMEIRO dia de trabalho em que ela pode entrar (não use limite nesse caso).
  Adiou a copy de um post: adie também o design do mesmo post, com a mesma data. O adiamento fica guardado; ela não precisa repetir.
- resposta a "ainda vale fazer?" de tarefa atrasada dizendo que vale, sem data nem "hoje" ("vale", "não cancela", "mantém"): {"acao":"manter","titulo":".."}
Use o título como aparece no plano atual quando for o mesmo item."""


def montar_prompt(resultado, cfg, marcos=(), pedido=None, plano_hoje=None):
    linhas = [f"Hoje é {date.today():%d/%m/%Y}, agora são {time.strftime('%H:%M')}. Você é o guardião da agenda de "
              f"{((cfg.get('pessoa') or {}).get('nome')) or 'uma pessoa'}.", REGRAS, ""]
    trabalho = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
    dias = {trabalho[n] for n in ((cfg.get("rotina") or {}).get("dias_trabalho") or []) if n in trabalho} or {0, 1, 2, 3, 4}
    if date.today().weekday() not in dias:
        linhas += ["HOJE É DIA DE FOLGA (fora dos dias de trabalho). Nunca proponha estender hoje nem hora extra hoje. Só entra hoje o que ela pediu "
                   "para hoje (acao hoje); o resto vai para o próximo dia de trabalho.", ""]
    if pedido:
        linhas += [PEDIDO, f'Ela disse: "{pedido}"', ""]
        if plano_hoje:
            linhas.append("PLANO ATUAL DE HOJE (antes do pedido):")
            linhas += [f"  {b.get('inicio')}-{b.get('fim')} {str(b.get('titulo'))[:80]}" + (" (feito)" if b.get("status") == "feito" else "")
                       for b in (plano_hoje.get("fixos") or []) + (plano_hoje.get("blocos") or [])]
            linhas.append("")
    perfil = _perfil(((cfg.get("pastas") or {}).get("memoria")))
    if perfil:
        linhas += ["PERFIL (resumo):", perfil, ""]
    try:  # o que a calibragem já sabe da pessoa (medido, provável e confirmado), em poucas linhas
        import calibragem_motor as cm
        secao = cm.secao_do_plano(cm.atualizar_perfil(((cfg.get("pastas") or {}).get("operacional")) or OPER))
        if secao:
            linhas += [secao, ""]
    except Exception:
        pass
    linhas.append("RASCUNHO DO MOTOR (dias ainda não aprovados):")
    for iso, plano in resultado["dias"].items():
        linhas.append(f"{iso}:")
        linhas += [f"  {b.get('inicio')}-{b.get('fim')} {str(b.get('titulo'))[:80]}" + (f" [id {b['clickup_id']}]" if b.get("clickup_id") else "") for b in plano.get("blocos") or []]
    if resultado["julgar"]:
        linhas += ["", "JULGAR (tempo padrão, sem medição):"] + [f"- [id {j.get('id')}] {j['titulo']} ({j['minutos_padrao']} min padrão)" for j in resultado["julgar"]]
    if resultado["nao_coube"]:
        linhas += ["", "NÃO COUBE:"] + [f"- [id {n.get('id')}] {n['titulo']} ({n['minutos']} min, limite {n.get('limite')}): {n['pergunta']}" for n in resultado["nao_coube"]]
    if marcos:
        linhas += ["", "MARCOS DE CAMPANHA SEM TAREFA:"] + [f"- {m}" for m in marcos]
    linhas += ["", 'Responda SOMENTE com um JSON: {"instrucoes": [...]} no formato:',
               '{"acao":"estimar","id":ID,"minutos":N} | {"acao":"janela","id":ID,"preferir":"manha|tarde|design|leve"} | {"acao":"prioridade","id":ID,"nivel":1}'
               ' | {"acao":"desdobrar","id":ID_OU_TITULO,"subtarefas":[{"titulo":"..","minutos":N,"tipo":"pesado|design|leve","dias_antes":N,"dono":"nome, se não for a pessoa"}]}'
               ' | {"acao":"perguntar","texto":".."} | {"acao":"explicar","texto":".."}',
               "Sem markdown. Inclua sempre um explicar curto. Lista vazia se nada precisa de ajuste além do explicar."]
    return "\n".join(linhas)


def _provedor(oper):
    try:
        with open(os.path.join(oper, "voz", "preferencias.json"), encoding="utf-8-sig") as f:
            return (json.load(f) or {}).get("provedor_ia") or "claude"
    except (OSError, ValueError):
        return "claude"


def _registrar(oper, modelo, uso, ms):
    try:
        with open(os.path.join(oper, "logs", "modelos.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "modelo": modelo, "motivo": "revisor da agenda", "ms": ms,
                                "custo_usd": uso.get("custo_usd", 0), "entrada": uso.get("entrada", 0), "saida": uso.get("saida", 0)}) + "\n")
    except OSError:
        pass


def chamar(prompt, oper=OPER):
    """Texto da resposta. Uma chamada, sem ferramentas. Registra o uso em logs/modelos.jsonl."""
    t0 = time.time()
    if _provedor(oper) == "codex":
        import guardiao_codex
        texto, uso = guardiao_codex.executar_sem_arquivos(prompt, timeout=TEMPO)
        _registrar(oper, "codex", {"entrada": uso.get("input_tokens", 0), "saida": uso.get("output_tokens", 0)}, int((time.time() - t0) * 1000))
        return texto
    import guardiao_sessao
    base = guardiao_sessao.comando_do_claude()
    if not base:
        raise RuntimeError("Claude Code não encontrado")
    modelo = os.environ.get("GUARDIAO_MODELO") or "claude-sonnet-5-5"
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    r = subprocess.run([*base, "-p", "--model", modelo, "--max-turns", "1", "--output-format", "json"], input=prompt, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=oper, timeout=TEMPO, creationflags=getattr(guardiao_sessao, "FLAGS_CLAUDE", 0))
    ev = json.loads(r.stdout or "{}")
    u = ev.get("usage") or {}
    _registrar(oper, modelo, {"custo_usd": ev.get("total_cost_usd", 0), "entrada": (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                              + (u.get("cache_creation_input_tokens") or 0), "saida": u.get("output_tokens") or 0}, int((time.time() - t0) * 1000))
    return str(ev.get("result") or "")


def interpretar(texto):
    """Lista de instruções válidas (as inválidas saem, com aviso no stderr)."""
    t = str(texto or "").strip()
    m = re.search(r"\{.*\}", t, re.S)
    try:
        dados = json.loads(m.group(0) if m else t)
    except ValueError:
        print("(revisor_ia: resposta sem JSON)", file=sys.stderr)
        return []
    validas = []
    for i in dados.get("instrucoes") or [] if isinstance(dados, dict) else []:
        if not isinstance(i, dict) or i.get("acao") not in ACOES:
            print(f"(revisor_ia: instrução ignorada: {i})", file=sys.stderr)
            continue
        if i["acao"] in ("estimar", "janela", "prioridade", "desdobrar") and not i.get("id"):
            continue
        if i["acao"] in SO_TITULO and not i.get("titulo"):
            continue
        if i["acao"] == "limite" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(i.get("ate") or "")):
            continue
        if i["acao"] == "adiar" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(i.get("a_partir") or "")):
            continue
        if i["acao"] == "imprevisto" and not all(re.fullmatch(r"\d{1,2}:\d{2}", str(i.get(k) or "")) for k in ("inicio", "fim")):
            continue
        if i["acao"] == "estimar" and not (isinstance(i.get("minutos"), (int, float)) and 5 <= i["minutos"] <= 480):
            continue
        validas.append(i)
    return validas


def ajustes(instrucoes):
    """Instruções -> ajustes que o motor entende."""
    a = {"minutos": {}, "janela": {}, "prioridade": {}, "desdobrar": {}, "perguntas": [], "explicar": [], "feitos": [], "tirar": [], "imprevistos": [],
         "limites": {}}
    tipos = {"manha": "pesado", "nobre": "pesado", "tarde": "leve", "design": "design", "leve": "leve", "pesado": "pesado"}
    for i in instrucoes:
        acao, chave = i["acao"], str(i.get("id") or "")
        if acao == "estimar":
            a["minutos"][chave] = int(i["minutos"])
        elif acao == "janela" and i.get("preferir") in tipos:
            a["janela"][chave] = tipos[i["preferir"]]
        elif acao == "prioridade":
            a["prioridade"][chave] = int(i.get("nivel") or 4)
        elif acao == "desdobrar" and isinstance(i.get("subtarefas"), list):
            a["desdobrar"][chave] = [s for s in i["subtarefas"] if isinstance(s, dict) and s.get("titulo")][:8]
        elif acao == "perguntar" and i.get("texto"):
            a["perguntas"].append(str(i["texto"])[:300])
        elif acao == "explicar" and i.get("texto"):
            a["explicar"].append(str(i["texto"])[:500])
        elif acao == "feito":
            a["feitos"].append({"titulo": str(i["titulo"]), "minutos": int(i.get("minutos") or 0)})
        elif acao == "tirar":
            a["tirar"].append(str(i["titulo"]))
        elif acao == "cancelar":
            a.setdefault("cancelar", []).append(str(i["titulo"]))
        elif acao == "hoje":
            a.setdefault("hoje", []).append(str(i["titulo"]))
        elif acao == "limite":
            a["limites"][str(i["titulo"])] = i["ate"]
        elif acao == "adiar":
            a.setdefault("adiar", {})[str(i["titulo"])] = i["a_partir"]
        elif acao == "manter":
            a.setdefault("manter", []).append(str(i["titulo"]))
        elif acao == "imprevisto":
            a["imprevistos"].append({"titulo": str(i["titulo"])[:80], "inicio": i["inicio"].zfill(5), "fim": i["fim"].zfill(5)})
    return a
