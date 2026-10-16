"""Adaptador local do Codex CLI para o painel do Guardião.

O Codex usa a mesma pasta operacional, memória e SKILL.md do Claude. Nenhuma
credencial é lida pelo Guardião; o login é gerenciado pelo próprio Codex CLI.
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time


SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MODELO_PADRAO = "gpt-6-sol"
ESFORCO_PADRAO = "medium"
AVISO_SEM_CODEX = ("Não achei o Codex CLI neste computador. Instale o Codex, "
                   "rode 'codex login' uma vez e escolha Codex de novo no painel.")
_estado_em_cache = {"ate": 0, "ok": False}
INSTRUCAO_PLANO = """
MODO DE ENTREGA DO CODEX (obrigatório): você só pode LER arquivos e executar comandos de leitura.
Não tente gravar, editar ou apagar arquivos com ferramentas. Faça as contas do plano e devolva
SOMENTE um objeto JSON válido, sem bloco Markdown, com as chaves "fala" (resumo para a pessoa)
e "planos" (lista). Cada item de "planos" tem "arquivo" (somente "plano_do_dia.json" ou
"planos/plano_AAAA-MM-DD.json") e "conteudo" (o objeto JSON inteiro do plano, não uma string).
O aplicativo confere e grava apenas esses planos depois da sua resposta. Inclua todos os dias
que precisar alterar na mesma resposta. Num pedido para montar ou refazer o plano, falta de
tempo NUNCA justifica "planos": []. Monte uma proposta viável nesta ordem: (1) tire do dia
o que pode esperar e reagende em outro dia; (2) simplifique e encurte uma tarefa mantendo
uma entrega útil; (3) se ainda faltar tempo, proponha hora extra explícita, sujeita à
aprovação da pessoa. Preserve compromissos fixos e o que ela já concluiu. Explique no
"aviso" o que saiu, o que foi simplificado e qualquer hora extra proposta. Se a caixinha
cair para 15 minutos porque o dia ficou apertado, use "modo_dia": "apertado" e explique
o aperto no "aviso". Entregue um plano mesmo que nem todas as tarefas caibam hoje.
Ao mover uma tarefa entre dias, não a deixe em dois planos: inclua o dia de origem sem o bloco
e o dia de destino com o bloco. Consulte os arquivos necessários em lotes e evite relê-los.
"""


def comando():
    """Encontra o executável mesmo quando só a extensão do VS Code está instalada."""
    for candidato in (
        os.environ.get("GUARDIAO_CODEX", "").strip().strip('"'),
        shutil.which("codex"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "OpenAI", "Codex", "bin", "codex.exe"),
        *sorted(glob.glob(os.path.join(os.path.expanduser("~"), ".vscode", "extensions",
                                      "openai.chatgpt-*-win32-x64", "bin", "windows-x86_64", "codex.exe")),
                reverse=True),
    ):
        if candidato and os.path.isfile(candidato):
            # Os atalhos .cmd do npm não são abertos por CreateProcess/Popen.
            if candidato.lower().endswith((".cmd", ".bat")):
                exe = os.path.join(os.path.dirname(candidato), "node_modules", "@openai", "codex",
                                   "bin", "codex.exe")
                if os.path.isfile(exe):
                    return [exe]
                continue
            return [candidato]
    return []


def estado():
    cmd = comando()
    if not cmd:
        return {"ok": False, "autenticado": False, "versao": "", "erro": AVISO_SEM_CODEX}
    try:
        ver = subprocess.run(cmd + ["--version"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=15, creationflags=SEM_JANELA)
        login = subprocess.run(cmd + ["login", "status"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=15, creationflags=SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired) as erro:
        return {"ok": False, "autenticado": False, "versao": "", "erro": str(erro)}
    linhas_versao = (ver.stdout or ver.stderr).strip().splitlines()
    return {"ok": ver.returncode == 0, "autenticado": login.returncode == 0,
            "versao": linhas_versao[0] if linhas_versao else "",
            "erro": "" if login.returncode == 0 else "Codex instalado; falta entrar na conta com 'codex login'."}


def disponivel():
    """Estado leve para o painel; confere o login a cada 30 segundos."""
    if time.monotonic() >= _estado_em_cache["ate"]:
        atual = estado()
        _estado_em_cache.update(ate=time.monotonic() + 30,
                               ok=atual["ok"] and atual["autenticado"])
    return _estado_em_cache["ok"]


def _gravar_atomico(caminho, dados):
    pasta = os.path.dirname(caminho)
    os.makedirs(pasta, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix=".guardiao_codex_", dir=pasta)
    try:
        with os.fdopen(fd, "wb") as arquivo:
            arquivo.write(dados)
        os.replace(temporario, caminho)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)


ROTINA = re.compile(r"consumo|recarga|stor(y|ies)|caixinha|almo[cç]o|pausa|whatsapp|respiro|descanso", re.I)


def _chave(bloco):
    """Identidade de uma tarefa entre dias: o id do ClickUp; sem id, o título, menos para bloco de rotina, que se repete todo dia
    (caso real 16/10: "Consumo" e "Stories (parte 1)" em dois dias derrubaram a proposta como "mesma tarefa em dois dias")."""
    cid = str(bloco.get("clickup_id") or "").strip().casefold()
    titulo = str(bloco.get("titulo") or "").strip()
    if cid:
        return cid, True
    return ("" if ROTINA.search(titulo) else titulo.casefold()), False


def _completar_origens(planos, operacional):
    """Inclui o dia futuro de origem quando a resposta moveu um bloco e omitiu esse dia."""
    futuros = glob.glob(os.path.join(operacional, "planos", "plano_????-??-??.json"))
    hoje = datetime.date.today().isoformat()
    while True:
        propostos = {str(item.get("arquivo") or "").replace("\\", "/") for item in planos if isinstance(item, dict)}
        destinos = {}
        for item in planos:
            if not isinstance(item, dict) or not isinstance(item.get("conteudo"), dict) or not isinstance(item["conteudo"].get("blocos"), list):
                raise RuntimeError("O Codex entregou um plano incompleto; nada foi alterado.")
            for bloco in item["conteudo"]["blocos"]:
                if not isinstance(bloco, dict):
                    raise RuntimeError("O Codex entregou um bloco inválido; nada foi alterado.")
                chave, do_clickup = _chave(bloco)
                if not chave:
                    continue
                rel = str(item["arquivo"]).replace("\\", "/")
                if chave in destinos and destinos[chave] != rel:
                    if do_clickup:
                        raise RuntimeError(f"A tarefa \"{bloco.get('titulo')}\" aparece em dois dias da proposta; deixe-a em um só.")
                    continue
                destinos[chave] = rel
        novos = 0
        for caminho in futuros:
            rel = "planos/" + os.path.basename(caminho)
            if rel in propostos or rel[-15:-5] <= hoje:
                continue
            try:
                with open(caminho, encoding="utf-8-sig") as arquivo:
                    origem = json.load(arquivo)
            except (OSError, ValueError):
                continue
            if not isinstance(origem, dict) or not isinstance(origem.get("blocos"), list):
                continue
            manter = []
            for bloco in origem["blocos"]:
                if not isinstance(bloco, dict):
                    manter.append(bloco)
                    continue
                chave = _chave(bloco)[0]
                if chave and chave in destinos and destinos[chave] != rel and bloco.get("status") not in ("feito", "concluido"):
                    continue
                manter.append(bloco)
            if len(manter) != len(origem["blocos"]):
                origem["blocos"] = manter
                planos.append({"arquivo": rel, "conteudo": origem})
                propostos.add(rel)
                novos += 1
        if not novos:
            return planos
        if len(planos) > 8:
            raise RuntimeError("A proposta afeta dias demais de uma vez; nada foi alterado.")


def _aplicar_planos(resposta, operacional, progresso=None, exigir_plano=False):
    """O app grava somente planos válidos; o processo do modelo permanece sem escrita."""
    if progresso:
        progresso("Conferindo a proposta")
    texto = resposta.strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.I)
    try:
        pacote = json.loads(texto)
    except ValueError as erro:
        raise RuntimeError("O Codex não entregou o plano em JSON válido; nada foi alterado.") from erro
    if not isinstance(pacote, dict) or not isinstance(pacote.get("fala"), str) or not isinstance(pacote.get("planos"), list):
        raise RuntimeError("O Codex não entregou o formato de plano esperado; nada foi alterado.")
    planos = pacote["planos"]
    if exigir_plano and not planos:
        raise RuntimeError("O pedido exige um plano. Reorganize as prioridades, simplifique uma tarefa ou proponha hora extra; não devolva uma recusa.")
    if len(planos) > 8:
        raise RuntimeError("O Codex entregou dias demais de uma vez; nada foi alterado.")
    if planos:
        planos = _completar_origens(planos, operacional)
    if len(planos) > 8:
        raise RuntimeError("A proposta afeta dias demais de uma vez; nada foi alterado.")
    import conferencia_plano as cp
    preparados = []
    problemas_planos = []
    vistos = set()
    for item in planos:
        if not isinstance(item, dict):
            raise RuntimeError("Um plano do Codex veio sem arquivo ou conteúdo; nada foi alterado.")
        rel = str(item.get("arquivo") or "").replace("\\", "/")
        if rel != "plano_do_dia.json" and not re.fullmatch(r"planos/plano_\d{4}-\d{2}-\d{2}\.json", rel):
            raise RuntimeError("O Codex tentou alterar um arquivo fora dos planos; nada foi alterado.")
        if rel in vistos:
            raise RuntimeError("O Codex repetiu um arquivo de plano; nada foi alterado.")
        vistos.add(rel)
        caminho = os.path.join(operacional, *rel.split("/"))
        novo = item.get("conteudo")
        if not isinstance(novo, dict) or not isinstance(novo.get("blocos"), list):
            raise RuntimeError("O Codex entregou um plano incompleto; nada foi alterado.")
        if rel.startswith("planos/") and novo.get("data") != rel[-15:-5]:
            raise RuntimeError("A data do plano não combina com o nome do arquivo; nada foi alterado.")
        novo["status"] = "sugerido"
        novo.pop("aprovado_em", None)
        antes = None
        if os.path.exists(caminho):
            with open(caminho, "rb") as arquivo:
                antes = arquivo.read()
        anterior = None
        if antes:
            try:
                anterior = json.loads(antes.decode("utf-8-sig"))
            except ValueError:
                pass
        # agenda_impoe que falta o código completa depois de gravar (plano_base.consertar); aviso não barra
        problemas = cp.separar([p for p in cp.conferir(novo, anterior) if "agenda_impoe" not in p])[0]
        if problemas:
            problemas_planos.extend(f"{rel}: {problema}" for problema in problemas)
        dados = json.dumps(novo, ensure_ascii=False, indent=2).encode("utf-8")
        preparados.append((caminho, dados, antes))
    if problemas_planos:
        raise RuntimeError("O plano do Codex não passou na conferência: " + " | ".join(problemas_planos[:12]))
    gravados = []
    try:
        if preparados and progresso:
            progresso("Salvando o plano")
        for caminho, dados, antes in preparados:
            _gravar_atomico(caminho, dados)
            gravados.append((caminho, antes))
        if preparados:
            import plano_base
            # preparar_arquivo conserta o que é mecânico (stories, consumo repetido, preparo da live), anota os avisos no plano e devolve só o grave
            preparar = getattr(plano_base, "preparar_arquivo", None)
            problemas_planos = []
            for caminho, _, _ in preparados:
                problemas = preparar(caminho, oper=operacional)[0] if preparar else plano_base.conferir_arquivo(caminho, oper=operacional)
                problemas_planos.extend(f"{os.path.relpath(caminho, operacional)}: {problema}" for problema in problemas)
            if problemas_planos:
                raise RuntimeError("O plano do Codex não passou na conferência: " + " | ".join(problemas_planos[:12]))
    except Exception:
        for caminho, antes in reversed(gravados):
            if antes is None:
                os.remove(caminho)
            else:
                _gravar_atomico(caminho, antes)
        raise
    fala = pacote["fala"].strip()
    return fala if planos or "não alterei o plano" in fala.casefold()[:60] else "Não alterei o plano. " + fala


def executar(pedido, operacional, memoria="", pode_escrever=False, timeout=600, progresso=None,
            exigir_plano=False, _tentativa=0, _pedido_original=None, _sessao_id=None):
    """Executa um turno e devolve (resposta final, uso). Falha sem trocar de provedor."""
    _pedido_original = _pedido_original or pedido
    base = comando()
    if not base:
        raise RuntimeError(AVISO_SEM_CODEX)
    situacao = estado()
    if not situacao["ok"] or not situacao["autenticado"]:
        raise RuntimeError(situacao["erro"] or "Codex indisponível. Confira 'codex login status'.")
    if _sessao_id:
        # A correção continua a pesquisa do turno anterior, sem abrir outra sessão.
        cmd = base + ["exec", "resume", "--json", "--skip-git-repo-check",
                      "--config", "sandbox_mode=read-only"]
    else:
        cmd = base + ["exec", "--json", "--skip-git-repo-check", "--cd", operacional,
                      "--sandbox", "read-only"]
    modelo = os.environ.get("GUARDIAO_MODELO_CODEX", "").strip() or MODELO_PADRAO
    esforco = os.environ.get("GUARDIAO_ESFORCO_CODEX", "").strip().lower() or ESFORCO_PADRAO
    if esforco not in ("none", "low", "medium", "high", "xhigh", "max"):
        raise RuntimeError("GUARDIAO_ESFORCO_CODEX inválido. Use none, low, medium, high, xhigh ou max.")
    cmd += ["--model", modelo, "--config", f"model_reasoning_effort={esforco}"]
    cmd += ([_sessao_id, "-"] if _sessao_id else ["-"])
    if pode_escrever:
        pedido += "\n\n" + INSTRUCAO_PLANO
    resposta, uso, erros = "", {}, []
    sessao_id = _sessao_id
    ultimo_status, ultimo_aviso = "", 0.0

    def avisar(rotulo):
        nonlocal ultimo_status, ultimo_aviso
        agora = time.monotonic()
        if progresso and (rotulo != ultimo_status or agora - ultimo_aviso >= 15):
            ultimo_status, ultimo_aviso = rotulo, agora
            try:
                progresso(rotulo)
            except Exception:
                pass  # falha visual nunca interrompe o pedido

    avisar("Iniciando o Codex")
    expirou = threading.Event()
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as stderr:
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                                    text=True, encoding="utf-8", errors="replace", cwd=operacional,
                                    creationflags=SEM_JANELA)
        except OSError as erro:
            raise RuntimeError("Não consegui iniciar o Codex: " + str(erro)) from erro
        try:  # o Esc e o botão Parar do painel encerram o Codex (controle_fala.cancelar_fundo); fora do painel não existe
            import controle_fala
            controle_fala.registrar_fundo(proc)
        except Exception:
            controle_fala = None
        relogio = threading.Timer(timeout, lambda: (expirou.set(), proc.kill()))
        relogio.daemon = True
        relogio.start()
        try:
            try:
                proc.stdin.write(pedido)
                proc.stdin.close()
            except BrokenPipeError:
                pass  # o processo saiu cedo; a mensagem de erro virá pelo fluxo de eventos/stderr
            for linha in proc.stdout:
                try:
                    evento = json.loads(linha)
                except ValueError:
                    continue
                tipo = evento.get("type")
                item = evento.get("item") or {}
                if tipo == "thread.started":
                    sessao_id = evento.get("thread_id") or sessao_id
                elif tipo == "turn.started":
                    avisar("Lendo o pedido")
                elif tipo == "item.started":
                    classe = item.get("type")
                    if classe == "command_execution":
                        avisar("Consultando arquivos")
                    elif classe in ("mcp_tool_call", "web_search"):
                        avisar("Consultando informações")
                    elif classe == "agent_message":
                        avisar("Preparando a resposta")
                    elif classe == "reasoning":
                        avisar("Organizando informações")
                elif tipo == "item.completed" and item.get("type") == "agent_message":
                    resposta = str(item.get("text") or resposta)
                    avisar("Preparando a resposta")
                elif tipo == "turn.completed":
                    uso = evento.get("usage") or {}
                elif tipo in ("turn.failed", "error"):
                    erro = evento.get("error") or evento.get("message") or evento
                    erros.append(str(erro))
            proc.wait()
        finally:
            relogio.cancel()
            if controle_fala:
                controle_fala.esquecer_fundo(proc)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if proc.stdout:
                proc.stdout.close()
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        stderr.seek(0)
        detalhe_stderr = stderr.read().strip()
    if expirou.is_set():
        raise RuntimeError("O Codex demorou demais para responder.")
    if proc.returncode and controle_fala and controle_fala.FUNDO_CANCELADO.is_set():
        raise InterruptedError("cancelado pelo botão Parar ou pelo Esc")
    if proc.returncode or not resposta:
        detalhe = (erros[-1] if erros else detalhe_stderr or "sem resposta")[:400]
        if any(marcador in detalhe.lower() for marcador in ("usage limit", "rate limit", "insufficient_quota")):
            raise RuntimeError("O Codex atingiu o limite de uso da conta. Escolha Claude no painel ou tente novamente após a renovação do limite.")
        raise RuntimeError("O Codex não concluiu: " + detalhe)
    if pode_escrever:
        try:
            resposta = _aplicar_planos(resposta, operacional, progresso=avisar, exigir_plano=exigir_plano)
        except RuntimeError as erro:
            if _tentativa >= 2:
                raise
            numero = _tentativa + 2
            avisar(f"Corrigindo o plano ({numero} de 3)")
            instrucao = (
                "Sua proposta anterior não passou na conferência do aplicativo. Corrija e devolva "
                "novamente o JSON completo, incluindo todos os dias alterados. Não repita a recusa.\n\n"
                "ORDEM DE DECISÃO OBRIGATÓRIA: primeiro reagende o que não precisa ser feito hoje; "
                "depois simplifique e encurte uma tarefa; por último, proponha hora extra sujeita ao "
                "ok da pessoa. Preserve o que já foi feito e os compromissos fixos.\n\n"
                f"ERRO DA CONFERÊNCIA: {erro}"
            )
            correcao = (instrucao if sessao_id else
                        instrucao + f"\n\nPEDIDO ORIGINAL:\n{_pedido_original}\n\nPROPOSTA ANTERIOR:\n{resposta}")
            return executar(correcao, operacional, memoria, pode_escrever=True,
                            timeout=min(timeout, 420), progresso=progresso,
                            exigir_plano=exigir_plano, _tentativa=_tentativa + 1,
                            _pedido_original=_pedido_original, _sessao_id=sessao_id)
    uso = dict(uso, sessao_id=sessao_id)  # quem chamou pode retomar a mesma sessão numa correção posterior
    return resposta, uso


def executar_sem_arquivos(pedido, timeout=120, progresso=None):
    """Turno sem leitura: o Codex roda numa pasta temporária vazia, porque tudo que ele precisa já vai no pedido.
    Na pasta do guardião ele carregava skill e arquivos e chegava a 200 mil tokens por chamada (medido em 16/10)."""
    with tempfile.TemporaryDirectory(prefix="guardiao_codex_") as vazia:
        return executar(pedido + "\n\nNão execute comandos nem leia arquivos: tudo de que você precisa está acima.", vazia,
                        timeout=timeout, progresso=progresso)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--operacional", required=True)
    p.add_argument("--memoria", default="")
    p.add_argument("--escrever", action="store_true")
    p.add_argument("--sessao-arquivo", default="")  # gerar_plano.ps1: a correção retoma a sessão da primeira chamada, sem reler tudo
    args = p.parse_args()
    with open(args.prompt_file, encoding="utf-8-sig") as arquivo:
        pedido = arquivo.read()
    sessao = ""
    if args.sessao_arquivo and os.path.exists(args.sessao_arquivo):
        with open(args.sessao_arquivo, encoding="utf-8") as arquivo:
            sessao = arquivo.read().strip()
    try:
        resposta, uso = executar(pedido, args.operacional, args.memoria, args.escrever, _sessao_id=sessao or None)
        if args.sessao_arquivo and uso.get("sessao_id"):
            with open(args.sessao_arquivo, "w", encoding="utf-8") as arquivo:
                arquivo.write(uso["sessao_id"])
        print(resposta)
    except RuntimeError as erro:
        print(str(erro), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
