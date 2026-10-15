"""Ajuste das tarefas agendadas e do atalho de quem já tem o guardião instalado (roda sozinho quando o guardião liga, em segundo plano).

O que muda (0.9.8, caso de 15/10/2026):
- a tarefa que chamava "powershell -WindowStyle Hidden" passa a chamar o pythonw com sem_janela.py: nenhuma janela de terminal pisca;
- o gatilho de logon ganha um atraso, para o guardião não disputar o computador com o resto do Windows que está ligando (e o som do
  computador, que demora a ficar pronto em alguns aparelhos, já estar no ar quando ele falar);
- a tarefa antiga "avisos" sai: quem mantém o aviso ligado é o próprio guardião.
Por que aqui e não no atualizar.ps1: quem roda durante uma atualização é o atualizar.ps1 da versão antiga. O guardião novo, ao ligar, é o
primeiro código novo que roda. Tudo é idempotente: tarefa já ajustada fica como está.
Instalação nova já nasce assim (scripts\\registrar_tarefas.ps1)."""
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

PREFIXO = "Guardiao Triwer - "
ATRASO_LOGON = {"tela": "PT30S", "voz": "PT1M", "ler ClickUp": "PT1M", "gerar plano": "PT2M"}
ANTIGAS = ("avisos",)
NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ARQUIVO_PS = re.compile(r'-File\s+"([^"]+)"\s*(.*)$', re.IGNORECASE)


def _tag(nome):
    return f"{{{NS}}}{nome}"


def converter(xml, pythonw, lancador, atraso):
    """Recebe o XML de uma tarefa e devolve o XML ajustado, ou None se não há nada a mudar.
    Troca a ação "powershell.exe ... -File script" por "pythonw sem_janela.py script" e põe o atraso nos gatilhos de logon que não têm."""
    ET.register_namespace("", NS)
    raiz = ET.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", xml))  # texto com a declaração de codificação o ElementTree recusa
    mudou = False
    for exe in raiz.iter(_tag("Exec")):
        cmd, args = exe.find(_tag("Command")), exe.find(_tag("Arguments"))
        if cmd is None or "powershell" not in (cmd.text or "").lower():
            continue
        achou = _ARQUIVO_PS.search((args.text if args is not None else "") or "")
        if not achou:
            continue
        script, resto = achou.group(1), achou.group(2).strip()
        cmd.text = pythonw
        if args is None:
            args = ET.SubElement(exe, _tag("Arguments"))
        args.text = f'"{lancador}" "{script}"' + (f" {resto}" if resto else "")
        pasta = exe.find(_tag("WorkingDirectory"))
        if pasta is None:
            pasta = ET.SubElement(exe, _tag("WorkingDirectory"))
        pasta.text = os.path.dirname(lancador)
        mudou = True
    if atraso:
        for gatilho in raiz.iter(_tag("LogonTrigger")):
            if gatilho.find(_tag("Delay")) is None:
                ET.SubElement(gatilho, _tag("Delay")).text = atraso
                mudou = True
    return ET.tostring(raiz, encoding="unicode") if mudou else None


def _schtasks(*args):
    return subprocess.run(["schtasks", *args], capture_output=True, creationflags=SEM_JANELA, timeout=30)


def _texto(saida):
    """O schtasks escreve em UTF-16 (com /xml) ou na página de código do console; aqui só interessa o texto."""
    for cod in ("utf-16", "utf-8", "cp850"):
        try:
            t = saida.decode(cod)
            if "<Task" in t or cod == "cp850":
                return t
        except UnicodeDecodeError:
            continue
    return ""


def listar():
    """Os nomes das tarefas do guardião deste usuário (sem o prefixo)."""
    r = _schtasks("/query", "/fo", "csv", "/nh")
    nomes = []
    for linha in _texto(r.stdout).splitlines():
        nome = linha.split('","')[0].strip('"').lstrip("\\")
        if nome.startswith(PREFIXO):
            nomes.append(nome[len(PREFIXO):])
    return sorted(set(nomes))


