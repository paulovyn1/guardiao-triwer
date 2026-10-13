"""O que a voz lê (fala.py): links viram o título ou o domínio, sem https, barras nem códigos. O texto da tela não passa por aqui."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import tempfile  # noqa: E402
import fala  # noqa: E402
from fala import normalizar_para_fala as f  # noqa: E402

# sem arquivo de pronúncias: o teste não depende do de quem roda (numa instalação o exemplo é copiado, e "CPL" passa a ser lido "cê pê éle")
PRONUNCIAS = os.path.join(tempfile.mkdtemp(prefix="gv_pron_"), "pronuncias.json")
fala.ARQ_PRONUNCIAS = PRONUNCIAS

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


r = f("Não havia tarefa sua para esse post, então criei uma na lista Conteúdos: [Post do desafio de outubro](https://app.clickup.com/t/86exemplo1). Pode abrir e finalizar por lá.")
confere("tarefa do ClickUp citada como link: a voz diz só o título", "Post do desafio de outubro. Pode abrir" in r and "http" not in r and "clickup" not in r.lower().replace("click up", "") and "86ex" not in r and "[" not in r and "(" not in r, r)
r = f("A página de vendas está em https://cpl.triwer.com.br/inscricao-aberta?utm_source=ig&x=1, pode conferir.")
confere("endereço solto: domínio e nome da página, sem https e sem o que vem depois da interrogação", r == "A página de vendas está em cpl ponto triwer ponto com ponto br, página inscricao aberta, pode conferir.", r)
r = f("Veja em https://www.youtube.com/watch?v=dQw4w9WgXcQ.")
confere("sem nome de página que preste, só o domínio (e o ponto final continua)", r == "Veja em youtube ponto com.", r)
r = f("O arquivo está em https://drive.google.com/file/d/1AbC9xYz77kLmNoPq/view e a tarefa em https://app.clickup.com/t/86a1b2c3.")
confere("código no meio do endereço não é lido, e tarefa do ClickUp sem título vira 'um link do ClickUp'", r == "O arquivo está em drive ponto google ponto com e a tarefa em um link do ClickUp.", r)
r = f("Abra www.triwer.com.br e [o painel](http://localhost:8767/v2/).")
confere("endereço sem https e link com título qualquer", r == "Abra triwer ponto com ponto br e o painel.", r)
r = f("[https://cpl.triwer.com.br/obrigado](https://cpl.triwer.com.br/obrigado)")
confere("link cujo título é o próprio endereço", r == "cpl ponto triwer ponto com ponto br, página obrigado", r)
a, b = f("Criei a tarefa [Post do desafio,"), f("de outubro](https://app.clickup.com/t/86exemplo1) na lista Conteúdos.")
confere("link cortado entre duas frases: nenhuma das metades lê o endereço nem os colchetes", a == "Criei a tarefa Post do desafio," and b == "de outubro na lista Conteúdos.", (a, b))
r = f("Das 14h às 16h30, lista [urgente] com 3 itens (veja o item 2).")
confere("texto sem link continua igual ao de antes", r == "Das catorze horas às dezesseis e meia, lista [urgente] com três itens (veja o item dois).", r)
# ---- a pronúncia que a pessoa define vale, inclusive dentro de um endereço dito em voz alta
with open(PRONUNCIAS, "w", encoding="utf-8") as arq:
    arq.write('{"CPL": "cê pê éle", "ClickUp": "clique âp"}')
r = f("O CPL abriu e o ClickUp avisou.")
confere("pronúncia própria do arquivo de pronúncias vale (CPL e ClickUp)", r == "O cê pê éle abriu e o clique âp avisou.", r)
os.remove(PRONUNCIAS)
r = f("O CPL abriu.")
confere("sem o arquivo, a sigla fica como está", r == "O CPL abriu.", r)

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
