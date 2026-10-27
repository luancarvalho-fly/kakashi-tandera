# Roda o msst/inference.py com STUBS das bibliotecas que o codigo do BandIt (Plus)
# importa so pra TREINO (asteroid, spafe, pedalboard, torch_audiomentations...).
# Nao instala nada na venv e nao mexe no repo: os stubs vivem so neste processo.
import sys, types, runpy
from unittest.mock import MagicMock
from pathlib import Path

FALTANDO = ["asteroid", "asteroid.losses", "asteroid.losses.sdr",
            "spafe", "spafe.fbanks", "spafe.fbanks.bark_fbanks", "spafe.utils", "spafe.utils.converters",
            "pedalboard", "torch_audiomentations", "audiomentations"]
for nome in FALTANDO:
    try:
        __import__(nome)
    except Exception:
        sys.modules[nome] = MagicMock(name=nome)

msst = Path(__file__).resolve().parents[2] / "msst"
sys.path.insert(0, str(msst))
sys.argv = [str(msst / "inference.py")] + sys.argv[1:]
runpy.run_path(str(msst / "inference.py"), run_name="__main__")
