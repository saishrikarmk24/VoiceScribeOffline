"""Build a spoken clinical encounter for verifying the real recording pipeline.

Uses Windows SAPI (two voices) to synthesise a short doctor/patient exchange and
joins the turns into one 16-bit mono WAV - the same format the browser recorder
uploads. The wording does not appear in any bundled demo conversation, so a
transcript containing it can only have come from this audio.

    python scripts/make_test_speech.py [output.wav]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNTH_SCRIPT = REPO_ROOT / "scripts" / "make_test_speech.ps1"
SILENCE_SECONDS = 0.35


def synthesise_turns(output_dir: Path) -> list[Path]:
    if sys.platform != "win32":
        raise SystemExit("Speech synthesis here relies on Windows SAPI; supply a WAV recording instead.")
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SYNTH_SCRIPT),
            str(output_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Speech synthesis failed:\n{result.stderr}")
    return sorted(output_dir.glob("turn_*.wav"))


def join(turns: list[Path], destination: Path) -> None:
    """Concatenate mono PCM WAVs, inserting a short pause between turns."""
    if not turns:
        raise SystemExit("No synthesised turns to join.")

    with wave.open(str(turns[0]), "rb") as first:
        params = first.getparams()
    if params.sampwidth != 2 or params.nchannels != 1:
        raise SystemExit(f"Expected 16-bit mono turns, got {params}")

    gap = b"\x00\x00" * int(params.framerate * SILENCE_SECONDS)

    with wave.open(str(destination), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(params.framerate)
        for index, turn in enumerate(turns):
            with wave.open(str(turn), "rb") as handle:
                if handle.getframerate() != params.framerate:
                    raise SystemExit(f"{turn.name} has a different sample rate")
                out.writeframes(handle.readframes(handle.getnframes()))
            if index < len(turns) - 1:
                out.writeframes(gap)


def main() -> int:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "verification_speech.wav"
    with tempfile.TemporaryDirectory() as raw_dir:
        turns = synthesise_turns(Path(raw_dir))
        join(turns, destination)

    with wave.open(str(destination), "rb") as handle:
        seconds = handle.getnframes() / handle.getframerate()
        print(
            f"Wrote {destination} :: {destination.stat().st_size} bytes, "
            f"{seconds:.1f}s, {handle.getframerate()} Hz mono 16-bit"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
