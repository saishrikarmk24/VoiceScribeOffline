import json
import time
import httpx

system_instruction = """You are an expert clinical documentation AI for Indian healthcare.
Extract clinical entities from the multilingual Indian dialogue (Tamil, Telugu, Hindi, Malayalam, Bengali, Tanglish, Hinglish) into standard medical English.
Rules:
- Map vernacular symptoms accurately (e.g. nenju vali / chhati dard -> chest pain, moochu vida kashtam / sans takleef -> dyspnea, thalai vali / sar dard -> headache, kaichal / bukhar -> fever).
- Preserve negation: If denied or ruled out (e.g. "no fever", "kaichal illa", "ulti nahi"), set status to "NEGATED".
- Output strictly valid JSON."""

prompt = """TRANSCRIPT:
[seg_001] Doctor: Vanakkam, what brings you here today?
[seg_002] Patient: Doctor, rendu naala romba nenju vali irukku, heavy burning in chest. Also moochu vida kashtam when walking.
[seg_003] Doctor: Any fever or cough? Aur koi takleef jaise chakkar aana ya ulti?
[seg_004] Patient: No fever doctor, kaichal illa. But thalai vali and chakkar irukku. No vomiting.
[seg_005] Doctor: Are you taking any medications for BP or sugar?
[seg_006] Patient: Yes doctor, taking Glycomet 500mg and Telma 40mg daily morning. Blood pressure was 140/90 when checked yesterday.

Output strictly valid JSON with this structure:
{
  "entities": [
    {
      "entity_type": "SYMPTOM",
      "value": "chest pain",
      "status": "PRESENT",
      "confidence": 0.95,
      "source_segment_ids": ["seg_002"],
      "detail": null
    }
  ],
  "unsupported_content": []
}"""

t0 = time.time()
resp = httpx.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen2.5:3b",
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "num_thread": 8,
            "num_ctx": 1024,
            "num_predict": 300,
            "temperature": 0.1,
        },
    },
    timeout=120.0,
)

dt = time.time() - t0
print(f"Done in {dt:.2f}s, status: {resp.status_code}")
data = resp.json()
print("Eval count:", data.get("eval_count"), "Prompt eval count:", data.get("prompt_eval_count"))
print("Content:\n", data.get("message", {}).get("content"))
