import asyncio, time, json
from app.services.llm.local_provider import LocalLLMProvider
from app.services.llm.json_parse import extract_json_object
from app.services.llm.schemas import NoteUpdate, coerce_llm_payload

async def main():
    p = LocalLLMProvider(model="qwen2.5:3b")
    prompt = """TASK: Write a structured clinical SOAP note from the transcript below in professional medical English.

TRANSCRIPT:
[seg_001] Doctor: What seems to be the problem today?
[seg_002] Patient: Doctor, I have had a severe throbbing headache and high fever since yesterday night.
[seg_003] Doctor: Any neck stiffness or vomiting?
[seg_004] Patient: No vomiting, but I feel very weak.

Output valid JSON with these sections (leave empty string "" if not discussed):
{
  "chief_complaint": "Primary complaint in 1 line",
  "history_of_present_illness": "Detailed symptom narrative",
  "past_medical_history": "",
  "physical_examination": "",
  "current_medication": "",
  "allergies": "",
  "assessment": "Clinical diagnostic impression",
  "plan": "Doctor treatment plan and recommendations",
  "follow_up": ""
}"""
    t0 = time.time()
    try:
        content, stats = await p._post_chat(prompt, purpose="test_fast_note")
        dur = round(time.time() - t0, 2)
        print(f"Fast note generation completed in: {dur}s")
        print("Raw Content:", content)
        parsed = extract_json_object(content)
        coerced = coerce_llm_payload(parsed, NoteUpdate)
        res = NoteUpdate.model_validate(coerced)
        print("\n--- Parsed SOAP Note ---")
        print("Chief Complaint:", res.note.chief_complaint.text)
        print("HPI:", res.note.history_of_present_illness.text)
        print("Assessment:", res.note.assessment.text)
        print("Plan:", res.note.plan.text)
    finally:
        await p.aclose()

asyncio.run(main())
