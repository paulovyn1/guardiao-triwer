"""Quebras de linha da resposta do Claude no caminho até a tela (sem navegador e sem Claude): o corte em frases mantém a lista e o parágrafo,
a voz não lê as marcas, a tela recebe o texto com "\n" e o que o guardião lembra também. Antes, tudo chegava emendado: "- **a** - **b**"."""
import os
import queue
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import fala  # noqa: E402
import guardiao_voz as g  # noqa: E402
import hud_servidor as h  # noqa: E402
import quebras  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe!r}" if not ok and detalhe != "" else ""))


def cortar(texto, tamanhos):
    """Alimenta o Cortador em pedaços do tamanho dado (como chega do Claude) e devolve o texto que a tela mostraria."""
    c, partes, i, n = g.Cortador(), [], 0, 0
    while i < len(texto):
        t = tamanhos[n % len(tamanhos)]
        partes += c.alimentar(texto[i:i + t])
        i += t
        n += 1
    resto = c.resto()
    if resto:
        partes.append(resto)
    return quebras.para_tela(" ".join(g.extrair_diretivas(p)[0] for p in partes)), partes


LISTA = ("Esta é a proposta de hoje:\n- **11h às 12h30:** revisar os vídeos do Carlos.\n- **15h às 17h:** as seis tarefas com prazo de hoje.\n"
         "- **17h45 às 20h:** Portal do Cliente.\n\nPosso rodar a conferência e gravar o plano?")
for tam in ([1], [3], [7], [11, 2, 5], [40], [500]):
    tela, partes = cortar(LISTA, tam)
    confere(f"corte em pedaços de {tam}: a lista e o parágrafo chegam como estavam", tela == LISTA, tela)
confere("cada item da lista é uma frase e a quebra vem antes dele", sum(1 for p in cortar(LISTA, [9])[1] if p.startswith(quebras.QUEBRA)) >= 2)
confere("a marca de parágrafo vem antes da pergunta final", any(p.startswith(quebras.PARAGRAFO) and "Posso rodar" in p for p in cortar(LISTA, [9])[1]))

ANINHADA = "Tarefas:\n- **15h:** as seis tarefas\n  - o bug da Central\n  - os fluxos\n    - detalhe fundo\n- **17h:** fim."
for tam in ([1], [5], [60]):
    confere(f"sublista: o recuo de cada nível chega à tela (pedaços de {tam})", cortar(ANINHADA, tam)[0] == ANINHADA, cortar(ANINHADA, tam)[0])
confere("a voz ignora o recuo", "" not in fala.normalizar_para_fala("a" + quebras.QUEBRA + quebras.RECUO + "- b"))

SIMPLES = "Tudo certo. Já deixei o plano pronto para amanhã. Quer revisar agora?"
confere("texto sem quebra continua igual (sem marca nenhuma)", cortar(SIMPLES, [5])[0] == SIMPLES and not any(c in "".join(cortar(SIMPLES, [5])[1]) for c in (quebras.QUEBRA, quebras.PARAGRAFO)))
confere("espaço duplo e tabulação viram um espaço só", cortar("Um  dois\tTrês quatro.", [4])[0] == "Um dois Três quatro.")
tela, _ = cortar("Primeiro item.\r\nSegundo item.\r\n\r\nFim.", [6])
confere("fim de linha do Windows (\r\n) também vira quebra", tela == "Primeiro item.\nSegundo item.\n\nFim.", tela)
tela, _ = cortar("Ok.\n\n\n\nDepois.", [3])
confere("várias linhas em branco viram um parágrafo só", tela == "Ok.\n\nDepois.", tela)
tela, partes = cortar("Frase curta.\nOutra.\nE mais uma frase um pouco maior para fechar.", [4])
confere("frase curtinha junta com a próxima sem perder a quebra de linha", tela == "Frase curta.\nOutra.\nE mais uma frase um pouco maior para fechar.", tela)
tela, _ = cortar("Veja os pontos:\n1. Primeiro\n2. Segundo\n3. Terceiro", [5])
confere("lista numerada sem ponto final: cada número numa linha", tela == "Veja os pontos:\n1. Primeiro\n2. Segundo\n3. Terceiro", tela)
tela, _ = cortar("{{foco:b1}}Primeira tarefa.\n{{foco:b2}}Segunda tarefa.", [6])
confere("as marcas {{foco}} saem do texto e a quebra fica", tela == "Primeira tarefa.\nSegunda tarefa.", tela)

# a voz
fal = fala.normalizar_para_fala("Hoje:" + quebras.QUEBRA + "- **11h às 12h30:** revisar." + quebras.PARAGRAFO + "Posso rodar?")
confere("a voz não lê as marcas nem o marcador de lista", not any(c in fal for c in (quebras.QUEBRA, quebras.PARAGRAFO, "*", " - ")) and "Posso rodar" in fal, fal)
confere("a voz lê o texto em uma linha só", "\n" not in fal and "revisar" in fal, fal)

# a tela e a memória
q = h.bus.assinar()
h.bus.emitir("guardiao_texto", texto="Lista:" + quebras.QUEBRA + "- um" + quebras.QUEBRA + "- dois")
h.bus.emitir("guardiao_fim", texto="Fim." + quebras.PARAGRAFO + "Tchau")
evs = []
while True:
    try:
        evs.append(q.get_nowait())
    except queue.Empty:
        break
txt = [e["texto"] for e in evs if e["t"] in ("guardiao_texto", "guardiao_fim")]
confere("o servidor entrega à tela o texto com as quebras de linha de verdade", txt == ["Lista:\n- um\n- dois", "Fim.\n\nTchau"], txt)
confere("texto sem marca passa intacto pelo servidor", (h.bus.emitir("guardiao_texto", texto="Oi, tudo bem?") or True) and quebras.para_tela("Oi, tudo bem?") == "Oi, tudo bem?")
confere("o que é lembrado não leva as marcas", quebras.para_tela("a" + quebras.QUEBRA + "b") == "a\nb" and quebras.QUEBRA not in quebras.para_tela("a" + quebras.QUEBRA + "b"))

print(f"\n{sum(resultados)} de {len(resultados)} checagens passaram.")
raise SystemExit(0 if all(resultados) else 1)
