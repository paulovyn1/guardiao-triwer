import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import tempfile  # noqa: E402
import hud_servidor as h  # noqa: E402
import guardiao_voz as g  # noqa: E402

h.OPER = g.OPER = tempfile.mkdtemp(prefix="gv_oper_dir_")  # nada de log dentro da pasta do repositório (o erro do Claude vai para logs\)

res = []


def confere(nome, ok, det=""):
    res.append(ok)
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {det}" if det and not ok else ""))


# ---- 1) mascarar / extrair / campos ----
t = "{{foco:b2}} Primeira frase. {{concluir:b2|Revisão feita. Tudo certo, sem pendência}} Segunda frase aqui."
m = g.mascarar(t)
confere("mascarar mantém o tamanho", len(m) == len(t))
confere("mascarar esconde pontos dentro da diretiva", ". Tudo" not in m and "Primeira frase." in m, m)
limpo, d = g.extrair_diretivas(t)
confere("extrair separa texto e marcas", limpo == "Primeira frase. Segunda frase aqui." and [x[0] for x in d] == ["foco", "concluir"], (limpo, d))
confere("diretiva aberta no fim não vaza para o texto", g.extrair_diretivas("Oi {{foco:b2")[0] == "Oi")
confere("campos lê chave=valor", g.campos("titulo=Pagar hospedagem|lista=Contas a pagar|prazo=2026-10-11 10:00") == {"titulo": "Pagar hospedagem", "lista": "Contas a pagar", "prazo": "2026-10-11 10:00"})


# ---- 2) corte de frases em streaming, com a marca partida em vários pedaços ----
class FakeProc:
    def __init__(self, textos):
        linhas = [json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"text": x}}}) + "\n" for x in textos]
        self.stdout = iter(linhas)

    def terminate(self):
        pass


texto = "{{detalhe:b2}} A tarefa da Marina é finalizar o contrato, das 15h às 18h. {{concluir:b2|Contrato enviado. Falta só assinar}} Concluindo agora, ok? Depois a gente vê o resto."
pedacos = [texto[i:i + 7] for i in range(0, len(texto), 7)]
g.subprocess.Popen = lambda *a, **k: FakeProc(pedacos)
g.comando_claude = lambda p, streaming=False, modelo=None: ([], {})
frases = list(g.frases_do_claude("x"))
confere("streaming não parte a diretiva no meio", all(f.count("{{") == f.count("}}") for f in frases), frases)
confere("streaming preserva todas as marcas", sum(len(g.extrair_diretivas(f)[1]) for f in frases) == 2, frases)
confere("o texto falado sai sem marcas", all("{{" not in g.extrair_diretivas(f)[0] for f in frases), [g.extrair_diretivas(f)[0] for f in frases])
print("  frases:", [g.extrair_diretivas(f) for f in frases])

# ---- 3) guarda de intenção ----
confere("concluir exige o Rafa ter pedido", g.permitido("concluir", "conclui a tarefa da Marina") and not g.permitido("concluir", "o que eu tenho amanhã?"))
confere("contar que já está feito libera concluir (caso real: já revisei, já foi para aprovação)",
        g.permitido("concluir", "Eu já disse que já foi para aprovação, eu já revisei") and g.permitido("concluir", "já mandei pra aprovação") and g.permitido("concluir", "tá feita também"))
confere("negar o feito não libera concluir", not g.permitido("concluir", "ainda não revisei") and not g.permitido("concluir", "não mandei ainda"))
confere("criar exige pedido de criar", g.permitido("criar", "cria uma tarefa para pagar a hospedagem") and not g.permitido("criar", "quais são as tarefas de amanhã"))
confere("resposta sim/não", g.SIM.search(g._norm("sim, pode criar")) and g.NAO.search(g._norm("não, cancela")) and not g.NAO.search(g._norm("pode criar")))

# ---- 4) o Claude de verdade emite as marcas certas? (só lê, nada é executado). Gasta chamadas: só roda com --real ----
if "--real" not in sys.argv:
    print(f"\n{sum(res)} de {len(res)} verificações passaram (a parte com o Claude de verdade só roda com --real).")
    sys.exit(0 if all(res) else 1)
import importlib  # noqa: E402

importlib.reload(g)  # volta o Popen/comando_claude de verdade
casos = [
    ("me fala da tarefa da Marina", ["detalhe"], []),
    ("quais são as minhas tarefas de amanhã?", ["foco"], ["concluir", "criar", "comentar"]),
    ("conclui a tarefa de revisar a skill do guardião, já terminei de revisar tudo", [], []),
    ("anota na tarefa do Caio que o briefing está esperando o cliente", ["comentar"], []),
    ("cria uma tarefa para pagar a hospedagem do site da empresa amanhã às 10 horas, na lista de contas a pagar", ["criar"], []),
    ("o que eu tenho agora?", [], ["concluir", "criar", "comentar", "reabrir"]),
]
for pergunta, esperadas, proibidas in casos:
    t0 = time.time()
    resposta, seg = g.perguntar_claude(pergunta)
    limpo, dirs = g.extrair_diretivas(resposta)
    nomes = [n for n, _ in dirs]
    print(f"\n>> {pergunta}  ({seg:.1f}s)\n   fala: {limpo}\n   marcas: {dirs}")
    confere("  traz as marcas esperadas " + str(esperadas), all(e in nomes for e in esperadas), nomes)
    confere("  não traz marcas proibidas " + str(proibidas), not any(p in nomes for p in proibidas), nomes)

print(f"\n{sum(res)} de {len(res)} verificações passaram.")
