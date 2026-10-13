"""Como o guardião acha e chama o Claude Code (guardiao_sessao.comando_do_claude), sem gastar nada: o instalador oficial, o npm (claude.cmd, que o Windows
não abre como "claude" e corta o pedido na primeira quebra de linha), o npm fora do PATH, a extensão do VS Code, versões antigas do npm (node e cli.js),
um atalho quebrado, nada instalado, e se o que foi achado executa de verdade. Os executáveis aqui são de mentira: só o `--version` é simulado."""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import guardiao_sessao as gs  # noqa: E402

resultados = []


def confere(nome, ok, detalhe=""):
    resultados.append(bool(ok))
    print(("PASSOU " if ok else "FALHOU ") + nome + (f" -> {detalhe}" if detalhe and not ok else ""))


# o atalho que o npm de verdade cria no Windows (copiado de uma instalação real, versão 2.1.296)
ATALHO_NPM = '\r\n@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\nCALL :find_dp0\r\n\r\n"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\bin\\claude.exe"   %*\r\n'
ATALHO_NPM_ANTIGO = '@ECHO off\r\nSETLOCAL\r\nCALL :find_dp0\r\n"%_prog%"  "%dp0%\\node_modules\\@anthropic-ai\\claude-code\\cli.js" %*\r\n'

tmp = tempfile.mkdtemp(prefix="gv_claude_")
casa = os.path.join(tmp, "usuario")
os.makedirs(os.path.join(casa, "AppData", "Roaming"))
variaveis = {k: os.environ.get(k) for k in ("PATH", "USERPROFILE", "APPDATA", "GUARDIAO_CLAUDE")}
tentativas = []  # o que o resolvedor tentou executar


def ambiente(path="", forcado=None):
    os.environ["PATH"] = path or os.environ.get("SystemRoot", r"C:\Windows")
    os.environ["USERPROFILE"] = casa
    os.environ["APPDATA"] = os.path.join(casa, "AppData", "Roaming")
    os.environ.pop("GUARDIAO_CLAUDE", None)
    if forcado:
        os.environ["GUARDIAO_CLAUDE"] = forcado
    del tentativas[:]
    gs._CLAUDE.update(comando=None, versao="", erro="", de="")


def arquivo(caminho, texto="x"):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        f.write(texto)
    return caminho


# `--version` de mentira: executa de verdade só o que a lista ESTRAGADOS não proíbe
ESTRAGADOS = set()


def executa_falso(comando):
    tentativas.append(list(comando))
    if comando[0].lower() in ESTRAGADOS:
        return "", "saiu com código 1: não executa"
    return "2.1.999 (Claude Code)", ""


executa_original = gs._executa
gs._executa = executa_falso
try:
    # ---- instalador oficial ----
    ambiente()
    oficial = arquivo(os.path.join(casa, ".local", "bin", "claude.exe"))
    confere("instalador oficial (pasta .local\\bin, fora do PATH): achado", gs.comando_do_claude() == [oficial], gs.comando_do_claude())
    confere("fica guardado: a segunda chamada não executa nada de novo", len(tentativas) == 1)

    # ---- npm no PATH (o defeito do relatório) ----
    ambiente()
    npm = os.path.join(tmp, "npm")
    arquivo(os.path.join(npm, "claude.cmd"), ATALHO_NPM)
    exe_npm = arquivo(os.path.join(npm, "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"))
    ambiente(path=npm + os.pathsep + os.environ["PATH"])
    achou = gs.comando_do_claude()
    confere("npm no PATH: não devolve o claude.cmd, devolve o claude.exe que ele chama", achou == [exe_npm], achou)
    confere("e o shutil.which, sozinho, aponta para o .cmd (o que quebrava: Popen(['claude']) não abre .cmd)", shutil.which("claude", path=npm).lower().endswith(".cmd"))

    # ---- npm fora do PATH (tarefa agendada, atalho do menu iniciar) ----
    ambiente()
    arquivo(os.path.join(casa, "AppData", "Roaming", "npm", "claude.cmd"), ATALHO_NPM)
    exe2 = arquivo(os.path.join(casa, "AppData", "Roaming", "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"))
    # (o instalador oficial de antes ainda está em .local\bin: tem preferência, pois é o que o terminal da pessoa usaria depois do PATH)
    os.remove(oficial)
    confere("npm fora do PATH: achado em %APPDATA%\\npm", gs.comando_do_claude() == [exe2], gs.comando_do_claude())

    # ---- os dois instalados: vale o que o terminal da pessoa usaria (PATH primeiro) ----
    arquivo(oficial)
    ambiente(path=npm + os.pathsep + os.environ["PATH"])
    confere("npm e instalador oficial juntos: vale o que o PATH mostra primeiro (o mesmo que a pessoa roda no terminal)", gs.comando_do_claude() == [exe_npm], gs.comando_do_claude())

    # ---- o candidato estragado é pulado ----
    ESTRAGADOS.add(exe_npm.lower())
    ambiente(path=npm + os.pathsep + os.environ["PATH"])
    confere("achado, mas não executa: passa para o próximo (o instalador oficial)", gs.comando_do_claude() == [oficial], (gs.comando_do_claude(), tentativas))
    ESTRAGADOS.clear()

    # ---- versão antiga do npm: node + cli.js ----
    ambiente()
    os.remove(oficial)
    shutil.rmtree(os.path.join(casa, "AppData", "Roaming", "npm"))
    antigo = os.path.join(tmp, "npm_antigo")
    arquivo(os.path.join(antigo, "claude.cmd"), ATALHO_NPM_ANTIGO)
    cli = arquivo(os.path.join(antigo, "node_modules", "@anthropic-ai", "claude-code", "cli.js"))
    node = arquivo(os.path.join(tmp, "nodejs", "node.exe"))
    ambiente(path=antigo + os.pathsep + os.path.dirname(node) + os.pathsep + os.environ["PATH"])
    achou = gs.comando_do_claude()
    confere("npm antigo (cli.js): chama node com o cli.js", len(achou) == 2 and achou[0].lower() == node.lower() and achou[1] == cli, achou)

    # ---- atalho quebrado ----
    quebrado = os.path.join(tmp, "npm_quebrado")
    arquivo(os.path.join(quebrado, "claude.cmd"), ATALHO_NPM)
    ambiente(path=quebrado + os.pathsep + os.environ["PATH"])
    confere("claude.cmd sem o programa por trás: não acha nada, em vez de devolver o .cmd", gs.comando_do_claude() == [], gs.comando_do_claude())
    confere("e o estado diz que não achou, com o motivo vazio (nada executou)", gs.estado_do_claude()["ok"] is False)

    # ---- nada instalado ----
    ambiente()
    confere("nada instalado: lista vazia e o aviso diz onde instalar", gs.comando_do_claude() == [] and "claude.com/claude-code" in gs.AVISO_SEM_CLAUDE)

    # ---- a extensão do VS Code, como último recurso ----
    ambiente()
    ext = arquivo(os.path.join(casa, ".vscode", "extensions", "anthropic.claude-code-2.1.296-win32-x64", "resources", "native-binary", "claude.exe"))
    confere("só a extensão do VS Code instalada: usa o executável que ela traz", gs.comando_do_claude() == [ext], gs.comando_do_claude())

    # ---- a pessoa manda ----
    ambiente(forcado=oficial)
    arquivo(oficial)
    confere("GUARDIAO_CLAUDE manda no resto", gs.comando_do_claude() == [oficial], gs.comando_do_claude())

    # ---- refazer a procura (instalou o Claude Code com o guardião aberto) ----
    ambiente()
    shutil.rmtree(os.path.join(casa, ".vscode"))
    os.remove(oficial)
    confere("sem nada: vazio", gs.comando_do_claude() == [])
    arquivo(oficial)
    confere("instalou depois: enquanto não pedir para refazer, continua 'não achei' (resultado guardado)", gs.comando_do_claude() == [])
    confere("pedindo para refazer, acha", gs.comando_do_claude(refazer=True) == [oficial])

    # ---- os testes do programa trocam o comando por um Claude de mentira ----
    gs.COMANDO = ["python", "falso.py"]
    confere("COMANDO trocado pelos testes continua valendo", gs.comando_do_claude() == ["python", "falso.py"])
    gs.COMANDO = None
