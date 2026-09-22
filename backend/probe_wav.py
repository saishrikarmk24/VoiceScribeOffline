import pathlib
import wave

from app.models.enums import AudioSource
from app.services.audio import AudioPreprocessingService, RawAudio

path = pathlib.Path(__file__).resolve().parents[1] / "verification_speech.wav"
data = path.read_bytes()
print("size", len(data))
print("first 64 bytes:", data[:64])

with wave.open(str(path), "rb") as handle:
    print(
        "channels", handle.getnchannels(),
        "rate", handle.getframerate(),
        "width", handle.getsampwidth(),
        "frames", handle.getnframes(),
        "duration", round(handle.getnframes() / handle.getframerate(), 2),
    )

service = AudioPreprocessingService()
frame = service.process(
    RawAudio(data=data, mime_type="audio/wav"),
    session_id="probe",
    sequence=1,
    start_time=0.0,
    source=AudioSource.UPLOAD,
)
print("decoded", frame.decoded, "speech_ratio", frame.speech_ratio, "rms_dbfs", frame.rms_dbfs)
print("duration", round(frame.duration, 2), "regions", len(frame.speech_regions))
