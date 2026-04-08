#!/usr/bin/env python3
"""
WebSocket Audio Server for Inspekt Browser VM.
Streams PulseAudio output as WebM/Opus via WebSocket to browser clients.

Replaces the websockify wrap-mode approach which required rebind.so.
Uses the same websockets library as terminal-server.py.
"""

import asyncio
import os
import signal
from websockets.server import serve
from websockets.exceptions import ConnectionClosed

PORT = 6081
PULSE_SERVER = os.environ.get("PULSE_SERVER", "unix:/tmp/pulse-socket")

# GStreamer pipeline: PulseAudio monitor → Opus/WebM → stdout
GST_CMD = [
    "gst-launch-1.0", "-q",
    "pulsesrc", "device=audio_out.monitor",
    "!", "audioconvert",
    "!", "audioresample",
    "!", "audio/x-raw,rate=48000,channels=2",
    "!", "queue", "max-size-time=100000000",
    "!", "opusenc", "audio-type=restricted-lowdelay",
    "bitrate=96000", "bitrate-type=0", "complexity=0", "frame-size=10",
    "!", "webmmux", "streamable=true", "min-cluster-duration=50000000",
    "!", "fdsink", "fd=1",
]


async def audio_handler(websocket):
    """Handle a single audio WebSocket client."""
    print(f"[Audio] Client connected from {websocket.remote_address}")

    env = os.environ.copy()
    env["PULSE_SERVER"] = PULSE_SERVER

    process = None
    try:
        # Start GStreamer pipeline as subprocess
        process = await asyncio.create_subprocess_exec(
            *GST_CMD,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        print(f"[Audio] GStreamer pipeline started (pid {process.pid})")

        # Stream audio data from GStreamer stdout to WebSocket
        while True:
            chunk = await process.stdout.read(4096)
            if not chunk:
                print("[Audio] GStreamer pipeline ended")
                break
            try:
                await websocket.send(chunk)
            except ConnectionClosed:
                print("[Audio] Client disconnected")
                break

    except Exception as e:
        print(f"[Audio] Error: {e}")
    finally:
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
            print("[Audio] GStreamer pipeline stopped")


async def main():
    print(f"[Audio] Server starting on port {PORT}")

    # Graceful shutdown on SIGTERM/SIGINT
    stop = asyncio.Future()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set_result, None)

    async with serve(audio_handler, "0.0.0.0", PORT):
        print(f"[Audio] Listening on ws://0.0.0.0:{PORT}")
        await stop


if __name__ == "__main__":
    asyncio.run(main())
