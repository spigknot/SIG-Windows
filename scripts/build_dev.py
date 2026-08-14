"""Build de desenvolvimento do sig.exe (dist/ flat) preservando os assets de runtime.

Uso: python scripts/build_dev.py

Por que este script existe (em vez de rodar PyInstaller direto):
- usa ``--clean``: o cache de ``build/`` já saiu com código velho em builds
  anteriores (o PyInstaller reusava o PYZ antigo e o ``sig.exe`` saía
  desatualizado sem nenhum erro);
- "achata" a saída onedir: o ``sig.spec`` gera ``dist/sig/sig.exe`` +
  ``dist/sig/_internal``, mas o projeto espera o layout flat
  ``dist/sig.exe`` + ``dist/_internal`` (o mesmo que o ``release.py``
  consome e que os assets de runtime esperam);
- preserva ``ffmpeg.exe``, ``ffplay.exe``, ``vad_worker.py`` e ``vad_deps``
  em ``dist/`` (o ``--clean`` do PyInstaller só limpa ``build/``, nunca
  ``dist/``, então os assets não são tocados).
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.run(list(args), cwd=ROOT, check=True)


def main() -> int:
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "sig.spec")

    nested = DIST / "sig"
    if not nested.is_dir():
        print("ERRO: dist/sig não foi gerado pelo PyInstaller")
        return 1

    # Achata o layout onedir: dist/sig/* -> dist/*
    for name in ("sig.exe", "_internal", "modelos"):
        src = nested / name
        dst = DIST / name
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            shutil.move(str(src), str(dst))
    shutil.rmtree(nested, ignore_errors=True)

    exe = DIST / "sig.exe"
    if not exe.is_file():
        print("ERRO: dist/sig.exe não encontrado após o flatten")
        return 1

    # Sanidade: o PYZ deve ser mais novo que o fonte (senão é código velho).
    pyz = ROOT / "build" / "sig" / "PYZ-00.pyz"
    source = ROOT / "src" / "sig_app.py"
    if pyz.is_file() and source.is_file():
        if pyz.stat().st_mtime_ns < source.stat().st_mtime_ns:
            print(
                "AVISO: build/sig/PYZ-00.pyz é mais antigo que src/sig_app.py "
                "— o exe pode estar com código desatualizado."
            )

    print(f"OK: {exe} pronto (layout flat), assets de runtime preservados em {DIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
