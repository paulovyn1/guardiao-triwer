"""Cérebro do guardião na revisão do plano: marcas, permissões, aprovação com "sim", abertura do dia (plano lido tarefa a tarefa, pedido de ok,
execução com incentivo), microfone aberto. Sem Claude, sem áudio, sem navegador."""
import argparse
import json
import os
import queue
import sys
import tempfile
import threading
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import limpeza_teste  # noqa: E402,F401
import hud_servidor as h  # noqa: E402
limpeza_teste.fixar_relogio(h)
import guardiao_voz as g  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


tmp = tempfile.mkdtemp(prefix="gv_oper_rev_")
h.OPER = tmp
hoje = date.today().isoformat()
caminho = os.path.join(tmp, "plano_do_dia.json")


def bloco(i, ini, fim, titulo, **extra):
    return {"id": f"b{i}", "inicio": ini, "fim": fim, "titulo": titulo, "dono": "Rafa Lima", "frente": "Teste",
            "descricao": f"Descrição {i}", "primeiro_passo": f"Passo {i}", "por_que_agora": f"Motivo {i}", **extra}


def gravar_plano(status="sugerido"):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"data": hoje, "status": status, "fixos": [], "blocos": [
            bloco(1, "09:00", "09:30", "Primeira", clickup_id="cid1"), bloco(2, "10:00", "11:00", "Segunda", lista_id="L1")]}, f, ensure_ascii=False)


def plano():
    return json.load(open(caminho, encoding="utf-8"))


with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"pessoa": {"nome": "Rafa Lima", "artigo": "o"}, "clickup": {"user_id": "1", "listas": [{"id": "L1", "nome": "Rotineiras"}]}}, f)
gravar_plano()
fila = h.bus.assinar()


def eventos():
    saida = []
    while not fila.empty():
        saida.append(fila.get_nowait())
    return saida


# ---- as marcas novas são reconhecidas e não vazam para a fala
t = "{{revisao:inicio}} {{foco:b1}} Das 9h às 9h30, Primeira. {{mover:b2|15:00-16:00}} Movi a segunda. {{aprovar}} Posso aprovar o plano?"
limpo, dirs = g.extrair_diretivas(t)
confere("extrair reconhece revisao, foco, mover e aprovar", [d[0] for d in dirs] == ["revisao", "foco", "mover", "aprovar"] and "{{" not in limpo, (limpo, dirs))
confere("mascarar protege as marcas novas contra cortes de frase", "15:00" not in g.mascarar(t) and g.mascarar("{{adicionar:titulo=A. B|inicio=10:00|fim=10:30}}").count(".") == 0)

# ---- permissões: fora da revisão, o ajuste só vale se a frase pedir
g.executar_diretivas([("mover", "b2|15:00-16:00")], "o que eu tenho amanhã?")
confere("fora da revisão, 'o que eu tenho amanhã' não mexe no plano", plano()["blocos"][1]["inicio"] == "10:00")
eventos()
g.executar_diretivas([("mover", "b2|15:00-16:00")], "move a segunda para as três da tarde")
confere("fora da revisão, pedir para mover move", plano()["blocos"][1]["inicio"] == "15:00")
ev = eventos()
confere("o ajuste emite plano_editado e plano, e destaca o bloco (foco)", [e["t"] for e in ev] == ["foco", "plano_editado", "plano"], [e["t"] for e in ev])
confere("o resultado do ajuste vai para o guardião saber na próxima fala", any("mover 'Segunda' ok" in x for x in g.AVISOS_AO_MODELO), g.AVISOS_AO_MODELO)
sit = g.situacao_plano()
confere("situacao_plano traz o status, lista o resultado e limpa a lista", "sugerido" in sit and "mover 'Segunda' ok" in sit and g.AVISOS_AO_MODELO == [], sit)
g.executar_diretivas([("mover", "b1|15:30-16:30")], "move a primeira para as 15:30")
ev = eventos()
confere("choque de horário: o evento do ajuste carrega o conflito (a tela avisa) e fica anotado para o modelo", any(e["t"] == "plano_editado" and e["conflitos"] for e in ev) and any("ATENÇÃO" in x for x in g.AVISOS_AO_MODELO), [e["t"] for e in ev])
g.AVISOS_AO_MODELO.clear()
g.executar_diretivas([("mover", "b1|09:00-09:30")], "move a primeira para as 9h")
eventos()

