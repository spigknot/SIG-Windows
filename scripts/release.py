"""Official local build/release command for SIG Windows.

Examples:

    python scripts/release.py validate --warn-path build/sig/warn-sig.txt
    python scripts/release.py tests
    python scripts/release.py updater-test
    python scripts/release.py release --version 20260806_005 --zip-file-id DRIVE_ID

The release command never uses the repository's existing dist/sig.exe. It
builds into a unique clean work directory and only uses the configured runtime
bundle for static assets whose source is currently outside Git.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path

from release_validation import (
    ValidationError,
    _manifest_payload,
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


def latest_generated_full_package(root: Path) -> Path:
    candidates = [
        path
        for path in (root / "release" / "generated").glob("*/*.zip")
        if path.is_file() and (path.parent / "package" / "vad_deps").is_dir()
    ]
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
    required = ("ffmpeg.exe", "ffplay.exe", "vad_deps")
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


def sign_manifest(manifest: dict, key_path: Path, output_path: Path) -> None:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:
        raise ValidationError("cryptography é necessária para assinar o manifesto") from exc
    if not key_path.is_file():
        raise ValidationError(f"chave privada do manifesto ausente: {key_path}")
    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    manifest = dict(manifest)
    manifest["signature"] = __import__("base64").b64encode(
        private_key.sign(_manifest_payload(manifest), padding.PKCS1v15(), hashes.SHA256())
    ).decode("ascii")
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_release(args: argparse.Namespace) -> int:
    root = repo_root()
    source_version = read_app_version(root / "src/sig_app.py")
    version = args.version or source_version
    if version != source_version:
        raise ValidationError(
            f"a versão do comando ({version}) diverge de APP_VERSION ({source_version}); "
            "altere somente APP_VERSION e execute novamente"
        )
    current_manifest = read_manifest(root / "release/latest.json")
    current_version = str(current_manifest.get("version") or "")
    if version <= current_version and not args.allow_same:
        raise ValidationError(f"release {version} não é posterior à versão publicada {current_version}")

    check_build_environment()
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
        run_command(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onefile",
                "--console",
                "--noupx",
                "--name",
                "SigUpdater",
                "--distpath",
                str(updater_build_dir),
                "--workpath",
                str(updater_work_dir),
                "--specpath",
                str(updater_work_dir),
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

        zip_path = output_root / f"{version}.zip"
        zip_directory(package_root, zip_path)
        validate_zip_layout(zip_path, full=True)
        # Exercise the exact ZIP and helper that are about to be published.
        # This runs only in the disposable harness and never touches the
        # user's installation.
        run_updater_test = load_updater_harness(root)

        for message in run_updater_test(
            package_root / "SigUpdater.exe",
            zip_path,
            args.updater_timeout,
        ):
            print(f"PASS: {message}")
        if args.zip_file_id:
            manifest = {
                "schema": 1,
                "version": version,
                "zip_file_id": args.zip_file_id,
                "zip_name": zip_path.name,
                "sha256": sha256_file(zip_path),
                "size": zip_path.stat().st_size,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            manifest_path = output_root / "latest.json"
            sign_manifest(manifest, root / "release/update_private_key.pem", manifest_path)
            final_manifest = read_manifest(manifest_path)
            validate_manifest_shape(final_manifest)
            validate_manifest_signature(final_manifest, root / "src/sig_app.py")
            validate_version_consistency(version, final_manifest, zip_path, frozen_version)
            print(f"PASS: release local aprovada: {zip_path}")
            print(f"Manifesto assinado: {manifest_path}")
        else:
            draft = output_root / "latest.draft.json"
            draft.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "version": version,
                        "zip_file_id": "PENDING_DRIVE_UPLOAD",
                        "zip_name": zip_path.name,
                        "sha256": sha256_file(zip_path),
                        "size": zip_path.stat().st_size,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"PASS: build limpo e pacote validado: {zip_path}")
            print(f"Manifesto rascunho: {draft}")
            print("A release ainda não é publicável: informe o ID do ZIP após o upload único ao Drive.")
        return 0
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


def validate_command(args: argparse.Namespace) -> int:
    root = repo_root()
    messages = validate_current(
        root,
        (args.package_root or root / "dist").resolve(),
        (args.manifest or root / "release/latest.json").resolve(),
        (args.updater_metadata or root / "scripts/updater_artifact.json").resolve(),
        args.warn_path.resolve() if args.warn_path else None,
        args.zip_path.resolve() if args.zip_path else None,
        args.require_build_info,
        (args.runtime_root or root / "dist").resolve(),
        (args.runtime_manifest or root / "scripts/runtime_artifact.json").resolve(),
    )
    for message in messages:
        print(f"PASS: {message}")
    return 0


def tests_command() -> int:
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
    result = unittest.TextTestRunner(verbosity=2).run(suite)
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
    for message in run(updater, package_zip, args.timeout):
        print(f"PASS: {message}")
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
    for message in run(updater, package_zip, args.timeout):
        print(f"PASS: {message}")
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

    sub.add_parser("tests", help="executar as regressões unitárias")

    updater = sub.add_parser("updater-test", help="executar o updater real em diretório temporário")
    updater.add_argument("--package-zip", type=Path)
    updater.add_argument("--updater", type=Path)
    updater.add_argument("--timeout", type=int, default=120)

    updater_v2 = sub.add_parser("updater-v2-test", help="testar o novo updater em cenários de falha")
    updater_v2.add_argument("--package-zip", type=Path)
    updater_v2.add_argument("--updater", type=Path)
    updater_v2.add_argument("--timeout", type=int, default=180)

    release = sub.add_parser("release", help="clean build, gates, ZIP e manifesto")
    release.add_argument("--version", help="deve ser igual a APP_VERSION")
    release.add_argument("--zip-file-id", help="ID do ZIP depois do upload único ao Drive")
    release.add_argument(
        "--allow-same",
        action="store_true",
        help="permite smoke test local da versão atual; nunca publicar com essa opção",
    )
    release.add_argument("--runtime-root", type=Path)
    release.add_argument("--output-root", type=Path)
    release.add_argument("--updater-timeout", type=int, default=180)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "validate":
            return validate_command(args)
        if args.command == "tests":
            return tests_command()
        if args.command == "updater-test":
            return updater_test_command(args)
        if args.command == "updater-v2-test":
            return updater_v2_test_command(args)
        if args.command == "release":
            return build_release(args)
        raise AssertionError(args.command)
    except (ValidationError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
