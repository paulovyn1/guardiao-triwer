# Versão do guardião e aviso de versão nova.
# O arquivo VERSION da pasta operacional diz qual versão está instalada (skill, scripts, programa de voz e painel andam juntos).
# Uma vez por dia, na primeira abertura do painel, este programa olha o repositório e compara. Havendo versão nova, o painel
# mostra um botão discreto; ao clicar, quem atualiza é o atualizar.ps1 (que não toca em memória, planos, registros nem config.json).
# Nada aqui chama o Claude: é leitura de arquivo, git e, para repositório público, um pedido simples ao GitHub.
import json
import os
import re
import subprocess
import threading
import time

import requests

import hud_servidor as h

BASE = os.path.dirname(os.path.abspath(__file__))
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NOVO_GRUPO = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
INICIO = time.time()
TRAVA = threading.Lock()
ATUALIZANDO = False
COMANDO_ATUALIZAR = None  # os testes trocam por uma função, para nada ser instalado de verdade


def versao_instalada():
    try:
        with open(os.path.join(h.OPER, "VERSION"), encoding="utf-8-sig") as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


CARREGADA = versao_instalada()  # a versão do código que este processo carregou ao ligar


def _num(versao):
    partes = [int(x) for x in re.findall(r"\d+", str(versao or ""))[:3]]
    return tuple(partes + [0] * (3 - len(partes)))


def _arq(nome):
    pasta = os.path.join(h.OPER, "logs")
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, nome)


def _estado():
    return h._ler_json(_arq("atualizacao.json")) or {}


