"""Cota REST do Gemini Transcribe: pacing, saldo local persistido e dados HTTP.

As cotas do Google são por projeto; este registro por chave identifica apenas
o uso neste computador. Headers opcionais não são tratados como saldo diário.
SQLite coordena workers e processos; nenhum segredo ou áudio é persistido.
"""
import hashlib
import json
import logging
import random
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone

from app_env import settings_path
from domain_models import Cancelled
from grok_stt_client import _retry_after_seconds

MINUTE_LIMIT = 10
DAILY_LIMIT = 100
PACE_SECONDS = 7.5  # 8/minuto, inclusive retentativas; sem rajada inicial.
MAX_ATTEMPTS = 5
HELP_TEXT = (
    "Gemini 3.5 Transcribe: limite considerado de 10 requisições por minuto "
    "e 100 por dia. O SIG inicia até 8 por minuto, inclusive retentativas. "
    "Por isso, o envio de vários arquivos pode demorar.\n\n"
    "A cota diária reinicia à meia-noite do horário do Pacífico. Ao esgotá-la, "
    "o SIG interrompe os novos envios. Parar interrompe a espera.\n\n"
    "A cota do Google é compartilhada pelo projeto. A contagem local não "
    "inclui outros aparelhos, aplicativos ou chaves do mesmo projeto. "
    "O saldo global só aparece quando informado pela API.\n\n"
)


def pacific_day(now: float) -> str:
    """Calendário Pacific (EUA, regra pós-2007), sem depender de tzdata no Windows."""
    utc = datetime.fromtimestamp(now, timezone.utc)
    march = datetime(utc.year, 3, 1, tzinfo=timezone.utc)
    november = datetime(utc.year, 11, 1, tzinfo=timezone.utc)
    start = march + timedelta(days=(6 - march.weekday()) % 7 + 7, hours=10)
    end = november + timedelta(days=(6 - november.weekday()) % 7, hours=9)
    return (utc - timedelta(hours=7 if start <= utc < end else 8)).date().isoformat()


def quota_details(raw: bytes) -> tuple[bool, float]:
    try:
        details = json.loads(raw).get("error", {}).get("details", [])
    except (ValueError, AttributeError, TypeError):
        return False, 0
    daily, retry = False, 0.0
    for detail in details:
        if not isinstance(detail, dict):
            continue
        for violation in detail.get("violations", []):
            if not isinstance(violation, dict):
                continue
            metric = str(violation.get("quotaMetric", "")) + str(violation.get("quotaId", ""))
            daily |= "per_day" in metric.lower() or "perday" in metric.lower()
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            value = str(detail.get("retryDelay", ""))
            if value.endswith("s"):
                retry = max(retry, _retry_after_seconds({"Retry-After": value[:-1]}))
    return daily, retry


