from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class Command(Enum):
    SET_IMAGE = "setImage"
    SET_TITLE = "setTitle"
    SET_SETTINGS = "setSettings"
    GET_SETTINGS = "getSettings"
    SEND_TO_PLUGIN = "sendToPlugin"
    SEND_TO_PI = "sendToPropertyInspector"
    LOG_MESSAGE = "logMessage"
    GET_GLOBAL_SETTINGS = "getGlobalSettings"
    SET_GLOBAL_SETTINGS = "setGlobalSettings"


@dataclass
class ParsedCommand:
    kind: Command
    context: str
    payload: Dict[str, Any]


def _appear_payload(
    action_uuid: str,
    context: str,
    device: str,
    row: int,
    column: int,
    settings: Dict[str, Any],
    event: str,
) -> Dict[str, Any]:
    return {
        "event": event,
        "action": action_uuid,
        "context": context,
        "device": device,
        "payload": {
            "settings": settings,
            "coordinates": {"row": row, "column": column},
            "state": 0,
            "controller": "Keypad",
            "isInMultiAction": False,
        },
    }


def make_did_receive_settings(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "didReceiveSettings")


def make_will_appear(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "willAppear")


def make_will_disappear(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "willDisappear")


def make_key_down(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "keyDown")


def make_key_up(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "keyUp")


def make_send_to_plugin(action_uuid, context, payload):
    return {
        "event": "sendToPlugin",
        "action": action_uuid,
        "context": context,
        "payload": payload,
    }


def make_send_to_pi(action_uuid, context, payload):
    return {
        "event": "sendToPropertyInspector",
        "action": action_uuid,
        "context": context,
        "payload": payload,
    }


def parse_command(raw: Dict[str, Any]) -> Optional[ParsedCommand]:
    event = raw.get("event")
    try:
        kind = Command(event)
    except ValueError:
        return None
    return ParsedCommand(
        kind=kind,
        context=raw.get("context", ""),
        payload=raw.get("payload", {}) or {},
    )
