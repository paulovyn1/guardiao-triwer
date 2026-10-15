"""Verificador da configuração (2026-10-14): usuário que atualiza sem os campos novos recebe pendência (o guardião segue funcionando);
completo, nada aparece; a rotina da pessoa (chegada, nobre, parar) vale nas contas no lugar do padrão; o padrão volta quando o campo sai."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import checar_config as cc
import visao_semana as vs

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHA"), nome, "" if ok else extra)
    falhas += 0 if ok else 1


oper = tempfile.mkdtemp()


def config(rotina):
    with open(os.path.join(oper, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"rotina": rotina}, f, ensure_ascii=False)


confere("sem config.json (antes do onboarding): nenhuma pendência", cc.pendencias(oper) == [])
config({"chegada": "09:00", "almoco": "12:00"})
ids = [p["id"] for p in cc.pendencias(oper)]
confere("usuário antigo que atualizou: as três pendências aparecem", ids == ["fixos_semana", "parar_por_dia", "horario_nobre"], ids)
t = cc.texto(oper)
confere("o texto manda deduzir dos arquivos, perguntar só o que faltar e não bloquear", "semana-base.md" in t and "pergunte só o que não estiver escrito" in t and "Não bloqueie" in t, t)
completa = {"chegada": "09:00", "fixos_semana": [{"dias": [0, 1, 2, 3, 4], "inicio": "12:00", "fim": "13:00", "titulo": "Almoço"}],
            "parar_por_dia": {"seg": "18:00", "sex": "17:00"}, "horario_nobre": [["09:00", "11:30"], ["20:00", "fim"]]}
config(completa)
confere("configuração completa: nada aparece", cc.pendencias(oper) == [] and cc.texto(oper) == "")

vs.aplicar_rotina({"rotina": completa})
confere("a rotina da pessoa vale nas contas: chegada, nobre e hora de parar", vs.CHEGADA == 9 * 60 and vs.NOBRE_MANHA == (9 * 60, 11 * 60 + 30)
        and vs.NOBRE_NOITE_INICIO == 20 * 60 and vs.hora_de_parar(date(2026, 10, 19)) == 18 * 60 and vs.hora_de_parar(date(2026, 10, 23)) == 17 * 60)
vs.aplicar_rotina({"rotina": {"horario_nobre": [["07:00", "fim"]]}})
confere("uma faixa só: sem nobre à noite", vs.NOBRE_MANHA == (7 * 60, 24 * 60) and vs.NOBRE_NOITE_INICIO == 24 * 60)
vs.aplicar_rotina({})
confere("campo que sai do config volta ao padrão", vs.CHEGADA == 8 * 60 + 40 and vs.NOBRE_MANHA == (8 * 60 + 40, 13 * 60) and vs.PARAR_CONFIG == {})
vs.aplicar_rotina({"rotina": {"chegada": "xx", "horario_nobre": "errado", "parar_por_dia": {"seg": "?"}}})
confere("valor inválido não derruba nada: fica o padrão", vs.CHEGADA == 8 * 60 + 40 and vs.NOBRE_MANHA == (8 * 60 + 40, 13 * 60) and vs.PARAR_CONFIG == {})
sys.exit(1 if falhas else 0)
