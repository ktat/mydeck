"""Device resilience helpers: DeckGuard proxy and DeviceSupervisor thread.

DeckGuard transparently proxies calls to a real StreamDeck device, catching
TransportError/OSError so a USB disconnect or laptop sleep does not crash
mydeck. DeviceSupervisor periodically re-enumerates devices so mydeck can
reattach to a matching serial when the device comes back.
"""
import logging
from StreamDeck.Transport.Transport import TransportError

_GUARDED_METHODS = frozenset({
    'set_key_image', 'set_touchscreen_image', 'set_brightness',
    'reset', 'close', 'open',
    'set_key_callback', 'set_dial_callback', 'set_touchscreen_callback',
    'set_dial_callback_async', 'set_touchscreen_callback_async',
    'set_poll_frequency',
    # Read methods that may be called while disconnected or before reattach.
    'deck_type', 'is_visual', 'get_serial_number', 'get_firmware_version',
})


class DeckGuard:
    """Transparent proxy for a real StreamDeck.

    All attribute access is delegated to the wrapped real_deck. Method calls
    listed in _GUARDED_METHODS are wrapped so that TransportError/OSError
    triggers the owning VirtualDeck.mark_disconnected().
    """

    def __init__(self, virtual_deck):
        object.__setattr__(self, '_virtual_deck', virtual_deck)
        object.__setattr__(self, '_real_deck', None)

    def _set_real_deck(self, real_deck):
        object.__setattr__(self, '_real_deck', real_deck)

    def _get_real_deck(self):
        return object.__getattribute__(self, '_real_deck')

    def __getattr__(self, name):
        real_deck = object.__getattribute__(self, '_real_deck')
        vd = object.__getattribute__(self, '_virtual_deck')

        if real_deck is None:
            if name in _GUARDED_METHODS:
                return lambda *a, **kw: None
            raise AttributeError(name)

        attr = getattr(real_deck, name)

        if not getattr(vd, 'connected', True):
            if name in _GUARDED_METHODS and callable(attr):
                return lambda *a, **kw: None
            return attr

        if not callable(attr) or name not in _GUARDED_METHODS:
            return attr

        def wrapped(*args, **kwargs):
            try:
                return attr(*args, **kwargs)
            except (TransportError, OSError) as e:
                logging.info(
                    "Device %s disconnected during %s: %s",
                    vd.get_serial_number(), name, e)
                vd.mark_disconnected()
                return None

        return wrapped

    def __enter__(self):
        real_deck = object.__getattribute__(self, '_real_deck')
        if real_deck is not None:
            try:
                real_deck.__enter__()
            except (TransportError, OSError):
                vd = object.__getattribute__(self, '_virtual_deck')
                vd.mark_disconnected()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        real_deck = object.__getattribute__(self, '_real_deck')
        if real_deck is not None:
            try:
                real_deck.__exit__(exc_type, exc_val, exc_tb)
            except (TransportError, OSError):
                vd = object.__getattribute__(self, '_virtual_deck')
                vd.mark_disconnected()
        return False


import threading


class DeviceSupervisor:
    """Periodically re-enumerate physical devices and reattach matching serials.

    The supervisor is a daemon thread. Dependency injection keeps tests fast:
    `enumerator` returns the current list of physical deck handles (same shape
    as `DeviceManager().enumerate()`); `opener` is a callable that opens a
    freshly-enumerated deck (default: `real_deck.open()`).
    """

    _last_waiting_log = 0.0

    def __init__(self, virtual_decks, enumerator=None, opener=None,
                 interval: float = 3.0):
        self._vdecks = list(virtual_decks)
        if enumerator is None:
            from StreamDeck.DeviceManager import DeviceManager
            enumerator = lambda: DeviceManager().enumerate()
        if opener is None:
            opener = lambda rd: rd.open()
        self._enumerator = enumerator
        self._opener = opener
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread = None

    def add_virtual_deck(self, vdeck) -> None:
        self._vdecks.append(vdeck)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, daemon=True, name='DeviceSupervisor')
        self._thread.start()
        logging.info(
            "DeviceSupervisor started (interval=%.1fs, watching %d decks)",
            self._interval, len(self._vdecks))

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick_once()
            except Exception as e:
                logging.error("DeviceSupervisor tick error: %s", e)
            self._stop_event.wait(self._interval)

    def _connected_paths(self) -> set:
        paths: set = set()
        for vd in self._vdecks:
            if not vd.has_real_deck() or not vd.connected:
                continue
            try:
                rd = vd._guard._get_real_deck()
                if rd is None:
                    continue
                path = rd.device.device_info.get('path')
                if path:
                    paths.add(path)
            except Exception as e:
                logging.debug("could not read path for %s: %s",
                              vd.get_serial_number(), e)
        return paths

    def tick_once(self) -> None:
        """Run one enumerate+reattach pass. Exposed for unit tests.

        Strategy: python-elgato-streamdeck's get_serial_number() requires the
        device to be open, so we open each enumerated candidate, read its
        serial, match against pending targets, reattach on match, otherwise
        close the candidate and move on.
        """
        targets = [vd for vd in self._vdecks
                   if vd.has_real_deck() and not vd.connected]
        if not targets:
            return

        target_serials = {vd.get_serial_number(): vd for vd in targets}

        # Throttled "still waiting" log (every ~30s).
        import time
        now = time.monotonic()
        if now - DeviceSupervisor._last_waiting_log > 30:
            logging.info(
                "DeviceSupervisor: waiting for %s to reconnect",
                sorted(target_serials.keys()))
            DeviceSupervisor._last_waiting_log = now

        try:
            enumerated = list(self._enumerator())
        except Exception as e:
            logging.error("enumerate failed: %s", e)
            return

        logging.debug(
            "DeviceSupervisor: enumerate returned %d candidates, %d targets",
            len(enumerated), len(targets))

        skip_paths = self._connected_paths()

        for rd in enumerated:
            try:
                cand_path = rd.device.device_info.get('path')
            except Exception:
                cand_path = None
            if cand_path and cand_path in skip_paths:
                logging.debug(
                    "DeviceSupervisor: skipping already-connected path %s",
                    cand_path)
                continue
            if not target_serials:
                break
            try:
                self._opener(rd)
            except (TransportError, OSError) as e:
                logging.debug("open candidate failed: %s", e)
                continue

            try:
                sn = rd.get_serial_number()
            except (TransportError, OSError) as e:
                logging.debug("get_serial after open failed: %s", e)
                try:
                    rd.close()
                except Exception:
                    pass
                continue

            vd = target_serials.pop(sn, None)
            if vd is None:
                # Not one of our targets; close it and move on.
                try:
                    rd.close()
                except Exception:
                    pass
                continue

            try:
                vd.reattach(rd)
                logging.info("device %s reconnected", sn)
            except Exception as e:
                logging.error("reattach failed for %s: %s", sn, e)
                try:
                    rd.close()
                except Exception:
                    pass
