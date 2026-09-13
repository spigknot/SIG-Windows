"""Execução paralela do lote com cancelamento IMEDIATO (regra do usuário, 13/09).

Cancelar não pode esperar resposta de servidor: as esperas são feitas em fatias
curtas (que checam o `cancel_event` a cada 50 ms) e o executor é desligado SEM
esperar (`shutdown(wait=False, cancel_futures=True)`).

Antes, `with ThreadPoolExecutor(...) as executor:` + `as_completed(...)`
bloqueavam até a última requisição em voo terminar (o timeout HTTP chega a
180 s), então o cancelamento parecia travado e o relatório parcial não saía.

Sem Tkinter, sem rede: só orquestração de futures (testável isolada).
"""

import concurrent.futures
import contextlib
import time

from domain_models import Cancelled

POLL_INTERVAL = 0.05


@contextlib.contextmanager
def cancellable_executor(max_workers: int):
    """Executor que NÃO segura o cancelamento na saída do bloco.

    `shutdown(wait=False)` devolve na hora: as tarefas em voo viram órfãs
    (morrem quando a requisição/processo delas terminar) e o workflow segue
    para o cancelamento.
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(max_workers)))
    try:
        yield executor
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def iter_completed(futures, *, cancel_event, poll: float = POLL_INTERVAL):
    """Itera as futures CONFORME completam, abortando na hora se cancelar.

    Substitui `concurrent.futures.as_completed` (que ignora o cancelamento e
    deixa o workflow preso até a última resposta chegar). Aceita qualquer
    iterável de futures (lista ou dict — o dict itera as chaves) e devolve as
    futures prontas; o chamador faz `future.result()`. Levanta `Cancelled`
    assim que o evento é visto — as futures pendentes ficam para trás.
    """
    pending = set(futures)
    while pending:
        if cancel_event.is_set():
            raise Cancelled()
        done, pending = concurrent.futures.wait(pending, timeout=poll)
        for future in done:
            yield future


def cancellable_join(work_queue, *, cancel_event, poll: float = POLL_INTERVAL) -> None:
    """`queue.Queue.join()` que não trava o cancelamento (mesma regra)."""
    with work_queue.all_tasks_done:
        while work_queue.unfinished_tasks:
            if cancel_event.is_set():
                raise Cancelled()
            work_queue.all_tasks_done.wait(poll)


def wait_cancellable(condition, *, cancel_event, poll: float = POLL_INTERVAL, timeout: float | None = None) -> bool:
    """Espera uma condição (callable) checar o cancelamento a cada `poll` s.

    Devolve True quando a condição ficou verdadeira e False quando o tempo
    acabou; levanta `Cancelled` se o cancelamento chegar antes.
    """
    limite = None if timeout is None else time.monotonic() + timeout
    while True:
        if cancel_event.is_set():
            raise Cancelled()
        if condition():
            return True
        if limite is not None and time.monotonic() >= limite:
            return False
        time.sleep(poll)
