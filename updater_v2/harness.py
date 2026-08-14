"""Failure-oriented integration harness for SigUpdaterV2."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

try:
    from .updater import REQUIRED_RUNTIME_FILES, REQUIRED_UPDATE_FILES
except ImportError:  # direct invocation from the updater_v2 directory
    from updater import REQUIRED_RUNTIME_FILES, REQUIRED_UPDATE_FILES


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = REQUIRED_UPDATE_FILES + REQUIRED_RUNTIME_FILES


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        archive.extractall(destination)


def _zip_directory(source: Path, destination: Path, extras: dict[str, bytes] | None = None) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
        for name, data in (extras or {}).items():
            archive.writestr(name, data)


def _minimal_zip(destination: Path, missing: set[str] | None = None, extras: dict[str, bytes] | None = None) -> None:
    missing = missing or set()
    with zipfile.ZipFile(destination, "w") as archive:
        for relative in REQUIRED_FILES:
            if any(relative == item or relative.startswith(item + "/") for item in missing):
                continue
            archive.writestr(relative, b"fixture")
        archive.writestr("vad_deps/fixture.txt", b"fixture")
        for name, data in (extras or {}).items():
            archive.writestr(name, data)


def _start_holder(seconds: int):
    return subprocess.Popen(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"Start-Sleep -Seconds {seconds}",
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_sig_processes(install_root: Path) -> None:
    escaped = str(install_root / "sig.exe").replace("'", "''")
    command = (
        "$target = '" + escaped + "'; "
        "Get-CimInstance Win32_Process -Filter \"Name = 'sig.exe'\" | "
        "Where-Object { $_.ExecutablePath -and $_.ExecutablePath -ieq $target } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _run_helper(updater: Path, package: Path, target: Path, log: Path, **options) -> int:
    timeout = options.pop("timeout", 180)
    command = [
        str(updater),
        "--zip",
        str(package),
        "--target",
        str(target),
        "--pid",
        str(options.pop("pid", 0)),
        "--log",
        str(log),
    ]
    for name, value in options.items():
        command.extend([f"--{name.replace('_', '-')}", str(value)])
    result = subprocess.run(
        command,
        check=False,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode


def _assert_rejected(
    updater: Path,
    package: Path,
    target: Path,
    workspace: Path,
    label: str,
    **options,
) -> None:
    before = _hash(target / "sig.exe") if (target / "sig.exe").is_file() else None
    log = workspace / f"{label}.log"
    code = _run_helper(updater, package, target, log, timeout=30, **options)
    if code == 0:
        raise AssertionError(f"cenário {label} foi aceito inesperadamente")
    if before is not None and _hash(target / "sig.exe") != before:
        raise AssertionError(f"cenário {label} alterou a instalação antes de falhar")


def _make_invalid_executable_zip(base_zip: Path, destination: Path) -> None:
    with zipfile.ZipFile(base_zip) as source, zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1
    ) as output:
        for member in source.infolist():
            if member.filename.rstrip("/") == "sig.exe":
                output.writestr(member.filename, b"not-a-windows-executable")
            else:
                output.writestr(member, source.read(member))


def _make_diff_zip(
    base_zip: Path,
    destination: Path,
    changes: dict[str, bytes],
    removidos: list[str],
) -> None:
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1
    ) as output:
        for name, data in changes.items():
            output.writestr(name, data)
        output.writestr(
            "removidos.txt",
            ("\n".join(removidos) + ("\n" if removidos else "")).encode(),
        )


def _member_bytes(package_zip: Path, name: str) -> bytes:
    with zipfile.ZipFile(package_zip) as archive:
        return archive.read(name)


def run(updater: Path, package_zip: Path, timeout: int = 180) -> list[str]:
    if not updater.is_file():
        raise AssertionError(f"updater V2 não encontrado: {updater}")
    if not package_zip.is_file():
        raise AssertionError(f"pacote base não encontrado: {package_zip}")

    workspace = Path(tempfile.mkdtemp(prefix="sig-updater-v2-harness-"))
    holder = None
    try:
        base = workspace / "base"
        _extract(package_zip, base)
        preflight_target = workspace / "preflight-target"
        shutil.copytree(base, preflight_target)

        # Layout e segurança do pacote: nenhum destes casos pode iniciar a
        # aplicação nem modificar a instalação anterior.
        bad_internal = workspace / "missing-internal.zip"
        _minimal_zip(bad_internal, {"_internal"})
        _assert_rejected(updater, bad_internal, preflight_target, workspace, "missing-internal")

        bad_helper = workspace / "missing-updater.zip"
        _minimal_zip(bad_helper, {"SigUpdater.exe"})
        _assert_rejected(updater, bad_helper, preflight_target, workspace, "missing-updater")

        bad_portaudio = workspace / "missing-portaudio.zip"
        _minimal_zip(
            bad_portaudio,
            {"_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll"},
        )
        _assert_rejected(updater, bad_portaudio, preflight_target, workspace, "missing-portaudio")

        for label, extra in (
            ("forbidden-g", {"g/old.txt": b"bad"}),
            ("forbidden-mei", {"_MEI123/old.txt": b"bad"}),
            ("nested-dist", {"dist/sig.exe": b"bad"}),
            ("traversal", {"../outside.txt": b"bad"}),
        ):
            bad_layout = workspace / f"{label}.zip"
            _minimal_zip(bad_layout, extras=extra)
            _assert_rejected(updater, bad_layout, preflight_target, workspace, label)

        corrupt = workspace / "corrupt.zip"
        corrupt.write_bytes(b"not a zip")
        _assert_rejected(updater, corrupt, preflight_target, workspace, "corrupt-zip")

        wrong_target = workspace / "wrong-target"
        wrong_target.mkdir()
        (wrong_target / "personal.txt").write_text("do not replace", encoding="utf-8")
        _assert_rejected(updater, package_zip, wrong_target, workspace, "wrong-target")

        # A live process must block the transaction and leave the target byte
        # for byte unchanged.
        holder = _start_holder(8)
        _assert_rejected(
            updater,
            package_zip,
            preflight_target,
            workspace,
            "process-active",
            pid=holder.pid,
            wait_timeout=1,
        )
        if holder.poll() is not None:
            raise AssertionError("o holder terminou antes do teste de processo ativo")

        # Real success path using the complete current onedir package.
        success_target = workspace / "success-target"
        success_target.mkdir()
        success_source = workspace / "success-source"
        shutil.copytree(base, success_source)
        marker = uuid.uuid4().hex
        success_zip = workspace / "success.zip"
        _zip_directory(
            success_source,
            success_zip,
            {"_internal/release-test-marker.txt": marker.encode()},
        )
        success_log = workspace / "success.log"
        success_holder = _start_holder(2)
        try:
            code = _run_helper(
                updater,
                success_zip,
                success_target,
                success_log,
                pid=success_holder.pid,
                timeout=timeout,
            )
        finally:
            if success_holder.poll() is None:
                success_holder.terminate()
                success_holder.wait(timeout=5)
            _stop_sig_processes(success_target)
        if code != 0:
            raise AssertionError(f"sucesso retornou {code}: {success_log.read_text(errors='replace')}")
        if (success_target / "_internal/release-test-marker.txt").read_text().strip() != marker:
            raise AssertionError("o pacote novo não foi instalado no cenário de sucesso")
        if "Atualização aplicada e validada." not in success_log.read_text(encoding="utf-8"):
            raise AssertionError("o log de sucesso não contém a validação final")

        # An executable that passes the structural gate but cannot start must
        # restore the previous installation and restart it.
        rollback_target = workspace / "rollback-target"
        shutil.copytree(base, rollback_target)
        old_hash = _hash(rollback_target / "sig.exe")
        invalid_zip = workspace / "invalid-executable.zip"
        _make_invalid_executable_zip(package_zip, invalid_zip)
        rollback_log = workspace / "rollback.log"
        rollback_code = _run_helper(
            updater,
            invalid_zip,
            rollback_target,
            rollback_log,
            startup_timeout=3,
            timeout=timeout,
        )
        _stop_sig_processes(rollback_target)
        rollback_text = rollback_log.read_text(encoding="utf-8", errors="replace")
        if rollback_code == 0:
            raise AssertionError("pacote com executável inválido foi aceito")
        if _hash(rollback_target / "sig.exe") != old_hash:
            raise AssertionError("rollback não restaurou o sig.exe original")
        if "Rollback concluído" not in rollback_text:
            raise AssertionError("o log não confirma rollback")

        # --- Cenários do pacote diff (incremental por arquivo) ---
        sig_bytes = _member_bytes(package_zip, "sig.exe")
        removed_name = "_internal/assets/appwin.jpg"
        if removed_name not in {member.filename for member in zipfile.ZipFile(package_zip).infolist()}:
            raise AssertionError("o pacote base não contém o arquivo de teste do diff")

        diff_target = workspace / "diff-target"
        shutil.copytree(base, diff_target)
        diff_zip = workspace / "diff.zip"
        _make_diff_zip(
            package_zip,
            diff_zip,
            {"sig.exe": sig_bytes, "_internal/diff-test-novo.txt": b"novo-conteudo"},
            [removed_name],
        )
        diff_log = workspace / "diff.log"
        diff_holder = _start_holder(2)
        try:
            code = _run_helper(
                updater, diff_zip, diff_target, diff_log, pid=diff_holder.pid, timeout=timeout
            )
        finally:
            if diff_holder.poll() is None:
                diff_holder.terminate()
                diff_holder.wait(timeout=5)
            _stop_sig_processes(diff_target)
        if code != 0:
            raise AssertionError(f"diff retornou {code}: {diff_log.read_text(errors='replace')}")
        if (diff_target / "_internal/diff-test-novo.txt").read_text() != "novo-conteudo":
            raise AssertionError("o diff não instalou o arquivo novo")
        if (diff_target / removed_name).exists():
            raise AssertionError("o diff não removeu o arquivo listado no removidos.txt")
        if (diff_target / "sig.exe").read_bytes() != sig_bytes:
            raise AssertionError("o diff não preservou o sig.exe aplicado")
        if not (diff_target / "_internal" / "python311.dll").is_file():
            raise AssertionError("o diff removeu arquivos intactos da instalação")
        if "Atualização aplicada e validada." not in diff_log.read_text(encoding="utf-8"):
            raise AssertionError("o log do diff não contém a validação final")

        for label, removidos_bad in (
            ("diff-forbidden-runtime", ["vad_worker.py"]),
            ("diff-traversal", ["../fora.txt"]),
            ("diff-absolute", ["C:/fora.txt"]),
            ("diff-mei", ["_MEI123/old.txt"]),
        ):
            bad_diff = workspace / f"{label}.zip"
            _make_diff_zip(package_zip, bad_diff, {"sig.exe": sig_bytes}, removidos_bad)
            _assert_rejected(updater, bad_diff, diff_target, workspace, label)

        rollback_diff_target = workspace / "rollback-diff-target"
        shutil.copytree(base, rollback_diff_target)
        old_sig_hash = _hash(rollback_diff_target / "sig.exe")
        bad_diff_zip = workspace / "bad-diff.zip"
        _make_diff_zip(
            package_zip,
            bad_diff_zip,
            {
                "sig.exe": b"not-a-windows-executable",
                "_internal/diff-test-novo.txt": b"novo",
            },
            [],
        )
        bad_diff_log = workspace / "bad-diff.log"
        bad_diff_code = _run_helper(
            updater,
            bad_diff_zip,
            rollback_diff_target,
            bad_diff_log,
            startup_timeout=3,
            timeout=timeout,
        )
        _stop_sig_processes(rollback_diff_target)
        if bad_diff_code == 0:
            raise AssertionError("diff com executável inválido foi aceito")
        if _hash(rollback_diff_target / "sig.exe") != old_sig_hash:
            raise AssertionError("rollback do diff não restaurou o sig.exe original")
        if (rollback_diff_target / "_internal/diff-test-novo.txt").exists():
            raise AssertionError("rollback do diff não removeu o arquivo novo aplicado")
        if "Rollback concluído" not in bad_diff_log.read_text(encoding="utf-8", errors="replace"):
            raise AssertionError("o log do rollback do diff não confirma a restauração")

        return [
            "pacotes incompletos, traversal, g, _MEI e dist foram rejeitados",
            "processo ativo foi bloqueado sem modificar a instalação",
            "atualização onedir completa executou e iniciou o aplicativo",
            "falha de inicialização acionou rollback e restaurou a versão anterior",
            "diff incremental aplicou arquivos novos, removeu os listados e preservou os intactos",
            "removidos.txt malicioso foi rejeitado sem alterar a instalação",
            "rollback do diff restaurou a versão anterior",
        ]
    finally:
        if holder is not None and holder.poll() is None:
            holder.terminate()
            holder.wait(timeout=5)
        _stop_sig_processes(workspace / "success-target")
        _stop_sig_processes(workspace / "rollback-target")
        shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--updater", type=Path, required=True)
    parser.add_argument("--package-zip", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        for message in run(args.updater.resolve(), args.package_zip.resolve(), args.timeout):
            print(f"PASS: {message}")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
