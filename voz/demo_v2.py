# Demonstração do painel novo, sem microfone, sem Claude e sem ClickUp: um dia de exemplo numa pasta temporária, na porta 8768.
# Serve para mostrar a tela a alguém. O que se escreve na barra recebe uma resposta fixa; os botões da tela funcionam de verdade (dentro do exemplo).
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from datetime import date, datetime, timedelta

import hud_servidor as h
import janela_painel
import guardiao_v2 as v2

PORTA = 8768
tmp = tempfile.mkdtemp(prefix="guardiao_demo_")
h.OPER = tmp
h.ARQ_PREFS = os.path.join(tmp, "preferencias.json")
h._token_clickup = lambda: None
for pasta in ("planos", "registros", "logs", os.path.join("memoria", "pops")):
    os.makedirs(os.path.join(tmp, pasta), exist_ok=True)
agora = datetime.now().replace(second=0, microsecond=0)
hm = lambda minutos: (agora + timedelta(minutes=minutos)).strftime("%H:%M")  # noqa: E731


def bloco(i, ini, fim, titulo, frente, passo, porque):
    return {"id": f"b{i}", "inicio": hm(ini), "fim": hm(fim), "titulo": titulo, "dono": "Você", "frente": frente,
            "descricao": f"{titulo}. Está pronto quando o resultado estiver entregue.", "primeiro_passo": passo, "por_que_agora": porque}


plano = {"data": date.today().isoformat(), "status": "aprovado", "exemplo": True, "aviso": "Dia de exemplo: nada aqui é real e nada vai para o ClickUp.",
         "fixos": [{"inicio": hm(200), "fim": hm(260), "titulo": "Reunião com o cliente"}],
         "blocos": [bloco(1, -120, -90, "Responder as mensagens dos clientes", "Atendimento", "Abra o WhatsApp e comece pelo mais antigo.", "Cliente esperando perde confiança."),
                    bloco(2, -50, 40, "Montar as campanhas de tráfego da Clínica Vitta", "Tráfego", "Abra a tarefa e releia o briefing.", "É a entrega de maior peso do dia."),
                    bloco(3, 40, 70, "Revisar o roteiro do vídeo da Padaria Sol", "Conteúdo", "Leia o roteiro até o fim sem editar.", "A gravação é amanhã cedo."),
                    bloco(4, 70, 130, "Fechar o relatório mensal da Loja Nativa", "Relatórios", "Exporte os números do mês.", "O cliente espera o relatório hoje."),
                    bloco(5, 130, 160, "Gravar os stories da semana", "Conteúdo", "Separe o celular e a lista de temas.", "Gravar em lote economiza a semana.")]}
with open(os.path.join(tmp, "plano_do_dia.json"), "w", encoding="utf-8") as f:
    json.dump(plano, f, ensure_ascii=False)
with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"pessoa": {"nome": "Você"}, "agente": {"nome": "Guardião"}, "pastas": {"memoria": os.path.join(tmp, "memoria")}, "rotina": {}, "clickup": {}}, f, ensure_ascii=False)
h.concluir_bloco({"id": "b1", "concluido": True, "inicio": plano["blocos"][0]["inicio"], "fim": plano["blocos"][0]["fim"]})
h.bus.emitir("saude", mic=False, groq=False, claude=False, voz="demonstração")
h.bus.emitir("estado", v="aguardando")


def falar(texto):
    h.bus.emitir("estado", v="falando")
    for i in range(3, len(texto) + 3, 3):
        h.bus.emitir("guardiao_texto", texto=texto[:i])
        time.sleep(0.07)
    h.bus.emitir("guardiao_fim", texto=texto)
    h.bus.emitir("estado", v="aguardando")


def atender():
    while True:
        try:
            tipo, valor = h.bus.comandos.get(timeout=1)
        except queue.Empty:
            continue
        if tipo == "perguntar":
            h.bus.emitir("voce", texto=valor)
            h.bus.emitir("estado", v="pensando")
            time.sleep(0.9)
            falar("Esta é a demonstração: aqui eu não estou ligado ao Claude. No guardião de verdade eu respondo, crio tarefas e ajusto o plano.")
        elif tipo == "checkin":
            falar(valor.get("texto") or "")
        elif tipo == "dizer" and valor:
            falar(str(valor))
        elif tipo == "saudacao":
            h.bus.portao_saudacao.wait(timeout=15)
            falar("Olá. Este é um dia de exemplo. Entre no modo execução para ver como eu acompanho o tempo da tarefa.")
        elif tipo in ("roteiro", "ditar", "acionar"):
            falar("Na demonstração o microfone fica desligado. Use os botões e o campo de texto.")


if not h.iniciar_servidor(PORTA):
    raise SystemExit(f"A porta {PORTA} está ocupada. Feche a outra demonstração e tente de novo.")
threading.Thread(target=atender, daemon=True).start()
janela_painel.abrir(f"http://localhost:{PORTA}/v2/?abertura=1")  # o mesmo jeito de abrir do painel de verdade: navegador padrão, perfil da pessoa
time.sleep(1800)  # fecha sozinha em 30 minutos
