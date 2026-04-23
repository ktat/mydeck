from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class Command(Enum):
    SET_IMAGE = "setImage"
    SET_TITLE = "setTitle"


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


def make_will_appear(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "willAppear")


def make_will_disappear(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "willDisappear")


def make_key_down(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "keyDown")


def make_key_up(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "keyUp")


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
