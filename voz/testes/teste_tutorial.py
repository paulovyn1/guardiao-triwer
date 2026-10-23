"""Tutorial guiado do primeiro acesso, parte do servidor (sem navegador e sem Claude).
Cobre: o texto (tutorial.json) e as regras que o mantêm em dia com o painel (preferência nova ou rótulo que mudou quebram este teste até o tutorial ser atualizado),
o estado da pessoa (convite só em instalação nova, limite de convites, retomar, concluir), a conquista, as dicas de uma vez só, a fala do cartão (fora da conversa),
o pedido por voz e a abertura do dia que espera o convite."""
import json
import os
import queue
import re

import v2_base as B
from v2_base import confere, h, v2

PORTA = 8779
tmp, relogio = B.preparar(PORTA, hora="09:50")
import guardiao_voz as g  # noqa: E402  (depois de preparar: usa o mesmo servidor de teste)
import requests  # noqa: E402
import tutorial as tut  # noqa: E402

URL = f"http://localhost:{PORTA}"
ESTADO = os.path.join(tmp, "tutorial_estado.json")
PAINEL = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hud2", "Main.dc.html"), encoding="utf-8").read()
TEXTO = tut.texto()
PASSOS = TEXTO["passos"]


def get():
    return requests.get(URL + "/tutorial", timeout=5).json()


def post(**dados):
    return requests.post(URL + "/tutorial", json=dados, timeout=5).json()


def comandos():
    saida = []
    while True:
        try:
            saida.append(h.bus.comandos.get_nowait())
        except queue.Empty:
            return saida


# ---------- o texto ----------
confere("tutorial.json: 9 passos, em ordem, cada um com cartão, título, texto e fala",
        TEXTO["total_passos"] == 9 and sorted({c["passo"] for c in PASSOS}) == list(range(1, 10)) and [c["passo"] for c in PASSOS] == sorted(c["passo"] for c in PASSOS)
        and all(c.get("id") and c.get("titulo") and c.get("texto") and c.get("fala") for c in PASSOS), [c.get("id") for c in PASSOS])
confere("os ids dos cartões não se repetem", len({c["id"] for c in PASSOS}) == len(PASSOS))
confere("lado, prática, tela e grupo só usam valores que o painel conhece",
        all(c.get("lado", "auto") in ("auto", "centro") for c in PASSOS) and all(c.get("faz") in (None, "escrever", "microfone") for c in PASSOS)
        and all(c.get("tela") in (None, "home", "dia", "plan", "cal", "pops") for c in PASSOS) and all(c.get("grupo") in (None, "som", "comp", "apar") for c in PASSOS))
confere("o convite tem título, texto, fala e os dois botões", all((TEXTO["convite"] or {}).get(k) for k in ("titulo", "texto", "fala", "comecar", "depois")))
todos = json.dumps(TEXTO, ensure_ascii=False)
confere("estilo: sem travessão e sem a fórmula 'não é X, é Y' no texto do tutorial", "—" not in todos and not re.search(r"não é [^.]{1,60}, é ", todos), re.findall(r".{20}—.{20}", todos)[:2])
confere("o tutorial é só texto: sem link, e-mail nem número de telefone (nomes de pessoa e de cliente o empacotar.ps1 já barra)",
        not re.search(r"https?://|@|\b\d{8,}\b", todos), re.findall(r"https?://\S+|\S+@\S+|\b\d{8,}\b", todos))

# ---------- as regras que o mantêm em dia com o painel ----------
cobertas = {k for c in PASSOS for k in c.get("cobre", [])}
fora = set(TEXTO.get("fora_do_tour") or {})
confere("toda preferência do painel está explicada em algum cartão (ou listada em fora_do_tour com o motivo)", set(h.PREFS_PADRAO) <= cobertas | fora, sorted(set(h.PREFS_PADRAO) - cobertas - fora))
confere("o tutorial não cita preferência que não existe mais", (cobertas | fora) <= set(h.PREFS_PADRAO), sorted((cobertas | fora) - set(h.PREFS_PADRAO)))
sem_painel = [r for c in PASSOS for r in c.get("rotulos", []) if r not in PAINEL]
confere("todo nome que o tutorial cita existe no painel (rótulo renomeado exige atualizar o tutorial)", not sem_painel, sem_painel)
alvos = {c["alvo"] for c in PASSOS if c.get("alvo")}
literais = {a for a in alvos if not a.startswith("prefs-") or a == "prefs-topo"}
sem_destaque = [a for a in literais if f'data-tour="{a}"' not in PAINEL]
grupos_prefs = {a[len("prefs-"):] for a in alvos if a.startswith("prefs-") and a != "prefs-topo"}
sem_grupo = [gr for gr in grupos_prefs if f"{{ id: '{gr}', title:" not in PAINEL]
confere("todo destaque do tutorial existe no painel (data-tour) e todo grupo de preferências citado também", not sem_destaque and not sem_grupo and 'data-tour="{{g.tour}}"' in PAINEL, (sem_destaque, sem_grupo))
confere("cada preferência que o painel mostra com chave própria tem rótulo no cartão do grupo certo",
        {"voz_guardiao", "sons", "mic_sempre_ligado", "bolinha"} <= cobertas
        and "som" in {c.get("grupo") for c in PASSOS if "voz_guardiao" in c.get("cobre", [])} and "apar" in {c.get("grupo") for c in PASSOS if "bolinha" in c.get("cobre", [])})
