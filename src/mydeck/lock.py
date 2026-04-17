import logging
import threading
import time
from typing import Callable


class Lock:
    """Per-name re-entrant lock.

    Previously this was a polling lock backed by a module-global dict, which
    deadlocks if the same thread tries to acquire the same lock recursively.
    Now each name maps to a threading.RLock so same-thread re-entry is safe
    and cross-thread contention still serializes correctly.
    """

    _rlocks: dict = {}
    _rlocks_mutex = threading.Lock()

    # Back-compat attribute: some callers read `Lock.locking` to check
    # whether a name is currently held. We expose a proxy that reflects
    # whether the RLock is currently acquired by *any* thread.
    locking: dict = {}

    def __init__(self, lock: str) -> None:
        self.lock = lock

    @classmethod
    def _get_rlock(cls, name: str) -> threading.RLock:
        with cls._rlocks_mutex:
            rlock = cls._rlocks.get(name)
            if rlock is None:
                rlock = threading.RLock()
                cls._rlocks[name] = rlock
            return rlock

    def is_locked(self) -> bool:
        return Lock.locked(self.lock)

    def wait(self, wait_second: float = 0.001) -> None:
        # The parameter is kept for API compatibility; RLock.acquire blocks
        # without polling so wait_second is ignored.
        del wait_second
        self._get_rlock(self.lock).acquire()
        Lock.locking[self.lock] = True

    def unlock(self) -> None:
        try:
            self._get_rlock(self.lock).release()
        except RuntimeError:
            # Releasing a lock we don't hold; ignore to match old
            # best-effort semantics.
            return
        # Best-effort: clear the back-compat flag only when nobody holds it.
        rlock = Lock._rlocks.get(self.lock)
        if rlock is not None:
            acquired = rlock.acquire(blocking=False)
            if acquired:
                try:
                    Lock.locking.pop(self.lock, None)
                finally:
                    rlock.release()

    @staticmethod
    def locked(lock: str) -> bool:
        rlock = Lock._rlocks.get(lock)
        if rlock is None:
            return False
        acquired = rlock.acquire(blocking=False)
        if acquired:
            rlock.release()
            return False
        return True

    @staticmethod
    def do_with_lock(lock: str, l: Callable, wait: float = 0.05) -> None:
        lo = Lock(lock)
        lo.wait(wait)
        try:
            l()
        finally:
            lo.unlock()
