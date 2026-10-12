# Carrega a escuta (Vosk) e a voz (Kokoro) de um jeito que funciona em qualquer pasta, inclusive quando o nome do usuário do
# Windows tem acento ("C:\Users\José\..."). As bibliotecas por baixo (Kaldi e espeak-ng) abrem os arquivos delas com funções antigas
# do Windows, que não entendem o caminho completo com acento. A saída: ficar na pasta do programa e dar a elas caminhos relativos,
# que não têm acento nenhum.
import os

VOZ_ONNX = os.path.join("kokoro", "kokoro-v1.0.int8.onnx")
VOZ_TIMBRES = os.path.join("kokoro", "voices-v1.0.bin")


def _relativo(caminho, base):
    """O caminho visto a partir da base. Se não der (outro disco), devolve o próprio caminho."""
    try:
        rel = os.path.relpath(str(caminho), base)
    except ValueError:
        return str(caminho)
    return str(caminho) if rel.startswith("..") else rel


def carregar_escuta(base):
    """O modelo de escuta da pasta <base>\\modelo."""
    from vosk import Model

    os.chdir(base)
    return Model("modelo")


def _espeak_com_caminho_relativo(base):
    """Faz o espeak-ng receber a pasta de dados dele como caminho relativo à pasta do programa."""
    try:
        from phonemizer.backend.espeak import wrapper
    except Exception:
        return
    original = wrapper.EspeakAPI
    if getattr(original, "_guardiao", False):
        return

    class EspeakRelativo(original):
        _guardiao = True

        def __init__(self, library, data_path):
            super().__init__(library, _relativo(data_path, base) if data_path is not None else None)

    wrapper.EspeakAPI = EspeakRelativo


def carregar_voz(base):
    """O Kokoro com os arquivos de <base>\\kokoro. Deixa o programa na pasta base: o espeak-ng lê os dados dele aos poucos, sempre a partir dela."""
    from kokoro_onnx import Kokoro

    os.chdir(base)
    _espeak_com_caminho_relativo(base)
    return Kokoro(VOZ_ONNX, VOZ_TIMBRES)
