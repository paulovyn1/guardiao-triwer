# Tarefa que já existe no ClickUp não é criada de novo: título igual vira a mesma, mesmo assunto com outras palavras é avisado,
# tarefas irmãs (carrossel A e B, copy e design) continuam separadas.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hud_servidor as h  # noqa: E402

resultados = []


def confere(nome, ok, extra=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + ("" if ok else f" -> {extra}"))


def T(nome):
    return {"nome": nome, "id": "x", "url": "u"}


abertas = [T("Preparar e enviar as VSLs reduzidas para Carlos gravar"), T("Aprovar o reels manifesto"),
           T("Design do carrossel A (posta qua 14)"), T("Copy do carrossel B (posta sex 16)"), T("Copy do carrossel A (posta qua 14)")]
casos = [
    ("Reduzir as VSLs do Carlos de 20 para 8 minutos", "parecida"),  # o caso real de 13/10: Zapia criou uma, o guardião outra
    ("Aprovar o reels manifesto!", "exata"),
    ("Copy do carrossel A (posta qua 14)", "exata"),
    ("Copy do carrossel C (posta seg 19)", "nenhuma"),
    ("Design do carrossel B (posta sex 16)", "nenhuma"),
    ("Pagar o cartão Itaú", "nenhuma"),
]
for titulo, esperado in casos:
    achada, exata = h.achar_parecida(titulo, abertas)
    obtido = "nenhuma" if not achada else ("exata" if exata else "parecida")
    confere(f"{titulo} -> {esperado}", obtido == esperado, obtido)

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
