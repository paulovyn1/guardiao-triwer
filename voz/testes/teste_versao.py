"""Versão 0.3.0, sem navegador: como o guardião chama a pessoa (nada de nome fixo), pendências e trazer tarefa atrasada para hoje,
guardião completo em segundo plano (com um Claude de mentira), versão instalada x publicada, o atualizar.ps1 numa pasta de teste
e a janela compacta por cima das outras. Não toca no ClickUp, no repositório de verdade nem na pasta de verdade."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, timedelta

from v2_base import ClickUpFalso, bloco, confere, h, placar, preparar, v2  # noqa: F401
import requests

import guardiao_atualizacao as at
import guardiao_janela as jan
import guardiao_voz as g

PORTA = 8793
ontem = (date.today() - timedelta(days=1)).isoformat()
anteontem = (date.today() - timedelta(days=2)).isoformat()
plano = {"data": date.today().isoformat(), "status": "sugerido", "fixos": [{"inicio": "14:00", "fim": "15:00", "titulo": "Reunião com o cliente"}], "blocos": [
    bloco(1, "09:00", "10:00", "Montar as campanhas da Clínica Vitta", clickup_id="cid1"),
    bloco(2, "10:00", "10:30", "Organizar a agenda da semana", lista_id="L1")]}
tmp, relogio = preparar(PORTA, plano=plano, hora="08:10", feitos=())
g.OPER = tmp
URL = f"http://localhost:{PORTA}"
eventos = []
emitir_original = h.bus.emitir


def emitir(tipo, /, **dados):
    eventos.append((tipo, dados))
    emitir_original(tipo, **dados)


h.bus.emitir = emitir


def config(**extra):
    caminho = os.path.join(tmp, "config.json")
    with open(caminho, encoding="utf-8") as f:
        c = json.load(f)
    c.update(extra)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)


# ---------------- como chamar a pessoa ----------------
config(pessoa={"nome": "Rafa Lima"})
p = h.pessoa()
confere("sem artigo no config: Rafa, de Rafa, a Rafa", (p["o"], p["do"], p["ao"], p["primeiro"]) == ("Rafa", "de Rafa", "a Rafa", "Rafa"), p)
config(pessoa={"nome": "Lara Souza", "artigo": "a"})
p = h.pessoa()
confere("com artigo 'a': a Lara, da Lara, à Lara", (p["o"], p["do"], p["ao"]) == ("a Lara", "da Lara", "à Lara"), p)
confere("a assinatura dos comentários sai do config", h.assinatura() == "— Guardião da Lara", h.assinatura())
prompt = g.prompt_sistema() if os.path.exists(os.path.join(tmp, "memoria", "perfil.md")) else None
if prompt is None:
    with open(os.path.join(tmp, "memoria", "perfil.md"), "w", encoding="utf-8") as f:
        f.write("Perfil de teste.")
    prompt = g.prompt_sistema()
regras = prompt.split("PERFIL:")[0]  # depois disso vêm os dados (perfil e planos), que nos testes citam o dono dos blocos
confere("o prompt da voz usa o nome do config e não sobra marca nem nome fixo", "Guardiao da Lara" in regras and "Fulano" not in prompt and "Rafa" not in regras,
        [x for x in ("Fulano", "Rafa") if x in regras])
confere("o prompt explica as pendências e o guardião completo", "PENDÊNCIAS" in prompt and "GUARDIÃO COMPLETO" in prompt and "{{completo:" in prompt)
confere("a frase antiga sobre a skill completa desligada saiu", "ainda nao esta ligada" not in prompt and "skill completa" not in prompt)
config(pessoa={"nome": "Rafa Lima", "artigo": "o"}, agente={"nome": "Guardião", "assinatura": "Guardião do Rafa"})
confere("assinatura escolhida no config vale", h.assinatura() == "— Guardião do Rafa", h.assinatura())
confere("a abertura do dia cumprimenta pelo primeiro nome", g.saudacao_local().endswith(", Rafa."), g.saudacao_local())
config(pessoa={})
confere("sem nome no config nada quebra", h.pessoa()["o"] == "a pessoa" and "Fulano" not in g.prompt_sistema())
config(pessoa={"nome": "Rafa Lima", "artigo": "o"})

# ---------------- pendências ----------------
with open(os.path.join(tmp, "resumo_clickup.json"), "w", encoding="utf-8") as f:
    json.dump({"gerado_em": "hoje 08:00", "tarefas": [
        {"id": "p1", "prazo": ontem, "nome": "Pagar a hospedagem do site", "lista": "Contas a pagar", "status": "open"},
        {"id": "p2", "prazo": anteontem, "nome": "Subir a gravação da aula", "lista": "Conteúdos", "status": "open"},
        {"id": "cid1", "prazo": ontem, "nome": "Montar as campanhas da Clínica Vitta", "lista": "Tráfego", "status": "open"},
        {"id": "x1", "prazo": date.today().isoformat(), "nome": "Tarefa de hoje", "lista": "Rotina", "status": "open"}]}, f, ensure_ascii=False)
with open(os.path.join(tmp, "planos", f"plano_{ontem}.json"), "w", encoding="utf-8") as f:
    json.dump({"data": ontem, "blocos": [bloco(1, "09:00", "10:00", "Escrever o roteiro do vídeo", lista_id="L1"), bloco(2, "10:00", "11:00", "Bloco concluído ontem")]}, f, ensure_ascii=False)
with open(os.path.join(tmp, "registros", f"registro_{ontem}.json"), "w", encoding="utf-8") as f:
    json.dump({"data": ontem, "blocos": [{"id": "b2", "estado": "feito"}]}, f)
pend = h.pendencias()
refs = [i["ref"] for i in pend]
confere("pendências: tarefas vencidas do ClickUp e bloco de ontem sem concluir; a de hoje e a concluída ficam de fora",
        set(refs) == {"cu:p1", "cu:p2", "cu:cid1", f"{ontem}:b1"}, refs)
confere("pendências: as mais recentes primeiro", pend[-1]["ref"] == "cu:p2", refs)
confere("pendências: marca o que já está no plano de hoje", next(i for i in pend if i["ref"] == "cu:cid1")["no_plano"] is True)
texto = h.pendencias_texto()
confere("texto das pendências traz id, quando venceu e lista", "cu:p1 | venceu" in texto and "há 1 dia" in texto and "Contas a pagar" in texto and "JÁ ESTÁ NO PLANO DE HOJE" in texto, texto)
confere("GET /pendencias responde", len(requests.get(URL + "/pendencias", timeout=5).json()["itens"]) == 4)
confere("a conversa sobre o fim de semana traz as pendências para o contexto", "TAREFAS ATRASADAS" in g.contexto_do_turno("revisa o que ficou pendente de sábado e domingo"))
confere("pergunta comum não carrega as pendências", "TAREFAS ATRASADAS" not in g.contexto_do_turno("que horas é a reunião"))
confere("pedido de pendências vai para o modelo padrão", g.escolher_modelo("o que ficou atrasado")[0] == g.MODELO_PADRAO)

r = h.editar_plano("adicionar", None, {"id": "cu:p1", "inicio": "11:00", "fim": "11:30"})
plano_agora = h._plano_de_hoje()
novo = next((b for b in plano_agora["blocos"] if b.get("clickup_id") == "p1"), None)
confere("trazer tarefa atrasada para hoje: entra com o id do ClickUp, sem duplicar e marcada para mudar de data",
        r["ok"] and novo and novo["titulo"] == "Pagar a hospedagem do site" and novo.get("reagendado") is True and "lista_id" not in novo, (r, novo))
confere("trazer a mesma tarefa de novo é recusado", h.editar_plano("adicionar", None, {"id": "cu:p1", "inicio": "12:00", "fim": "12:30"})["ok"] is False)
confere("tarefa que já está no plano não entra de novo", h.editar_plano("adicionar", None, {"id": "cu:cid1", "inicio": "12:00", "fim": "12:30"})["ok"] is False)
r = h.editar_plano("adicionar", None, {"id": f"{ontem}:b1", "inicio": "15:00", "fim": "16:00"})
novo2 = next((b for b in h._plano_de_hoje()["blocos"] if b["titulo"] == "Escrever o roteiro do vídeo"), None)
confere("bloco de ontem sem tarefa no ClickUp entra como bloco novo, com a lista e a descrição de antes", r["ok"] and novo2 and novo2.get("lista_id") == "L1" and "clickup_id" not in novo2, novo2)
confere("id que não existe é recusado com explicação", h.editar_plano("adicionar", None, {"id": "cu:nao-existe", "inicio": "16:00", "fim": "16:30"})["ok"] is False)
g.executar_diretivas([("adicionar", "id=cu:p2|inicio=11:30|fim=12:00")], "coloca a gravação da aula hoje às onze e meia")
confere("a marca adicionar com id funciona pela voz", any(b.get("clickup_id") == "p2" for b in h._plano_de_hoje()["blocos"]))
ClickUpFalso.chamadas.clear()
r = h.aprovar_plano()
puts = [c for c in ClickUpFalso.chamadas if c[0] == "PUT"]
# desde a 0.11.0 quem manda na data é o guardião: aprovar leva ao ClickUp o horário de toda tarefa do plano que não é fixa (cid1 também)
confere("ao aprovar, as tarefas trazidas mudam de data no ClickUp e nenhuma é criada em duplicidade",
        r["ok"] and r["reagendadas"] == 3 and {c[1].rsplit("/", 1)[1] for c in puts} == {"cid1", "p1", "p2"} and r["criadas"] == 2, (r, puts))

# ---------------- guardião completo ----------------
def plano_refeito(pedido, arquivo):
    with open(arquivo, encoding="utf-8") as f:
        atual = json.load(f)
    atual["blocos"].append(bloco(9, "16:00", "16:30", "Bloco montado pelo guardião completo", lista_id="L1"))
    atual["status"] = "aprovado"  # mesmo que o Claude grave errado, a mudança tem de voltar como sugerida
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False)
    return "**Refiz o plano** — encaixei um bloco novo às 16h. Quer revisar o plano?"


def esperar_fim():
    fim = time.time() + 5
    while time.time() < fim:
        try:
            c = h.bus.comandos.get(timeout=0.2)
        except Exception:
            continue
        if c[0] == "completo_fim":
            return c[1]
    return None


eventos.clear()
g.COMANDO_COMPLETO = plano_refeito
g.executar_diretivas([("completo", "refazer o plano de hoje com as pendências do fim de semana")], "quero refazer o plano de hoje")
confere("a marca completo liga o trabalho em segundo plano e avisa a tela", any(t == "completo" and d.get("ativo") for t, d in eventos), eventos[:3])
fim = esperar_fim()
novo_plano = h._plano_de_hoje()
confere("o plano refeito volta como sugerido, mesmo se o Claude gravar 'aprovado'", novo_plano["status"] == "sugerido" and any(b["id"] == "b9" for b in novo_plano["blocos"]), novo_plano.get("status"))
confere("a fala do resultado chega limpa (sem markdown nem travessão) e pede a revisão", fim and fim["mudou"] and "*" not in fim["fala"] and "—" not in fim["fala"] and fim["fala"].endswith("?"), fim)
confere("ao terminar, a tela é avisada e o plano recarrega", any(t == "completo" and not d.get("ativo") for t, d in eventos) and any(t == "plano" for t, _ in eventos))
confere("o contexto não fala mais em trabalho em andamento", "GUARDIAO COMPLETO TRABALHANDO" not in g.situacao_plano())

antes = open(os.path.join(tmp, "plano_do_dia.json"), encoding="utf-8").read()


def plano_estragado(pedido, arquivo):
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write('{"blocos": [{"id": "b1", "titulo": "sem hora"}')
    return "Pronto."


g.COMANDO_COMPLETO = plano_estragado
g.executar_diretivas([("completo", "refazer tudo")], "refaz o plano")
fim = esperar_fim()
confere("plano com defeito é desfeito e o guardião avisa", open(os.path.join(tmp, "plano_do_dia.json"), encoding="utf-8").read() == antes and fim and "desfiz" in fim["fala"], fim)

travado = threading.Event()
g.COMANDO_COMPLETO = lambda pedido, arquivo: (travado.wait(5), "Terminei.")[1]
confere("primeiro pedido entra", g.iniciar_completo("planejar a semana") is True)
confere("com um pedido em andamento, o segundo não entra", g.iniciar_completo("outro pedido") is False)
confere("enquanto trabalha, o contexto avisa a voz", "GUARDIAO COMPLETO TRABALHANDO" in g.situacao_plano())
travado.set()
esperar_fim()
eventos.clear()
g.executar_diretivas([("completo", "refazer o plano")], "que horas são")
time.sleep(0.3)
confere("a marca completo sem pedido da pessoa é ignorada", not any(t == "completo" for t, _ in eventos))
r = requests.post(URL + "/completo", json={"pedido": "Monta o meu dia."}, timeout=5)
c = h.bus.comandos.get(timeout=2)
confere("POST /completo entrega o pedido ao programa de voz", r.status_code == 202 and c == ("completo", "Monta o meu dia."), c)
def demorado(pedido, arquivo):
    raise subprocess.TimeoutExpired("claude", 1)


g.COMANDO_COMPLETO = demorado
g.iniciar_completo("pedido demorado")
fim = esperar_fim()
confere("se o Claude demorar demais, o guardião avisa e libera o próximo pedido", fim and "demorou" in fim["fala"] and g.COMPLETO is None, fim)
confere("o prompt do guardião completo proíbe o ClickUp e limita a escrita ao plano", "Não crie nem altere nada no ClickUp" in g.prompt_completo("x", "plano.json")
        and '"status": "sugerido"' in g.prompt_completo("x", "plano.json") and "Rafa Lima" in g.prompt_completo("x", "plano.json"))

# ---------------- escuta: rota de cancelar ----------------
h.bus.cancelar_escuta.clear()
confere("POST /escuta pede o cancelamento da escuta", requests.post(URL + "/escuta", json={}, timeout=5).status_code == 202 and h.bus.cancelar_escuta.is_set())
h.bus.cancelar_escuta.clear()

# ---------------- versão ----------------
CHANGELOG = """# Changelog

