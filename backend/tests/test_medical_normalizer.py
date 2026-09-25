"""Tests for the Indian medical terminology & phonetic normalizer."""

from app.services.asr.medical_normalizer import normalize_medical_transcript, normalize_segments


def test_normalize_telema_and_pand():
    raw = "Patient was prescribed tell my 40 once daily and penn d before breakfast"
    normalized = normalize_medical_transcript(raw)
    assert "Telma 40" in normalized
    assert "OD (once daily)" in normalized
    assert "Pan-D" in normalized


def test_normalize_common_indian_brands():
    cases = [
        ("take crossin when needed", "take Crocin SOS (as needed)"),
        ("dolo six fifty twice a day", "Dolo 650 BD (twice daily)"),
        ("glyco met 500 milligram", "Glycomet 500 mg"),
        ("am long 5 and atorva 10", "Amlong 5 and Atorva 10"),
        ("take ogmentin 625", "take Augmentin 625"),
        ("azithral 500 for 3 days", "Azithral 500 for 3 days"),
        ("combi flam for headache", "Combiflam for headache"),
    ]
    for raw, expected in cases:
        assert normalize_medical_transcript(raw) == expected


def test_tell_me_is_not_rewritten_as_telma():
    raw = "Please tell me 2 days se fever hai"
    assert "Telma" not in normalize_medical_transcript(raw)
    assert "tell me" in normalize_medical_transcript(raw).lower()


def test_normalize_segments_list():
    segs = [
        {"ref": "seg_01", "text": "Doctor gave tell my 20 and panto sid"},
        {"ref": "seg_02", "text": "Check b.p and sugar test"},
    ]
    cleaned = normalize_segments(segs)
    assert cleaned[0]["text"] == "Doctor gave Telma 20 and Pantocid"
    assert "BP" in str(cleaned[1]["text"])
    assert "blood sugar" in str(cleaned[1]["text"])
