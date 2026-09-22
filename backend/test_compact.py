import asyncio
import json
import time
import httpx

SYSTEM = """Clinical documentation AI. Extract entities into JSON:
{"entities": [{"type": "SYMPTOM", "value": "chest pain", "status": "PRESENT", "refs": ["seg_002"]}]}
Allowed types: SYMPTOM, DIAGNOSIS, MEDICATION, EXAMINATION_FINDING.
Allowed status: PRESENT, NEGATED.
Translate Indian terms to clinical English (nenju vali -> chest pain, thalai vali -> headache, moochu kashtam -> dyspnea, kaichal -> fever).
If denied, status is NEGATED. Output JSON only."""

PROMPT = """Doctor: [seg_001] Priya, enna aachu?
Patient: [seg_002] Doctor, rendu naala romba nenju vali irukku, burning in chest. Moochu vida kashtam.
Doctor: [seg_003] Any fever or cough? Chakkar or ulti?
Patient: [seg_004] No fever doctor, kaichal illa. But thalai vali and chakkar irukku. No vomiting.
Doctor: [seg_005] Taking medications for BP or sugar?
Patient: [seg_006] Taking Glycomet 500mg and Telma 40mg daily. BP 140/90 yesterday."""

async def test():
    async with httpx.AsyncClient(timeout=120.0) as client:
        t0 = time.perf_counter()
        resp = await client.post("http://localhost:11434/api/chat", json={
            "model": "qwen2.5:3b",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": PROMPT}
            ],
            "stream": False,
            "format": "json",
            "options": {
                "num_thread": 8,
                "num_ctx": 1024,
                "num_predict": 250,
                "temperature": 0.1
            }
        })
        print(f"Elapsed: {time.perf_counter() - t0:.2f}s")
        print(resp.json()["message"]["content"])

if __name__ == "__main__":
    asyncio.run(test())
