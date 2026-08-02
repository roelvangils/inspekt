"""
Text-to-Speech service using ElevenLabs streaming API.

This module provides streaming TTS with progressive audio playback,
allowing audio to start playing as soon as the first chunks arrive.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from typing import Any

import requests

from inspekt.config import get_tts_voice
from inspekt.services import http_client


class TTSError(Exception):
    """Exception raised for TTS-related errors."""
    pass


def _find_audio_player() -> tuple[str, list[str]] | None:
    """
    Find an available audio player for streaming playback.

    Returns:
        Tuple of (player_path, args) or None if no player found.
        The args list contains command-line arguments for the player.
    """
    # Try ffplay first (from ffmpeg) - best for streaming
    ffplay = shutil.which("ffplay")
    if ffplay:
        # -nodisp: no video window, -autoexit: exit when done, -loglevel quiet: no output
        return (ffplay, ["-nodisp", "-autoexit", "-loglevel", "quiet", "-"])

    # Try mpv (also good for streaming)
    mpv = shutil.which("mpv")
    if mpv:
        return (mpv, ["--no-video", "--really-quiet", "-"])

    # Try afplay on macOS (doesn't support stdin streaming well, but works)
    # Note: afplay doesn't support streaming from stdin, so we'll skip it
    # afplay = shutil.which("afplay")
    # if afplay:
    #     return (afplay, [])

    return None


def speak_text(
    text: str,
    voice_name: str | None = None,
    on_start: callable = None,
    on_error: callable = None,
    detached: bool = False,
) -> bool:
    """
    Convert text to speech using ElevenLabs streaming API and play it immediately.

    Uses progressive streaming: audio starts playing as soon as the first
    chunks arrive from the API, providing minimal latency.

    Args:
        text: The text to convert to speech.
        voice_name: Name of the voice to use (from config). If None, uses default.
        on_start: Optional callback called when audio starts playing.
        on_error: Optional callback called on error with error message.
        detached: If True, audio playback survives parent process termination.
                  Use this when called from URL schemes with timeouts.

    Returns:
        True if successful, False otherwise.

    Raises:
        TTSError: If configuration is missing or API call fails.
    """
    # Get voice configuration
    voice_config = get_tts_voice(voice_name)
    if not voice_config:
        error_msg = f"Voice '{voice_name or 'default'}' not found in configuration"
        if on_error:
            on_error(error_msg)
        raise TTSError(error_msg)

    api_key = voice_config.get("api-key")
    if not api_key:
        error_msg = "ElevenLabs API key not set. Set ELEVENLABS_API_KEY environment variable."
        if on_error:
            on_error(error_msg)
        raise TTSError(error_msg)

    # Find audio player
    player_info = _find_audio_player()
    if not player_info:
        error_msg = "No audio player found. Install ffmpeg (ffplay) or mpv."
        if on_error:
            on_error(error_msg)
        raise TTSError(error_msg)

    player_path, player_args = player_info

    # Build ElevenLabs streaming endpoint URL
    voice_id = voice_config["voice-id"]
    output_format = voice_config.get("output-format", "mp3_44100_192")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream?output_format={output_format}"

    # Build request payload
    voice_settings = voice_config.get("voice-settings", {})
    payload = {
        "text": text,
        "model_id": voice_config.get("model-id", "eleven_v3"),
        "voice_settings": {
            "stability": voice_settings.get("stability", 0.5),
            "similarity_boost": voice_settings.get("similarity-boost", 0.75),
            "style": voice_settings.get("style", 0),
            "use_speaker_boost": voice_settings.get("use-speaker-boost", False),
        },
    }

    # Add language code if specified
    language_code = voice_config.get("language-code")
    if language_code:
        payload["language_code"] = language_code

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }

    try:
        # Make streaming request to ElevenLabs
        response = http_client.post(
            url,
            json=payload,
            headers=headers,
            stream=True,
            timeout=120,  # Allow time for long text to generate
        )

        if response.status_code != 200:
            error_detail = response.text[:200] if response.text else "Unknown error"
            error_msg = f"ElevenLabs API error ({response.status_code}): {error_detail}"
            if on_error:
                on_error(error_msg)
            raise TTSError(error_msg)

        if detached:
            # DETACHED MODE: Buffer all audio first, then play via temp file
            # This ensures audio completes even if parent process is killed
            import tempfile

            # Collect all audio chunks
            audio_chunks = []
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    if not audio_chunks and on_start:
                        on_start()  # First chunk received
                    audio_chunks.append(chunk)

            if not audio_chunks:
                error_msg = "No audio data received from ElevenLabs"
                if on_error:
                    on_error(error_msg)
                raise TTSError(error_msg)

            # Write to temp file (won't be auto-deleted, ffplay needs it)
            temp_file = tempfile.NamedTemporaryFile(
                suffix=".mp3",
                delete=False,
                prefix="inspekt_tts_"
            )
            for chunk in audio_chunks:
                temp_file.write(chunk)
            temp_file.close()

            # Play via detached process (survives parent termination)
            # Use shell to handle cleanup: play file, then delete it
            cleanup_cmd = f'"{player_path}" -nodisp -autoexit -loglevel quiet "{temp_file.name}" && rm -f "{temp_file.name}"'
            subprocess.Popen(
                cleanup_cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Survives parent termination
            )

            # Return immediately - audio plays in background
            return True

        else:
            # STREAMING MODE: Pipe directly to player for minimal latency
            player_cmd = [player_path] + player_args
            player_process = subprocess.Popen(
                player_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Call on_start callback when we get the first chunk
            started = False

            # Stream audio chunks to the player
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    if not started:
                        started = True
                        if on_start:
                            on_start()

                    try:
                        player_process.stdin.write(chunk)
                        player_process.stdin.flush()
                    except BrokenPipeError:
                        # Player was closed (user interrupted)
                        break

            # Close stdin to signal end of stream
            try:
                player_process.stdin.close()
            except Exception:
                pass

            # Wait for player to finish
            player_process.wait()

            return True

    except requests.exceptions.Timeout:
        error_msg = "ElevenLabs API request timed out"
        if on_error:
            on_error(error_msg)
        raise TTSError(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Network error: {e}"
        if on_error:
            on_error(error_msg)
        raise TTSError(error_msg)


def generate_audio(
    text: str,
    voice_name: str | None = None,
    on_progress: callable = None,
) -> bytes:
    """
    Generate audio bytes from text using ElevenLabs API.

    Unlike speak_text(), this returns the raw audio bytes instead of
    playing them. Useful for saving to file or processing multiple chunks.

    Args:
        text: The text to convert to speech.
        voice_name: Name of the voice to use (from config). If None, uses default.
        on_progress: Optional callback called with bytes received so far.

    Returns:
        Raw MP3 audio bytes.

    Raises:
        TTSError: If configuration is missing or API call fails.
    """
    # Get voice configuration
    voice_config = get_tts_voice(voice_name)
    if not voice_config:
        raise TTSError(f"Voice '{voice_name or 'default'}' not found in configuration")

    api_key = voice_config.get("api-key")
    if not api_key:
        raise TTSError("ElevenLabs API key not set. Set ELEVENLABS_API_KEY environment variable.")

    # Build ElevenLabs streaming endpoint URL
    voice_id = voice_config["voice-id"]
    output_format = voice_config.get("output-format", "mp3_44100_192")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream?output_format={output_format}"

    # Build request payload
    voice_settings = voice_config.get("voice-settings", {})
    payload = {
        "text": text,
        "model_id": voice_config.get("model-id", "eleven_v3"),
        "voice_settings": {
            "stability": voice_settings.get("stability", 0.5),
            "similarity_boost": voice_settings.get("similarity-boost", 0.75),
            "style": voice_settings.get("style", 0),
            "use_speaker_boost": voice_settings.get("use-speaker-boost", False),
        },
    }

    # Add language code if specified
    language_code = voice_config.get("language-code")
    if language_code:
        payload["language_code"] = language_code

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }

    try:
        response = http_client.post(
            url,
            json=payload,
            headers=headers,
            stream=True,
            timeout=120,
        )

        if response.status_code != 200:
            error_detail = response.text[:200] if response.text else "Unknown error"
            raise TTSError(f"ElevenLabs API error ({response.status_code}): {error_detail}")

        # Collect all audio chunks
        audio_chunks = []
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=4096):
            if chunk:
                audio_chunks.append(chunk)
                total_bytes += len(chunk)
                if on_progress:
                    on_progress(total_bytes)

        if not audio_chunks:
            raise TTSError("No audio data received from ElevenLabs")

        return b''.join(audio_chunks)

    except requests.exceptions.Timeout:
        raise TTSError("ElevenLabs API request timed out")
    except requests.exceptions.RequestException as e:
        raise TTSError(f"Network error: {e}")


def play_audio_bytes(audio_bytes: bytes) -> bool:
    """
    Play raw audio bytes through the system audio player.

    Args:
        audio_bytes: Raw audio data (MP3 format).

    Returns:
        True if playback completed successfully.

    Raises:
        TTSError: If no audio player is available.
    """
    player_info = _find_audio_player()
    if not player_info:
        raise TTSError("No audio player found. Install ffmpeg (ffplay) or mpv.")

    player_path, player_args = player_info
    player_cmd = [player_path] + player_args

    try:
        player_process = subprocess.Popen(
            player_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Write all audio data to player
        player_process.stdin.write(audio_bytes)
        player_process.stdin.close()

        # Wait for playback to complete
        player_process.wait()
        return True

    except Exception as e:
        raise TTSError(f"Audio playback failed: {e}")


def speak_text_async(
    text: str,
    voice_name: str | None = None,
    on_start: callable = None,
    on_complete: callable = None,
    on_error: callable = None,
) -> threading.Thread:
    """
    Convert text to speech asynchronously in a background thread.

    Args:
        text: The text to convert to speech.
        voice_name: Name of the voice to use (from config). If None, uses default.
        on_start: Optional callback called when audio starts playing.
        on_complete: Optional callback called when playback completes.
        on_error: Optional callback called on error with error message.

    Returns:
        The background thread running the TTS.
    """
    def run_tts():
        try:
            speak_text(text, voice_name, on_start=on_start, on_error=on_error)
            if on_complete:
                on_complete()
        except TTSError:
            pass  # Error already handled via on_error callback

    thread = threading.Thread(target=run_tts, daemon=True)
    thread.start()
    return thread


def list_available_voices() -> dict[str, dict[str, Any]]:
    """
    Get all configured voices from the TTS configuration.

    Returns:
        Dictionary of voice names to their configurations.
    """
    from inspekt.config import get_tts_config
    tts_config = get_tts_config()
    return tts_config.get("voices", {})


def is_tts_available() -> tuple[bool, str | None]:
    """
    Check if TTS is available (API key set and audio player found).

    Returns:
        Tuple of (is_available, error_message).
        If available, error_message is None.
    """
    from inspekt.config import get_tts_config

    # Check API key
    tts_config = get_tts_config()
    if not tts_config.get("api-key"):
        return (False, "ELEVENLABS_API_KEY environment variable not set")

    # Check for audio player
    if not _find_audio_player():
        return (False, "No audio player found. Install ffmpeg (ffplay) or mpv.")

    # Check for at least one configured voice
    if not tts_config.get("voices"):
        return (False, "No TTS voices configured")

    return (True, None)
