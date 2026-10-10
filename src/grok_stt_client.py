"""Controle de envios REST do Grok STT na aba Transcrição, sem UI.

xAI: docs.x.ai/developers/rate-limits e
docs.x.ai/developers/model-capabilities/audio/speech-to-text.
O limite de 10 RPS tem margem (8 RPS); todos os uploaders do lote compartilham
o pacing no processo, inclusive retentativas. Outras instâncias/equipes que
usam a mesma cota podem causar 429, tratado com cooldown e backoff.
"""

import logging
import math
import random
import threading
import time
from collections import deque
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from domain_models import Cancelled
from http_clients import GraniteUploader


GROK_STT_REQUESTS_PER_SECOND = 8
GROK_STT_MAX_ATTEMPTS = 5
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_LOGGER = logging.getLogger(__name__)


def _retry_after_seconds(headers: dict[str, str]) -> float:
    value = next((v for k, v in headers.items() if k.casefold() == "retry-after"), "")
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 0.0
    return max(0.0, seconds) if math.isfinite(seconds) else 0.0


class GrokRequestLimiter:
    """Pacing sem reserva antecipada, para não acumular permissões e rajadas.

    O lock cobre somente o início HTTP (conexão + headers), nunca a espera da
    resposta. A próxima permissão conta a partir do envio efetivo dos headers.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._next_start = 0.0
        self._blocked_until = 0.0

    def start(self, cancel_event: threading.Event, send_headers) -> None:
        while True:
            if cancel_event.is_set():
                raise Cancelled()
            if not self._lock.acquire(timeout=0.1):
                continue
            try:
                if cancel_event.is_set():
                    raise Cancelled()
                delay = max(self._next_start, self._blocked_until) - time.monotonic()
                if delay <= 0:
                    try:
                        send_headers()
                    finally:
                        self._next_start = time.monotonic() + 1 / GROK_STT_REQUESTS_PER_SECOND
                    return
            finally:
                self._lock.release()
            if cancel_event.wait(min(delay, 0.1)):
                raise Cancelled()

    def defer(self, seconds: float) -> None:
        with self._lock:
            self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)


_GROK_REQUEST_LIMITER = GrokRequestLimiter()


class GrokTranscriptionUploader(GraniteUploader):
    """Grok REST com até cinco tentativas e métricas sem áudio ou credenciais."""

    def __init__(self, cancel_event, form_fields, extra_headers):
        super().__init__(cancel_event, form_fields, extra_headers, "file")
        self._rate_limiter = _GROK_REQUEST_LIMITER
        self._metrics_lock = threading.Lock()
        self._starts = deque()
        self._peak_rps = 0
        self._responses = 0
        self._successes = 0
        self._rate_limited = 0
        self.on_retry = None

    def _start_request(self, conn) -> None:
        def send_headers():
            conn.endheaders()
            with self._metrics_lock:
                now = time.monotonic()
                self._starts.append(now)
                while self._starts and now - self._starts[0] >= 1:
                    self._starts.popleft()
                self._peak_rps = max(self._peak_rps, len(self._starts))

        self._rate_limiter.start(self.cancel_event, send_headers)

    def statistics_text(self) -> str:
        with self._metrics_lock:
            total = self._responses
            success_pct = 100 * self._successes / total if total else 0
            limited_pct = 100 * self._rate_limited / total if total else 0
            return (
                f"Grok STT: {total} respostas HTTP; "
                f"sucesso {self._successes} ({success_pct:.0f}%); "
                f"429 {self._rate_limited} ({limited_pct:.0f}%); "
                f"pico de início {self._peak_rps} RPS (limite do SIG: {GROK_STT_REQUESTS_PER_SECOND})."
            )

    def post_file_raw(self, url, file_path, mime_type, raw_path, form_fields=None,
                      accept="application/json"):
        for attempt in range(GROK_STT_MAX_ATTEMPTS):
            if self.cancel_event.is_set():
                raise Cancelled()
            status, raw, headers = super().post_file_raw(
                url, file_path, mime_type, raw_path, form_fields, accept
            )
            with self._metrics_lock:
                self._responses += 1
                self._successes += int(200 <= status < 300)
                self._rate_limited += int(status == 429)
            _LOGGER.info(self.statistics_text())
            if status not in _RETRYABLE_STATUS:
                return status, raw, headers
            delay = max(2 ** attempt + random.uniform(0, 0.5), _retry_after_seconds(headers))
            # Mesmo a última resposta 429 protege os outros arquivos da fila.
            if status == 429:
                self._rate_limiter.defer(delay)
            if attempt == GROK_STT_MAX_ATTEMPTS - 1:
                return status, raw, headers
            notice = (
                f"Grok STT: HTTP {status}; nova tentativa {attempt + 2}/{GROK_STT_MAX_ATTEMPTS} "
                f"em {delay:.1f}s."
            )
            _LOGGER.warning(notice)
            if self.on_retry is not None:
                self.on_retry(notice)
            if self.cancel_event.wait(delay):
                raise Cancelled()
