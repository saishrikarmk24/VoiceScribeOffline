# Record Google Meet

This is an additive capture path. It does **not** change the transcription,
note, or evidence pipeline. A Meet is recorded in the browser, encoded as the
same 16 kHz mono WAV the microphone recorder already produces, and uploaded
with `POST /api/sessions/{id}/audio/upload`.

## Use it

1. Open Google Meet in **Chrome or Edge**.
2. In MedScribe, open **Record Meet** (`/sessions/gmeet`).
3. Create a session.
4. Click **Share Meet tab**.
5. In the browser picker, select the Meet tab — not the whole screen — and tick **Share tab audio**.
6. Speak as usual. Optionally keep “Mix this computer’s microphone” on so the local clinician is included.
7. Press **Stop & transcribe**. The existing ASR → transcript → Gemini note path runs as for any uploaded recording.

## Requirements

- Chrome or Edge (tab audio capture). Firefox cannot reliably share Meet tab audio.
- `https` or `localhost`.
- Real ASR configured (`ASR_PROVIDER=gemini` or `faster_whisper`). Mock ASR will refuse real audio, same as microphone/upload.

## What it cannot do

Google does not expose a Meet recording API to third-party apps. MedScribe
cannot join the meeting as a bot or pull Google’s own cloud recording. This
path captures whatever the browser is allowed to share from the Meet tab.