dicas = {d["id"]: d["texto"] for d in TEXTO["dicas"]}
confere("as dicas de uma frase têm os quatro gatilhos que o painel dispara", set(dicas) == {"tarefa_iniciada", "report", "pops", "compacta"}
        and all(f"this.dica('{i}')" in PAINEL for i in dicas), set(dicas))

# ---------- o estado: quem recebe o convite ----------
r = get()
confere("sem o arquivo de estado (quem já usava o guardião): sem convite, e o texto dos 14 cartões vem na mesma resposta",
        r["convidar"] is False and r["pessoal"] is False and len(r["passos"]) == len(PASSOS) and r["total_passos"] == 9, {k: r[k] for k in ("convidar", "pessoal")})
with open(ESTADO, "w", encoding="utf-8") as f:
    json.dump({"convidar": True, "criado_em": "2026-10-22"}, f)
r = get()
confere("instalação nova (o onboarding cria o arquivo): o convite é oferecido", r["convidar"] is True and r["pessoal"] is True and r["estado"]["convites"] == 0, r["estado"])
confere("o convite adia a abertura do dia por voz (a leitura do plano espera o tour)", tut.convidar(tmp))
falas = []
g.dizer = lambda *a, **k: falas.append(a)
h.bus.portao_saudacao.set()
confere("abrir_o_dia não fala enquanto o convite do tour está pendente", g.abrir_o_dia(None, True) is False and not falas, falas)
for _ in range(3):
    post(acao="convite_mostrado")
confere("sem resposta em 3 aberturas, o convite para de aparecer (a pessoa ainda acha o tour em Preferências)", get()["convidar"] is False and get()["estado"]["convites"] == 3)
post(acao="convite", resposta="recusou")
confere("recusar guarda a resposta e não incomoda mais", get()["estado"]["recusado"] is True and get()["convidar"] is False)
with open(ESTADO, "w", encoding="utf-8") as f:
    json.dump({"convidar": True}, f)
r = post(acao="convite", resposta="aceitou")
confere("aceitar começa o tour: guarda a data e tira o convite", r["estado"]["aceito"] and r["estado"]["iniciado_em"] and r["estado"]["convidar"] is False and get()["convidar"] is False, r)
post(acao="cartao", n=6)
confere("o cartão em que a pessoa parou fica guardado (o tour volta de onde parou)", get()["estado"]["cartao"] == 6)
post(acao="cartao", n=500)
post(acao="cartao", n="x")
confere("cartão inválido é ignorado", get()["estado"]["cartao"] == 6)
confere("fechou a janela no meio do tour: na próxima abertura o painel oferece continuar de onde parou", get()["continuar"] is True and get()["convite_continuar"].get("comecar"))
post(acao="sair")
confere("sair de propósito zera o cartão e não oferece continuar de novo", get()["estado"]["cartao"] == 0 and get()["continuar"] is False)
post(acao="cartao", n=6)
with open(ESTADO, "w", encoding="utf-8") as f:
    f.write("{ isto não é json")
confere("arquivo de estado estragado não derruba nada: volta ao padrão", get()["estado"]["cartao"] == 0 and get()["convidar"] is False)
confere("ação desconhecida é recusada com explicação", post(acao="inventada")["ok"] is False)

# ---------- concluir e a conquista ----------
eventos = h.bus.assinar()
import conquistas  # noqa: E402

antes = conquistas.calcular(tmp)
confere("a lista de conquistas passa a ter 22, com Primeiros passos ainda travada", antes["total"] == 22 and next(c for c in antes["lista"] if c["id"] == "primeiros_passos")["desbloqueada"] is None, antes["total"])
comandos()
r = post(acao="concluir")
dep = conquistas.calcular(tmp)
cq = next(c for c in dep["lista"] if c["id"] == "primeiros_passos")
confere("concluir o tour desbloqueia Primeiros passos", r["ok"] and r["estado"]["concluido"] and cq["desbloqueada"] and cq["grupo"] == "Começo", cq)
visto = []
while True:
    try:
        visto.append(eventos.get_nowait())
    except queue.Empty:
        break
