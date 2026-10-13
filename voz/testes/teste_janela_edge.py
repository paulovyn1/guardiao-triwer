"""A janela do painel (janela_edge.py), sem abrir o Edge: as opções que impedem o perfil do guardião de entrar na conta Microsoft da pessoa, de sincronizar
e de rodar extensões; como se reconhece um perfil que já entrou na conta (as versões antigas abriam o Edge sem essas opções); e a limpeza dele, que
nunca mexe num perfil que está em uso."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import janela_edge as je  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


tmp = tempfile.mkdtemp(prefix="gv_edge_")
args = je.argumentos("http://localhost:8767/v2/", "1456,939", os.path.join(tmp, "perfil com espaço"))
confere("a janela abre sem sincronização, sem a entrada automática na conta Microsoft e sem extensões",
        "--disable-sync" in args and "--disable-features=msImplicitSignin" in args and "--disable-extensions" in args, args)
confere("é uma janela de aplicativo, com perfil só do guardião e o som da abertura liberado",
        "--app=http://localhost:8767/v2/" in args and any(a.startswith("--user-data-dir=") for a in args) and "--autoplay-policy=no-user-gesture-required" in args, args)
confere("sem a tela de boas-vindas do Edge (que oferece entrar na conta)", "--no-first-run" in args)


def perfil(nome, preferencias):
    pasta = os.path.join(tmp, nome)
    os.makedirs(os.path.join(pasta, "Default"))
    with open(os.path.join(pasta, "Default", "Preferences"), "w", encoding="utf-8") as f:
        json.dump(preferencias, f)
    with open(os.path.join(pasta, "Default", "Bookmarks"), "w") as f:
        f.write("favoritos da pessoa")
    return pasta


# o que o Edge gravou num perfil medido de verdade, com e sem as opções
com_conta = perfil("com_conta", {"account_info": [{"email": "pessoa@exemplo.com", "account_id": "1"}], "google": {"services": {"consented_to_sync": True}}, "sync": {"bookmarks": True}})
so_sync = perfil("so_sync", {"google": {"services": {"consented_to_sync": True}}})
limpo = perfil("limpo", {"account_info": [], "signin": {"allowed": True}, "edge": {"services": {"signin_scoped_device_id": "x"}}})
vazio = os.path.join(tmp, "nao_existe")
confere("perfil que entrou na conta e sincronizou é reconhecido", je.perfil_contaminado(com_conta))
confere("perfil que só tem o consentimento de sincronizar também", je.perfil_contaminado(so_sync))
confere("perfil novo, aberto com as opções seguras, não é contaminado", not je.perfil_contaminado(limpo))
confere("perfil que ainda não existe não é contaminado (e não dá erro)", not je.perfil_contaminado(vazio))

# em uso: o Edge segura o lockfile enquanto roda (aqui, um arquivo aberto faz o mesmo papel)
with open(os.path.join(com_conta, "lockfile"), "w") as f:
    f.write("x")
trava = open(os.path.join(com_conta, "lockfile"), "r")
confere("com o Edge do painel aberto, o perfil é visto como em uso", je.em_uso(com_conta))
confere("e então a limpeza não mexe em nada (nem nos favoritos que ele guarda)", not je.limpar_perfil_contaminado(com_conta) and os.path.exists(os.path.join(com_conta, "Default", "Bookmarks")))
trava.close()
confere("fechado o Edge, o perfil não está mais em uso", not je.em_uso(com_conta))
confere("a limpeza apaga o perfil contaminado do guardião (favoritos, senhas e extensões sincronizados saem da pasta)", je.limpar_perfil_contaminado(com_conta) and not os.path.exists(com_conta))
confere("perfil limpo é deixado como está (guarda as preferências da tela)", not je.limpar_perfil_contaminado(limpo) and os.path.exists(os.path.join(limpo, "Default", "Preferences")))
confere("perfil que não existe: nada a fazer", not je.limpar_perfil_contaminado(vazio))
confere("sem Edge, abrir cai no navegador padrão sem dar erro", callable(je.abrir))

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
