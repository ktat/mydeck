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