# ---- revisão aberta: qualquer ajuste vale e o microfone reabre
confere("revisão começa fechada", not g.revisao_ativa())
g.executar_diretivas([("revisao", "inicio")], "bora revisar")
confere("{{revisao:inicio}} abre a revisão", g.revisao_ativa())
g.executar_diretivas([("remover", "b2")], "esse bloco não vai dar")
confere("na revisão, remover vale", all(b["id"] != "b2" for b in plano()["blocos"]))
g.executar_diretivas([("desfazer", "")], "volta como estava")
confere("desfazer traz o bloco de volta", any(b["id"] == "b2" for b in plano()["blocos"]))
g.executar_diretivas([("adicionar", "titulo=Ligar para a Débora|inicio=16:00|fim=16:15|lista=rotineiras")], "inclui uma ligação para a Débora às 16h")
novo = next((b for b in plano()["blocos"] if b["titulo"] == "Ligar para a Débora"), None)
confere("adicionar cria o bloco com lista", novo and novo["lista_id"] == "L1", novo)
g.REVISAO["ultimo"] -= 1300
confere("revisão parada há mais de 20 min se encerra sozinha", not g.revisao_ativa())

# ---- aprovar: explícito executa, vago propõe e espera o sim
chamadas = []
import hud_servidor as _hs
_hs._token_clickup = lambda: None  # ajuste em plano aprovado vai ao ClickUp: no teste, sem token, nada sai para a rede
g.agir = lambda tipo, *a, **k: chamadas.append((tipo, a, k)) or {"ok": True, "criadas": 1}
eventos()
g.executar_diretivas([("aprovar", "")], "pode aprovar o plano")
time.sleep(0.2)
confere("'pode aprovar' aprova direto (sem pergunta)", chamadas and chamadas[0][0] == "aprovar" and g.PROPOSTA is None, chamadas)
chamadas.clear()
g.executar_diretivas([("aprovar", "")], "tá bom assim")
confere("'tá bom assim' só propõe: nada é aprovado e a tela mostra a proposta", not chamadas and g.PROPOSTA and g.PROPOSTA["tipo"] == "aprovar" and any(e["t"] == "proposta" and e.get("tipo") == "aprovar" for e in eventos()))
confere("proposta de aprovar: 'sim' e 'ok' confirmam", g.resolver_proposta("sim") == "sim" and g.resolver_proposta("ok") == "sim" and g.resolver_proposta("pode aprovar") == "sim" and g.resolver_proposta("tá bom, pode aprovar") == "sim")
confere("proposta de aprovar: 'pode mover a reunião' NÃO aprova (é outro pedido)", g.resolver_proposta("pode mover a reunião para as 16h") == "outro")
confere("proposta de aprovar: 'não' recusa e 'não, muda a hora' é outro pedido", g.resolver_proposta("não") == "nao" and g.resolver_proposta("não, muda a hora") == "outro")
confere("proposta de aprovar: conversa solta também vira 'outro'", g.resolver_proposta("e como está o tempo hoje") == "outro")
g.PROPOSTA["quando"] -= 400
ev_antes = eventos()
confere("proposta velha expira e avisa a tela", g.resolver_proposta("sim") is None and g.PROPOSTA is None and any(e["t"] == "proposta_fim" and e["resultado"] == "expirada" for e in eventos()))
gravar_plano("aprovado")
chamadas.clear()
g.executar_diretivas([("aprovar", "")], "aprova")
time.sleep(0.1)
confere("com o plano já aprovado, {{aprovar}} não faz nada e avisa", not chamadas and any(e["t"] == "aviso" for e in eventos()))
g.executar_diretivas([("mover", "b2|12:00-13:00")], "move a segunda")
confere("depois de aprovado, mover pela voz vale (imprevisto) e o plano continua aprovado", plano()["blocos"][1]["inicio"] == "12:00" and plano()["status"] == "aprovado"
        and not any("FALHOU" in x for x in g.AVISOS_AO_MODELO), (plano()["blocos"][1], g.AVISOS_AO_MODELO))
