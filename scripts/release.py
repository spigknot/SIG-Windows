"""Official local build/release command for SIG Windows.

Examples:

    python scripts/release.py validate --warn-path build/sig/warn-sig.txt
    python scripts/release.py tests
    python scripts/release.py preflight --quiet
    python scripts/release.py ui-smoke --quiet
    python scripts/release.py release --version 20260806_005 --incremental

The release command never uses the repository's existing dist/sig.exe. It
builds into a unique clean work directory and only uses the configured runtime
bundle for static assets whose source is currently outside Git.
"""

from __future__ import annotations

import argparse
import io
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import warnings
import zipfile
from pathlib import Path, PurePosixPath

from release_validation import (
    ValidationError,
    frozen_app_version,
    read_app_version,
    read_manifest,
    sha256_file,
    source_fingerprint,
    validate_build_info,
    validate_current,
    validate_frozen_dependencies,
    validate_manifest_shape,
    validate_manifest_signature,
    validate_package_layout,
    validate_pyinstaller_warnings,
    validate_runtime_assets,
    validate_updater_artifact,
    validate_version_consistency,
    validate_zip_layout,
    write_build_info,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_updater_harness(root: Path):
    root_text = str(root.resolve())
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return importlib.import_module("updater_v2.harness").run


def load_ui_smoke(root: Path):
    scripts_dir = str((root / "scripts").resolve())
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module("ui_smoke").run


def latest_generated_full_package(root: Path) -> Path:
    candidates = []
    for path in (root / "release" / "generated").glob("*/*.zip"):
        if not path.is_file() or not (path.parent / "package" / "vad_deps").is_dir():
            continue
        explicit_full_exists = any(
            sibling.name.endswith("_full.zip")
            for sibling in path.parent.glob("*.zip")
        )
        if (
            (explicit_full_exists and path.name.endswith("_full.zip"))
            or (not explicit_full_exists and path.name == f"{path.parent.name}.zip")
        ):
            candidates.append(path)
    if not candidates:
        raise ValidationError(
            "nenhum pacote full validado foi encontrado em release/generated; "
            "informe --package-zip ou gere uma release primeiro"
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def check_build_environment() -> None:
    try:
        import PyInstaller  # noqa: F401
        import _sounddevice_data  # noqa: F401
        import pypdfium2  # noqa: F401
        import sounddevice as sd
        import websocket
    except Exception as exc:
        raise ValidationError(
            f"ambiente de build inválido ({sys.executable}): {exc}. "
            "Use o Python configurado para o PyInstaller."
        ) from exc
    if not getattr(websocket, "WebSocketApp", None) or not getattr(websocket, "ABNF", None):
        raise ValidationError("websocket-client está instalado, mas sua API necessária não está disponível")
    portaudio = Path(str(getattr(sd, "_libname", "")))
    if not portaudio.is_file():
        raise ValidationError(f"PortAudio não está carregável no ambiente de build: {portaudio}")


def run_command(
    command: list[str],
    cwd: Path,
    log_path: Path,
    environment: dict[str, str] | None = None,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(
            command,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
            env=environment,
        )
    if process.returncode != 0:
        raise ValidationError(
            f"comando falhou ({process.returncode}): {' '.join(command)}\n"
            f"Consulte {log_path}"
        )


def copy_runtime_assets(runtime_root: Path, package_root: Path, updater_path: Path | None = None) -> None:
    required = ("ffmpeg.exe", "ffplay.exe", "ffprobe.exe", "vad_deps")
    for relative in required:
        source = runtime_root / relative
        if not source.exists():
            raise ValidationError(f"runtime asset ausente: {source}")
        destination = package_root / relative
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
    updater_source = updater_path or (runtime_root / "SigUpdater.exe")
    if not updater_source.is_file():
        raise ValidationError(f"SigUpdater.exe ausente: {updater_source}")
    shutil.copy2(updater_source, package_root / "SigUpdater.exe")


def zip_directory(source_root: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        raise ValidationError(f"ZIP de saída já existe: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path in sorted(source_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_root).as_posix())


INCREMENTAL_EXCLUDED_TOP_LEVEL = {
    "ffmpeg.exe",
    "ffplay.exe",
    "ffprobe.exe",
    "vad_worker.py",
    "vad_deps",
}


def create_incremental_tree(source_root: Path, destination_root: Path) -> None:
    """Copy only files that an existing onedir installation may replace.

    Runtime assets are deliberately excluded: they are large, machine-local
    dependencies and belong to the full GitHub package.  The updater keeps
    every excluded asset already present at the destination.
    """
    if destination_root.exists():
        raise ValidationError(f"diretório incremental já existe: {destination_root}")
    destination_root.mkdir(parents=True)
    for child in sorted(source_root.iterdir(), key=lambda path: path.name.casefold()):
        if child.name in INCREMENTAL_EXCLUDED_TOP_LEVEL:
            continue
        destination = destination_root / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def _version_parts(version: str) -> tuple[int, ...]:
    match = re.fullmatch(r"(\d{4})(\d{2})(\d{2})_(\d{3})", version or "")
    if not match:
        return (-1,)
    return tuple(int(part) for part in match.groups())


def build_content_snapshot(package_root: Path) -> dict[str, dict]:
    """Hash de todos os arquivos que a incremental gerencia (sem runtime)."""
    snapshot: dict[str, dict] = {}
    for path in sorted(package_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        relative = path.relative_to(package_root).as_posix()
        if relative.split("/", 1)[0] in INCREMENTAL_EXCLUDED_TOP_LEVEL:
            continue
        snapshot[relative] = {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
    return snapshot


def read_content_snapshots(root: Path) -> dict[str, dict]:
    """Lê release/content_snapshot.json: {versão: {relpath: {sha256, size}}}."""
    path = root / "release" / "content_snapshot.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    snapshots: dict[str, dict] = {}
    for version, entry in data.items():
        files = entry.get("files", {}) if isinstance(entry, dict) else {}
        if isinstance(files, dict):
            snapshots[str(version)] = files
    return snapshots


def latest_snapshot_before(root: Path, version: str) -> tuple[str, dict] | None:
    """Entrada mais recente do snapshot com versão menor que a atual."""
    candidates = [
        (snapshot_version, files)
        for snapshot_version, files in read_content_snapshots(root).items()
        if _version_parts(snapshot_version) < _version_parts(version) and files
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: _version_parts(item[0]))


def find_iscc() -> Path | None:
    """Localiza o ISCC.exe do Inno Setup 6 (instalador)."""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def build_installer(root: Path, version: str, *, quiet: bool = False) -> Path | None:
    """Gera o instalador (Inno Setup) a partir do package validado.

    O setup.exe é um canal ADICIONAL (instalação assistida com atalhos) e só
    é publicado como asset do GitHub — o mecanismo de atualização continua
    sendo o sync por arquivo / ZIP.
    """
    iscc = find_iscc()
    if iscc is None:
        print("AVISO: Inno Setup não encontrado — instalador não gerado.")
        return None
    setup_exe = root / "release" / "generated" / version / f"setup_sig_{version}.exe"
    if setup_exe.exists():
        setup_exe.unlink()
    result = subprocess.run(
        [str(iscc), f"-DAppVersion={version}", str(root / "installer" / "sig_installer.iss")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0 or not setup_exe.exists():
        print("ERRO: falha ao gerar o instalador:")
        print(result.stdout[-800:])
        print(result.stderr[-800:])
        return None
    if not quiet:
        print(f"PASS: instalador gerado para GitHub: {setup_exe}")
    return setup_exe


def build_installer_online(root: Path, version: str, *, quiet: bool = False) -> Path | None:
    """Gera o instalador online (PyInstaller onefile + UAC).

    O instalador online baixa o pacote full da última release do GitHub e
    instala com atalhos, sem pacote embutido.
    """
    python = sys.executable
    output = root / "release" / "generated" / version / f"online_setup_sig{version}.exe"
    if output.exists():
        output.unlink()
    work = root / "build" / "installer_online"
    result = subprocess.run(
        [
            str(python), "-m", "PyInstaller", "--onefile", "--windowed", "--uac-admin",
            "--name", f"online_setup_sig{version}",
            "--distpath", str(output.parent),
            "--workpath", str(work),
            "--specpath", str(work),
            "--clean", "--noconfirm",
            str(root / "installer" / "installer_online.py"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0 or not output.exists():
        print("ERRO: falha ao gerar o instalador online:")
        print(result.stdout[-1000:])
        print(result.stderr[-1000:])
        return None
    if not quiet:
        print(f"PASS: instalador online gerado para GitHub: {output}")
    return output


def write_snapshot_entry(root: Path, version: str, files: dict[str, dict]) -> None:
    """Adiciona/substitui a entrada da versão no snapshot versionado."""
    snapshots = read_content_snapshots(root)
    snapshots.pop(version, None)
    snapshots[version] = files
    ordered = dict(sorted(snapshots.items(), key=lambda item: _version_parts(item[0])))
    path = root / "release" / "content_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {snapshot_version: {"files": snapshot_files} for snapshot_version, snapshot_files in ordered.items()},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def create_incremental_diff_tree(
    source_root: Path,
    destination_root: Path,
    previous_files: dict[str, dict],
) -> tuple[int, int]:
    """Monta a incremental por diff (hash por arquivo).

    Inclui apenas arquivos novos/alterados em relação ao snapshot anterior e
    escreve ``removidos.txt`` com os caminhos que sumiram. Retorna
    ``(incluídos, removidos)``.
    """
    if destination_root.exists():
        raise ValidationError(f"diretório incremental já existe: {destination_root}")
    destination_root.mkdir(parents=True)
    previous = {
        str(name): str(entry.get("sha256") or "")
        for name, entry in previous_files.items()
    }
    # Estes identificam o pacote instalado e sempre viajam (prompts/modelos
    # são pequenos e mantêm os padrões editáveis em dia).
    always_top_levels = {"sig.exe", "build-info.json", "prompts", "modelos"}
    included = 0
    current_names: set[str] = set()
    for path in sorted(source_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root).as_posix()
        if relative.split("/", 1)[0] in INCREMENTAL_EXCLUDED_TOP_LEVEL:
            continue
        current_names.add(relative)
        if relative.split("/", 1)[0] in always_top_levels or previous.get(relative) != sha256_file(path):
            destination = destination_root / Path(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            included += 1
    removed = sorted(
        name
        for name in previous
        if name not in current_names and name.split("/", 1)[0] not in INCREMENTAL_EXCLUDED_TOP_LEVEL
    )
    (destination_root / "removidos.txt").write_text(
        "\n".join(removed) + ("\n" if removed else ""),
        encoding="utf-8",
    )
    return included, len(removed)


def verify_build_environment() -> None:
    """Gate do ambiente de build por VERSÕES (sem depender de caminho absoluto).

    O ambiente aprovado é Python 3.11.0 + PyInstaller 6.21.0 (o hash do
    SigUpdater reprodutível depende deles). Divergência falha com diagnóstico
    acionável em vez de produzir um artefato de hash diferente.
    """
    problems = []
    python_version = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
    if sys.version_info[:3] != (3, 11, 0):
        problems.append(
            f"Python em execução: {python_version} (aprovado: 3.11.0). "
            "Use uma instalação Python 3.11.0 — ver AGENTS.md, seção 'Build do aplicativo'."
        )
    try:
        import PyInstaller

        pyinstaller_version = PyInstaller.__version__
        if pyinstaller_version != "6.21.0":
            problems.append(
                f"PyInstaller em execução: {pyinstaller_version} (aprovado: 6.21.0)."
            )
    except ImportError:
        problems.append("PyInstaller não instalado (aprovado: 6.21.0).")
    if problems:
        raise ValidationError("Ambiente de build divergente do aprovado. " + " ".join(problems))


def build_release(args: argparse.Namespace) -> int:
    quiet = bool(getattr(args, "quiet", False))
    verify_build_environment()
    root = repo_root()
    source_version = read_app_version(root / "src/sig_app.py")
    version = args.version or source_version
    if version != source_version:
        raise ValidationError(
            f"a versão do comando ({version}) diverge de APP_VERSION ({source_version}); "
            "altere somente APP_VERSION e execute novamente"
        )
    snapshots = read_content_snapshots(root)
    current_version = max(snapshots, key=_version_parts) if snapshots else ""
    if version <= current_version and not args.allow_same:
        raise ValidationError(f"release {version} não é posterior à versão publicada {current_version}")

    check_build_environment()
    # O harness do updater roda abaixo, com o pacote NOVO (com ffprobe). O
    # preflight interno não deve rodá-lo contra o pacote da última release:
    # quando um runtime asset novo é adicionado (ex.: ffprobe), o pacote
    # antigo não o contém e o updater novo o rejeitaria (falso negativo).
    run_preflight(root, quiet=True, skip_updater_harness=True)
    runtime_root = (args.runtime_root or root / "dist").resolve()
    runtime_manifest = root / "scripts/runtime_artifact.json"
    validate_runtime_assets(runtime_root, runtime_manifest)
    output_root = (args.output_root or root / "release/generated" / version).resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise ValidationError(f"diretório de saída não está vazio: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    build_started = time.time()
    build_id = uuid.uuid4().hex
    work_root = Path(tempfile.mkdtemp(prefix=f"sig-clean-build-{version}-"))
    try:
        updater_build_dir = work_root / "updater-dist"
        updater_work_dir = work_root / "updater-work"
        updater_environment = os.environ.copy()
        updater_environment["SOURCE_DATE_EPOCH"] = "946684800"
        updater_environment["PYTHONHASHSEED"] = "0"
        # Use a stable PyInstaller work/spec path. A random temporary path
        # changes the one-file binary hash and makes the release gate reject
        # an otherwise identical updater.
        run_command(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onefile",
                "--windowed",
                "--noupx",
                "--name",
                "SigUpdater",
                "--distpath",
                str(updater_build_dir),
                "--workpath",
                str(root / "build" / "updater_v2"),
                "--specpath",
                str(root / "build" / "updater_v2"),
                str(root / "updater_v2" / "updater.py"),
            ],
            root,
            output_root / "pyinstaller-updater.log",
            updater_environment,
        )
        fresh_updater = updater_build_dir / "SigUpdater.exe"
        if not fresh_updater.is_file():
            raise ValidationError("PyInstaller não produziu o SigUpdater.exe endurecido")
        pyinstaller_dist = work_root / "pyinstaller-dist"
        pyinstaller_work = work_root / "pyinstaller-work"
        run_command(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--distpath",
                str(pyinstaller_dist),
                "--workpath",
                str(pyinstaller_work),
                "sig.spec",
            ],
            root,
            output_root / "pyinstaller.log",
        )
        fresh_pyinstaller_root = pyinstaller_dist / "sig"
        if not fresh_pyinstaller_root.is_dir():
            raise ValidationError("PyInstaller não produziu a pasta sig no dist limpo")

        package_root = output_root / "package"
        shutil.copytree(fresh_pyinstaller_root, package_root)
        shutil.copytree(root / "prompts", package_root / "prompts")
        shutil.copytree(root / "modelos", package_root / "modelos")
        copy_runtime_assets(runtime_root, package_root, fresh_updater)
        shutil.copy2(root / "src/vad_worker.py", package_root / "vad_worker.py")
        validate_runtime_assets(package_root, runtime_manifest)
        write_build_info(package_root, root, version, build_id, build_started, runtime_manifest)

        warning_path = pyinstaller_work / "sig" / "warn-sig.txt"
        validate_pyinstaller_warnings(warning_path)
        # Keep the exact warning report from this clean build beside the
        # generated package before the temporary PyInstaller work tree is
        # removed. This makes the release decision auditable and repeatable.
        shutil.copy2(warning_path, output_root / "warn-sig.txt")
        validate_package_layout(package_root, full=True)
        validate_frozen_dependencies(package_root)
        validate_updater_artifact(package_root, root / "scripts/updater_artifact.json")
        frozen_version = frozen_app_version(package_root / "sig.exe")
        if frozen_version != version:
            raise ValidationError(
                f"sig.exe recém-gerado contém {frozen_version}, esperado {version}"
            )
        validate_build_info(package_root, root, version, build_started, runtime_manifest)

        if args.incremental:
            full_zip_path = output_root / f"{version}_full.zip"
            zip_directory(package_root, full_zip_path)
            validate_zip_layout(full_zip_path, full=True)
            # A sincronização por arquivo é publicada depois pelo
            # scripts/sync_r2.py com o package gerado aqui. O ZIP incremental
            # foi aposentado: o snapshot continua como referência de conteúdo.
            write_snapshot_entry(root, version, build_content_snapshot(package_root))
            if not quiet:
                print(
                    "AVISO: release/content_snapshot.json foi atualizado; "
                    "commite-o junto com a publicação."
                )
                print(f"PASS: pacote full local preservado para GitHub: {full_zip_path}")
                print("PASS: sincronização incremental será publicada por sync_r2.py (arquivo por arquivo).")
            build_installer(root, version, quiet=quiet)
            build_installer_online(root, version, quiet=quiet)
        else:
            zip_path = output_root / f"{version}.zip"
            zip_directory(package_root, zip_path)
            validate_zip_layout(zip_path, full=True)
        # Exercise the exact ZIP and helper that are about to be published.
        # This runs only in the disposable harness and never touches the
        # user's installation.
        run_updater_test = load_updater_harness(root)

        try:
            harness_messages = list(run_updater_test(
                package_root / "SigUpdater.exe",
                full_zip_path if args.incremental else zip_path,
                args.updater_timeout,
            ))
        except AssertionError as exc:
            raise ValidationError(str(exc)) from None
        if not quiet:
            for message in harness_messages:
                print(f"PASS: {message}")
        if not args.incremental and not quiet:
            print(f"PASS: build limpo e pacote validado: {zip_path}")
        if quiet:
            package_kind = "full+package" if args.incremental else "full"
            print(
                f"PASS: release {version} kind={package_kind} "
                f"harness={len(harness_messages)}"
            )
        return 0
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


def validate_command(args: argparse.Namespace) -> int:
    verify_build_environment()
    root = repo_root()
    messages = validate_current(
        root,
        (args.package_root or root / "dist").resolve(),
        args.manifest.resolve() if args.manifest else None,
        (args.updater_metadata or root / "scripts/updater_artifact.json").resolve(),
        args.warn_path.resolve() if args.warn_path else None,
        args.zip_path.resolve() if args.zip_path else None,
        args.require_build_info,
        (args.runtime_root or root / "dist").resolve(),
        (args.runtime_manifest or root / "scripts/runtime_artifact.json").resolve(),
    )
    if not getattr(args, "quiet", False):
        for message in messages:
            print(f"PASS: {message}")
    return 0


def _bounded_tail(text: str, *, max_lines: int = 20, max_chars: int = 4000) -> str:
    lines = text.splitlines()
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
    return tail


def tests_command(*, quiet: bool = False, emit_summary: bool = False) -> int:
    root = repo_root()
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.defaultTestLoader.discover(
            str(root / "tests"), pattern="test_*.py", top_level_dir=str(root)
        )
    )
    suite.addTests(
        unittest.defaultTestLoader.discover(
            str(root / "updater_v2"), pattern="test_*.py", top_level_dir=str(root)
        )
    )
    stream = io.StringIO() if quiet else None
    runner = unittest.TextTestRunner(
        stream=stream,
        verbosity=0 if quiet else 2,
    )
    if quiet:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = runner.run(suite)
    else:
        result = runner.run(suite)
    if quiet and not result.wasSuccessful():
        output = _bounded_tail(stream.getvalue() if stream else "")
        print("FAIL: tests")
        if output:
            print(output)
    elif quiet and emit_summary:
        print("PASS: tests")
    return 0 if result.wasSuccessful() else 1


def updater_test_command(args: argparse.Namespace) -> int:
    root = repo_root()
    run = load_updater_harness(root)
    package_zip = (
        args.package_zip.resolve()
        if args.package_zip
        else latest_generated_full_package(root).resolve()
    )
    updater = (args.updater or root / "updater_v2/bin/SigUpdater.exe").resolve()
    try:
        messages = list(run(updater, package_zip, args.timeout))
    except AssertionError as exc:
        raise ValidationError(str(exc)) from None
    if not getattr(args, "quiet", False):
        for message in messages:
            print(f"PASS: {message}")
    elif getattr(args, "emit_summary", False):
        print(f"PASS: updater-test scenarios={len(messages)}")
    return 0


def updater_v2_test_command(args: argparse.Namespace) -> int:
    root = repo_root()
    updater = (args.updater or root / "updater_v2/bin/SigUpdater.exe").resolve()
    metadata_path = root / "updater_v2/artifact.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if sha256_file(updater) != str(metadata.get("sha256") or "").lower():
        raise ValidationError("SigUpdaterV2.exe não corresponde ao artifact.json")
    if sha256_file(root / "updater_v2/updater.py") != str(metadata.get("source_sha256") or "").lower():
        raise ValidationError("updater_v2/updater.py não corresponde ao artifact.json")
    run = load_updater_harness(root)
    package_zip = (
        args.package_zip.resolve()
        if args.package_zip
        else latest_generated_full_package(root).resolve()
    )
    try:
        messages = list(run(updater, package_zip, args.timeout))
    except AssertionError as exc:
        raise ValidationError(str(exc)) from None
    if not getattr(args, "quiet", False):
        for message in messages:
            print(f"PASS: {message}")
    elif getattr(args, "emit_summary", False):
        print(f"PASS: updater-v2-test scenarios={len(messages)}")
    return 0


def ui_smoke_command(args: argparse.Namespace) -> int:
    root = repo_root()
    run = load_ui_smoke(root)
    return run(quiet=bool(getattr(args, "quiet", False)))


def syntax_command(root: Path, *, quiet: bool = False) -> int:
    """Run the fast standard-library syntax gate before expensive checks."""
    paths = [root / "scripts", root / "src", root / "updater_v2", root / "tests"]
    command = [sys.executable, "-m", "compileall"]
    if quiet:
        command.append("-q")
    command.extend(str(path) for path in paths)
    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        print("FAIL: syntax")
        output = _bounded_tail((completed.stdout or "") + (completed.stderr or ""))
        if output:
            print(output)
        return completed.returncode
    if not quiet:
        print("PASS: syntax")
    return 0


def prompt_context_command(root: Path, *, quiet: bool = False) -> int:
    """Validate the always-loaded agent context before the other release gates."""
    command = [sys.executable, str(root / "scripts" / "check_prompt_context.py")]
    if quiet:
        command.append("--quiet")
    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0 or not quiet:
        if output:
            print(output, end="")
    return completed.returncode


def _current_validation_args(root: Path, *, quiet: bool) -> argparse.Namespace:
    return argparse.Namespace(
        package_root=None,
        manifest=None,
        updater_metadata=None,
        warn_path=root / "build" / "sig" / "warn-sig.txt",
        zip_path=None,
        require_build_info=False,
        runtime_root=None,
        runtime_manifest=None,
        quiet=quiet,
    )


def run_preflight(root: Path, *, quiet: bool = False, skip_updater_harness: bool = False) -> None:
    """Run every operator-facing gate before a clean release build."""
    if syntax_command(root, quiet=quiet) != 0:
        raise ValidationError("preflight: o gate de sintaxe falhou")
    if prompt_context_command(root, quiet=quiet) != 0:
        raise ValidationError("preflight: o contrato de contexto do agente falhou")
    if tests_command(quiet=quiet) != 0:
        raise ValidationError("preflight: a suíte de testes falhou")
    if validate_command(_current_validation_args(root, quiet=quiet)) != 0:
        raise ValidationError("preflight: a validação do estado atual falhou")
    if not skip_updater_harness:
        updater_args = argparse.Namespace(
            package_zip=None,
            updater=None,
            timeout=180,
            quiet=quiet,
        )
        if updater_v2_test_command(updater_args) != 0:
            raise ValidationError("preflight: o harness do updater v2 falhou")
    ui_args = argparse.Namespace(quiet=quiet)
    if ui_smoke_command(ui_args) != 0:
        raise ValidationError("preflight: o smoke test da interface falhou")


def preflight_command(args: argparse.Namespace) -> int:
    root = repo_root()
    run_preflight(root, quiet=bool(getattr(args, "quiet", False)))
    if not getattr(args, "quiet", False):
        print("PASS: preflight completo")
    else:
        print("PASS: preflight")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Gates executáveis do SIG Windows")
    sub = result.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validar o estado atual ou um pacote")
    validate.add_argument("--package-root", type=Path)
    validate.add_argument("--manifest", type=Path)
    validate.add_argument("--updater-metadata", type=Path)
    validate.add_argument("--warn-path", type=Path)
    validate.add_argument("--zip-path", type=Path)
    validate.add_argument("--require-build-info", action="store_true")
    validate.add_argument("--runtime-root", type=Path)
    validate.add_argument("--runtime-manifest", type=Path)
    validate.add_argument("--quiet", action="store_true")

    tests = sub.add_parser("tests", help="executar as regressões unitárias")
    tests.add_argument("--quiet", action="store_true")

    updater = sub.add_parser("updater-test", help="executar o updater real em diretório temporário")
    updater.add_argument("--package-zip", type=Path)
    updater.add_argument("--updater", type=Path)
    updater.add_argument("--timeout", type=int, default=120)
    updater.add_argument("--quiet", action="store_true")

    updater_v2 = sub.add_parser("updater-v2-test", help="testar o novo updater em cenários de falha")
    updater_v2.add_argument("--package-zip", type=Path)
    updater_v2.add_argument("--updater", type=Path)
    updater_v2.add_argument("--timeout", type=int, default=180)
    updater_v2.add_argument("--quiet", action="store_true")

    preflight = sub.add_parser("preflight", help="executar todos os gates antes do build")
    preflight.add_argument("--quiet", action="store_true")

    ui_smoke = sub.add_parser("ui-smoke", help="verificar a construção da interface Tk")
    ui_smoke.add_argument("--quiet", action="store_true")

    syntax = sub.add_parser("syntax", help="verificar sintaxe Python sem dependências extras")
    syntax.add_argument("--quiet", action="store_true")

    release = sub.add_parser("release", help="clean build, gates, ZIP e manifesto")
    release.add_argument("--version", help="deve ser igual a APP_VERSION")
    release.add_argument(
        "--incremental",
        action="store_true",
        help=(
            "gera o package para publicação no R2 sem ZIP incremental; o full "
            "fica como *_full.zip para o GitHub"
        ),
    )
    release.add_argument(
        "--allow-same",
        action="store_true",
        help="permite smoke test local da versão atual; nunca publicar com essa opção",
    )
    release.add_argument("--runtime-root", type=Path)
    release.add_argument("--output-root", type=Path)
    release.add_argument("--updater-timeout", type=int, default=180)
    release.add_argument("--quiet", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "validate":
            result = validate_command(args)
            if result == 0 and args.quiet:
                print("PASS: validate")
            return result
        if args.command == "tests":
            return tests_command(quiet=args.quiet, emit_summary=True)
        if args.command == "updater-test":
            args.emit_summary = True
            return updater_test_command(args)
        if args.command == "updater-v2-test":
            args.emit_summary = True
            return updater_v2_test_command(args)
        if args.command == "preflight":
            return preflight_command(args)
        if args.command == "ui-smoke":
            result = ui_smoke_command(args)
            if result == 0 and args.quiet:
                print("PASS: ui-smoke")
            return result
        if args.command == "syntax":
            result = syntax_command(repo_root(), quiet=args.quiet)
            if result == 0 and args.quiet:
                print("PASS: syntax")
            return result
        if args.command == "release":
            return build_release(args)
        raise AssertionError(args.command)
    except (ValidationError, FileNotFoundError, json.JSONDecodeError, AssertionError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