finally:
    gs._executa = executa_original
    for k, v in variaveis.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    gs._CLAUDE.update(comando=None, versao="", erro="", de="")

# ---- o `--version` de verdade: executa, mede o código de saída e não trava ----
ok_versao, erro = gs._executa([sys.executable, "-c", "import sys; print('9.9.9 (Claude Code de teste)'); sys.exit(0)"])
confere("--version que funciona: devolve a versão", ok_versao.startswith("9.9.9") and not erro, (ok_versao, erro))
_, erro = gs._executa([sys.executable, "-c", "import sys; sys.exit(3)"])
confere("--version que sai com erro: reprova com o motivo", "código 3" in erro, erro)
_, erro = gs._executa([os.path.join(tmp, "nao_existe.exe")])
confere("programa que não abre: reprova com o motivo (não levanta exceção)", bool(erro), erro)

# ---- o PowerShell usa a mesma lógica (instalador, -Verificar e plano diário) ----
script = os.path.join(tmp, "ps_resolvedor.ps1")
comum = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app", "_comum.ps1")
if not os.path.exists(comum):
    comum = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "_comum.ps1")  # instalação: _comum.ps1 fica ao lado da pasta voz
if os.path.exists(comum):
    npm_ps = os.path.join(tmp, "npm_ps")
    arquivo(os.path.join(npm_ps, "claude.cmd"), ATALHO_NPM)
    # um executável que existe de verdade e responde ao --version: o cmd.exe não serve, então usa uma cópia do python do teste não é possível;
    # aqui só o que não precisa executar é conferido (a resolução do atalho), pela função de baixo nível
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(f". '{comum}'\n$r = @(Get-ClaudeReal '{os.path.join(npm_ps, 'claude.cmd')}')\n'achou=' + $r.Count\n"
                f"New-Item -ItemType Directory -Path '{os.path.join(npm_ps, 'node_modules', '@anthropic-ai', 'claude-code', 'bin')}' -Force | Out-Null\n"
                f"Set-Content -Path '{os.path.join(npm_ps, 'node_modules', '@anthropic-ai', 'claude-code', 'bin', 'claude.exe')}' -Value 'x'\n"
                f"$r = @(Get-ClaudeReal '{os.path.join(npm_ps, 'claude.cmd')}')\n'depois=' + $r.Count + ' ' + $r[0]\n")
    saida = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    linhas = saida.strip().splitlines()
    confere("PowerShell: o atalho do npm sem o exe por trás não resolve; com o exe, devolve o caminho do claude.exe (um só item, não uma letra)",
            len(linhas) >= 2 and linhas[0] == "achou=0" and linhas[1].startswith("depois=1 ") and linhas[1].endswith("claude.exe"), saida)
else:
    print("(não achei o _comum.ps1: pulei a parte do PowerShell)")

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) else 1)