g.AVISOS_AO_MODELO.clear()
gravar_plano()

# ---- abertura do dia: o guardião monta (se preciso), vai para a aba Dia e diz numa frase para aprovar na barra de baixo; nas outras aberturas, execução com incentivo
import controle_fala  # noqa: E402
import guardiao_v2 as v2  # noqa: E402
a = argparse.Namespace(cerebro=True, voz="kokoro", voz_kokoro="pm_santa", voz_nome="", sem_preview=True, previa_local=True, sem_escuta_aberta=False)
ditas = []
pular_na_leitura = [False]


def dizer_falso(texto, a_, marcas=False):
    ditas.append((texto, marcas))
    if marcas and pular_na_leitura[0]:
        controle_fala.esc()  # a pessoa aperta Esc no meio da leitura
    return texto


dizer_original = g.dizer
g.dizer = dizer_falso
h.bus.portao_saudacao.set()  # a animação de abertura já terminou
eventos()
r = g.abrir_o_dia(a, primeira=True)
ev = eventos()
leitura = ditas[0][0] if ditas else ""
confere("primeira abertura com plano sugerido: vai para a aba Dia", any(e["t"] == "ui" and e.get("cmd") == "tela" and e.get("id") == "dia" for e in ev), [e["t"] for e in ev])
confere("diz numa frase só, sem ler tarefa por tarefa (sem marca de foco) e sem abrir proposta nem revisão", len(ditas) == 1 and not ditas[0][1] and "{{foco" not in leitura
        and "Primeira" not in leitura and r is False and g.PROPOSTA is None and not any(e["t"] == "proposta" for e in ev) and not g.revisao_ativa(), (r, ditas, [e["t"] for e in ev]))
confere("cumprimenta pelo nome, diz quantas tarefas são e manda aprovar na barra de baixo", leitura.startswith(g.saudacao_local()) and "2 tarefas" in leitura
        and "aprove na barra de baixo" in leitura and "Posso aprovar" not in leitura, leitura)
confere("sem o ok, nada de execução", not v2.estado_exec()["ativo"])
confere("a leitura em voz antiga não fica ligada", not controle_fala.LEITURA.is_set())
g.PROPOSTA = None
g.encerrar_revisao()
ditas.clear()
r = g.abrir_o_dia(a, primeira=False)
confere("reaberta no mesmo dia com o plano ainda sem ok: não repete o plano, só lembra de aprovar na barra de baixo", r is False and len(ditas) == 1 and "ainda espera o seu ok" in ditas[0][0]
        and "barra de baixo" in ditas[0][0] and g.PROPOSTA is None, ditas)
g.PROPOSTA = None
ditas.clear()
g.ABERTURA["leu"] = ""
pular_na_leitura[0] = True
g.abrir_o_dia(a, primeira=True)
confere("primeira abertura de novo (mesmo com Esc armado): continua uma frase, sem leitura para pular nem 'Pulei a leitura'", len(ditas) == 1 and not ditas[0][1] and "Pulei" not in ditas[0][0] and g.PROPOSTA is None, ditas)
confere("e o Esc armado não desliga a voz nem deixa marca pendente", h.preferencias()["voz_guardiao"] is True and not controle_fala.PULAR_LEITURA.is_set())
pular_na_leitura[0] = False
g.PROPOSTA = None
g.encerrar_revisao()
gravar_plano("aprovado")
ditas.clear()
r = g.abrir_o_dia(a, primeira=False)
e = v2.estado_exec()
confere("plano aprovado: entra em execução sozinho, sem iniciar a tarefa", e["ativo"] and e["sessao"] is None, e)
confere("e fala uma frase de incentivo com a tarefa de agora", r is False and len(ditas) == 1 and ditas[0][0].startswith(g.saudacao_local()) and "Primeira" in ditas[0][0], ditas)
v2.sair()
h.salvar_preferencias({"execucao_ao_abrir": False})
g.abrir_o_dia(a, primeira=False)
confere("com 'ir direto para a execução' desligado, só o incentivo", not v2.estado_exec()["ativo"])
h.salvar_preferencias({"execucao_ao_abrir": True})
os.remove(caminho)
pedidos = []
iniciar_original = g.iniciar_completo
g.iniciar_completo = lambda pedido: pedidos.append(pedido) or True
ditas.clear()
r = g.abrir_o_dia(a, primeira=True)
confere("sem plano: pede para montar sem perguntar e avisa que está montando", pedidos == [g.PEDIDO_PLANO_DO_DIA] and g.ABERTURA["esperando_plano"] and "Estou montando o seu plano de hoje" in ditas[0][0] and r is False, (pedidos, ditas))
gravar_plano()
ditas.clear()
r = g.plano_montado_na_abertura(a, {"pedido": g.PEDIDO_PLANO_DO_DIA, "mudou": True, "fala": "Montei."})
confere("plano montado: diz numa frase para aprovar na barra de baixo (sem ler tarefa a tarefa, sem pedir ok falado)", r is False and not g.ABERTURA["esperando_plano"] and len(ditas) == 1
        and not ditas[0][1] and ditas[0][0].startswith("Pronto.") and "aprove na barra de baixo" in ditas[0][0] and g.PROPOSTA is None, (r, ditas))