def _salvar(estado):
    with open(_arq("atualizacao.json"), "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def origem():
    """De onde vêm as atualizações: campo "atualizacao" do config.json ({"origem": pasta do clone ou endereço do GitHub, "ramo", "pasta"}).
    Sem o campo, vale o marcador .repo-path da skill instalada (o mesmo das outras skills internas)."""
    cfg = h._config().get("atualizacao") or {}
    onde = str(cfg.get("origem") or "").strip()
    if not onde:
        marcador = os.path.join(h.OPER, ".claude", "skills", "guardiao-triwer", ".repo-path")
        try:
            with open(marcador, encoding="utf-8-sig") as f:
                onde = f.read().strip()
        except OSError:
            onde = ""
    pasta = cfg.get("pasta")
    return {"origem": onde, "ramo": str(cfg.get("ramo") or "main"), "pasta": "guardiao-triwer" if pasta is None else str(pasta).strip("/\\"),
            "verificar": cfg.get("verificar", True) is not False}


def _git(pasta, *args, timeout=40):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")  # sem janela pedindo senha: se não tiver acesso, falha e pronto
    return subprocess.run(["git", "-C", pasta, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                          env=env, creationflags=SEM_JANELA)


def ler_remoto(o):
    """Devolve (versão publicada, texto do CHANGELOG, aviso). Aceita um clone local do repositório, um endereço público do GitHub ou uma pasta simples."""
    onde, ramo = o["origem"], o["ramo"]
    prefixo = (o["pasta"] + "/") if o["pasta"] else ""
    if os.path.isdir(os.path.join(onde, ".git")):
        busca = _git(onde, "fetch", "--quiet", "origin", ramo)
        versao = _git(onde, "show", f"origin/{ramo}:{prefixo}VERSION")
        if versao.returncode != 0:
            raise RuntimeError("não achei o arquivo VERSION no repositório")
        notas = _git(onde, "show", f"origin/{ramo}:{prefixo}CHANGELOG.md")
        return versao.stdout.strip(), notas.stdout if notas.returncode == 0 else "", None if busca.returncode == 0 else "sem acesso ao repositório agora"
    m = re.match(r"https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", onde)
    if m:
        base = f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{ramo}/{prefixo}"
        versao = requests.get(base + "VERSION", timeout=12)
        versao.raise_for_status()
        notas = requests.get(base + "CHANGELOG.md", timeout=12)
        return versao.text.strip(), notas.text if notas.ok else "", None
    pasta = os.path.join(onde, o["pasta"]) if o["pasta"] and os.path.isdir(os.path.join(onde, o["pasta"])) else onde
    if os.path.isfile(os.path.join(pasta, "VERSION")):
        with open(os.path.join(pasta, "VERSION"), encoding="utf-8-sig") as f:
            versao = f.read().strip()
        try:
            with open(os.path.join(pasta, "CHANGELOG.md"), encoding="utf-8-sig") as f:
                notas = f.read()
        except OSError:
            notas = ""
        return versao, notas, None
    raise RuntimeError("a origem das atualizações não é um repositório nem uma pasta do guardião")


def notas_desde(changelog, instalada, publicada):
    """Entradas do CHANGELOG mais novas que a versão instalada (a mais recente primeiro)."""
    saida = []
    for trecho in re.split(r"(?m)^##\s+", changelog or "")[1:]:
        titulo, _, corpo = trecho.partition("\n")
        m = re.match(r"v?(\d+\.\d+(?:\.\d+)?)", titulo.strip())
        if not m or not (_num(instalada) < _num(m.group(1)) <= _num(publicada)):
            continue
        data = re.search(r"\d{4}-\d{2}-\d{2}", titulo)
        itens = [re.sub(r"\s+", " ", x[1:]).strip()[:220] for x in corpo.splitlines() if x.strip().startswith("-")]
        saida.append({"versao": m.group(1), "data": data.group(0) if data else "", "critica": "CRITICAL" in titulo.upper(), "itens": itens[:6]})
    saida.sort(key=lambda n: _num(n["versao"]), reverse=True)
    return saida[:5]


def codigo_mudou():
    """O programa ligado é mais antigo que os arquivos no disco (acabou de atualizar e ainda não reiniciou)."""
    if versao_instalada() != CARREGADA:
        return True
    try:
        return any(os.path.getmtime(os.path.join(BASE, n)) > INICIO for n in os.listdir(BASE) if n.endswith(".py"))
    except OSError:
        return False


def publico():
    """O que o painel precisa saber (GET /versao)."""
    estado, instalada = _estado(), versao_instalada()
    publicada = estado.get("remota")
    nova = bool(publicada) and _num(publicada) > _num(instalada)
    resultado = h._ler_json(_arq("atualizacao_resultado.json")) or {}
    return {"instalada": instalada, "carregada": CARREGADA, "remota": publicada, "nova": nova,
            "notas": [n for n in estado.get("notas") or [] if _num(n.get("versao")) > _num(instalada)] if nova else [],
            "verificado_em": estado.get("verificado_em"), "erro": estado.get("erro"), "tem_origem": bool(origem()["origem"]),
            "atualizando": ATUALIZANDO, "reiniciar": codigo_mudou(), "ultimo": resultado or None}


def verificar(forcar=False):
    """Compara a versão instalada com a publicada. Sem forçar, só olha o repositório uma vez por dia."""
    with TRAVA:
        estado = _estado()
        if not forcar and str(estado.get("verificado_em") or "")[:10] == time.strftime("%Y-%m-%d"):
            return publico()
        o = origem()
        estado["verificado_em"] = time.strftime("%Y-%m-%d %H:%M")
        estado["erro"] = None
        if not o["origem"]:
            estado["erro"] = "sem_origem"
        else:
            try:
                publicada, changelog, aviso = ler_remoto(o)
                if not re.fullmatch(r"v?\d+\.\d+(\.\d+)?", publicada):
                    raise RuntimeError("o arquivo VERSION do repositório não tem um número de versão")
                estado["remota"] = publicada.lstrip("v")
                estado["notas"] = notas_desde(changelog, versao_instalada(), publicada)
                estado["erro"] = aviso
            except Exception as erro:  # sem rede, sem git, sem acesso: o painel segue normal e tenta de novo amanhã
                estado["erro"] = str(erro)[:200]
        _salvar(estado)
    dados = publico()
    h.bus.emitir("versao", **dados)
    return dados


def ao_abrir():
    """GET /versao: responde na hora com o que já se sabe e, se hoje ainda não olhou o repositório, olha em segundo plano."""
    estado = _estado()
    if origem()["verificar"] and str(estado.get("verificado_em") or "")[:10] != time.strftime("%Y-%m-%d"):
        threading.Thread(target=verificar, daemon=True).start()
    return publico()


def _vigiar_resultado(antes):
    """Enquanto o atualizar.ps1 trabalha: se ele terminar com erro sem reiniciar o guardião, o painel precisa saber."""
    global ATUALIZANDO
    fim = time.time() + 420
    while time.time() < fim:
        time.sleep(1.5)
        r = h._ler_json(_arq("atualizacao_resultado.json")) or {}
        if r and r != antes:
            ATUALIZANDO = False
            h.bus.emitir("versao", **publico())
            if r.get("resultado") != "ok":
                h.bus.emitir("aviso", texto="A atualização não terminou. " + str(r.get("mensagem") or ""), erro=True)
            return
    ATUALIZANDO = False
    h.bus.emitir("versao", **publico())


def atualizar():
    """Chama o atualizar.ps1 fora deste programa (ele desliga e religa o guardião)."""
    global ATUALIZANDO
    if ATUALIZANDO:
        return {"ok": True, "atualizando": True}
    script = os.path.join(h.OPER, "atualizar.ps1")
    if not os.path.isfile(script):
        return {"ok": False, "erro": "Não achei o atualizar.ps1 na pasta do guardião."}
    if not origem()["origem"]:
        return {"ok": False, "erro": "A origem das atualizações não está configurada (campo atualizacao do config.json)."}
    antes = h._ler_json(_arq("atualizacao_resultado.json")) or {}
    ATUALIZANDO = True
    try:
        if COMANDO_ATUALIZAR:
            COMANDO_ATUALIZAR(script)
        else:
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script],
                             cwd=h.OPER, creationflags=SEM_JANELA | NOVO_GRUPO, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as erro:
        ATUALIZANDO = False
        return {"ok": False, "erro": f"Não consegui iniciar a atualização: {erro}"}
    threading.Thread(target=_vigiar_resultado, args=(antes,), daemon=True).start()
    h.bus.emitir("versao", **publico())
    return {"ok": True, "atualizando": True}


def rota_post(caminho):
    if caminho == "/versao/verificar":
        return verificar(forcar=True)
    if caminho == "/versao/atualizar":
        return atualizar()
    return None
