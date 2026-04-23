from mydeck.openaction.protocol import (
    make_will_appear,
    make_will_disappear,
    make_key_down,
    make_key_up,
    parse_command,
    Command,
)


def test_make_will_appear_has_required_fields():
    msg = make_will_appear(
        action_uuid="com.example.mvp.ping",
        context="ctx-1",
        device="dev-1",
        row=0,
        column=2,
        settings={"foo": "bar"},
    )
    assert msg["event"] == "willAppear"
    assert msg["action"] == "com.example.mvp.ping"
    assert msg["context"] == "ctx-1"
    assert msg["device"] == "dev-1"
    assert msg["payload"]["coordinates"] == {"row": 0, "column": 2}
    assert msg["payload"]["settings"] == {"foo": "bar"}
    assert msg["payload"]["state"] == 0
    assert msg["payload"]["controller"] == "Keypad"


def test_make_will_disappear_mirrors_will_appear():
    msg = make_will_disappear(
        action_uuid="com.example.mvp.ping",
        context="ctx-1",
        device="dev-1",
        row=1,
        column=0,
        settings={},
    )
    assert msg["event"] == "willDisappear"
    assert msg["action"] == "com.example.mvp.ping"


def test_make_key_down_and_up():
    down = make_key_down("com.example.mvp.ping", "ctx-1", "dev-1", 0, 0, {"x": 1})
    up = make_key_up("com.example.mvp.ping", "ctx-1", "dev-1", 0, 0, {"x": 1})
    assert down["event"] == "keyDown"
    assert up["event"] == "keyUp"
    assert down["payload"]["settings"] == {"x": 1}


def test_parse_command_set_image():
    raw = {
        "event": "setImage",
        "context": "ctx-1",
        "payload": {"image": "data:image/png;base64,AAA", "target": 0, "state": None},
    }
    cmd = parse_command(raw)
    assert cmd.kind == Command.SET_IMAGE
    assert cmd.context == "ctx-1"
    assert cmd.payload["image"] == "data:image/png;base64,AAA"


def test_parse_command_set_title():
    raw = {
        "event": "setTitle",
        "context": "ctx-1",
        "payload": {"title": "Hi", "target": 0},
    }
    cmd = parse_command(raw)
    assert cmd.kind == Command.SET_TITLE
    assert cmd.payload["title"] == "Hi"


def test_parse_command_unknown_event_returns_none():
    raw = {"event": "somethingElse", "context": "c"}
    assert parse_command(raw) is None


def test_parse_command_set_settings():
    raw = {"event": "setSettings", "context": "ctx-1", "payload": {"value": 5}}
    cmd = parse_command(raw)
    assert cmd.kind == Command.SET_SETTINGS
    assert cmd.payload == {"value": 5}


def test_parse_command_get_settings():
    raw = {"event": "getSettings", "context": "ctx-1", "payload": {}}
    cmd = parse_command(raw)
    assert cmd.kind == Command.GET_SETTINGS


def test_make_did_receive_settings():
    from mydeck.openaction.protocol import make_did_receive_settings
    msg = make_did_receive_settings("com.x.action", "ctx-1", "dev-1", 0, 2, {"value": 5})
    assert msg["event"] == "didReceiveSettings"
    assert msg["action"] == "com.x.action"
    assert msg["context"] == "ctx-1"
    assert msg["payload"]["settings"] == {"value": 5}
