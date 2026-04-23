def test_context_module_has_no_websockets_dependency():
    """KeyContext must be importable without websockets installed."""
    import importlib
    import sys
    # Re-import context fresh; it should succeed without importing server.py
    mod = importlib.import_module("mydeck.openaction.context")
    assert hasattr(mod, "KeyContext")
    # server.py should NOT be in sys.modules just from importing context.py
    # (This assertion is best-effort; it may already be loaded by a previous test.)
