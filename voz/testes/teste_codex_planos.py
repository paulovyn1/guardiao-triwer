"""Codex entrega planos por resposta; só o aplicativo grava arquivos permitidos."""
import json
import io
import os
import sys
import tempfile
import types
from unittest import mock
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import guardiao_codex as codex


def confere(ok, mensagem):
    if not ok:
        raise AssertionError(mensagem)
    print("PASSOU", mensagem)


dia = date.today().isoformat()
plano = {"data": dia, "agenda_impoe": "Sem campanha ativa hoje.", "status": "aprovado",
         "blocos": [{"id": "b1", "titulo": "Revisar agenda", "inicio": "09:00", "fim": "09:30"}]}
sys.modules["plano_base"] = types.SimpleNamespace(conferir_arquivo=lambda caminho, oper: [])

with tempfile.TemporaryDirectory(prefix="guardiao_codex_planos_") as pasta:
    mensagem = json.dumps({"fala": "Montei uma proposta.", "planos": [
        {"arquivo": "plano_do_dia.json", "conteudo": plano}]}, ensure_ascii=False)
    fala = codex._aplicar_planos(mensagem, pasta)
    caminho = os.path.join(pasta, "plano_do_dia.json")
    gravado = json.load(open(caminho, encoding="utf-8"))
    confere(fala == "Montei uma proposta." and gravado["status"] == "sugerido", "plano válido é gravado como sugerido")

    for nome in ("../config.json", "config.json", "planos/plano_outra_coisa.json"):
        try:
            codex._aplicar_planos(json.dumps({"fala": "", "planos": [
                {"arquivo": nome, "conteudo": plano}]}), pasta)
        except RuntimeError:
            pass
        else:
            raise AssertionError("aceitou caminho proibido: " + nome)
    confere(not os.path.exists(os.path.join(pasta, "config.json")), "caminhos fora dos planos são recusados")

    sys.modules["plano_base"].conferir_arquivo = lambda caminho, oper: ["erro de conferência A", "erro de conferência B"]
    try:
        codex._aplicar_planos(mensagem, pasta)
    except RuntimeError as erro:
        confere("erro de conferência A" in str(erro) and "erro de conferência B" in str(erro),
                "problemas do plano são reunidos para uma correção só")
    else:
        raise AssertionError("não reprovou plano inválido")
    confere(json.load(open(caminho, encoding="utf-8")) == gravado, "conferência reprovada restaura o plano anterior")

    sys.modules["plano_base"].conferir_arquivo = lambda caminho, oper: []
    futuro = (date.today() + timedelta(days=2)).isoformat()
    os.makedirs(os.path.join(pasta, "planos"), exist_ok=True)
    origem = {"data": futuro, "agenda_impoe": "Sem campanha ativa.", "status": "aprovado",
              "blocos": [dict(plano["blocos"][0]), {"id": "b2", "titulo": "Outra tarefa", "inicio": "10:00", "fim": "10:30"}]}
    arq_origem = os.path.join(pasta, "planos", "plano_" + futuro + ".json")
    with open(arq_origem, "w", encoding="utf-8") as arquivo:
        json.dump(origem, arquivo)
    futuro_2 = (date.today() + timedelta(days=3)).isoformat()
    arq_origem_2 = os.path.join(pasta, "planos", "plano_" + futuro_2 + ".json")
    with open(arq_origem_2, "w", encoding="utf-8") as arquivo:
        json.dump({"data": futuro_2, "agenda_impoe": "Sem campanha ativa.", "status": "aprovado",
                   "blocos": [dict(origem["blocos"][1]),
                              {"id": "b4", "titulo": "Terceira tarefa", "inicio": "11:00", "fim": "11:30"}]}, arquivo)
    arq_hoje = os.path.join(pasta, "planos", "plano_" + dia + ".json")
    with open(arq_hoje, "w", encoding="utf-8") as arquivo:
        json.dump(dict(plano, status="aprovado"), arquivo)
    codex._aplicar_planos(mensagem, pasta)
    origem_depois = json.load(open(arq_origem, encoding="utf-8"))
    origem_2_depois = json.load(open(arq_origem_2, encoding="utf-8"))
    confere(origem_depois["status"] == "sugerido" and [b["titulo"] for b in origem_depois["blocos"]] == ["Outra tarefa"],
            "movimento para outro dia remove duplicata futura e preserva os demais blocos")
    confere(origem_2_depois["status"] == "sugerido" and [b["titulo"] for b in origem_2_depois["blocos"]] == ["Terceira tarefa"],
            "duplicatas descobertas em dias incluídos também são resolvidas")
    confere(json.load(open(arq_hoje, encoding="utf-8"))["status"] == "aprovado",
            "arquivo histórico do mesmo dia não vira outra proposta")

    evento = {"type": "item.completed", "item": {"type": "agent_message", "text": mensagem}}
    fluxo = "\n".join(json.dumps(e) for e in (
        {"type": "turn.started"},
        {"type": "item.started", "item": {"type": "command_execution"}},
        evento)) + "\n"
    processo = types.SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(fluxo),
                                    returncode=0, poll=lambda: 0, wait=lambda: 0, kill=lambda: None)
    etapas = []
    with mock.patch.object(codex, "comando", return_value=["codex"]), \
         mock.patch.object(codex, "estado", return_value={"ok": True, "autenticado": True}), \
         mock.patch.object(codex.subprocess, "Popen", return_value=processo) as chamada:
        fala, _ = codex.executar("monte o plano", pasta, pode_escrever=True, progresso=etapas.append)
        argumentos = chamada.call_args.args[0]
        confere(fala == "Montei uma proposta." and argumentos[argumentos.index("--sandbox") + 1] == "read-only",
                "o modelo só lê; o aplicativo grava o plano")
        confere("Consultando arquivos" in etapas and "Conferindo a proposta" in etapas,
                "andamento da execução chega ao painel")
        limite = {"type": "error", "message": "You've hit your usage limit"}
        chamada.return_value = types.SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(json.dumps(limite) + "\n"),
                                                  returncode=1, poll=lambda: 1, wait=lambda: 1, kill=lambda: None)
        try:
            codex.executar("pergunta", pasta)
        except RuntimeError as erro:
            confere("limite de uso" in str(erro) and "Claude" in str(erro),
                    "limite da conta aparece como orientação clara")
        else:
            raise AssertionError("não mostrou o limite de uso")

    def processo_com(texto):
        final = {"type": "item.completed", "item": {"type": "agent_message", "text": texto}}
        inicio = {"type": "thread.started", "thread_id": "11111111-1111-1111-1111-111111111111"}
        fluxo = "\n".join(json.dumps(e) for e in (inicio, final)) + "\n"
        return types.SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(fluxo),
                                     returncode=0, poll=lambda: 0, wait=lambda: 0, kill=lambda: None)

    sem_plano = json.dumps({"fala": "Não cabe tudo hoje.", "planos": []}, ensure_ascii=False)
    fases = []
    with mock.patch.object(codex, "comando", return_value=["codex"]), \
         mock.patch.object(codex, "estado", return_value={"ok": True, "autenticado": True}), \
         mock.patch.object(codex.subprocess, "Popen", side_effect=[processo_com(sem_plano), processo_com(mensagem)]) as chamadas:
        fala, _ = codex.executar("Refaça o plano de hoje", pasta, pode_escrever=True,
                                exigir_plano=True, progresso=fases.append)
        confere(fala == "Montei uma proposta." and chamadas.call_count == 2
                and any("Corrigindo o plano" in fase for fase in fases),
                "falta de tempo não encerra o replanejamento: o Codex corrige")
        retomada = chamadas.call_args_list[1].args[0]
        confere(retomada[1:3] == ["exec", "resume"] and
                "11111111-1111-1111-1111-111111111111" in retomada and
                "sandbox_mode=read-only" in retomada,
                "a correção retoma a pesquisa na mesma sessão de leitura")

    conflito = dict(plano, blocos=plano["blocos"] + [{"id": "b3", "titulo": "Conflito", "inicio": "09:15", "fim": "09:45"}])
    pacote_ruim = json.dumps({"fala": "Proposta inicial.", "planos": [
        {"arquivo": "plano_do_dia.json", "conteudo": conflito}]}, ensure_ascii=False)
    with mock.patch.object(codex, "comando", return_value=["codex"]), \
         mock.patch.object(codex, "estado", return_value={"ok": True, "autenticado": True}), \
         mock.patch.object(codex.subprocess, "Popen", side_effect=[processo_com(pacote_ruim), processo_com(mensagem)]) as chamadas:
        fala, _ = codex.executar("Refaça o plano de hoje", pasta, pode_escrever=True, exigir_plano=True)
        confere(fala == "Montei uma proposta." and chamadas.call_count == 2,
                "inconsistência de horários gera correção e só grava o plano válido")
