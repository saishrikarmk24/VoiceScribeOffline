import time
import httpx

prompt = """TASK: Extract clinical entities from the transcript into JSON format.
Transcript:
[seg_001] Patient: Doctor, nenju vali and heavy burning in chest for 2 days. No fever.

Output ONLY a JSON object with key 'entities':
{"entities": [{"entity_type": "SYMPTOM", "value": "chest pain", "status": "PRESENT", "source_segment_ids": ["seg_001"]}]}"""

# Test 1: without format="json"
t0 = time.time()
resp = httpx.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "qwen2.5:3b",
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 1024,
            "num_predict": 200,
            "temperature": 0.1,
        },
    },
    timeout=60.0,
)
print(f"Without format='json': {time.time()-t0:.2f}s")
print("Output:", resp.json().get("response"))

# Test 2: with format="json"
t1 = time.time()
resp2 = httpx.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "qwen2.5:3b",
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "num_ctx": 1024,
            "num_predict": 200,
            "temperature": 0.1,
        },
    },
    timeout=120.0,
)
print(f"With format='json': {time.time()-t1:.2f}s")
print("Output:", resp2.json().get("response"))
