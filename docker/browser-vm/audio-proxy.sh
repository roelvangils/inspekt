#!/bin/sh
# Audio proxy for noVNC - encodes PulseAudio output to WebM/Opus for browser playback
# Based on noVNC-audio-plugin by Mehrzad Asri (MPL 2.0)
#
# This script:
# 1. Monitors the PulseAudio null sink for audio output
# 2. Encodes it to WebM/Opus format using GStreamer
# 3. Outputs to stdout for websockify to stream via WebSocket
#
# Note: No handshake protocol — websockify bridges stdin/stdout as binary
# WebSocket frames, making text-based handshakes unreliable. Settings are
# hardcoded and the stream starts immediately on connection.

# Set PulseAudio socket (container-friendly fixed path)
export PULSE_SERVER="${PULSE_SERVER:-unix:/tmp/pulse-socket}"

readonly PULSE_SINK="audio_out.monitor"
readonly PULSE_SAMPLE_RATE="48000"
readonly PULSE_CHANNELS="2"
readonly BITRATE="96000"

# Start Opus encoding via GStreamer — output goes to stdout (fd=1)
# for websockify to relay as binary WebSocket frames.
exec gst-launch-1.0 -q \
    pulsesrc device="$PULSE_SINK" \
    ! audioconvert \
    ! audioresample \
    ! audio/x-raw,rate=$PULSE_SAMPLE_RATE,channels=$PULSE_CHANNELS \
    ! queue max-size-time=100000000 \
    ! opusenc audio-type=restricted-lowdelay bitrate="$BITRATE" bitrate-type=0 complexity=0 frame-size=10 \
    ! webmmux streamable=true min-cluster-duration=50000000 \
    ! fdsink fd=1
