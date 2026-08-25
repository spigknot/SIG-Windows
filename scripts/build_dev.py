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
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def run(*args: str, quiet: bool = False) -> int:
    command = list(args)
    if quiet:
        log_path = ROOT / "build" / "build_dev.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                text=True,
            )
        if result.returncode != 0:
            print(f"ERRO: build falhou ({result.returncode}); consulte {log_path}")
        return result.returncode
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build de desenvolvimento do SIG Windows")
    parser.add_argument("--quiet", action="store_true", help="mostrar somente o resumo; manter log em build/build_dev.log")
    args = parser.parse_args(argv)
    pyinstaller_args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean"]
    if args.quiet:
        pyinstaller_args.extend(["--log-level", "WARN"])
    pyinstaller_args.append("sig.spec")
    if run(*pyinstaller_args, quiet=args.quiet) != 0:
        return 1

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

    # Sincroniza prompts/ e modelos/ da raiz para dist/: o exe lê os arquivos
    # ao lado dele com PRIORIDADE (assistant_prompts._prompt_path), então o
    # dist desatualizaria os prompts que o usuário edita na raiz.
    for relative in ("prompts", "modelos"):
        source_dir = ROOT / relative
        target_dir = DIST / relative
        if source_dir.is_dir():
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(source_dir, target_dir)
            if not args.quiet:
                print(f"+ sincronizado {relative}/ da raiz para dist/")

    if args.quiet:
        print(f"PASS: build_dev sig.exe size={exe.stat().st_size}")
    else:
        print(f"OK: {exe} pronto (layout flat), assets de runtime preservados em {DIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
