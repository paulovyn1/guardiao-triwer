"""Conferência do plano (2026-10-14): campanha encerrada sai da exigência, gravação sem leitura é negada, sobreposição e removido voltando são barrados."""
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conferencia_plano as cp

falhas = 0


def confere(nome, ok):
    global falhas
    print(("ok   " if ok else "FALHA"), nome)
    falhas += 0 if ok else 1


mem = tempfile.mkdtemp()
os.makedirs(os.path.join(mem, "campanhas"))


def campanha(slug, ini, fim, status):
    with open(os.path.join(mem, "campanhas", slug + ".md"), "w", encoding="utf-8") as f:
        f.write(f"---\nnome: {slug}\nslug: {slug}\ndata_inicio: {ini}\ndata_fim: {fim}\nstatus: {status}\n---\n# x\n")


hoje = date(2026, 10, 14)
campanha("viva", "2026-10-08", "2026-11-03", "em-execucao")
campanha("acabou", "2026-10-01", "2026-10-13", "em-execucao")
campanha("encerrada", "2026-10-01", "2026-11-03", "concluida")
campanha("longe", "2026-12-01", "2026-12-10", "planejando")
campanha("proxima", "2026-10-28", "2026-10-30", "planejando")
confere("só as campanhas que pesam hoje", sorted(cp.campanhas_ativas(mem, hoje)) == ["proxima", "viva"])
confere("Read da nota conta", cp.slug_lido("Read", {"file_path": "C:/x/campanhas/viva.md"}, mem) == "viva")
confere("ler_campanha.ps1 conta", cp.slug_lido("PowerShell", {"command": "powershell -File ler_campanha.ps1 -Slug proxima"}, mem) == "proxima")
confere("outro Read não conta", cp.slug_lido("Read", {"file_path": "C:/x/perfil.md"}, mem) is None)
confere("plano de hoje é arquivo de plano", cp.eh_arquivo_de_plano("D:/a/plano_do_dia.json") and cp.eh_arquivo_de_plano("D:/a/planos/plano_2026-10-15.json"))
confere("outro json não é", not cp.eh_arquivo_de_plano("D:/a/resumo_clickup.json"))

bom = {"agenda_impoe": "roteiro até 21/10", "fixos": [], "blocos": [{"id": "b1", "inicio": "16:55", "fim": "17:40", "titulo": "Material de aula"}]}
confere("plano limpo passa", cp.conferir(bom) == [])
confere("sem agenda_impoe barra", any("agenda_impoe" in p for p in cp.conferir({"blocos": []})))
sobre = dict(bom, blocos=bom["blocos"] + [{"id": "b2", "inicio": "17:30", "fim": "17:50", "titulo": "Stories"}])
confere("sobreposição barra", any("sobrepõe" in p for p in cp.conferir(sobre)))
confere("bloco já feito não conta na sobreposição", cp.conferir(sobre, feitos={"b2"}) == [])
volta = dict(bom, blocos=bom["blocos"] + [{"id": "b7", "inicio": "18:00", "fim": "18:15", "titulo": "Aprovações do Vitor (1 do Carlos)"}])
confere("removido não volta", any("Vitor" in p for p in cp.conferir(volta, {"removidos": ["Aprovações do Vitor"]})))
sys.exit(1 if falhas else 0)
