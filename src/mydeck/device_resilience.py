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

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick_once()
            except Exception as e:
                logging.error("DeviceSupervisor tick error: %s", e)
            self._stop_event.wait(self._interval)

    def tick_once(self) -> None:
        """Run one enumerate+reattach pass. Exposed for unit tests."""
        targets = [vd for vd in self._vdecks
                   if vd.has_real_deck() and not vd.connected]
        if not targets:
            return
        try:
            enumerated = list(self._enumerator())
        except Exception as e:
            logging.error("enumerate failed: %s", e)
            return
        by_serial = {}
        for rd in enumerated:
            try:
                sn = rd.get_serial_number()
            except Exception:
                continue
            by_serial[sn] = rd
        for vd in targets:
            sn = vd.get_serial_number()
            rd = by_serial.get(sn)
            if rd is None:
                continue
            try:
                self._opener(rd)
            except (TransportError, OSError) as e:
                logging.info(
                    "reconnect open failed for %s: %s (will retry)", sn, e)
                continue
            try:
                vd.reattach(rd)
                logging.info("device %s reconnected", sn)
            except Exception as e:
                logging.error("reattach failed for %s: %s", sn, e)
