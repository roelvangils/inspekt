"""
Audio synthesis and playback for Inspekt CLI.

Generates synthesized sounds that match the Web Audio API sounds in replay_visual.js,
but plays them through the system audio (bypassing browser autoplay restrictions).

Uses only Python standard library - no external dependencies.
"""

import io
import math
import platform
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Literal

# Sample rate for audio generation
SAMPLE_RATE = 44100


def generate_sine_wave(frequency: float, duration: float, volume: float = 0.5) -> list[float]:
    """Generate a sine wave."""
    num_samples = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        sample = volume * math.sin(2 * math.pi * frequency * t)
        samples.append(sample)
    return samples


def generate_triangle_wave(frequency: float, duration: float, volume: float = 0.5) -> list[float]:
    """Generate a triangle wave."""
    num_samples = int(SAMPLE_RATE * duration)
    samples = []
    period = SAMPLE_RATE / frequency
    for i in range(num_samples):
        # Triangle wave formula
        t = (i % period) / period
        if t < 0.5:
            sample = volume * (4 * t - 1)
        else:
            sample = volume * (3 - 4 * t)
        samples.append(sample)
    return samples


def generate_square_wave(frequency: float, duration: float, volume: float = 0.5) -> list[float]:
    """Generate a square wave."""
    num_samples = int(SAMPLE_RATE * duration)
    samples = []
    period = SAMPLE_RATE / frequency
    for i in range(num_samples):
        t = (i % period) / period
        sample = volume if t < 0.5 else -volume
        samples.append(sample)
    return samples


def apply_envelope(samples: list[float], attack: float = 0.01, decay: float = 0.02) -> list[float]:
    """Apply attack/decay envelope to samples."""
    attack_samples = int(SAMPLE_RATE * attack)
    decay_samples = int(SAMPLE_RATE * decay)

    result = samples.copy()

    # Attack (fade in)
    for i in range(min(attack_samples, len(result))):
        result[i] *= i / attack_samples

    # Decay (fade out)
    decay_start = len(result) - decay_samples
    for i in range(max(0, decay_start), len(result)):
        result[i] *= (len(result) - i) / decay_samples

    return result


def mix_samples(*sample_lists: list[float]) -> list[float]:
    """Mix multiple sample lists together, padding shorter ones with silence."""
    if not sample_lists:
        return []

    max_len = max(len(s) for s in sample_lists)
    mixed = [0.0] * max_len

    for samples in sample_lists:
        for i, sample in enumerate(samples):
            mixed[i] += sample

    # Normalize to prevent clipping
    max_val = max(abs(s) for s in mixed) if mixed else 1.0
    if max_val > 1.0:
        mixed = [s / max_val for s in mixed]

    return mixed


def delay_samples(samples: list[float], delay_seconds: float) -> list[float]:
    """Add silence at the beginning of samples."""
    delay_samples_count = int(SAMPLE_RATE * delay_seconds)
    return [0.0] * delay_samples_count + samples


def samples_to_wav_bytes(samples: list[float]) -> bytes:
    """Convert float samples to WAV file bytes."""
    # Convert to 16-bit PCM
    pcm_data = b''
    for sample in samples:
        # Clamp to [-1, 1] and convert to 16-bit integer
        clamped = max(-1.0, min(1.0, sample))
        int_sample = int(clamped * 32767)
        pcm_data += struct.pack('<h', int_sample)

    # Create WAV file in memory
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm_data)

    return buffer.getvalue()


