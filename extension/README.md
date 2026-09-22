# MedScribe Meet Capture Chrome extension

This is a standalone Manifest V3 Chrome extension. It does not modify the MedScribe application. It captures audio from the active Google Meet tab, encodes it as 16 kHz mono WAV in the browser, and uploads it through MedScribe's existing upload pipeline.

## Load it in Chrome

1. Start the MedScribe backend and frontend locally.
2. Open `chrome://extensions`, enable **Developer mode**, then select **Load unpacked**.
3. Choose this `extension` folder.
4. Make the Google Meet tab active, then click the MedScribe extension icon once. This immediately authorizes the Meet tab and opens the side panel. Do not open the panel from `chrome://extensions`, because Chrome pages cannot be captured.
5. Create the session, start recording, then stop to transcribe. Use **Open review in MedScribe** to view the evidence-linked note.

The defaults are `http://127.0.0.1:8000/api` and `http://127.0.0.1:5173`. Change them in the extension's **Settings** page if your local ports differ.

## Notes

- Start a capture only while a Google Meet tab is active. The side panel remains available so it can explain this requirement.
- Keep the side panel open while recording. By default it mixes the local microphone with Meet tab audio; microphone permission can be declined if only remote audio is needed.
- It uses the backend's configured development identity when no identity headers are supplied.
