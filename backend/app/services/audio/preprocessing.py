"""Audio preprocessing: decode -> mono -> resample -> VAD -> denoise -> segment.

Implemented with the standard library only (``audioop`` was removed in Python
3.13, and pulling numpy/librosa in would make Demo Mode heavy). Demo buffers are
small enough that pure Python is fast enough; the class is a
drop-in place to swap a vectorised implementation later.
"""

from __future__ import annotations

import array
import io
import math
import struct
import wave

from app.core.config import settings
from app.core.logging import get_logger, track_duration
from app.models.enums import AudioSource
from app.services.audio.base import RawAudio
from app.services.types import AudioFrame

logger = get_logger(__name__)

_COMPRESSED_MIME_HINTS = ("webm", "ogg", "opus", "mp4", "m4a", "mpeg", "mp3", "aac")


class EchoCanceller:
    """Interface placeholder for acoustic echo cancellation.

    Browser capture gives us no far-end reference signal, so this stage is a
    documented pass-through rather than a fake filter. A real AEC implementation
    (WebRTC APM / speexdsp) plugs in here without touching the pipeline.
    """

    enabled = False

    def process(self, samples: array.array, reference: array.array | None = None) -> array.array:
        if not self.enabled or reference is None:
            return samples
        return samples  # pragma: no cover - reserved for a real AEC backend