def play_wav_bytes(wav_bytes: bytes) -> bool:
    """Play WAV audio bytes using system audio."""
    system = platform.system()

    # Write to temp file and play
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(wav_bytes)
            temp_path = f.name

        if system == 'Darwin':  # macOS
            subprocess.run(['afplay', temp_path], check=True, capture_output=True)
        elif system == 'Linux':
            # Try aplay first (ALSA), fall back to paplay (PulseAudio)
            try:
                subprocess.run(['aplay', '-q', temp_path], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                subprocess.run(['paplay', temp_path], check=True, capture_output=True)
        elif system == 'Windows':
            # Use PowerShell to play audio
            ps_script = f'(New-Object Media.SoundPlayer "{temp_path}").PlaySync()'
            subprocess.run(['powershell', '-Command', ps_script], check=True, capture_output=True)
        else:
            return False

        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    finally:
        # Clean up temp file
        try:
            Path(temp_path).unlink()
        except Exception:
            pass


class CLIAudio:
    """
    CLI audio synthesizer that matches the Web Audio sounds in replay_visual.js.

    All sounds are generated in real-time using Python and played through system audio.
    """

    def __init__(self, volume: float = 0.5):
        self.volume = volume

    def _tone(
        self,
        frequency: float,
        duration: float,
        wave_type: Literal['sine', 'triangle', 'square'] = 'sine',
        volume: float | None = None,
        delay: float = 0
    ) -> list[float]:
        """Generate a single tone with envelope."""
        vol = (volume if volume is not None else self.volume)

        if wave_type == 'sine':
            samples = generate_sine_wave(frequency, duration, vol)
        elif wave_type == 'triangle':
            samples = generate_triangle_wave(frequency, duration, vol)
        else:
            samples = generate_square_wave(frequency, duration, vol)

        samples = apply_envelope(samples)

        if delay > 0:
            samples = delay_samples(samples, delay)

        return samples

    def _play(self, samples: list[float]) -> bool:
        """Convert samples to WAV and play."""
        wav_bytes = samples_to_wav_bytes(samples)
        return play_wav_bytes(wav_bytes)

    # ==========================================================================
    # Session Sounds (Tritones - 3 notes)
    # ==========================================================================

    def play_start_recording(self) -> bool:
        """Start recording - 3 ascending notes (major chord feel)."""
        # Choice 2: Ascending with acceleration
        t1 = self._tone(300, 0.12, 'triangle', self.volume * 0.4)
        t2 = self._tone(450, 0.1, 'triangle', self.volume * 0.44, delay=0.1)
        t3 = self._tone(600, 0.15, 'sine', self.volume * 0.5, delay=0.18)
        return self._play(mix_samples(t1, t2, t3))

    def play_stop_recording(self) -> bool:
        """Stop recording - 3 descending notes."""
        # Choice 4: Quick descending
        t1 = self._tone(550, 0.1, 'triangle', self.volume * 0.45)
        t2 = self._tone(400, 0.1, 'triangle', self.volume * 0.4, delay=0.08)
        t3 = self._tone(300, 0.15, 'sine', self.volume * 0.35, delay=0.16)
        return self._play(mix_samples(t1, t2, t3))

    def play_start_playback(self) -> bool:
        """Start playback - 3 ascending notes (different from recording)."""
        # Choice 2: Bright ascending
        t1 = self._tone(350, 0.1, 'sine', self.volume * 0.35)
        t2 = self._tone(525, 0.1, 'sine', self.volume * 0.4, delay=0.1)
        t3 = self._tone(700, 0.15, 'triangle', self.volume * 0.45, delay=0.18)
        return self._play(mix_samples(t1, t2, t3))

    def play_stop_playback(self) -> bool:
        """Stop playback - 3 descending notes."""
        # Choice 5: Gentle fade
        t1 = self._tone(600, 0.12, 'sine', self.volume * 0.4)
        t2 = self._tone(450, 0.12, 'sine', self.volume * 0.35, delay=0.12)
        t3 = self._tone(350, 0.18, 'sine', self.volume * 0.3, delay=0.24)
        return self._play(mix_samples(t1, t2, t3))

    # ==========================================================================
    # Action Sounds (Singletones / Duotones)
    # ==========================================================================

    def play_navigate(self) -> bool:
        """Page navigation - ascending sweep."""
        # Choice 2: Quick chirp
        samples = []
        duration = 0.08
        num_samples = int(SAMPLE_RATE * duration)
        for i in range(num_samples):
            t = i / SAMPLE_RATE
            progress = i / num_samples
            freq = 400 + 400 * progress  # 400Hz to 800Hz
            vol = self.volume * 0.35 * (1 - progress * 0.5)
            sample = vol * math.sin(2 * math.pi * freq * t)
            samples.append(sample)
        samples = apply_envelope(samples, attack=0.005, decay=0.02)
        return self._play(samples)

    def play_click(self) -> bool:
        """Mouse click - short tick sound."""
        # Choice 3: Tick
        t1 = self._tone(1200, 0.015, 'square', self.volume * 0.2)
        t2 = self._tone(300, 0.03, 'sine', self.volume * 0.25, delay=0.01)
        return self._play(mix_samples(t1, t2))

    def play_rightclick(self) -> bool:
        """Right click - lower tick."""
        # Choice 5: Low thump
        t1 = self._tone(150, 0.04, 'sine', self.volume * 0.35)
        t2 = self._tone(100, 0.05, 'sine', self.volume * 0.25, delay=0.02)
        return self._play(mix_samples(t1, t2))

    def play_activate(self) -> bool:
        """Enter/Space activation - confirmation ding."""
        # Choice 2: Soft ding
        samples = self._tone(700, 0.12, 'sine', self.volume * 0.35)
        return self._play(samples)

    def play_type(self) -> bool:
        """Typing text - keyboard clack."""
        # Choice 4: Mechanical
        t1 = self._tone(1400, 0.01, 'square', self.volume * 0.15)
        t2 = self._tone(200, 0.04, 'sine', self.volume * 0.2, delay=0.008)
        return self._play(mix_samples(t1, t2))

    def play_keypress(self) -> bool:
        """Keyboard shortcut - key sound."""
        # Choice 5: Soft tap
        samples = self._tone(250, 0.05, 'sine', self.volume * 0.25)
        return self._play(samples)

    def play_hover(self) -> bool:
        """Mouse hover - gentle whoosh."""
        # Choice 1: Gentle breeze
        samples = []
        duration = 0.1
        num_samples = int(SAMPLE_RATE * duration)
        for i in range(num_samples):
            t = i / SAMPLE_RATE
            progress = i / num_samples
            freq = 800 - 400 * progress  # 800Hz to 400Hz
            vol = self.volume * 0.15 * math.sin(math.pi * progress)
            sample = vol * math.sin(2 * math.pi * freq * t)
            samples.append(sample)
        return self._play(samples)

    def play_check(self) -> bool:
        """Checkbox checked - ascending duo."""
        # Choice 1: Quick up
        t1 = self._tone(500, 0.06, 'sine', self.volume * 0.3)
        t2 = self._tone(700, 0.08, 'sine', self.volume * 0.35, delay=0.05)
        return self._play(mix_samples(t1, t2))

    def play_uncheck(self) -> bool:
        """Checkbox unchecked - descending duo."""
        # Choice 1: Quick down
        t1 = self._tone(700, 0.06, 'sine', self.volume * 0.3)
        t2 = self._tone(500, 0.08, 'sine', self.volume * 0.35, delay=0.05)
        return self._play(mix_samples(t1, t2))

    def play_radio(self) -> bool:
        """Radio button - selection ping."""
        # Choice 3: Pop
        samples = self._tone(800, 0.08, 'triangle', self.volume * 0.35)
        return self._play(samples)

    def play_select(self) -> bool:
        """Dropdown selection - selection blip."""
        # Choice 5: Subtle duo
        t1 = self._tone(450, 0.05, 'sine', self.volume * 0.25)
        t2 = self._tone(550, 0.06, 'sine', self.volume * 0.3, delay=0.04)
        return self._play(mix_samples(t1, t2))

    def play_scroll(self) -> bool:
        """Page scroll - soft descending sweep."""
        # Choice 1: Soft slide
        samples = []
        duration = 0.08
        num_samples = int(SAMPLE_RATE * duration)
        for i in range(num_samples):
            t = i / SAMPLE_RATE
            progress = i / num_samples
            freq = 500 - 150 * progress  # 500Hz to 350Hz
            vol = self.volume * 0.15 * (1 - progress * 0.3)
            sample = vol * math.sin(2 * math.pi * freq * t)
            samples.append(sample)
        samples = apply_envelope(samples, attack=0.01, decay=0.02)
        return self._play(samples)

    def play_plugin(self) -> bool:
        """Running plugin - bloop-bloop (identical double tone)."""
        # Choice 1: Bloop-bloop
        t1 = self._tone(500, 0.1, 'sine', self.volume * 0.4)
        t2 = self._tone(500, 0.1, 'sine', self.volume * 0.4, delay=0.15)
        return self._play(mix_samples(t1, t2))

    def play_inspekt(self) -> bool:
        """Running inspekt command - bleep-bleep (identical double tone, higher)."""
        # Choice 3: Analysis beep-beep
        t1 = self._tone(650, 0.1, 'triangle', self.volume * 0.35)
        t2 = self._tone(650, 0.1, 'triangle', self.volume * 0.35, delay=0.14)
        return self._play(mix_samples(t1, t2))

    def play_failure(self) -> bool:
        """Action failed - dissonant error buzz."""
        # Choice 1: Harsh buzz
        t1 = self._tone(150, 0.15, 'square', self.volume * 0.25)
        t2 = self._tone(155, 0.15, 'square', self.volume * 0.25)  # Slightly detuned for dissonance
        t3 = self._tone(200, 0.1, 'triangle', self.volume * 0.2, delay=0.08)
        return self._play(mix_samples(t1, t2, t3))

    def play_success(self) -> bool:
        """Success chime - pleasant ascending arpeggio."""
        t1 = self._tone(523, 0.1, 'sine', self.volume * 0.3)  # C5
        t2 = self._tone(659, 0.1, 'sine', self.volume * 0.35, delay=0.1)  # E5
        t3 = self._tone(784, 0.15, 'sine', self.volume * 0.4, delay=0.2)  # G5
        return self._play(mix_samples(t1, t2, t3))

    # ==========================================================================
    # Action dispatcher
    # ==========================================================================

    def play_for_action(self, action: str) -> bool:
        """Play sound for a given action type."""
        action_map = {
            'start_recording': self.play_start_recording,
            'stop_recording': self.play_stop_recording,
            'start_playback': self.play_start_playback,
            'stop_playback': self.play_stop_playback,
            'navigate': self.play_navigate,
            'click': self.play_click,
            'rightclick': self.play_rightclick,
            'activate': self.play_activate,
            'type': self.play_type,
            'keypress': self.play_keypress,
            'hover': self.play_hover,
            'check': self.play_check,
            'uncheck': self.play_uncheck,
            'radio': self.play_radio,
            'select': self.play_select,
            'scroll': self.play_scroll,
            'plugin': self.play_plugin,
            'inspekt': self.play_inspekt,
            'failure': self.play_failure,
            'success': self.play_success,
        }

        player = action_map.get(action)
        if player:
            return player()
        return False


# Global instance for convenience
_cli_audio: CLIAudio | None = None


def get_cli_audio(volume: float = 0.5) -> CLIAudio:
    """Get or create the global CLI audio instance."""
    global _cli_audio
    if _cli_audio is None or _cli_audio.volume != volume:
        _cli_audio = CLIAudio(volume=volume)
    return _cli_audio