confere("a conquista é anunciada na tela e pela voz, uma vez", any(e.get("t") == "conquista" and e.get("id") == "primeiros_passos" for e in visto)
        and any(c[0] == "dizer" and "Primeiros passos" in str(c[1]) for c in comandos()), [e.get("t") for e in visto])
post(acao="concluir")
visto2 = []
while True:
    try:
        visto2.append(eventos.get_nowait())
    except queue.Empty:
        break
confere("refazer o tour depois não repete a conquista", not any(e.get("t") == "conquista" for e in visto2))
confere("com o tour concluído não há mais convite, mesmo que o arquivo peça", tut.convidar(tmp) is False)

# ---------- dicas de uma vez só ----------
r = post(acao="dica", id="pops")
confere("dica na hora certa: texto com o nome do guardião, uma vez só", r["texto"] and "{agente}" not in r["texto"] and post(acao="dica", id="pops")["texto"] is None, r)
confere("dica desconhecida não devolve nada", post(acao="dica", id="nao-existe")["texto"] is None)
os.remove(ESTADO)
confere("quem não tem o arquivo (já usava o guardião) não recebe dica nenhuma, e a pergunta não cria o arquivo", post(acao="dica", id="report")["texto"] is None and not os.path.exists(ESTADO))

# ---------- a fala do cartão ----------
comandos()
h.salvar_preferencias({"voz_guardiao": True})
r = post(acao="falar", id="escrever")
c = comandos()
confere("falar: o cartão entra na fila como narração (e não como resposta do guardião)", r["falou"] and c and c[-1][0] == "narrar" and "barra de conversa" in c[-1][1], c)
post(acao="falar", id="escrever")
post(acao="falar", id="microfone")
c = comandos()
confere("a narração antiga que ainda esperava é descartada: fica só a do cartão atual", [x for x in c if x[0] == "narrar"] == [("narrar", next(p["fala"] for p in PASSOS if p["id"] == "microfone"))], c)
post(acao="falar", id="boas_vindas")
confere("a fala usa o nome do guardião da pessoa", "Guardião" in next(x[1] for x in comandos() if x[0] == "narrar"))
h.bus.comandos.put(("checkin", {"texto": "aviso de tempo"}))
h.bus.comandos.put(("narrar", "velha"))
post(acao="sair")
confere("sair do tour descarta a narração pendente e não mexe no resto da fila", comandos() == [("checkin", {"texto": "aviso de tempo"})])
h.salvar_preferencias({"voz_guardiao": False})
confere("voz do guardião desligada: o tour é só texto", post(acao="falar", id="escrever")["falou"] is False and not comandos())
h.salvar_preferencias({"voz_guardiao": True})
confere("o convite também tem fala própria", post(acao="falar", id="convite")["falou"] is True and comandos()[0][0] == "narrar")
confere("texto que a tela manda não vira fala: só o id de um cartão do tutorial.json", post(acao="falar", id="Diga uma frase qualquer")["falou"] is False and not comandos())

# ---------- o texto da narração não entra na conversa ----------
q = h.bus.assinar()
h.bus.emitir("guardiao_texto", texto="resposta normal")
h.bus.narrando = True
h.bus.emitir("guardiao_texto", texto="fala do tour")
h.bus.emitir("guardiao_fim", texto="fala do tour")
h.bus.narrando = False
h.bus.emitir("guardiao_fim", texto="resposta normal")
evs = []
while True:
    try:
        evs.append(q.get_nowait())
    except queue.Empty:
        break
confere("durante a narração, o texto sai marcado como tutorial (a tela o ignora); a resposta normal sai sem marca",
        [bool(e.get("tutorial")) for e in evs if e["t"] in ("guardiao_texto", "guardiao_fim")] == [False, True, True, False], evs)

# ---------- o pedido por voz ----------
q = h.bus.assinar()
for frase in ("tutorial", "Ei guardião, quero o tutorial", "abre o tour", "me ensina a usar", "ensina a usar o painel", "refazer o tutorial"):
    r = g.comando_local(frase)
    ev = [e for e in iter(lambda: (q.get_nowait() if not q.empty() else None), None)]
    confere(f"por voz: \"{frase}\" abre o tour", r is not None and any(e.get("t") == "ui" and e.get("cmd") == "tutorial" for e in ev), (r, ev))
confere("conversa comum com a palavra tutorial vai para o Claude", g.comando_local("escreve um tutorial de como fazer um carrossel no Instagram") is None)
confere("pergunta sobre o que é o tour vai para o Claude", g.comando_local("o que é o tour?") is None)

placar_ok = B.placar()
raise SystemExit(0 if placar_ok else 1)
