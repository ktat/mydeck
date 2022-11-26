import time
import logging

class Lock:
    locking: dict = {}

    def __init__(self) -> None:
        pass
        
    def locked(lock: str) -> bool:
        return Lock.locking.get(lock) is not None

    def wait_can_lock(lock: str, wait_second: float = 0.001):
        time_locked: float = 0
        while Lock.locked(lock):
            time_locked += wait_second
            time.sleep(time_locked)
            if wait_second % 0.01 == 0:
                logging.debug("waiting lock for %s (%f sec)" % (lock, time_locked))
        Lock.locking[lock] = True

    def unlock(lock):
        if Lock.locking.get(lock) is not None:
            del Lock.locking[lock]