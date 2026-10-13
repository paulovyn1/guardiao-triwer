"""Catálogo de POPs da escola (POPs da escola, no painel): lido do Supabase da escola pela API aberta (só POPs publicados), sem a pessoa configurar nada.
Aqui um servidor falso faz o papel do Supabase, na porta que o sistema der: nada sai do computador. Confere os cabeçalhos e a consulta enviados, a leitura
das linhas, o cache, o último catálogo guardado quando a rede cai, a troca do catálogo pelo config.json e a instalação de um POP no Meus POPs."""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests

import v2_base as B
from v2_base import confere, h, v2

tmp, relogio = B.preparar(8776, hora="09:50")
v2.requests = requests  # o preparar troca por um ClickUp falso; aqui a leitura do catálogo precisa de um servidor de verdade (o falso, local)

LINHAS = [
    {"id": "fechamento-mensal", "nome": "Fechamento mensal de relatório", "proposito": "Reunir os números do mês e entregar.", "frente": "Relatórios", "versao": "v2",
     "etapas": [{"t": "Exportar os números", "dono": "Você", "tempo": "8 min"}, {"t": "Conferir os totais", "dono": "Você", "tempo": "10 min"}],
     "tempo_medio": "18 min", "criterio": "Relatório enviado.", "prazo": "1 dia útil depois do fechamento", "atencao": "Conferir o período.", "fontes": "Escola",
     "ordem": 1, "publicado": True},
    {"id": "briefing-cliente", "nome": "Briefing de cliente novo", "proposito": "", "frente": "Atendimento", "versao": "v1", "etapas": ["Marcar a conversa", "Preencher o briefing"],
     "tempo_medio": None, "criterio": "", "prazo": "", "atencao": "", "fontes": "", "ordem": 2, "publicado": True},
]
estado = {"pedidos": [], "falhar": False}


