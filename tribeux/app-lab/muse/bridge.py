"""Muse 2 LSL → WebSocket bridge.

Run this AFTER `muselsl stream` is already running in another terminal.
The bridge resolves the EEG stream from LSL, pulls samples at ~256 Hz, and
forwards each sample to every connected WebSocket client as JSON.

Why this design:
- muselsl handles the Muse 2 BLE quirks (channel ordering, unit scaling).
- LSL → WS is a simple pipe that keeps the BLE state in one process and the
  browser-side code fully decoupled.
- JSON is lossy but adequate for 256 Hz * 4ch; packing frames over the wire
  would be a micro-optimisation for the hackathon.

Protocol:
    Once on connect:
        {"type": "hello", "channels": ["TP9","AF7","AF8","TP10"], "sr": 256}
    Then for every sample:
        {"type": "eeg", "t": <seconds>, "ch": [v_tp9, v_af7, v_af8, v_tp10]}
    Heartbeat when no EEG pulled for >1s:
        {"type": "idle"}

Usage:
    pip install pylsl websockets
    python bridge.py        # listens on ws://127.0.0.1:8787
"""
from __future__ import annotations

import asyncio
import json
import signal
import sys
import time
from typing import Set

from pylsl import resolve_byprop, StreamInlet
import websockets
from websockets.server import WebSocketServerProtocol

HOST = "127.0.0.1"
PORT = 8787
EEG_CHANNELS = ["TP9", "AF7", "AF8", "TP10"]
SR = 256  # Hz — Muse 2 EEG nominal sample rate
LSL_TIMEOUT = 5.0

clients: Set[WebSocketServerProtocol] = set()


async def broadcast(msg: dict) -> None:
    """Send msg to every connected client. Drops dead clients silently."""
    if not clients:
        return
    payload = json.dumps(msg)
    dead = set()
    for ws in clients:
        try:
            await ws.send(payload)
        except websockets.ConnectionClosed:
            dead.add(ws)
    clients.difference_update(dead)


async def handler(ws: WebSocketServerProtocol) -> None:
    """One coroutine per connected client. Just holds the connection open."""
    clients.add(ws)
    print(f"[ws] client connected ({len(clients)} total)", file=sys.stderr)
    try:
        await ws.send(
            json.dumps({"type": "hello", "channels": EEG_CHANNELS, "sr": SR})
        )
        # Keep the connection open; server→client is one-way.
        async for _ in ws:
            pass
    finally:
        clients.discard(ws)
        print(f"[ws] client disconnected ({len(clients)} total)", file=sys.stderr)


async def pump_lsl() -> None:
    """Resolve the Muse EEG LSL stream and forward samples forever.

    Fails loudly if no stream is found — never returns silently. The bridge
    is useless without a live EEG stream, so that's correct.
    """
    print(f"[lsl] resolving EEG stream (timeout {LSL_TIMEOUT}s)…", file=sys.stderr)
    streams = resolve_byprop("type", "EEG", timeout=LSL_TIMEOUT)
    if not streams:
        raise SystemExit(
            "[lsl] no EEG stream found. Start one first:\n"
            "      muselsl stream\n"
            "and make sure your Muse 2 is on and paired."
        )
    inlet = StreamInlet(streams[0], max_chunklen=12)
    info = inlet.info()
    print(
        f"[lsl] connected to '{info.name()}' "
        f"({info.channel_count()}ch @ {info.nominal_srate()} Hz)",
        file=sys.stderr,
    )

    last_emit = time.monotonic()
    while True:
        chunk, ts = inlet.pull_chunk(timeout=0.1, max_samples=32)
        now = time.monotonic()
        if chunk:
            for i, sample in enumerate(chunk):
                # Take only the first 4 values — Muse 2 LSL sometimes carries
                # an AUX channel as a 5th; we ignore it.
                ch = sample[:4]
                await broadcast(
                    {"type": "eeg", "t": ts[i], "ch": list(ch)}
                )
            last_emit = now
        elif now - last_emit > 1.0:
            await broadcast({"type": "idle"})
            last_emit = now
        # Yield to the event loop so WS sends go out.
        await asyncio.sleep(0)


async def main() -> None:
    print(f"[ws] listening on ws://{HOST}:{PORT}", file=sys.stderr)
    async with websockets.serve(handler, HOST, PORT):
        await pump_lsl()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
