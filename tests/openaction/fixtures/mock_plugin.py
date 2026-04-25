"""Minimal in-process mock of an Elgato plugin (WebSocket client).

Run as: python mock_plugin.py -port <port> -pluginUUID <uuid> -registerEvent registerPlugin -info '<json>'
"""
import argparse
import asyncio
import json
import os

import websockets


async def run(port: int, plugin_uuid: str, register_event: str, info_json: str, script: str):
    uri = f"ws://127.0.0.1:{port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"event": register_event, "uuid": plugin_uuid}))
        if script == "echo-key":
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("event") == "keyDown":
                    await ws.send(json.dumps({
                        "event": "setTitle",
                        "context": msg["context"],
                        "payload": {"title": "pressed", "target": 0},
                    }))
        elif script == "noop":
            await asyncio.Event().wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-port", type=int, required=True)
    parser.add_argument("-pluginUUID", required=True)
    parser.add_argument("-registerEvent", required=True)
    parser.add_argument("-info", required=True)
    args = parser.parse_args()
    script = os.environ.get("MOCK_PLUGIN_SCRIPT", "noop")
    asyncio.run(run(args.port, args.pluginUUID, args.registerEvent, args.info, script))


if __name__ == "__main__":
    main()