class Falso(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        estado["pedidos"].append({"caminho": url.path, "consulta": parse_qs(url.query), "cab": {k.lower(): v for k, v in self.headers.items()}})
        if estado["falhar"]:
            self.send_response(500)
            self.end_headers()
            return
        corpo = json.dumps(LINHAS, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


servidor = HTTPServer(("127.0.0.1", 0), Falso)
porta = servidor.server_address[1]
threading.Thread(target=servidor.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{porta}"


def zerar():
    estado["pedidos"].clear()
    estado["falhar"] = False
    v2._CACHE_CATALOGO.clear()


def gravar_padrao(**extra):
    dados = {"url": base + "/rest/v1/pops_escola", "schema": "guardiao", "chave": "chave-publica-de-teste", **extra}
    v2.ARQ_CATALOGO_PADRAO = os.path.join(tmp, "catalogo_pops.json")
    with open(v2.ARQ_CATALOGO_PADRAO, "w", encoding="utf-8") as f:
        json.dump(dados, f)


# ---------------- o catálogo padrão da escola, sem configurar nada ----------------
gravar_padrao()
zerar()
escola = v2.pops()["escola"]
confere("sem config.json de catálogo, lê o da escola e traz os dois POPs", escola["ok"] and [p["nome"] for p in escola["itens"]] == ["Fechamento mensal de relatório", "Briefing de cliente novo"], escola)
p1 = escola["itens"][0]
confere("o POP vem inteiro: id com origem, frente, versão, etapas com dono e tempo, critério e prazo",
        p1["id"] == "escola:fechamento-mensal" and p1["frente"] == "Relatórios" and p1["versao"] == "v2" and p1["etapas"][0] == {"t": "Exportar os números", "dono": "Você", "tempo": "8 min", "m": "Você · 8 min"}
        and p1["tempo_medio"] == "18 min" and p1["criterio"] == "Relatório enviado." and p1["prazo"].startswith("1 dia útil") and not p1["meu"], p1)
confere("etapa escrita só como texto também vale", [e["t"] for e in escola["itens"][1]["etapas"]] == ["Marcar a conversa", "Preencher o briefing"])
pedido = estado["pedidos"][0]
confere("o pedido leva a chave pública e o schema da escola nos cabeçalhos", pedido["cab"].get("apikey") == "chave-publica-de-teste" and pedido["cab"].get("accept-profile") == "guardiao", pedido["cab"])
confere("e pede só os publicados, na ordem da escola", pedido["caminho"] == "/rest/v1/pops_escola" and pedido["consulta"].get("publicado") == ["eq.true"] and pedido["consulta"].get("order") == ["ordem.asc,nome.asc"], pedido)
confere("nenhum cabeçalho de pessoa vai junto (sem Authorization, sem cookie)", "authorization" not in pedido["cab"] and "cookie" not in pedido["cab"], pedido["cab"])

# ---------------- cache e rede caindo ----------------
v2.pops()
confere("a segunda leitura, logo depois, vem do cache (um pedido só)", len(estado["pedidos"]) == 1, len(estado["pedidos"]))
for chave in list(v2._CACHE_CATALOGO):
    v2._CACHE_CATALOGO[chave] = (time.time() - 3600, v2._CACHE_CATALOGO[chave][1])  # o cache venceu
estado["falhar"] = True
escola = v2.pops()["escola"]
confere("cache vencido e a escola fora do ar: continua mostrando o último catálogo que veio", escola["ok"] and len(escola["itens"]) == 2 and len(estado["pedidos"]) == 2, escola)
zerar()
estado["falhar"] = True
escola = v2.pops()["escola"]
confere("sem nada guardado e a escola fora do ar: a tela diz indisponível (e dá para tentar de novo)", not escola["ok"] and escola["motivo"] == "indisponivel" and escola["itens"] == [], escola)

# ---------------- instalar ----------------
zerar()
r = v2.instalar_pop({"id": "escola:fechamento-mensal"})
P = v2.pops()
confere("instalar copia o POP do catálogo da escola para Meus POPs, com a origem", r["ok"] and len(P["meus"]) == 1 and P["meus"][0]["de"] == "escola:fechamento-mensal"
        and P["meus"][0]["tempo_medio"] == "18 min" and P["escola"]["itens"][0]["instalado"], (r, P["meus"]))

# ---------------- trocar o catálogo pelo config.json ----------------
zerar()
cfg = h._config()
cfg["pops"] = {"catalogo": base + "/outro-catalogo"}
with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False)
escola = v2.pops()["escola"]
confere("pops.catalogo no config.json vale no lugar do da escola, sem a chave da escola", escola["ok"] and estado["pedidos"][-1]["caminho"] == "/outro-catalogo"
        and "apikey" not in estado["pedidos"][-1]["cab"] and "accept-profile" not in estado["pedidos"][-1]["cab"], estado["pedidos"][-1])
cfg.pop("pops")
with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False)

# ---------------- sem catálogo nenhum ----------------
zerar()
v2.ARQ_CATALOGO_PADRAO = os.path.join(tmp, "nao_existe.json")
escola = v2.pops()["escola"]
confere("sem arquivo da escola e sem config.json: a tela diz que o catálogo ainda não foi publicado, sem pedir nada à rede", not escola["ok"] and escola["motivo"] == "nao_configurado" and not estado["pedidos"], escola)
gravar_padrao()
with open(v2.ARQ_CATALOGO_PADRAO, "w", encoding="utf-8") as f:
    json.dump({"url": base, "schema": "guardiao"}, f)  # sem chave
confere("arquivo da escola incompleto (sem chave) é tratado como sem catálogo", v2.pops()["escola"]["motivo"] == "nao_configurado")

# ---------------- o arquivo que vai no pacote ----------------
real = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "catalogo_pops.json"), encoding="utf-8"))
confere("o catalogo_pops.json do pacote aponta para a tabela pops_escola do schema guardiao", real["url"].startswith("https://") and real["url"].endswith("/rest/v1/pops_escola") and real["schema"] == "guardiao", real["url"])
confere("e leva só a chave pública (publishable), nunca uma chave de servidor", real["chave"].startswith("sb_publishable_") and "service_role" not in json.dumps(real) and "sb_secret" not in json.dumps(real))

servidor.shutdown()
raise SystemExit(0 if B.placar() else 1)
