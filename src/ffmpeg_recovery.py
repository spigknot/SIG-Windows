"""Checkpoints locais das ferramentas FFmpeg; reutiliza somente etapas concluídas."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path


def fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


class RecoveryJob:
    VERSION = 1

    def __init__(self, journal: Path, state: dict):
        self.journal, self.state = journal, state
        self.lock = threading.RLock()
        self.work_root = Path(state["work_root"])

    @classmethod
    def create(cls, registry: Path, request: dict, inputs: list[Path]) -> "RecoveryJob":
        registry.mkdir(parents=True, exist_ok=True)
        identifier = uuid.uuid4().hex
        work_root = Path(request["output_dir"]) / f".sig_ffmpeg_resume_{identifier}"
        work_root.mkdir(parents=True, exist_ok=True)
        state = {"version": cls.VERSION, "status": "running", "request": request,
                 "work_root": str(work_root), "inputs": {str(p.resolve()): fingerprint(p) for p in inputs},
                 "paths": {}, "steps": {}}
        job = cls(registry / f"{identifier}.json", state)
        job.save()
        return job

    @classmethod
    def load(cls, journal: Path) -> "RecoveryJob":
        state = json.loads(journal.read_text(encoding="utf-8"))
        if state.get("version") != cls.VERSION or state.get("status") == "complete":
            raise ValueError("Checkpoint de FFmpeg indisponível.")
        job = cls(journal, state)
        expected_root = Path(state["request"]["output_dir"]).resolve()
        if job.work_root.resolve().parent != expected_root or not job.work_root.name.startswith(".sig_ffmpeg_resume_"):
            raise ValueError("Diretório de retomada inválido.")
        for raw, expected in state["inputs"].items():
            if fingerprint(Path(raw)) != expected:
                raise ValueError("Um arquivo de entrada mudou; inicie uma nova tarefa.")
        return job

    @classmethod
    def pending(cls, registry: Path) -> list[Path]:
        found = []
        for path in registry.glob("*.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                if state.get("version") == cls.VERSION and state.get("status") in {"running", "failed"}:
                    found.append(path)
            except (OSError, ValueError):
                continue
        return sorted(found, key=lambda path: path.stat().st_mtime_ns, reverse=True)

    def save(self) -> None:
        with self.lock:
            temporary = self.journal.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, self.journal)

    def allocate(self, key: str, factory) -> Path:
        with self.lock:
            if key not in self.state["paths"]:
                self.state["paths"][key] = str(factory())
                self.save()
            return Path(self.state["paths"][key])

    def directory(self, key: str) -> Path:
        name = hashlib.sha256(key.encode()).hexdigest()[:20]
        directory = self.work_root / name
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def command_key(command: list[str]) -> str:
        return hashlib.sha256(json.dumps(command, ensure_ascii=False).encode()).hexdigest()

    def can_reuse(self, command: list[str]) -> bool:
        with self.lock:
            record = self.state["steps"].get(self.command_key(command))
            if not record or record.get("status") != "complete":
                return False
            try:
                if "outputs" in record:
                    return bool(record["outputs"]) and all(fingerprint(Path(path)) == expected
                                                          for path, expected in record["outputs"].items())
                return fingerprint(Path(record["output"])) == record["fingerprint"]
            except OSError:
                return False

    def begin_step(self, command: list[str]) -> None:
        with self.lock:
            self.state["steps"][self.command_key(command)] = {"status": "running"}
            self.save()

    def complete_step(self, command: list[str]) -> None:
        output = Path(command[-1])
        if "%" in output.name and output.is_absolute():
            expression = re.escape(output.name)
            expression = re.sub(r"%0?\d*d", lambda _: r"\d+", expression)
            outputs = [p for p in output.parent.iterdir() if re.fullmatch(expression, p.name) and p.is_file()]
            if not outputs or any(p.stat().st_size <= 0 for p in outputs):
                return
            with self.lock:
                self.state["steps"][self.command_key(command)] = {
                    "status": "complete", "outputs": {str(p): fingerprint(p) for p in outputs}}
                self.save()
            return
        if not output.is_absolute() or not output.is_file() or output.stat().st_size <= 0:
            return
        with self.lock:
            self.state["steps"][self.command_key(command)] = {
                "status": "complete", "output": str(output), "fingerprint": fingerprint(output)}
            self.save()

    def finish(self, status: str) -> None:
        with self.lock:
            self.state["status"] = status
            self.save()
        if status in {"complete", "cancelled"}:
            parent = Path(self.state["request"]["output_dir"]).resolve()
            if self.work_root.resolve().parent == parent and self.work_root.name.startswith(".sig_ffmpeg_resume_"):
                shutil.rmtree(self.work_root, ignore_errors=True)

    def publish(self, staged: Path, output: Path) -> None:
        """Mantém o checkpoint sem duplicar o vídeo quando o volume suporta links."""
        if output.exists():
            if staged.samefile(output):
                return
            raise RuntimeError("O nome da saída de retomada já está ocupado; preserve esse arquivo e escolha outra pasta.")
        try:
            os.link(staged, output)
        except OSError:
            staged.replace(output)