class GeminiQuota:
    """Registra cada início real de inferência; respostas continuam paralelas."""
    def __init__(self, api_key: str, path=None, now=time.time):
        self.scope = hashlib.sha256(api_key.encode()).hexdigest()
        self.path = path or settings_path().parent / "gemini_stt_quota.sqlite3"
        self.now = now
        self._errors = 0
        self._lock = threading.Lock()
        self.on_error = None
        self.on_retry = None

    @property
    def error_count(self):
        with self._lock:
            return self._errors

    def _open(self):
        db = sqlite3.connect(self.path, timeout=0.1)
        try:
            db.execute("CREATE TABLE IF NOT EXISTS quota (scope TEXT PRIMARY KEY, state TEXT NOT NULL)")
        except Exception:
            db.close()
            raise
        return db

    def _load(self, db):
        row = db.execute("SELECT state FROM quota WHERE scope=?", (self.scope,)).fetchone()
        state = json.loads(row[0]) if row else {}
        day = pacific_day(self.now())
        if state.get("day") != day:
            state.update(day=day, used=0, daily_block=False, responses=0, errors=0, limited=0)
        return state

    def _save(self, db, state):
        db.execute("INSERT OR REPLACE INTO quota VALUES (?, ?)", (self.scope, json.dumps(state)))

    def check_available(self):
        db = self._open()
        try:
            state = self._load(db)
            if state.get("daily_block") or state.get("used", 0) >= DAILY_LIMIT:
                raise RuntimeError("Gemini: limite diário de 100 requisições atingido. Retome após a meia-noite do Pacífico.")
        finally:
            db.close()

    def start(self, cancel_event, send_headers):
        while True:
            if cancel_event.is_set():
                raise Cancelled()
            try:
                db = self._open()
                try:
                    db.execute("BEGIN IMMEDIATE")
                    state = self._load(db)
                    if state.get("daily_block") or state.get("used", 0) >= DAILY_LIMIT:
                        raise RuntimeError("Gemini: limite diário de 100 requisições atingido. Retome após a meia-noite do Pacífico.")
                    delay = max(state.get("next", 0), state.get("blocked", 0)) - self.now()
                    if delay <= 0:
                        if cancel_event.is_set():
                            raise Cancelled()
                        state["used"] = state.get("used", 0) + 1
                        state["starts"] = [t for t in state.get("starts", []) if self.now() - t < 60]
                        state["starts"].append(self.now())
                        try:
                            send_headers()
                        finally:
                            state["next"] = self.now() + PACE_SECONDS
                            self._save(db, state)
                            db.commit()
                        return
                finally:
                    db.close()
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                delay = 0.1
            if cancel_event.wait(min(delay, 0.1)):
                raise Cancelled()

    def observe(self, status, raw, headers):
        daily, retry = quota_details(raw) if status == 429 else (False, 0)
        normalized = {k.lower(): str(v)[:120] for k, v in headers.items()}
        with self._lock:
            self._errors += int(not 200 <= status < 300)
        # Uma resposta não deve se perder por competição breve entre workers.
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            state = self._load(db)
            state["responses"] = state.get("responses", 0) + 1
            state["errors"] = state.get("errors", 0) + int(not 200 <= status < 300)
            state["limited"] = state.get("limited", 0) + int(status == 429)
            state["status"] = status
            state["observed"] = self.now()
            state["headers"] = {k: v for k, v in normalized.items() if k in (
                "x-ratelimit-remaining-requests", "x-ratelimit-limit-requests",
                "x-ratelimit-remaining-tokens", "x-ratelimit-reset",
            )}
            state["daily_block"] = state.get("daily_block", False) or daily
            self._save(db, state)
        if not 200 <= status < 300 and self.on_error:
            self.on_error()
        return daily, max(retry, _retry_after_seconds(normalized))

    def defer(self, delay):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            state = self._load(db)
            state["blocked"] = max(state.get("blocked", 0), self.now() + delay)
            self._save(db, state)

    def execute(self, cancel_event, request):
        for attempt in range(MAX_ATTEMPTS):
            if cancel_event.is_set():
                raise Cancelled()
            status, raw, headers = result = request()
            daily, server_delay = self.observe(status, raw, headers)
            logging.getLogger(__name__).info("Gemini STT: HTTP %s; erros na rodada %s", status, self.error_count)
            if daily or status not in {429, 500, 502, 503, 504}:
                return result
            delay = max(2 ** attempt + random.uniform(0, .5), server_delay)
            if status == 429:
                self.defer(delay)
            if attempt == MAX_ATTEMPTS - 1:
                return result
            if self.on_retry:
                self.on_retry(f"Gemini STT: HTTP {status}; nova tentativa {attempt + 2}/5 após {delay:.1f}s e o pacing de 8/min.")
            if cancel_event.wait(delay):
                raise Cancelled()

    def statistics_text(self):
        db = self._open()
        try:
            state = self._load(db)
        finally:
            db.close()
        now = self.now()
        minute = sum(now - t < 60 for t in state.get("starts", []))
        used = state.get("used", 0)
        wait = max(0, max(state.get("next", 0), state.get("blocked", 0)) - now)
        text = (f"Uso local: {minute}/10 no último minuto; {used}/100 hoje (Pacífico).\n"
                f"Saldo diário local: {max(0, DAILY_LIMIT - used)}.\n"
                f"Respostas HTTP hoje: {state.get('responses', 0)}; erros: {state.get('errors', 0)}; 429: {state.get('limited', 0)}.\n")
        if state.get("daily_block") or used >= DAILY_LIMIT:
            text += "Novos envios bloqueados até a meia-noite do Pacífico.\n"
        else:
            text += f"Próxima permissão local em {wait:.1f}s.\n"
        if state.get("daily_block"):
            text += "A API informou esgotamento da cota diária; novos envios bloqueados.\n"
        headers = state.get("headers", {})
        if not headers:
            text += "Saldo global de requisições/tokens: não informado pela API."
        else:
            labels = {"x-ratelimit-remaining-requests": "Requisições restantes", "x-ratelimit-limit-requests": "Limite da janela",
                      "x-ratelimit-remaining-tokens": "Tokens restantes", "x-ratelimit-reset": "Reinício informado"}
            text += "Dados da última resposta da API (janela não especificada):\n" + "\n".join(f"{labels[k]}: {v}" for k, v in headers.items())
        if state.get("observed"):
            text += "\nÚltima resposta: " + datetime.fromtimestamp(state["observed"]).strftime("%d/%m %H:%M:%S")
        return text
