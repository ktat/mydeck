import time
import logging
from typing import Callable

class Lock:
    locking: dict = {}

    def __init__(self, lock:str) -> None:
        self.lock = lock

    def is_locked(self) -> bool:
        return Lock.locked(self.lock)

    def wait(self, wait_second: float = 0.001):
        time_locked: float = 0
        while Lock.locked(self.lock):
            time_locked += wait_second
            time.sleep(time_locked)
            if wait_second % 0.01 == 0:
                logging.debug("waiting lock for %s (%f sec)" % (self.lock, time_locked))
        Lock.locking[self.lock] = True

    def unlock(self):
        if Lock.locking.get(self.lock) is not None:
            del Lock.locking[self.lock]

    @staticmethod
    def locked(lock: str) -> bool:
        return Lock.locking.get(lock) is not None

    @staticmethod
    def do_with_lock(lock: str, l: Callable, wait: float = 0.001):
        lo = Lock(lock)
        lo.wait(wait)
        l()
        lo.unlock()