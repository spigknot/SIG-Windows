"""Transactional updater for the SIG Windows onedir app.

The helper keeps the legacy command-line contract, but validates and stages
every update before touching the installation.  It also keeps a transaction
journal so an interrupted replacement can be rolled back safely on the next
run.
"""

from __future__ import annotations

import argparse
import ctypes
from contextlib import contextmanager
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath


VERSION_RE = re.compile(r"^\d{8}_\d{3}$")
MAX_ZIP_ENTRIES = 10_000
MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED_BYTES = 1 * 1024 * 1024 * 1024
REQUIRED_CORE_FILES = (
    "sig.exe",
    "_internal/base_library.zip",
    "_internal/python311.dll",
    "_internal/vcruntime140.dll",
    "_internal/vcruntime140_1.dll",
    "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
)
REQUIRED_RUNTIME_FILES = (
    "ffmpeg.exe",
    "ffplay.exe",
    "vad_worker.py",
)
REQUIRED_UPDATE_FILES = REQUIRED_CORE_FILES + ("SigUpdater.exe",)
REQUIRED_DIRECTORIES = ("_internal", "vad_deps")
MUTABLE_TOP_LEVEL_NAMES = {"temp", "cache", "logs"}
ALLOWED_TOP_LEVEL_NAMES = {
    "sig.exe",
    "_internal",
    "SigUpdater.exe",
    "ffmpeg.exe",
    "ffplay.exe",
    "vad_worker.py",
    "vad_deps",
    "prompts",
    "modelos",
    "build-info.json",
    # These directories are created by the running application and are not
    # part of an update package.
    "temp",
    "cache",
    "logs",
}
REQUIRED_FILES = REQUIRED_UPDATE_FILES + REQUIRED_RUNTIME_FILES
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class UpdateError(RuntimeError):
    pass


def _log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def _normalized_member_name(name: str) -> str:
    raw = name.replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise UpdateError(f"entrada absoluta ou vazia no ZIP: {name!r}")
    path = PurePosixPath(raw)
    if any(part in ("", ".", "..") for part in path.parts):
        raise UpdateError(f"caminho inseguro no ZIP: {name!r}")
    for part in path.parts:
        if "\x00" in part or ":" in part or part.endswith((" ", ".")):
            raise UpdateError(f"nome incompatível com Windows no ZIP: {name!r}")
        if part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            raise UpdateError(f"nome reservado do Windows no ZIP: {name!r}")
        if len(part) > 240:
            raise UpdateError(f"componente de caminho longo demais no ZIP: {name!r}")
        lowered = part.casefold()
        if lowered == "g":
            raise UpdateError("o pacote contém a pasta proibida g")
        if lowered.startswith("_mei"):
            raise UpdateError("o pacote contém artefato _MEI de one-file")
        if lowered == "dist":
            raise UpdateError("o pacote contém o diretório dist; o layout deve estar na raiz")
    return "/".join(path.parts)


def _is_symlink(member: zipfile.ZipInfo) -> bool:
    mode = (member.external_attr >> 16) & 0o170000
    return mode == 0o120000


def _validate_entry_topology(entries: dict[str, bool]) -> None:
    for name, is_directory in entries.items():
        parts = PurePosixPath(name).parts
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            if parent in entries and not entries[parent]:
                raise UpdateError(f"arquivo usado como diretório no ZIP: {parent}")
        if not is_directory and name.endswith("/"):
            raise UpdateError(f"entrada contraditória no ZIP: {name}")


def _validate_required_names(
    file_names: set[str], all_names: set[str], *, full: bool
) -> None:
    required_files = REQUIRED_UPDATE_FILES + (REQUIRED_RUNTIME_FILES if full else ())
    for relative in required_files:
        if relative not in file_names:
            if "portaudio" in relative.casefold():
                raise UpdateError("DLL do PortAudio ausente no pacote")
            raise UpdateError(f"componente obrigatório ausente no pacote: {relative}")
    required_directories = REQUIRED_DIRECTORIES if full else ("_internal",)
    for relative in required_directories:
        if not any(name == relative or name.startswith(relative + "/") for name in all_names):
            raise UpdateError(f"diretório obrigatório ausente no pacote: {relative}")


def _validate_top_level_names(file_names: set[str], all_names: set[str], *, full: bool) -> None:
    top_level = {PurePosixPath(name).parts[0] for name in all_names if name}
    unknown = sorted(top_level - ALLOWED_TOP_LEVEL_NAMES)
    if unknown:
        raise UpdateError("componente desconhecido na raiz do pacote: " + ", ".join(unknown))
    if not full and set(REQUIRED_RUNTIME_FILES) & file_names:
        raise UpdateError("pacote incremental não pode substituir apenas parte dos recursos de runtime")