def ajustar(voz, anotar=print):
    """Ajusta as tarefas existentes. Devolve a lista do que mudou (para o registro)."""
    pythonw = os.path.join(voz, ".venv", "Scripts", "pythonw.exe")
    lancador = os.path.join(voz, "sem_janela.py")
    if not (os.path.exists(pythonw) and os.path.exists(lancador)):
        return []
    feitos = []
    for nome in listar():
        completo = PREFIXO + nome
        if nome in ANTIGAS:
            if _schtasks("/delete", "/tn", completo, "/f").returncode == 0:
                feitos.append(f"tarefa antiga apagada: {nome}")
            continue
        r = _schtasks("/query", "/tn", completo, "/xml")
        if r.returncode:
            continue
        novo = converter(_texto(r.stdout), pythonw, lancador, ATRASO_LOGON.get(nome))
        if not novo:
            continue
        arq = os.path.join(tempfile.gettempdir(), f"guardiao_tarefa_{os.getpid()}.xml")
        try:
            with open(arq, "w", encoding="utf-16") as f:
                f.write('<?xml version="1.0" encoding="UTF-16"?>\n' + novo)
            if _schtasks("/create", "/tn", completo, "/xml", arq, "/f").returncode == 0:
                feitos.append(f"tarefa sem janela e com atraso no logon: {nome}")
            else:
                anotar(f"  (não consegui ajustar a tarefa {nome})")
        finally:
            try:
                os.remove(arq)
            except OSError:
                pass
    if ajustar_atalho(voz):
        feitos.append("atalho da área de trabalho sem janela")
    if renovar_avisos(os.path.dirname(voz)):
        feitos.append("aviso por pop-up reiniciado com o código novo")
    for f in feitos:
        anotar(f"  ({f})")
    return feitos


def renovar_avisos(oper):
    """Fecha o avisos.ps1 que ainda roda o código de antes de uma atualização (o arquivo mudou depois que ele ligou). O próprio guardião o
    liga de novo em até 30 s (vigiar_avisos), já com o código novo. Antes, o aviso velho seguia até reiniciar o computador. Devolve True se fechou."""
    script = os.path.join(oper, "avisos.ps1")
    if not os.path.exists(script):
        return False
    literal = script.replace("'", "''")  # aspas simples no caminho (nome de usuário com apóstrofo) dobradas, como o PowerShell pede
    comando = (f"$arq = '{literal}';$m = (Get-Item -LiteralPath $arq).LastWriteTime; "
               "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -and "
               "$_.CommandLine.ToLower().Contains($arq.ToLower()) -and $_.CreationDate -lt $m } | "
               "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; 'fechado' }")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", comando], capture_output=True,
                       creationflags=SEM_JANELA, timeout=60)
    return b"fechado" in r.stdout


def atalho_usa_powershell(caminho):
    """O atalho aponta para o powershell? (o .lnk guarda o caminho em ANSI e em UTF-16; basta achar o nome do programa)"""
    try:
        with open(caminho, "rb") as f:
            dados = f.read().lower()
    except OSError:
        return False
    return b"powershell.exe" in dados or "powershell.exe".encode("utf-16-le") in dados


def area_de_trabalho():
    """A pasta da área de trabalho de verdade (pode estar no OneDrive), como o Windows diz."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
            return winreg.QueryValueEx(k, "Desktop")[0]
    except OSError:
        return os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")


def ajustar_atalho(voz, area=None):
    """Recria o atalho "Guardião" da área de trabalho se ele ainda abre pelo powershell (que pisca uma janela). Devolve True se recriou."""
    area = area or area_de_trabalho()
    caminho = os.path.join(area, "Guardião.lnk")
    script = os.path.join(voz, "criar_atalho.ps1")
    if not (os.path.exists(caminho) and os.path.exists(script) and atalho_usa_powershell(caminho)):
        return False
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script],
                       capture_output=True, creationflags=SEM_JANELA, timeout=60)
    return r.returncode == 0 and not atalho_usa_powershell(caminho)
