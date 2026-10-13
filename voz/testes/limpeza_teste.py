"""Ao terminar, mata o Edge de teste e apaga as pastas temporárias gv_* (cada perfil do Edge ocupa centenas de MB)."""
import atexit
import glob
import os
import shutil
import subprocess
import tempfile
import time


def _limpar():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -match 'gv_edge' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    for d in glob.glob(os.path.join(tempfile.gettempdir(), "gv_*")):
        shutil.rmtree(d, ignore_errors=True)


atexit.register(_limpar)


class RelogioDeMeioDia:
    """Para o servidor, "agora" (só no formato HH:MM) é 12:00: os testes de concluir não dependem da hora em que rodam."""

    def __getattr__(self, nome):
        return getattr(time, nome)

    def strftime(self, fmt, t=None):
        if t is None and fmt == "%H:%M":
            return "12:00"
        return time.strftime(fmt, t) if t is not None else time.strftime(fmt)


def fixar_relogio(servidor):
    servidor.time = RelogioDeMeioDia()
    servidor.ARQ_PREFS = os.path.join(tempfile.mkdtemp(prefix="gv_prefs_"), "preferencias.json")  # nunca o arquivo de verdade