def _validate_file_sizes(root: Path, *, full: bool) -> None:
    required = REQUIRED_UPDATE_FILES + (REQUIRED_RUNTIME_FILES if full else ())
    for relative in required:
        path = root / Path(*PurePosixPath(relative).parts)
        if not path.is_file():
            continue
        if path.stat().st_size <= 0:
            raise UpdateError(f"arquivo obrigatório vazio: {relative}")


def validate_zip(zip_path: Path, *, full: bool | None = None) -> bool:
    if not zip_path.is_file():
        raise UpdateError(f"ZIP não encontrado: {zip_path}")
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise UpdateError(f"entrada corrompida no ZIP: {corrupt_member}")
            members = archive.infolist()
            if len(members) > MAX_ZIP_ENTRIES:
                raise UpdateError("o pacote excede o limite de entradas")
            entries: dict[str, bool] = {}
            total_size = 0
            for member in members:
                if member.flag_bits & 0x1:
                    raise UpdateError("ZIP criptografado não é permitido")
                if _is_symlink(member):
                    raise UpdateError(f"link simbólico não permitido: {member.filename}")
                normalized = _normalized_member_name(member.filename.rstrip("/"))
                is_directory = member.is_dir()
                if normalized in entries:
                    raise UpdateError(f"entrada duplicada no ZIP: {normalized}")
                entries[normalized] = is_directory
                total_size += member.file_size
                if member.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                    raise UpdateError(f"entrada individual grande demais: {member.filename}")
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise UpdateError("o pacote descompactado excede o limite permitido")
            _validate_entry_topology(entries)
            file_names = {name for name, is_directory in entries.items() if not is_directory}
            all_runtime_present = set(REQUIRED_RUNTIME_FILES) <= file_names
            if full is None:
                full = all_runtime_present
            elif full and not all_runtime_present:
                raise UpdateError("pacote completo não contém todos os recursos de runtime")
            _validate_top_level_names(file_names, set(entries), full=full)
            _validate_required_names(file_names, set(entries), full=full)
            build_info = "build-info.json"
            if build_info in file_names:
                try:
                    with archive.open(build_info) as handle:
                        metadata = json.loads(handle.read().decode("utf-8"))
                    version = str(metadata.get("version") or "")
                    if not VERSION_RE.fullmatch(version):
                        raise UpdateError("build-info.json contém uma versão inválida")
                except UpdateError:
                    raise
                except Exception as exc:
                    raise UpdateError(f"build-info.json inválido: {exc}") from exc
            return bool(full)
    except zipfile.BadZipFile as exc:
        raise UpdateError(f"ZIP inválido: {zip_path}") from exc