g.PROPOSTA = None
g.encerrar_revisao()
g.iniciar_completo = iniciar_original
g.dizer = dizer_original
g.ABERTURA.update(esperando_plano=False, leu="")

# ---- atender: microfone aberto depois de pergunta
g.winsound.Beep = lambda *x: (_ for _ in ()).throw(AssertionError("bipe tocou no seguimento"))
g.dizer = lambda *x, **k: None
chamadas_resp = []
modelos_usados = []


def falso_responder(pergunta, voz, texto_usuario=None, acoes=True, portao=None, modelo=None, motivo="", fonte=None, pedir=None, limite_primeira=None, modo="rapido"):
    chamadas_resp.append({"texto_usuario": texto_usuario, "acoes": acoes, "portao": portao is not None})
    modelos_usados.append((modelo, motivo))
    return 1.0, 2.0, FALA[0]


FALA = ["Quer revisar o plano agora?"]
g.responder_falando = falso_responder
g.executar_diretivas = lambda *x, **k: None
q = queue.Queue()
r = g.atender(a, q, None, None, 0, texto_digitado="e agora?")
confere("pergunta digitada nunca abre o microfone sozinho", r is False)
FALA[0] = "Pronto, está feito."
r = g.atender(a, q, None, None, 0, texto_digitado="a saudação já passou")
confere("resposta sem pergunta não reabre o microfone", r is False)
g.REVISAO = {"inicio": time.time(), "ultimo": time.time()}
g.gravar = lambda *x, **k: None
r = g.atender(a, q, None, None, 0, seguimento=True)
confere("seguimento: sem bipe; se ninguém falar, a conversa termina", r is False)
g.REVISAO = None

# ---- conversar: repete enquanto o guardião espera resposta, com limite (só com a escuta contínua, que é opção)
turnos = []
sequencia = [True, True, True, False]
g.atender = lambda *x, **k: turnos.append(k) or sequencia[len(turnos) - 1]
g.conversar(a, q, None, None, 0)
confere("escuta contínua desligada (padrão): o microfone não reabre sozinho, mesmo com pergunta do guardião", len(turnos) == 1, len(turnos))
turnos.clear()
h.salvar_preferencias({"mic_sempre_ligado": True})
g.conversar(a, q, None, None, 0)
confere("conversar repete até o guardião não esperar mais resposta (3 seguimentos)", len(turnos) == 4 and [bool(t.get("seguimento")) for t in turnos] == [False, True, True, True], turnos)
turnos.clear()
sequencia[:] = [True] * 30
g.atender = lambda *x, **k: turnos.append(k) or True
g.conversar(a, q, None, None, 0)
confere("limite de 12 seguimentos seguidos", len(turnos) == 13, len(turnos))
turnos.clear()
a.sem_escuta_aberta = True
g.conversar(a, q, None, None, 0)
confere("--sem-escuta-aberta desliga o microfone aberto", len(turnos) == 1)

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
