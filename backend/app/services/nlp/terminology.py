"""Terminology normalisation interfaces (SNOMED CT / ICD-10 / RxNorm / LOINC).

The prototype ships a *mock* provider that normalises surface forms only. It
deliberately never invents a code: an unverifiable code in a clinical document is
worse than no code, so ``normalized_code`` stays ``None`` until a real
terminology service is wired in through this interface.
"""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass

from app.models.enums import EntityType


class TerminologySystem:
    SNOMED_CT = "SNOMED-CT"
    ICD10 = "ICD-10"
    RXNORM = "RxNorm"
    LOINC = "LOINC"


@dataclass(slots=True)
class NormalizationResult:
    normalized_value: str | None = None
    normalized_code: str | None = None
    system: str | None = None
    verified: bool = False


PREFERRED_SYSTEM: dict[EntityType, str] = {
    EntityType.SYMPTOM: TerminologySystem.SNOMED_CT,
    EntityType.FINDING: TerminologySystem.SNOMED_CT,
    EntityType.DIAGNOSIS_MENTIONED: TerminologySystem.ICD10,
    EntityType.MEDICATION: TerminologySystem.RXNORM,
    EntityType.ALLERGY: TerminologySystem.SNOMED_CT,
    EntityType.INVESTIGATION: TerminologySystem.LOINC,
    EntityType.PROCEDURE: TerminologySystem.SNOMED_CT,
    EntityType.MEDICAL_HISTORY: TerminologySystem.SNOMED_CT,
}

_FILLER = (
    "some",
    "a bit of",
    "a little",
    "kind of",
    "sort of",
    "really",
    "very",
    "just",
    "like",
)

_SYNONYMS = {
    "sob": "shortness of breath",
    "short of breath": "shortness of breath",
    "breathlessness": "shortness of breath",
    "chest pain": "chest pain",
    "chest discomfort": "chest discomfort",
    "tummy pain": "abdominal pain",
    "belly pain": "abdominal pain",
    "stomach pain": "abdominal pain",
    "temperature": "fever",
    "high temperature": "fever",
    "throwing up": "vomiting",
    "being sick": "vomiting",
    "loose motions": "diarrhoea",
    "ecg": "electrocardiogram",
    "fbc": "full blood count",
    "cbc": "complete blood count",
    "bp": "blood pressure",
    # Indian / Tamil / Hindi / regional terms
    "thalavali": "headache",
    "thala vali": "headache",
    "thalavaliya": "headache",
    "thalaveli": "headache",
    "தலைவலி": "headache",
    "kaachal": "fever",
    "kaichal": "fever",
    "காய்ச்சல்": "fever",
    "juram": "fever",
    "bukhar": "fever",
    "vayiru vali": "abdominal pain",
    "vayiruvali": "abdominal pain",
    "வயிறு வலி": "abdominal pain",
    "vaandhi": "vomiting",
    "vaanthi": "vomiting",
    "வாந்தி": "vomiting",
    "mayakkam": "dizziness",
    "மயக்கம்": "dizziness",
    "irumal": "cough",
    "இருமல்": "cough",
    "nenju vali": "chest pain",
    "நெஞ்சு வலி": "chest pain",
    "moochu vida mudiyala": "shortness of breath",
    "moochu thinarel": "shortness of breath",
    "kal vali": "leg pain",
    "kai vali": "arm pain",
    "muttuvalli": "knee pain",
    "muttu vali": "knee pain",
    "mudhugu vali": "back pain",
    "sali": "cold / congestion",
    "dham": "asthma / breathlessness",
    "sugar": "diabetes mellitus",
    "sakkarai": "diabetes mellitus",
    "rakthakothippu": "hypertension",
    "high bp": "hypertension",
    "dolo": "paracetamol (Dolo 650)",
    "dolo 650": "paracetamol (Dolo 650)",
    "dolo650": "paracetamol (Dolo 650)",
}


class TerminologyProvider(abc.ABC):
    name = "base"

    @abc.abstractmethod
    def normalize(self, value: str, entity_type: EntityType) -> NormalizationResult: ...


class MockTerminologyProvider(TerminologyProvider):
    """Surface-form normalisation with no code assignment."""

    name = "mock"

    def normalize(self, value: str, entity_type: EntityType) -> NormalizationResult:
        cleaned = value.strip().lower()
        cleaned = re.sub(r"^(the|a|an)\s+", "", cleaned)
        for filler in _FILLER:
            cleaned = re.sub(rf"\b{re.escape(filler)}\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
        cleaned = _SYNONYMS.get(cleaned, cleaned)
        if not cleaned:
            return NormalizationResult()
        return NormalizationResult(
            normalized_value=cleaned,
            normalized_code=None,  # never fabricate a terminology code
            system=PREFERRED_SYSTEM.get(entity_type),
            verified=False,
        )


class TerminologyService:
    """Facade so callers do not depend on the concrete provider."""

    def __init__(self, provider: TerminologyProvider | None = None) -> None:
        self.provider = provider or MockTerminologyProvider()

    def normalize(self, value: str, entity_type: EntityType) -> NormalizationResult:
        try:
            return self.provider.normalize(value, entity_type)
        except Exception:  # pragma: no cover - a terminology outage must not break a session
            return NormalizationResult(normalized_value=value.strip().lower() or None)

    def describe(self) -> dict[str, object]:
        return {
            "provider": self.provider.name,
            "systems": [
                TerminologySystem.SNOMED_CT,
                TerminologySystem.ICD10,
                TerminologySystem.RXNORM,
                TerminologySystem.LOINC,
            ],
            "codes_assigned": False,
            "note": "Mock provider normalises text only; codes require a licensed terminology service.",
        }
