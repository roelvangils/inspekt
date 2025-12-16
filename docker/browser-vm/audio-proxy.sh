#!/bin/sh
# Audio proxy for noVNC - encodes PulseAudio output to WebM/Opus for browser playback
# Based on noVNC-audio-plugin by Mehrzad Asri (MPL 2.0)
#
# This script:
# 1. Monitors the PulseAudio null sink for audio output
# 2. Encodes it to WebM/Opus format using GStreamer
# 3. Outputs to stdout for websockify to stream via WebSocket

# Set PulseAudio socket (container-friendly fixed path)
export PULSE_SERVER="${PULSE_SERVER:-unix:/tmp/pulse-socket}"

readonly PULSE_SINK="audio_out.monitor"
readonly PULSE_FORMAT="s16le"
readonly PULSE_SAMPLE_RATE="48000"
readonly PULSE_CHANNELS="2"

# Default audio settings
CODEC="opus"
BITRATE="96000"

# Read handshake from client (optional codec/bitrate config)
read_handshake() {
    while IFS= read -r line; do
        # Empty line signals end of handshake
        [ -z "$line" ] && break

        case "$line" in
            CD:*) CODEC="${line#CD:}" ;;
            BR:*) BITRATE="${line#BR:}" ;;
        esac
    done
}

# Send ready signal to client
proto_ready() {
    echo "READY"
}

# Start Opus encoding via GStreamer
start_opus_stream() {
    exec gst-launch-1.0 -q \
        pulsesrc device="$PULSE_SINK" \
        ! audioconvert \
        ! audioresample \
        ! audio/x-raw,rate=$PULSE_SAMPLE_RATE,channels=$PULSE_CHANNELS \
        ! opusenc audio-type=restricted-lowdelay bitrate="$BITRATE" bitrate-type=0 complexity=0 frame-size=10 \
        ! webmmux streamable=true min-cluster-duration=50000000 \
        ! fdsink fd=1
}

# Main
read_handshake
proto_ready
start_opus_stream
