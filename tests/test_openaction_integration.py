from unittest.mock import MagicMock

from mydeck.openaction.server import KeyContext


def test_set_key_with_action_calls_bridge_will_appear():
    from mydeck import MyDeck

    bridge = MagicMock()
    mydeck = MyDeck.__new__(MyDeck)
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck._exit = False
    mydeck._openaction_bridge = bridge
    mydeck._current_page = "@HOME"
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k

    # Minimal fake conf: action + settings only, no image
    conf = {"action": "com.example.mvp.ping", "settings": {"foo": "bar"}}
    mydeck.set_key(0, conf, use_lock=False)

    bridge.will_appear.assert_called_once()
    call_args = bridge.will_appear.call_args
    ctx = call_args.args[0]
    assert isinstance(ctx, KeyContext)
    assert ctx.key == 0
    assert call_args.args[1] == "com.example.mvp.ping"
    assert call_args.args[2] == {"foo": "bar"}


def test_set_key_without_action_uses_default_path():
    from mydeck import MyDeck

    bridge = MagicMock()
    mydeck = MyDeck.__new__(MyDeck)
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck._exit = False
    mydeck._openaction_bridge = bridge
    mydeck.abs_key = lambda k: k
    mydeck.update_key_image = MagicMock()
    mydeck.render_key_image = MagicMock(return_value=b"x")

    conf = {"image": "foo.png", "label": "Foo"}
    mydeck.set_key(0, conf, use_lock=False)

    bridge.will_appear.assert_not_called()
    mydeck.update_key_image.assert_called_once()


def test_key_change_callback_with_action_dispatches_key_down():
    from mydeck import MyDeck
    from unittest.mock import MagicMock

    bridge = MagicMock()
    mydeck = MyDeck.__new__(MyDeck)
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck._exit = False
    mydeck._openaction_bridge = bridge
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k
    mydeck.debug = lambda *a, **kw: None
    mydeck.key_config = lambda: {"@HOME": {0: {"action": "com.example.mvp.ping", "settings": {"a": 1}}}}
    mydeck.config = None

    # Press
    mydeck.key_change_callback(0, True)
    bridge.key_down.assert_called_once()
    assert bridge.key_down.call_args.args[1] == "com.example.mvp.ping"
    # Release
    mydeck.key_change_callback(0, False)
    bridge.key_up.assert_called_once()