def _reject_bad_tree_entries(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise UpdateError(f"link simbólico não permitido na instalação: {path}")
        relative = path.relative_to(root)
        for part in relative.parts:
            lowered = part.casefold()
            if lowered == "g":
                raise UpdateError(f"a instalação contém a pasta proibida g: {path}")
            if lowered.startswith("_mei"):
                raise UpdateError(f"a instalação contém artefato _MEI: {path}")


def validate_install_tree(root: Path, *, full: bool = True) -> None:
    if not root.is_dir():
        raise UpdateError(f"diretório da instalação não encontrado: {root}")
    _reject_bad_tree_entries(root)
    files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    names = {path.relative_to(root).as_posix() for path in root.rglob("*")}
    _validate_required_names(files, names, full=full)
    _validate_file_sizes(root, full=full)


def validate_target_shell(root: Path) -> None:
    """Validate enough of an existing install to repair a partial update."""
    if not root.is_dir():
        raise UpdateError(f"diretório da instalação não encontrado: {root}")
    _reject_bad_tree_entries(root)
    required = {"sig.exe", "_internal", "SigUpdater.exe", "ffmpeg.exe", "ffplay.exe", "vad_deps"}
    present = {path.name for path in root.iterdir()}
    missing = sorted(required - present)
    if missing:
        raise UpdateError("instalação não reconhecida; componentes ausentes: " + ", ".join(missing))


def _extract_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            normalized = _normalized_member_name(member.filename.rstrip("/"))
            target = (destination / Path(*PurePosixPath(normalized).parts)).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise UpdateError(f"destino inseguro no ZIP: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 256)


def _write_journal(path: Path, data: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _read_journal(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise UpdateError(f"diário de atualização inválido: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("names"), list):
        raise UpdateError(f"diário de atualização incompleto: {path}")
    return data


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=False)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _atomic_move(source: Path, destination: Path) -> None:
    if not _path_exists(source):
        raise UpdateError(f"origem ausente durante a troca: {source}")
    if _path_exists(destination):
        raise UpdateError(f"destino já existe durante a troca: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _rollback_transaction(transaction: Path, target: Path, log_path: Path) -> None:
    journal_path = transaction / "journal.json"
    if not journal_path.is_file():
        shutil.rmtree(transaction, ignore_errors=True)
        return
    journal = _read_journal(journal_path)
    if os.path.normcase(os.path.abspath(str(journal.get("target") or ""))) != os.path.normcase(os.path.abspath(str(target))):
        raise UpdateError(f"diário aponta para outra instalação: {transaction}")
    backup = transaction / "backup"
    names = {str(name) for name in journal.get("names", []) if isinstance(name, str)}
    if backup.is_dir():
        names.update(path.name for path in backup.iterdir())
    _log(log_path, f"Recuperando transação interrompida: {transaction.name}.")
    for name in sorted(names, key=str.casefold, reverse=True):
        destination = target / name
        old = backup / name
        if _path_exists(old):
            if _path_exists(destination):
                _remove_path(destination)
            _atomic_move(old, destination)
        elif not journal.get("target_existed", {}).get(name, True) and _path_exists(destination):
            _remove_path(destination)
    try:
        validate_install_tree(target, full=True)
        _log(log_path, "Recuperação da instalação anterior concluída.")
    except UpdateError as exc:
        # A previous installation may already have been damaged before this
        # updater started. Preserve it exactly instead of hiding the original
        # failure behind a second rollback error.
        validate_target_shell(target)
        _log(log_path, f"Versão anterior restaurada, mas já estava incompleta: {exc}")
    shutil.rmtree(transaction, ignore_errors=True)


def _recover_interrupted_transactions(target: Path, log_path: Path) -> None:
    parent = target.parent
    for transaction in sorted(parent.glob(".sig-updater-v2-*"), key=lambda item: item.name):
        if not transaction.is_dir():
            continue
        journal = transaction / "journal.json"
        if not journal.is_file():
            shutil.rmtree(transaction, ignore_errors=True)
            continue
        journal_path = transaction / "journal.json"
        journal = _read_journal(journal_path)
        if journal.get("phase") == "validated":
            try:
                validate_install_tree(target, full=True)
                _log(log_path, f"Removendo transação já validada: {transaction.name}.")
                shutil.rmtree(transaction, ignore_errors=True)
            except UpdateError:
                _rollback_transaction(transaction, target, log_path)
        else:
            _rollback_transaction(transaction, target, log_path)


@contextmanager
def _installation_lock(target: Path, log_path: Path):
    lock_path = target.parent / f".{target.name}.sig-update.lock"
    handle = lock_path.open("a+b")
    handle.seek(0)
    handle.write(b"0")
    handle.flush()
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError) as exc:
        handle.close()
        raise UpdateError("já existe outra atualização do SIG em andamento") from exc
    try:
        _log(log_path, "Lock exclusivo da instalação adquirido.")
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _process_image_paths() -> dict[int, str]:
    if os.name != "nt":
        return {}
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", ctypes.c_ulong),
            ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32FirstW.restype = ctypes.c_int
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32NextW.restype = ctypes.c_int
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (0, ctypes.c_void_p(-1).value):
        return {}
    result: dict[int, str] = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        first = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while first:
            pid = int(entry.th32ProcessID)
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                try:
                    size = ctypes.c_ulong(32768)
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(
                        handle, 0, buffer, ctypes.byref(size)
                    ):
                        result[pid] = buffer.value
                finally:
                    kernel32.CloseHandle(handle)
            first = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return result


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


def _wait_for_processes(pid: int, target_exe: Path, timeout: int, log_path: Path) -> None:
    deadline = time.monotonic() + timeout
    while True:
        blockers = []
        if _process_alive(pid):
            blockers.append(f"pid={pid}")
        for process_id, image_path in _process_image_paths().items():
            if process_id != os.getpid() and _same_path(image_path, target_exe):
                blockers.append(f"sig.exe pid={process_id}")
        if not blockers:
            _log(log_path, "Todos os processos do SIG encerrados.")
            return
        if time.monotonic() >= deadline:
            raise UpdateError(
                "tempo esgotado aguardando o SIG fechar: " + ", ".join(blockers)
            )
        time.sleep(0.25)


def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _launch_and_verify(target_exe: Path, timeout: int, log_path: Path) -> subprocess.Popen[bytes]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(
            [str(target_exe)],
            cwd=str(target_exe.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception as exc:
        raise UpdateError(f"não foi possível iniciar o SIG atualizado: {exc}") from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise UpdateError(
                f"o SIG atualizado encerrou durante a inicialização (código {process.returncode})"
            )
        time.sleep(0.25)
    if process.poll() is not None:
        raise UpdateError("o SIG atualizado não permaneceu em execução")
    _log(log_path, f"SIG atualizado confirmado em execução (PID {process.pid}).")
    return process


def _apply_transaction(
    staged: Path,
    target: Path,
    transaction: Path,
    startup_timeout: int,
    log_path: Path,
) -> None:
    backup = transaction / "backup"
    backup.mkdir()
    started_process: subprocess.Popen[bytes] | None = None
    # An incremental package replaces only the top-level names it contains;
    # runtime assets omitted from it must remain untouched.
    names = sorted({item.name for item in staged.iterdir()}, key=str.casefold)
    target_existed = {name: _path_exists(target / name) for name in names}
    journal = {
        "schema": 1,
        "target": str(target),
        "phase": "prepared",
        "names": names,
        "target_existed": target_existed,
    }
    _write_journal(transaction / "journal.json", journal)
    try:
        for name in names:
            destination = target / name
            if _path_exists(destination):
                _atomic_move(destination, backup / name)
        journal["phase"] = "old-moved"
        _write_journal(transaction / "journal.json", journal)
        for name in sorted((item.name for item in staged.iterdir()), key=str.casefold):
            _atomic_move(staged / name, target / name)
        journal["phase"] = "new-moved"
        _write_journal(transaction / "journal.json", journal)
        validate_install_tree(target)
        _log(log_path, "Estrutura onedir instalada; validando inicialização.")
        started_process = _launch_and_verify(target / "sig.exe", startup_timeout, log_path)
        journal["phase"] = "validated"
        _write_journal(transaction / "journal.json", journal)
        _log(log_path, "Atualização aplicada e validada.")
        shutil.rmtree(transaction, ignore_errors=True)
    except Exception:
        _stop_process(started_process)
        _log(log_path, "Falha na aplicação; iniciando rollback.")
        _rollback_transaction(transaction, target, log_path)
        _log(log_path, "Rollback concluído; a versão anterior foi restaurada.")
        try:
            _launch_and_verify(target / "sig.exe", min(startup_timeout, 5), log_path)
        except Exception as restart_error:
            _log(log_path, f"Não foi possível reiniciar a versão anterior: {restart_error}")
        raise


def execute(
    zip_path: Path,
    target: Path,
    pid: int,
    log_path: Path,
    wait_timeout: int = 120,
    startup_timeout: int = 12,
) -> None:
    zip_path = zip_path.resolve()
    target = target.resolve()
    log_path = log_path.resolve()
    _log(log_path, "SigUpdaterV2 iniciado.")
    _log(log_path, f"ZIP={zip_path}; target={target}; pid={pid}")
    with _installation_lock(target, log_path):
        _recover_interrupted_transactions(target, log_path)
        package_is_full = validate_zip(zip_path)
        if not package_is_full:
            validate_target_shell(target)
        else:
            validate_install_tree(target, full=True)
        _wait_for_processes(pid, target / "sig.exe", wait_timeout, log_path)
        transaction = Path(tempfile.mkdtemp(prefix=".sig-updater-v2-", dir=str(target.parent)))
        staged = transaction / "staged"
        try:
            _extract_zip(zip_path, staged)
            validate_install_tree(staged, full=package_is_full)
            _log(log_path, "Pacote extraído e layout validado.")
            _apply_transaction(staged, target, transaction, startup_timeout, log_path)
        except Exception:
            if transaction.exists():
                try:
                    _rollback_transaction(transaction, target, log_path)
                except Exception as rollback_error:
                    _log(log_path, f"Falha crítica no rollback: {rollback_error}")
            raise
        finally:
            if transaction.exists():
                shutil.rmtree(transaction, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SigUpdaterV2")
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--wait-timeout", type=int, default=120)
    parser.add_argument("--startup-timeout", type=int, default=12)
    args = parser.parse_args(argv)
    try:
        execute(
            args.zip,
            args.target,
            args.pid,
            args.log,
            args.wait_timeout,
            args.startup_timeout,
        )
        return 0
    except (UpdateError, OSError, ValueError) as exc:
        try:
            _log(args.log.resolve(), f"Falha na atualização: {exc}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
