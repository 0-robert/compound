# Muse 2 bridge

Pipes Muse 2 EEG samples into the browser via LSL → WebSocket.

```
Muse 2 ──Bluetooth──▶ muselsl ──LSL──▶ bridge.py ──WebSocket──▶ /muse page
```

## One-time setup

```bash
pip install -r requirements.txt
```

Pair the Muse 2 with your Mac (Bluetooth settings → turn on headset → Pair).

## Each run — two terminals

**Terminal 1** — start the LSL stream (keep running):
```bash
muselsl stream
```

You'll see "Streaming EEG…" once the headset is connected.

**Terminal 2** — start the WebSocket bridge (keep running):
```bash
python bridge.py
```

You'll see `[lsl] connected to 'Muse-XXXX' (5ch @ 256.0 Hz)`.

## Use it

Open http://localhost:5180/muse — it connects to `ws://127.0.0.1:8787`
automatically and starts drawing.

## Troubleshooting

- `[lsl] no EEG stream found` → muselsl isn't running or the headset lost its
  Bluetooth link. Restart `muselsl stream`.
- `websocket.ConnectionClosed` spam in the bridge log → the browser tab
  closed. Harmless.
- Waveforms look flat → check the muselsl terminal for signal-quality warnings;
  the Muse 2 needs skin contact on all four sensors.