## 0.4.0 [CRITICAL] - 2026-11-02
- Novidade grande da quatro.
- Segunda linha.

## 0.3.1 - 2026-10-20
- Correção da três ponto um.

## 0.3.0 - 2026-10-12
- Versão instalada.
"""
confere("versões se comparam por número, não por texto", at._num("0.10.0") > at._num("0.9.3") and at._num("v1.2") == (1, 2, 0))
notas = at.notas_desde(CHANGELOG, "0.3.0", "0.4.0")
confere("notas: só as versões mais novas que a instalada, a mais recente primeiro", [n["versao"] for n in notas] == ["0.4.0", "0.3.1"] and notas[0]["critica"] and notas[0]["itens"][0] == "Novidade grande da quatro", notas)
confere("o aluno vê só o título curto de cada mudança: o negrito, ou a primeira frase; nota interna de teste fica de fora",
        at.titulo_da_mudanca("- **Mais tempo pela voz.** Detalhe técnico longo que o aluno não precisa ler.") == "Mais tempo pela voz"
        and at.titulo_da_mudanca("- Corrigido: o botão falhava. E mais detalhes.") == "Corrigido: o botão falhava"
        and at.titulo_da_mudanca("- Testado: a suíte inteira.") == "" and at.titulo_da_mudanca("- Ainda sem teste: o microfone.") == ""
        and len(at.titulo_da_mudanca("- " + "palavra " * 40)) <= 93)
longo = "## 0.5.0 - 2026-11-10\n" + "".join(f"- Item {i}.\n" for i in range(9)) + "## 0.4.9 - 2026-11-09\n- a.\n## 0.4.8 - 2026-11-08\n- b.\n## 0.4.7 - 2026-11-07\n- c.\n"
notas_longas = at.notas_desde(longo, "0.4.0", "0.5.0")
confere("no máximo 3 versões e 4 mudanças por versão no cartão", len(notas_longas) == 3 and len(notas_longas[0]["itens"]) == 4, notas_longas)

with open(os.path.join(tmp, "VERSION"), "w", encoding="utf-8") as f:
    f.write("0.3.0\n")
at.CARREGADA = "0.3.0"
at.INICIO = time.time() + 5
fonte = tempfile.mkdtemp(prefix="gv_fonte_")
raiz = os.path.join(fonte, "guardiao-triwer")
for pasta in ("app", "voz", os.path.join("voz", "hud2"), "references"):
    os.makedirs(os.path.join(raiz, pasta))


def escrever(caminho, texto):
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


escrever(os.path.join(raiz, "VERSION"), "0.3.0\n")
escrever(os.path.join(raiz, "CHANGELOG.md"), CHANGELOG)
config(atualizacao={"origem": fonte, "pasta": "guardiao-triwer"})
v = at.verificar(forcar=True)
confere("mesma versão no repositório: nada de novo", v["instalada"] == "0.3.0" and v["remota"] == "0.3.0" and v["nova"] is False and v["tem_origem"], v)
escrever(os.path.join(raiz, "VERSION"), "0.4.0\n")
confere("sem forçar, só olha o repositório uma vez por dia", at.verificar()["nova"] is False)
eventos.clear()
v = at.verificar(forcar=True)
confere("versão nova publicada: avisa, com as notas", v["nova"] and v["remota"] == "0.4.0" and [n["versao"] for n in v["notas"]] == ["0.4.0", "0.3.1"], v)
confere("a tela é avisada pelo evento versao", any(t == "versao" and d.get("nova") for t, d in eventos))
v = requests.get(URL + "/versao", timeout=5).json()
confere("GET /versao traz instalada, publicada e notas", v["instalada"] == "0.3.0" and v["nova"] and v["carregada"] == "0.3.0" and v["reiniciar"] is False, v)
config(atualizacao={"origem": os.path.join(tmp, "nao-existe")})
v = requests.post(URL + "/versao/verificar", json={}, timeout=20).json()
confere("origem errada não derruba nada: fica o aviso e o painel segue", v["erro"] and v["instalada"] == "0.3.0", v)
config(atualizacao={})
confere("sem origem configurada, o painel sabe dizer", at.verificar(forcar=True)["erro"] == "sem_origem" and at.publico()["tem_origem"] is False)
confere("sem origem, atualizar é recusado com explicação", at.atualizar()["ok"] is False)

# repositório git de verdade (local): a versão nova é vista sem mexer na cópia de trabalho
if shutil.which("git"):
    def git(pasta, *args):
        return subprocess.run(["git", "-C", pasta, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")

    remoto, clone, outro = (tempfile.mkdtemp(prefix=f"gv_git_{n}_") for n in ("remoto", "clone", "outro"))
    subprocess.run(["git", "init", "--bare", "-b", "main", remoto], capture_output=True)
    subprocess.run(["git", "clone", remoto, outro], capture_output=True)
    for chave, valor in (("user.email", "teste@teste"), ("user.name", "Teste")):
        git(outro, "config", chave, valor)
    os.makedirs(os.path.join(outro, "guardiao-triwer"))
    escrever(os.path.join(outro, "guardiao-triwer", "VERSION"), "0.3.0\n")
    escrever(os.path.join(outro, "guardiao-triwer", "CHANGELOG.md"), CHANGELOG)
    git(outro, "add", "-A"); git(outro, "commit", "-m", "v0.3.0"); git(outro, "push", "origin", "HEAD:main")
    subprocess.run(["git", "clone", "-b", "main", remoto, clone], capture_output=True)
    config(atualizacao={"origem": clone})
    confere("clone em dia: nada de novo", at.verificar(forcar=True)["nova"] is False, at.publico())
    escrever(os.path.join(outro, "guardiao-triwer", "VERSION"), "0.3.1\n")
    git(outro, "commit", "-am", "v0.3.1"); git(outro, "push", "origin", "HEAD:main")
    v = at.verificar(forcar=True)
    confere("alguém publicou a 0.3.1: o guardião vê pelo git, sem baixar nada", v["nova"] and v["remota"] == "0.3.1" and [n["versao"] for n in v["notas"]] == ["0.3.1"], v)
    confere("a cópia de trabalho do clone não foi mexida pela verificação", open(os.path.join(clone, "guardiao-triwer", "VERSION")).read().strip() == "0.3.0")

    # repositório com o guardião NA RAIZ (o público) e configuração antiga, sem o campo "pasta": a verificação não pode presumir a subpasta
    remoto2, clone2, outro2 = (tempfile.mkdtemp(prefix=f"gv_git_{n}_") for n in ("remoto", "clone", "outro"))
    subprocess.run(["git", "init", "--bare", "-b", "main", remoto2], capture_output=True)
    subprocess.run(["git", "clone", remoto2, outro2], capture_output=True)
    for chave, valor in (("user.email", "teste@teste"), ("user.name", "Teste")):
        git(outro2, "config", chave, valor)
    escrever(os.path.join(outro2, "VERSION"), "0.3.0\n")
    escrever(os.path.join(outro2, "CHANGELOG.md"), CHANGELOG)
    git(outro2, "add", "-A"); git(outro2, "commit", "-m", "v0.3.0"); git(outro2, "push", "origin", "HEAD:main")
    subprocess.run(["git", "clone", "-b", "main", remoto2, clone2], capture_output=True)
    config(atualizacao={"origem": clone2})
    confere("repositório com o guardião na raiz e configuração sem 'pasta': em dia, sem erro", at.verificar(forcar=True)["erro"] is None and at.verificar(forcar=True)["nova"] is False, at.publico())
    escrever(os.path.join(outro2, "VERSION"), "0.3.1\n")
    git(outro2, "commit", "-am", "v0.3.1"); git(outro2, "push", "origin", "HEAD:main")
    v = at.verificar(forcar=True)
    confere("repositório com o guardião na raiz: a versão nova é vista (era o caso do clone do repositório público)", v["nova"] and v["remota"] == "0.3.1" and v["erro"] is None, v)
    config(atualizacao={"origem": clone2, "pasta": ""})
    confere("e com 'pasta' vazia, que é como o instalador novo grava", at.verificar(forcar=True)["remota"] == "0.3.1")
    config(atualizacao={"origem": clone})
else:
    clone = None
    print("(git não encontrado: pulei a verificação por repositório)")

# ---------------- atualizar.ps1 numa pasta de teste ----------------
escrever(os.path.join(raiz, "VERSION"), "0.4.0\n")
escrever(os.path.join(raiz, "SKILL.md"), "skill nova")
escrever(os.path.join(raiz, "references", "painel.md"), "referência nova")
escrever(os.path.join(raiz, "app", "ler_clickup.ps1"), "# script novo")
escrever(os.path.join(raiz, "app", "tempos.json"), '{"modelo": true}')
escrever(os.path.join(raiz, "app", "config.json"), '{"nao": "deveria existir"}')
escrever(os.path.join(raiz, "voz", "guardiao_voz.py"), "# programa novo")
escrever(os.path.join(raiz, "voz", "hud2", "index.html"), "<p>painel novo</p>")
escrever(os.path.join(raiz, "voz", "preferencias.json"), '{"sons": false}')
escrever(os.path.join(raiz, "voz", "pronuncias.exemplo.json"), '{"ClickUp": "clique âp"}')
os.makedirs(os.path.join(raiz, "templates"), exist_ok=True)
escrever(os.path.join(raiz, "templates", "aprendizados.md"), "# Aprendizados de {{nome}}\nCriado em {{data}}.")
escrever(os.path.join(raiz, "templates", "perfil.md"), "modelo do perfil")
os.makedirs(os.path.join(raiz, "voz", "__pycache__"))
escrever(os.path.join(raiz, "voz", "__pycache__", "lixo.pyc"), "x")

inst = tempfile.mkdtemp(prefix="gv_inst_")
raiz_guardiao = os.path.dirname(g.BASE)  # na instalação o script fica ao lado da pasta voz; no repositório, em app\
origem_script = next(c for c in (os.path.join(raiz_guardiao, "atualizar.ps1"), os.path.join(raiz_guardiao, "app", "atualizar.ps1")) if os.path.exists(c))
shutil.copy(origem_script, os.path.join(inst, "atualizar.ps1"))
skill = os.path.join(inst, ".claude", "skills", "guardiao-triwer")
for pasta in ("voz", os.path.join("voz", "hud2"), "memoria", skill):
    os.makedirs(os.path.join(inst, pasta), exist_ok=True)
escrever(os.path.join(inst, "VERSION"), "0.3.0\n")
escrever(os.path.join(inst, "config.json"), json.dumps({"pessoa": {"nome": "Pessoa de Teste"}, "pastas": {"memoria": os.path.join(inst, "memoria")},
                                                        "atualizacao": {"origem": fonte, "pasta": "guardiao-triwer", "pastas_skill": [os.path.join(inst, "outra", "guardiao-triwer")]}}))
escrever(os.path.join(inst, "tempos.json"), '{"meus": "tempos"}')
escrever(os.path.join(inst, "plano_do_dia.json"), '{"meu": "plano"}')
escrever(os.path.join(inst, "ler_clickup.ps1"), "# script antigo")
for velho in ("servidor_tela.ps1", "tela_modelo.html", "favicon.svg"):  # a tela antiga, que saiu na 0.6.0
    escrever(os.path.join(inst, velho), "tela antiga")
escrever(os.path.join(inst, "memoria", "perfil.md"), "meu perfil")
escrever(os.path.join(inst, "voz", "guardiao_voz.py"), "# programa antigo")
escrever(os.path.join(inst, "voz", "preferencias.json"), '{"sons": true}')
escrever(os.path.join(inst, "voz", "hud2", "index.html"), "<p>painel antigo</p>")
escrever(os.path.join(skill, "SKILL.md"), "skill antiga")
escrever(os.path.join(skill, "memoria.md"), "minha memória da skill")
escrever(os.path.join(skill, "extensoes-minhas.md"), "minhas extensões")
os.makedirs(os.path.join(skill, "app"), exist_ok=True)
escrever(os.path.join(skill, "app", "servidor_tela.ps1"), "tela antiga")
skill2 = os.path.join(inst, "outra", "guardiao-triwer")  # skill instalada pelo instalar.bat: traz uma cópia do programa, que precisa acompanhar as versões
os.makedirs(os.path.join(skill2, "voz"), exist_ok=True)
escrever(os.path.join(skill2, "SKILL.md"), "skill antiga")
escrever(os.path.join(skill2, "voz", "guardiao_voz.py"), "# programa antigo")
casa = tempfile.mkdtemp(prefix="gv_casa_")  # pasta de usuário de mentira: a skill global de quem roda o teste nunca é tocada


def atualizar(*extra):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(inst, "atualizar.ps1"), "-SemReiniciar", *extra],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, env=dict(os.environ, USERPROFILE=casa))


def ler(*partes):
    with open(os.path.join(inst, *partes), encoding="utf-8-sig") as f:
        return f.read()


r = atualizar("-SoVerificar")
confere("-SoVerificar mostra as duas versões e não muda nada", "0.3.0" in r.stdout and "0.4.0" in r.stdout and ler("VERSION").strip() == "0.3.0", r.stdout + r.stderr)
r = atualizar()
confere("atualizar.ps1 termina bem", r.returncode == 0, r.stdout[-600:] + r.stderr[-600:])
confere("a versão instalada passa a ser a nova", ler("VERSION").strip() == "0.4.0")
confere("scripts, programa de voz e painel são trocados", ler("ler_clickup.ps1") == "# script novo" and ler("voz", "guardiao_voz.py") == "# programa novo" and "painel novo" in ler("voz", "hud2", "index.html"))
confere("config.json, tempos.json, plano e memória ficam como estavam",
        "Pessoa de Teste" in ler("config.json") and ler("tempos.json") == '{"meus": "tempos"}' and ler("plano_do_dia.json") == '{"meu": "plano"}' and ler("memoria", "perfil.md") == "meu perfil")
confere("a memória antiga ganha o aprendizados.md do modelo (a skill lê em toda ativação) e o perfil existente fica",
        ler("memoria", "aprendizados.md").startswith("# Aprendizados de Pessoa\nCriado em 20") and ler("memoria", "perfil.md") == "meu perfil", r.stdout[-400:])
confere("preferências da pessoa ficam; as pronúncias de exemplo entram só se ela não tiver as dela",
        ler("voz", "preferencias.json") == '{"sons": true}' and "clique" in ler("voz", "pronuncias.json"))
confere("lixo do Python não é copiado", not os.path.exists(os.path.join(inst, "voz", "__pycache__")))
confere("a skill instalada é atualizada e os arquivos pessoais dela ficam",
        open(os.path.join(skill, "SKILL.md"), encoding="utf-8").read() == "skill nova" and os.path.exists(os.path.join(skill, "references", "painel.md"))
        and open(os.path.join(skill, "memoria.md"), encoding="utf-8").read() == "minha memória da skill"
        and open(os.path.join(skill, "extensoes-minhas.md"), encoding="utf-8").read() == "minhas extensões" and not os.path.exists(os.path.join(skill, "voz")))
confere("os arquivos da tela antiga saem da pasta operacional e da skill",
        not any(os.path.exists(os.path.join(inst, v)) for v in ("servidor_tela.ps1", "tela_modelo.html", "favicon.svg")) and not os.path.exists(os.path.join(skill, "app", "servidor_tela.ps1")))
confere("a skill que traz uma cópia do programa recebe o programa novo, sem lixo nem preferências",
        open(os.path.join(skill2, "voz", "guardiao_voz.py"), encoding="utf-8").read() == "# programa novo" and open(os.path.join(skill2, "SKILL.md"), encoding="utf-8").read() == "skill nova"
        and not os.path.exists(os.path.join(skill2, "voz", "__pycache__")) and not os.path.exists(os.path.join(skill2, "voz", "preferencias.json")))
confere("fica uma cópia de segurança do código antigo", any(n.startswith("codigo_antes_0.3.0_") for n in os.listdir(os.path.join(inst, "logs"))), os.listdir(os.path.join(inst, "logs")))
res = json.loads(ler("logs", "atualizacao_resultado.json"))
confere("o resultado fica registrado para o painel", res["resultado"] == "ok" and res["de"] == "0.3.0" and res["para"] == "0.4.0", res)
r = atualizar()
confere("rodar de novo na mesma versão não faz nada", r.returncode == 0 and "Nada a fazer" in r.stdout, r.stdout)
escrever(os.path.join(inst, "config.json"), json.dumps({"atualizacao": {"origem": os.path.join(inst, "nao-existe")}}))
r = atualizar("-Forcar")
res = json.loads(ler("logs", "atualizacao_resultado.json"))
confere("origem errada: o erro fica registrado e nada é trocado", r.returncode == 1 and res["resultado"] == "erro" and ler("VERSION").strip() == "0.4.0", (r.stdout, res))
if clone:
    escrever(os.path.join(inst, "VERSION"), "0.3.0\n")
    escrever(os.path.join(inst, "config.json"), json.dumps({"atualizacao": {"origem": clone}}))
    r = atualizar()
    confere("a partir de um clone git: baixa a versão publicada (git pull) e instala", r.returncode == 0 and ler("VERSION").strip() == "0.3.1", r.stdout[-500:] + r.stderr[-300:])
    escrever(os.path.join(clone, "guardiao-triwer", "rascunho.txt"), "mudança local")
    escrever(os.path.join(inst, "VERSION"), "0.3.0\n")
    r = atualizar()
    confere("clone com mudança não publicada: para e explica, sem instalar pela metade", r.returncode == 1 and "publicadas" in r.stdout and ler("VERSION").strip() == "0.3.0", r.stdout[-400:])
    r = atualizar("-Local")
    confere("-Local instala o clone como está (para quem desenvolve)", r.returncode == 0 and ler("VERSION").strip() == "0.3.1", r.stdout[-400:])

# o botão do painel chama o script fora do programa
chamados = []
at.COMANDO_ATUALIZAR = chamados.append
config(atualizacao={"origem": fonte})
escrever(os.path.join(tmp, "atualizar.ps1"), "# de mentira")
r = requests.post(URL + "/versao/atualizar", json={}, timeout=5).json()
confere("POST /versao/atualizar dispara o script e marca 'atualizando'", r["ok"] and chamados and chamados[0].endswith("atualizar.ps1") and at.publico()["atualizando"], (r, chamados))
escrever(os.path.join(tmp, "logs", "atualizacao_resultado.json"), json.dumps({"resultado": "erro", "mensagem": "sem rede"}))
fim_espera = time.time() + 6
while at.ATUALIZANDO and time.time() < fim_espera:
    time.sleep(0.2)
confere("se o script falhar sem reiniciar o guardião, o painel deixa de mostrar 'atualizando' e avisa", not at.ATUALIZANDO and any(t == "aviso" and d.get("erro") for t, d in eventos))
escrever(os.path.join(tmp, "VERSION"), "0.4.0\n")
confere("versão no disco diferente da carregada: o programa sabe que precisa reiniciar", at.publico()["reiniciar"] is True)

# ---------------- janela compacta por cima das outras ----------------
import tkinter  # noqa: E402

janela = tkinter.Tk()
janela.title("Guardião compacto (teste)")
janela.geometry("900x700+40+40")
janela.update()
r = jan.fixar_compacta(dw=16, dh=39, titulo="Guardião compacto (teste)", principal=None, classe=None, espera=2, minimizar=False)
janela.update()
confere("a janela compacta fica por cima das outras", r.get("ok") and r.get("por_cima") is True, r)
if r.get("ok"):
    hwnd = jan._achar("Guardião compacto (teste)", None)
    anterior = jan._em_pixels_reais()
    ret = jan._retangulo(hwnd)
    info = jan._MONITORINFO()
    info.cbSize = jan.ctypes.sizeof(info)
    jan._u.GetMonitorInfoW(jan._u.MonitorFromWindow(hwnd, 2), jan.ctypes.byref(info))
    jan._voltar_modo(anterior)
    e = r["escala"]
    confere("no tamanho do palco compacto (320 x 420 mais a moldura)", abs((ret.right - ret.left) - round(336 * e)) <= 2 and abs((ret.bottom - ret.top) - round(459 * e)) <= 2, (ret.right - ret.left, ret.bottom - ret.top, e))
    confere("no canto inferior direito da área de trabalho", 0 <= info.rcWork.right - ret.right + 12 * e <= 40 * e and 0 <= info.rcWork.bottom - ret.bottom + 12 * e <= 40 * e,
            (info.rcWork.right - ret.right, info.rcWork.bottom - ret.bottom))
janela.destroy()
confere("sem a janela aberta, a resposta é um erro explicado (não derruba o servidor)", jan.fixar_compacta(titulo="Guardião compacto (teste)", classe=None, espera=0.3)["ok"] is False)
r = requests.post(URL + "/janela", json={"acao": "qualquer"}, timeout=5).json()
confere("POST /janela com ação desconhecida responde sem quebrar", r["ok"] is False, r)

for pasta in (fonte, inst):
    shutil.rmtree(pasta, ignore_errors=True)
sys.exit(0 if placar() else 1)
