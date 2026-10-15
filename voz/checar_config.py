"""Verificador da configuração: depois de uma atualização, confere se os arquivos da pessoa têm o que as versões novas usam.

Roda sem Claude e sem rede, a cada vez que o contexto do guardião é montado (custa milissegundos). O que faltar vira PENDÊNCIA: o guardião
continua funcionando com o padrão, avisa em uma frase na primeira conversa e propõe resolver. Para resolver, ele DEDUZ dos arquivos que a
pessoa já preencheu no onboarding (semana-base.md, perfil.md), mostra o que deduziu, pergunta só o que não estiver escrito e grava no
config.json. Nada do conteúdo dos arquivos da pessoa é reescrito: só entra o campo que falta.

Versão nova que passar a exigir um campo: acrescentar uma checagem em CHECAGENS. Assim ninguém precisa lembrar de migrar à mão.
Uso: python checar_config.py   -> imprime as pendências (sai 1 se houver)"""
import json
import os
import sys

OPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _json(caminho):
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _rotina(cfg):
    return (cfg or {}).get("rotina") or {}


# Cada checagem: (id, desde a versão, está faltando?(cfg), o que é, de onde deduzir e como gravar)
CHECAGENS = [
    ("fixos_semana", "0.9.3",
     lambda cfg: not _rotina(cfg).get("fixos_semana"),
     "os compromissos fixos de cada dia (almoço, reuniões, lives, aprovações)",
     "Deduza de semana-base.md (Compromissos fixos e Agenda por dia) e grave em config.json, rotina.fixos_semana: "
     "[{\"dias\": [0, 1, 2, 3, 4], \"inicio\": \"13:00\", \"fim\": \"14:00\", \"titulo\": \"Almoço\"}, ...], com 0 = segunda e 4 = sexta. "
     "Compromisso de data avulsa ou quinzenal vai em rotina.fixos_datas: [{\"data\": \"AAAA-MM-DD\", \"inicio\", \"fim\", \"titulo\"}]."),
    ("parar_por_dia", "0.9.3",
     lambda cfg: not _rotina(cfg).get("parar_por_dia"),
     "a hora de parar de cada dia de trabalho",
     "Deduza de perfil.md (Agenda por dia ou Relógio) e de semana-base.md e grave em config.json, rotina.parar_por_dia: "
     "{\"seg\": \"19:00\", \"ter\": \"19:20\", ...}, só os dias de trabalho."),
    ("horario_nobre", "0.9.3",
     lambda cfg: not _rotina(cfg).get("horario_nobre"),
     "as faixas do dia para trabalho pesado (copy, decisão, estratégia)",
     "Deduza de perfil.md (Relógio ou Faixas do dia por tipo de trabalho) e grave em config.json, rotina.horario_nobre: "
     "[[\"08:40\", \"13:00\"], [\"18:00\", \"fim\"]], onde \"fim\" é a hora de parar do dia. No máximo duas faixas."),
]


def pendencias(oper=OPER):
    cfg = _json(os.path.join(oper, "config.json"))
    if cfg is None:
        return []  # sem config.json ainda: é o onboarding que cuida, não esta checagem
    return [{"id": i, "desde": v, "o_que": o, "como": c} for i, v, falta, o, c in CHECAGENS if falta(cfg)]


def texto(oper=OPER):
    """Bloco para o contexto do guardião. Vazio quando não há pendência."""
    p = pendencias(oper)
    if not p:
        return ""
    linhas = ["CONFIGURAÇÃO PENDENTE (veio com a atualização; o guardião segue funcionando com o padrão, mas as contas de horário ficam piores):",
              *[f"- Falta {x['o_que']}. {x['como']}" for x in p],
              "Como tratar: na primeira resposta desta conversa, depois de atender o pedido, avise em uma frase que a atualização precisa de um ajuste "
              "rápido e proponha fazer agora. Não bloqueie nada e não repita o aviso na mesma conversa se a pessoa disser depois. Ao resolver: deduza "
              "dos arquivos citados, mostre em poucas frases o que deduziu, pergunte só o que não estiver escrito, e grave no config.json da pasta "
              "operacional só o campo que falta, sem mudar o resto do arquivo. Depois de gravar, a pendência some sozinha."]
    return "\n".join(linhas)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    t = texto()
    print(t or "Configuração completa.")
    sys.exit(1 if t else 0)