class AudioPreprocessingService:
    """Turns arbitrary capture buffers into canonical 16 kHz mono PCM16 frames."""

    def __init__(
        self,
        target_sample_rate: int | None = None,
        frame_ms: int = 30,
        vad_threshold_dbfs: float = -45.0,
    ) -> None:
        self.target_sample_rate = target_sample_rate or settings.audio_sample_rate
        self.frame_ms = frame_ms
        self.vad_threshold_dbfs = vad_threshold_dbfs
        self.echo_canceller = EchoCanceller()

    # ------------------------------------------------------------------ decode
    def _decode(self, raw: RawAudio) -> tuple[array.array, int, int, bool]:
        mime = (raw.mime_type or "").lower()
        if raw.data[:4] == b"RIFF":
            samples, rate, channels = self._decode_wav(raw.data)
            return samples, rate, channels, True
        if any(hint in mime for hint in _COMPRESSED_MIME_HINTS):
            # Compressed containers need ffmpeg; we accept and forward the bytes
            # untouched instead of pretending we analysed them.
            return array.array("h"), raw.sample_rate or self.target_sample_rate, raw.channels or 1, False
        samples = array.array("h")
        usable = len(raw.data) - (len(raw.data) % 2)
        samples.frombytes(raw.data[:usable])
        return samples, raw.sample_rate or self.target_sample_rate, raw.channels or 1, True

    @staticmethod
    def _decode_wav(data: bytes) -> tuple[array.array, int, int]:
        with wave.open(io.BytesIO(data), "rb") as handle:
            channels = handle.getnchannels()
            rate = handle.getframerate()
            width = handle.getsampwidth()
            frames = handle.readframes(handle.getnframes())
        samples = array.array("h")
        if width == 2:
            samples.frombytes(frames[: len(frames) - (len(frames) % 2)])
        elif width == 1:
            samples.extend(((byte - 128) << 8) for byte in frames)
        elif width == 4:
            for offset in range(0, len(frames) - 3, 4):
                value = struct.unpack_from("<i", frames, offset)[0]
                samples.append(max(-32768, min(32767, value >> 16)))
        else:  # pragma: no cover - unusual bit depth
            raise ValueError(f"Unsupported WAV sample width: {width}")
        return samples, rate, channels

    # ------------------------------------------------------- channel / resample
    @staticmethod
    def to_mono(samples: array.array, channels: int) -> array.array:
        if channels <= 1:
            return samples
        mono = array.array("h", bytes(2 * (len(samples) // channels)))
        for index in range(len(mono)):
            base = index * channels
            total = sum(samples[base : base + channels])
            mono[index] = int(total / channels)
        return mono

    def resample(self, samples: array.array, source_rate: int) -> array.array:
        if source_rate == self.target_sample_rate or not samples:
            return samples
        ratio = self.target_sample_rate / source_rate
        target_length = max(1, int(len(samples) * ratio))
        resampled = array.array("h", bytes(2 * target_length))
        for index in range(target_length):
            position = index / ratio
            left = int(position)
            right = min(left + 1, len(samples) - 1)
            weight = position - left
            resampled[index] = int(samples[left] * (1 - weight) + samples[right] * weight)
        return resampled

    # ------------------------------------------------------------- enhancement
    @staticmethod
    def high_pass(samples: array.array, cutoff_hz: float, sample_rate: int) -> array.array:
        """Single-pole high-pass filter: removes rumble and DC offset."""
        if not samples:
            return samples
        rc = 1.0 / (2 * math.pi * cutoff_hz)
        dt = 1.0 / sample_rate
        alpha = rc / (rc + dt)
        filtered = array.array("h", bytes(2 * len(samples)))
        previous_in = samples[0]
        previous_out = 0.0
        for index, value in enumerate(samples):
            previous_out = alpha * (previous_out + value - previous_in)
            previous_in = value
            filtered[index] = int(max(-32768, min(32767, previous_out)))
        return filtered

    def suppress_noise(self, samples: array.array, noise_floor: float) -> array.array:
        """Spectral-subtraction-style gate applied in the time domain.

        Frames whose energy sits at or below the estimated noise floor are
        attenuated instead of removed, so timestamps stay aligned.
        """
        if not samples:
            return samples
        frame_size = max(1, int(self.target_sample_rate * self.frame_ms / 1000))
        gated = array.array("h", samples)
        for start in range(0, len(samples), frame_size):
            window = samples[start : start + frame_size]
            level = self._dbfs(window)
            if level <= noise_floor + 3.0:
                for offset in range(len(window)):
                    gated[start + offset] = int(window[offset] * 0.25)
        return gated

    # ---------------------------------------------------------------- analysis
    @staticmethod
    def _dbfs(samples: array.array | list[int]) -> float:
        if not samples:
            return -90.0
        total = 0.0
        for value in samples:
            total += float(value) * float(value)
        rms = math.sqrt(total / len(samples))
        if rms <= 1e-9:
            return -90.0
        return max(-90.0, 20 * math.log10(rms / 32768.0))

    def detect_voice_activity(self, samples: array.array) -> tuple[list[tuple[float, float]], float, float]:
        """Energy-based VAD with hysteresis.

        Returns speech regions (seconds, relative to the frame), the speech
        ratio and the estimated noise floor in dBFS.
        """
        frame_size = max(1, int(self.target_sample_rate * self.frame_ms / 1000))
        if not samples:
            return [], 0.0, -90.0

        levels: list[float] = []
        for start in range(0, len(samples), frame_size):
            levels.append(self._dbfs(samples[start : start + frame_size]))

        ordered = sorted(levels)
        noise_floor = ordered[max(0, int(len(ordered) * 0.15))]
        threshold = max(noise_floor + 8.0, self.vad_threshold_dbfs)

        regions: list[tuple[float, float]] = []
        speech_frames = 0
        active_start: int | None = None
        silence_run = 0
        hangover_frames = max(1, int(200 / self.frame_ms))

        for index, level in enumerate(levels):
            if level >= threshold:
                speech_frames += 1
                silence_run = 0
                if active_start is None:
                    active_start = index
            elif active_start is not None:
                silence_run += 1
                if silence_run >= hangover_frames:
                    regions.append(
                        (active_start * self.frame_ms / 1000, (index - silence_run + 1) * self.frame_ms / 1000)
                    )
                    active_start = None
        if active_start is not None:
            regions.append((active_start * self.frame_ms / 1000, len(levels) * self.frame_ms / 1000))

        ratio = speech_frames / len(levels) if levels else 0.0
        return regions, ratio, noise_floor

    # ------------------------------------------------------------------ public
    def process(
        self,
        raw: RawAudio,
        *,
        session_id: str,
        sequence: int,
        start_time: float,
        source: AudioSource = AudioSource.SIMULATION,
    ) -> AudioFrame:
        with track_duration("audio_preprocessing", logger, session_id=session_id):
            samples, rate, channels, decoded = self._decode(raw)

            if not decoded:
                duration = raw.duration_seconds or 0.0
                return AudioFrame(
                    session_id=session_id,
                    sequence=sequence,
                    pcm=raw.data,
                    sample_rate=raw.sample_rate or self.target_sample_rate,
                    channels=raw.channels or 1,
                    start_time=start_time,
                    end_time=start_time + duration,
                    source=source,
                    speech_ratio=1.0,
                    rms_dbfs=-30.0,
                    decoded=False,
                    hints={
                        "reason": "compressed container forwarded without local decoding",
                        # Kept so a transcription provider that accepts the
                        # container natively knows what it is holding.
                        "container_mime_type": raw.mime_type,
                    },
                )

            mono = self.to_mono(samples, channels)
            resampled = self.resample(mono, rate)
            filtered = self.high_pass(resampled, cutoff_hz=80.0, sample_rate=self.target_sample_rate)
            regions, ratio, noise_floor = self.detect_voice_activity(filtered)
            cleaned = self.suppress_noise(filtered, noise_floor)
            cleaned = self.echo_canceller.process(cleaned)
            duration = len(cleaned) / self.target_sample_rate if cleaned else (raw.duration_seconds or 0.0)

            return AudioFrame(
                session_id=session_id,
                sequence=sequence,
                pcm=cleaned.tobytes(),
                sample_rate=self.target_sample_rate,
                channels=1,
                start_time=start_time,
                end_time=start_time + duration,
                source=source,
                speech_ratio=round(ratio, 4),
                rms_dbfs=round(self._dbfs(cleaned), 2),
                decoded=True,
                speech_regions=[(round(s, 3), round(e, 3)) for s, e in regions],
            )

    def to_wav_bytes(self, frame: AudioFrame) -> bytes:
        """Canonical on-disk representation (16 kHz mono PCM WAV)."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(frame.sample_rate)
            handle.writeframes(frame.pcm)
        return buffer.getvalue()
