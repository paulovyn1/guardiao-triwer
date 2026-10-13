"""Base dos testes do painel novo (v2): pasta operacional temporária, ClickUp falso, relógio que o teste controla e um Edge sem janela.
Nada aqui toca no ClickUp nem nos arquivos de verdade do Rafa."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta

import limpeza_teste  # noqa: F401  (fecha o Edge de teste e apaga as pastas gv_* ao terminar)
import requests
import websocket

VOZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_PNG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capturas")
sys.path.insert(0, VOZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import hud_servidor as h  # noqa: E402
import guardiao_v2 as v2  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe != "" and not ok else ""))


def placar():
    print(f"\n{sum(resultados)} de {len(resultados)} checagens passaram.")
    return all(resultados)


class Relogio:
    """Para o servidor, "agora" (no formato HH:MM) é a hora que o teste escolher."""

    def __init__(self, hora="10:20"):
        self.hora = hora

    def __getattr__(self, nome):
        return getattr(time, nome)

    def strftime(self, fmt, t=None):
        if t is None and fmt == "%H:%M":
            return self.hora
        return time.strftime(fmt, t) if t is not None else time.strftime(fmt)


class Resp:
    def __init__(self, dados=None):
        self.dados = dados or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self.dados


class ClickUpFalso:
    RequestException = requests.RequestException
    chamadas = []

    @classmethod
    def get(cls, url, **kw):
        cls.chamadas.append(("GET", url, kw.get("json")))
        if "/list/" in url:
            return Resp({"statuses": [{"status": "open", "type": "open"}, {"status": "complete", "type": "closed"}]})
        return Resp({"list": {"id": "L1", "name": "Lista de teste"}, "status": {"status": "open"},
                     "subtasks": [{"name": "Reler o briefing", "status": {"type": "closed"}}, {"name": "Definir os públicos", "status": {"type": "open"}},
                                  {"name": "Criar os anúncios", "status": {"type": "open"}}], "url": "https://app.clickup.com/t/x"})

    @classmethod
    def post(cls, url, **kw):
        cls.chamadas.append(("POST", url, kw.get("json")))
        return Resp({"id": "novo1"})

    @classmethod
    def put(cls, url, **kw):
        cls.chamadas.append(("PUT", url, kw.get("json")))
        return Resp()


def bloco(i, ini, fim, titulo, **extra):
    return {"id": f"b{i}", "inicio": ini, "fim": fim, "titulo": titulo, "dono": "Rafa Lima", "frente": extra.pop("frente", "Tráfego"),
            "descricao": extra.pop("descricao", f"Descrição da tarefa {i}. Está pronto quando o resultado {i} existir."),
            "primeiro_passo": extra.pop("primeiro_passo", f"Abra a tarefa {i} e releia o briefing."), "por_que_agora": extra.pop("por_que_agora", f"Motivo {i}."), **extra}


PLANO_PADRAO = lambda: {"data": date.today().isoformat(), "status": "aprovado", "aviso": "Deixei a revisão de contratos para amanhã, para proteger o seu pico de foco.", "fixos": [{"inicio": "14:00", "fim": "15:00", "titulo": "Reunião com o cliente"}], "blocos": [  # noqa: E731
    bloco(1, "08:00", "08:30", "Responder as mensagens dos clientes", frente="Atendimento"),
    bloco(2, "08:30", "09:00", "Organizar a agenda da semana", frente="Rotina"),
    bloco(3, "09:00", "10:30", "Montar as campanhas de tráfego da Clínica Vitta", clickup_id="cid3"),
    bloco(4, "10:30", "11:00", "Revisar o roteiro do vídeo da Padaria Sol", frente="Conteúdo", clickup_id="cid4"),
    bloco(5, "11:00", "12:00", "Fechar o relatório mensal da Loja Nativa", frente="Relatórios"),
    bloco(6, "13:30", "14:00", "Gravar os stories da semana", frente="Conteúdo"),
    bloco(7, "15:00", "15:30", "Ligar para o contador sobre o imposto do trimestre", frente="Financeiro"),
]}


def preparar(porta, plano=None, hora="09:50", feitos=("b1", "b2"), prefs=None):
    """Sobe um servidor de teste numa pasta temporária. Devolve (pasta, relógio)."""
    tmp = tempfile.mkdtemp(prefix="gv_oper_v2_")
    h.OPER = tmp
    relogio = Relogio(hora)
    h.time = relogio
    h.ARQ_PREFS = os.path.join(tempfile.mkdtemp(prefix="gv_prefs_"), "preferencias.json")
    if prefs:
        with open(h.ARQ_PREFS, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    h.requests = ClickUpFalso
    v2.requests = ClickUpFalso
    h._token_clickup = lambda: "token-de-teste"
    h._CACHE_TAREFA.clear()
    for pasta in ("planos", "registros", "logs", os.path.join("memoria", "pops")):
        os.makedirs(os.path.join(tmp, pasta), exist_ok=True)
    plano = PLANO_PADRAO() if plano is None else plano
    if plano:
        with open(os.path.join(tmp, "plano_do_dia.json"), "w", encoding="utf-8") as f:
            json.dump(plano, f, ensure_ascii=False)
    amanha = (date.today() + timedelta(days=1)).isoformat()
    with open(os.path.join(tmp, "planos", f"plano_{amanha}.json"), "w", encoding="utf-8") as f:
        json.dump({"blocos": [bloco(1, "08:00", "09:00", "Gravar o vídeo da Padaria Sol"), bloco(2, "10:00", "11:30", "Subir as campanhas da Clínica Vitta")]}, f, ensure_ascii=False)
    with open(os.path.join(tmp, "resumo_clickup.json"), "w", encoding="utf-8") as f:
        json.dump({"tarefas": [{"id": "x1", "prazo": date.today().isoformat(), "nome": "Enviar relatório mensal da Loja Nativa", "lista": "Relatórios", "status": "open", "url": "https://app.clickup.com/t/x1"},
                               {"id": "x2", "prazo": amanha, "nome": "Gravação do vídeo da Padaria Sol", "lista": "Conteúdo", "status": "open", "url": "https://app.clickup.com/t/x2"}]}, f, ensure_ascii=False)
    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"pessoa": {"nome": "Rafa Lima", "artigo": "o"}, "agente": {"nome": "Guardião"}, "pastas": {"memoria": os.path.join(tmp, "memoria")},
                   "rotina": {"dias_trabalho": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "chegada": "08:00", "fim": "16:30"},
                   "clickup": {"user_id": "1001", "status_abertos": ["open"], "listas": [{"id": "L1", "nome": "Lista de teste"}],
                               "membros": [{"nome": "Rafa Lima", "id": "1001"}]}}, f, ensure_ascii=False)
    with open(os.path.join(tmp, "tempos.json"), "w", encoding="utf-8") as f:
        json.dump({"tipos": {}}, f)
    for bid in feitos:
        b = next((x for x in (plano or {}).get("blocos", []) if x["id"] == bid), None)
        if b:
            h.concluir_bloco({"id": bid, "concluido": True, "nota": "feito no teste", "inicio": b["inicio"], "fim": b["fim"]})
    h.bus.emitir("saude", mic=True, groq=True, claude=True, voz="kokoro")
    h.bus.emitir("estado", v="aguardando")
    if not h.iniciar_servidor(porta):
        raise RuntimeError(f"a porta {porta} está ocupada")
    return tmp, relogio


class Navegador:
    """Edge sem janela controlado pelo protocolo de depuração (CDP)."""

    def __init__(self, url, porta_cdp=9341, largura=1440, altura=900, gpu=False):
        self.erros = []
        self.n = 0
        edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if not os.path.exists(edge):
            edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        perfil = tempfile.mkdtemp(prefix="gv_edge_v2_")
        # CalculateNativeWinOcclusion desligado: com a tela do Windows bloqueada ou em descanso o Chromium dá a janela de teste como "coberta", a página fica
        # visibilityState=hidden e as transições de CSS param no instante zero (os testes de layout mediam uma tela no meio do caminho)
        args = [edge, "--headless=new", "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
                "--disable-features=CalculateNativeWinOcclusion",
                "--autoplay-policy=no-user-gesture-required", f"--user-data-dir={perfil}", f"--remote-debugging-port={porta_cdp}", f"--window-size={largura},{altura}",
                "--hide-scrollbars", "--mute-audio"]
        args += ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] if not gpu else []
        self.proc = subprocess.Popen(args + [url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        marca = url.split("//", 1)[1].split("/", 1)[0]
        for _ in range(60):
            try:
                achou = [p for p in requests.get(f"http://localhost:{porta_cdp}/json", timeout=2).json() if p.get("type") == "page" and marca in p.get("url", "")]
                if achou:
                    ws_url = achou[0]["webSocketDebuggerUrl"]
                    break
            except requests.RequestException:
                pass
            time.sleep(0.5)
        if not ws_url:
            raise RuntimeError("o Edge de teste não abriu")
        self.ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
        self.cdp("Runtime.enable")
        self.cdp("Page.enable")
        self.cdp("Emulation.setFocusEmulationEnabled", {"enabled": True})  # a página se comporta como a que está em foco e à vista
        self.cdp("Page.bringToFront")
        self.cdp("Emulation.setDeviceMetricsOverride", {"width": largura, "height": altura, "deviceScaleFactor": 1, "mobile": False})

    def cdp(self, metodo, params=None):
        self.n += 1
        meu = self.n
        self.ws.send(json.dumps({"id": meu, "method": metodo, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                self.erros.append(json.dumps(msg["params"]["exceptionDetails"], ensure_ascii=False)[:500])
            if msg.get("method") == "Runtime.consoleAPICalled" and msg["params"].get("type") == "error":
                self.erros.append("console.error " + json.dumps([a.get("value") or a.get("description") for a in msg["params"].get("args", [])], ensure_ascii=False)[:500])
            if msg.get("id") == meu:
                return msg.get("result", {})

    def js(self, expr):
        r = self.cdp("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if r.get("exceptionDetails"):
            self.erros.append("js: " + json.dumps(r["exceptionDetails"], ensure_ascii=False)[:400])
        return r.get("result", {}).get("value")

    def espera(self, expr, ate=8):
        fim = time.time() + ate
        while time.time() < fim:
            if self.js(f"!!({expr})"):  # !! porque um elemento da página chega aqui como {} (que o Python lê como falso)
                return True
            time.sleep(0.2)
        return False

    def foto(self, nome):
        os.makedirs(PASTA_PNG, exist_ok=True)
        caminho = os.path.join(PASTA_PNG, f"v2_{nome}.png")
        with open(caminho, "wb") as f:
            f.write(base64.b64decode(self.cdp("Page.captureScreenshot", {"format": "png"})["data"]))
        return caminho

    def abrir(self, url):
        self.cdp("Page.navigate", {"url": url})
        time.sleep(0.5)

    def clicar(self, seletor, indice=0):
        return self.js(f"(() => {{ const e = document.querySelectorAll({json.dumps(seletor)})[{indice}]; if (!e) return false; e.click(); return true; }})()")

    def clicar_texto(self, texto, seletor="button"):
        return self.js("(() => { const t = %s; const e = [...document.querySelectorAll(%s)].find((x) => x.offsetParent !== null && x.textContent.trim().includes(t)); if (!e) return false; e.click(); return true; })()"
                       % (json.dumps(texto), json.dumps(seletor)))

    def fechar(self):
        try:
            self.ws.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass
