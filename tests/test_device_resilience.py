import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock

# Stub StreamDeck.Transport.Transport so we can import device_resilience
# without the native library installed in the test env.
transport_mod = MagicMock()
class _TransportError(Exception):
    pass
transport_mod.TransportError = _TransportError
sys.modules.setdefault('StreamDeck', MagicMock())
sys.modules.setdefault('StreamDeck.Transport', MagicMock())
sys.modules['StreamDeck.Transport.Transport'] = transport_mod

_module_path = os.path.join(
    os.path.dirname(__file__), '..', 'src', 'mydeck', 'device_resilience.py')
_spec = importlib.util.spec_from_file_location(
    'mydeck.device_resilience', _module_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules['mydeck.device_resilience'] = _mod
_spec.loader.exec_module(_mod)

DeckGuard = _mod.DeckGuard
TransportError = _TransportError


class FakeVirtualDeck:
    def __init__(self, serial='SN1'):
        self.connected = True
        self.serial = serial
        self.mark_disconnected_called = 0

    def get_serial_number(self):
        return self.serial

    def mark_disconnected(self):
        self.mark_disconnected_called += 1
        self.connected = False


class TestDeckGuardProxy(unittest.TestCase):
    def test_method_call_passes_through_when_connected(self):
        vd = FakeVirtualDeck()
        real = MagicMock()
        real.set_key_image.return_value = 'ok'
        guard = DeckGuard(vd)
        guard._set_real_deck(real)

        result = guard.set_key_image(0, 'img')

        self.assertEqual(result, 'ok')
        real.set_key_image.assert_called_once_with(0, 'img')


if __name__ == '__main__':
    unittest.main()
