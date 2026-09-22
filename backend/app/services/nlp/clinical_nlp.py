"""Deterministic clinical NLP pre-pass.

This runs *before* the LLM and serves three purposes:

1. It gives Gemini a candidate list plus negation analysis (grounding, not
   instructions), which measurably reduces missed negations.
2. It is the fallback extractor when Gemini is unavailable, so a session never
   loses clinical structure entirely.
3. It cross-checks the LLM: an entity marked PRESENT by the model while the
   rule engine sees a negation trigger gets flagged for human review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.logging import get_logger, track_duration
from app.models.enums import EntityStatus, EntityType, SpeakerRole
from app.services.nlp.negation import NegationDetector
from app.services.nlp.terminology import TerminologyService
from app.services.types import AssembledSegment

logger = get_logger(__name__)


@dataclass(slots=True)
class EntityCandidate:
    entity_type: EntityType
    value: str
    status: EntityStatus
    confidence: float
    source_segment_refs: list[str] = field(default_factory=list)
    normalized_value: str | None = None
    normalized_code: str | None = None
    terminology_system: str | None = None
    detail: str | None = None
    matched_text: str | None = None

    @property
    def key(self) -> str:
        return f"{self.entity_type.value}:{(self.normalized_value or self.value).lower()}"


SYMPTOM_LEXICON = (
    "chest discomfort",
    "chest pressure",
    "chest pain",
    "chest tightness",
    "shortness of breath",
    "breathlessness",
    "palpitations",
    "dizziness",
    "light headedness",
    "lightheadedness",
    "syncope",
    "fainting",
    "nausea",
    "vomiting",
    "diarrhoea",
    "diarrhea",
    "constipation",
    "abdominal pain",
    "stomach pain",
    "headache",
    "headaches",
    "blurred vision",
    "visual disturbance",
    "weakness",
    "numbness",
    "tingling",
    "cough",
    "fever",
    "chills",
    "night sweats",
    "weight loss",
    "fatigue",
    "tiredness",
    "back pain",
    "joint pain",
    "swelling",
    "rash",
    "itching",
    "sore throat",
    "wheeze",
    "wheezing",
    "sputum",
    "heartburn",
    "indigestion",
    "leg swelling",
    "ankle swelling",
    "shoulder pain",
    "sweating",
    "insomnia",
    "loss of appetite",
    "thalavali",
    "thala vali",
    "thalavaliya",
    "thalaveli",
    "தலைவலி",
    "kaachal",
    "kaichal",
    "காய்ச்சல்",
    "juram",
    "bukhar",
    "vayiru vali",
    "vayiruvali",
    "வயிறு வலி",
    "vaandhi",
    "vaanthi",
    "வாந்தி",
    "mayakkam",
    "மயக்கம்",
    "irumal",
    "இருமல்",
    "nenju vali",
    "நெஞ்சு வலி",
    "moochu thinarel",
    "muttu vali",
    "mudhugu vali",
)

FINDING_LEXICON = (
    "temperature",
    "blood pressure",
    "heart rate",
    "pulse",
    "respiratory rate",
    "oxygen saturation",
    "wound dressing",
    "tenderness",
    "murmur",
    "crackles",
    "clear chest",
    "abdomen soft",
    "no swelling",
)

MEDICATION_LEXICON = (
    "metformin",
    "paracetamol",
    "acetaminophen",
    "ibuprofen",
    "aspirin",
    "atorvastatin",
    "simvastatin",
    "amlodipine",
    "ramipril",
    "lisinopril",
    "bisoprolol",
    "salbutamol",
    "insulin",
    "omeprazole",
    "amoxicillin",
    "penicillin",
    "warfarin",
    "clopidogrel",
    "gliclazide",
    "levothyroxine",
    "sertraline",
    "codeine",
    "morphine",
    "furosemide",
    "prednisolone",
    "dolo",
    "dolo 650",
    "dolo650",
    "crocin",
    "calpol",
    "glycomet",
    "pantoprazole",
    "pantocid",
    "pan 40",
)

INVESTIGATION_LEXICON = (
    "ecg",
    "electrocardiogram",
    "chest x-ray",
    "chest xray",
    "x-ray",
    "blood test",
    "blood tests",
    "full blood count",
    "complete blood count",
    "troponin",
    "hba1c",
    "urea and electrolytes",
    "ct scan",
    "mri",
    "ultrasound",
    "echocardiogram",
    "urine dipstick",
    "blood glucose",
    "lipid profile",
    "thyroid function test",
    "spirometry",
)

PROCEDURE_LEXICON = (
    "cannulation",
    "catheter",
    "operation",
    "surgery",
    "appendicectomy",
    "endoscopy",
    "colonoscopy",
    "biopsy",
    "suturing",
    "dressing change",
    "physiotherapy",
)

HISTORY_LEXICON = (
    "diabetes",
    "type 2 diabetes",
    "type 1 diabetes",
    "hypertension",
    "high blood pressure",
    "asthma",
    "copd",
    "ischaemic heart disease",
    "heart failure",
    "stroke",
    "epilepsy",
    "depression",
    "anxiety",
    "hypothyroidism",
    "chronic kidney disease",
    "migraine",
)

CHARACTER_LEXICON = (
    "pressure",
    "squeezing",
    "crushing",
    "burning",
    "sharp",
    "dull",
    "stabbing",
    "aching",
    "throbbing",
    "cramping",
    "tight band",
    "tightness",
    "colicky",
    "radiating",
)

SEVERITY_PATTERNS = (
    r"\b(mild|moderate|severe|excruciating|unbearable|slight|intense)\b",
    r"\b(\d{1,2})\s*(?:out of|/)\s*10\b",
)

FREQUENCY_PATTERNS = (
    r"\bcomes and goes\b",
    r"\bintermittent(?:ly)?\b",
    r"\bconstant(?:ly)?\b",
    r"\bcontinuous(?:ly)?\b",
    r"\ball the time\b",
    r"\bon and off\b",
    r"\bevery (?:day|morning|night|hour|few hours)\b",
    r"\b(?:once|twice|three times|\d+ times) (?:a|per) (?:day|week|month|night)\b",
    r"\bmostly in the (?:morning|afternoon|evening|night)\b",
    r"\boccasionally\b",
    r"\brarely\b",
)

DURATION_PATTERNS = (
    r"\bsince (?:yesterday(?: evening| morning| afternoon| night)?|last (?:night|week|month|year)|this (?:morning|afternoon|evening))\b",
    r"\bfor (?:about |around |roughly )?\d+ (?:minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\b",
    r"\b(?:about|around|roughly)? ?\d+ (?:minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years) ago\b",
    r"\bstarted (?:about |around )?(?:\w+ )?(?:days?|weeks?|months?|years?) ago\b",
    r"\bthree weeks ago\b",
    r"\bsince (?:the )?(?:operation|surgery|admission)\b",
    r"\byesterday evening\b",
    r"\bovernight\b",
)

# "you have X" only counts as an assertion when it is not preceded by an
# auxiliary verb ("do you have X?" is a question, not documentation).
DIAGNOSIS_ASSERTION_PATTERN = (
    r"(?<!do )(?<!does )(?<!did )(?<!don't )(?<!doesn't )"
    r"\b(?:you have|he has|she has|the patient has|this is|diagnosis of|consistent with)\s+"
    r"(?P<value>[a-z][a-z \-]{2,40})"
)

ALLERGY_PATTERNS = (
    r"\bno known (?:drug )?allergies\b",
    r"\bno drug allergies\b",
    r"\bnot allergic to [a-z ]+\b",
    r"\ballergic to ([a-z]+)\b",
    r"\ballergy to ([a-z]+)\b",
)

PLAN_PATTERNS = (
    r"\b(?:i|we) will (?:continue|start|stop|arrange|prescribe|request|order|refer|document|repeat|check)[^.?!]*",
    r"\bplease arrange[^.?!]*",
    r"\blet's (?:start|continue|arrange|check)[^.?!]*",
    r"\b(?:i am|i'm) going to[^.?!]*",
    r"\bwe should[^.?!]*",
)

FOLLOW_UP_PATTERNS = (
    r"\b(?:review|see) you (?:again )?in [^.?!]*",
    r"\bcome back (?:in|after) [^.?!]*",
    r"\bfollow(?:-| )up (?:in|after)? ?[^.?!]*",
    r"\bwe will review (?:the results|you)[^.?!]*",
    r"\breview (?:the results|him|her|the patient)[^.?!]*",
)


class ClinicalNLPService:
    def __init__(
        self,
        negation: NegationDetector | None = None,
        terminology: TerminologyService | None = None,
    ) -> None:
        self.negation = negation or NegationDetector()
        self.terminology = terminology or TerminologyService()

    # ------------------------------------------------------------------ public
    def extract(self, segments: list[AssembledSegment]) -> list[EntityCandidate]:
        """Extract candidates from speaker-attributed segments."""
        with track_duration("clinical_nlp", logger, segments=len(segments)):
            candidates: list[EntityCandidate] = []
            for segment in segments:
                candidates.extend(self._extract_from_segment(segment))
            return self.merge(candidates)

    def merge(self, candidates: list[EntityCandidate]) -> list[EntityCandidate]:
        """Deduplicate by (type, normalized value), keeping the strongest status."""
        merged: dict[str, EntityCandidate] = {}
        status_rank = {
            EntityStatus.NEGATED: 4,
            EntityStatus.UNCERTAIN: 3,
            EntityStatus.HISTORICAL: 2,
            EntityStatus.PRESENT: 1,
            EntityStatus.UNKNOWN: 0,
        }
        for candidate in candidates:
            existing = merged.get(candidate.key)
            if existing is None:
                merged[candidate.key] = candidate
                continue
            for ref in candidate.source_segment_refs:
                if ref not in existing.source_segment_refs:
                    existing.source_segment_refs.append(ref)
            if status_rank[candidate.status] > status_rank[existing.status]:
                existing.status = candidate.status
            existing.confidence = max(existing.confidence, candidate.confidence)
        return list(merged.values())

    def statuses_by_value(self, segments: list[AssembledSegment]) -> dict[str, EntityStatus]:
        """Value -> status map used to cross-check LLM output."""
        return {
            (candidate.normalized_value or candidate.value).lower(): candidate.status
            for candidate in self.extract(segments)
        }

    # ------------------------------------------------------------------ private
    def _extract_from_segment(self, segment: AssembledSegment) -> list[EntityCandidate]:
        text = segment.text
        lowered = text.lower()
        base_confidence = max(0.45, min(segment.confidence, 0.95))
        found: list[EntityCandidate] = []

        lexicons: tuple[tuple[EntityType, tuple[str, ...]], ...] = (
            (EntityType.SYMPTOM, SYMPTOM_LEXICON),
            (EntityType.MEDICATION, MEDICATION_LEXICON),
            (EntityType.INVESTIGATION, INVESTIGATION_LEXICON),
            (EntityType.PROCEDURE, PROCEDURE_LEXICON),
            (EntityType.MEDICAL_HISTORY, HISTORY_LEXICON),
            (EntityType.CHARACTER, CHARACTER_LEXICON),
            (EntityType.FINDING, FINDING_LEXICON),
        )
        for entity_type, lexicon in lexicons:
            for term in lexicon:
                if not re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", lowered):
                    continue
                if entity_type is EntityType.SYMPTOM and self._covered_by_longer_term(term, lowered):
                    continue
                found.append(self._build(entity_type, term, text, base_confidence, segment))

        for pattern in DURATION_PATTERNS:
            for match in re.finditer(pattern, lowered):
                found.append(self._build(EntityType.DURATION, match.group(0), text, base_confidence, segment))
        for pattern in SEVERITY_PATTERNS:
            for match in re.finditer(pattern, lowered):
                found.append(self._build(EntityType.SEVERITY, match.group(0), text, base_confidence, segment))
        for pattern in FREQUENCY_PATTERNS:
            for match in re.finditer(pattern, lowered):
                found.append(self._build(EntityType.FREQUENCY, match.group(0), text, base_confidence, segment))
        for pattern in ALLERGY_PATTERNS:
            for match in re.finditer(pattern, lowered):
                found.append(self._allergy(match.group(0), text, base_confidence, segment))

        # Plan and follow-up language only counts when a clinician says it.
        if segment.role in (SpeakerRole.DOCTOR, SpeakerRole.NURSE, SpeakerRole.UNKNOWN):
            for pattern in PLAN_PATTERNS:
                for match in re.finditer(pattern, lowered):
                    found.append(
                        self._build(EntityType.PLAN, match.group(0).strip(), text, base_confidence, segment)
                    )
            for pattern in FOLLOW_UP_PATTERNS:
                for match in re.finditer(pattern, lowered):
                    found.append(
                        self._build(EntityType.FOLLOW_UP, match.group(0).strip(), text, base_confidence, segment)
                    )

        # A diagnosis is only recorded when a clinician explicitly asserts it.
        if segment.role is SpeakerRole.DOCTOR:
            for sentence in self._statements(text):
                for match in re.finditer(DIAGNOSIS_ASSERTION_PATTERN, sentence.lower()):
                    value = match.group("value").strip(" .,")
                    if self._is_plausible_diagnosis(value):
                        found.append(
                            self._build(
                                EntityType.DIAGNOSIS_MENTIONED, value, sentence, base_confidence * 0.9, segment
                            )
                        )

        return found

    @staticmethod
    def _statements(text: str) -> list[str]:
        """Declarative sentences only - a question is not an assertion."""
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [sentence for sentence in sentences if sentence and not sentence.rstrip().endswith("?")]

    @staticmethod
    def _is_plausible_diagnosis(value: str) -> bool:
        if len(value) < 3:
            return False
        if re.match(r"^(any|some|no|a|an|the|your|his|her|my)\b", value):
            return False
        return not any(
            re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", value)
            for term in ("allergies", "allergy", "medication", "medications", "symptoms", "questions")
        )

    @staticmethod
    def _covered_by_longer_term(term: str, lowered: str) -> bool:
        """Drop a short match when a more specific lexicon entry also matched."""
        for other in SYMPTOM_LEXICON:
            if other != term and term in other and re.search(rf"(?<![a-z]){re.escape(other)}(?![a-z])", lowered):
                return True
        return False

    def _build(
        self,
        entity_type: EntityType,
        matched: str,
        sentence: str,
        confidence: float,
        segment: AssembledSegment,
    ) -> EntityCandidate:
        negation = self.negation.detect(sentence, matched)
        normalization = self.terminology.normalize(matched, entity_type)
        status = negation.status
        if entity_type in (EntityType.PLAN, EntityType.FOLLOW_UP, EntityType.DURATION) and status is EntityStatus.HISTORICAL:
            status = EntityStatus.PRESENT
        return EntityCandidate(
            entity_type=entity_type,
            value=matched,
            status=status,
            confidence=round(confidence * (0.95 if status is EntityStatus.PRESENT else 0.9), 4),
            source_segment_refs=[segment.ref],
            normalized_value=normalization.normalized_value,
            normalized_code=normalization.normalized_code,
            terminology_system=normalization.system,
            detail=negation.rationale,
            matched_text=matched,
        )

    def _allergy(
        self, matched: str, sentence: str, confidence: float, segment: AssembledSegment
    ) -> EntityCandidate:
        """Allergy statements are frequently negative assertions ("no known allergies")."""
        normalized = matched.strip()
        if re.match(r"^no (known )?(drug )?allerg", normalized):
            return EntityCandidate(
                entity_type=EntityType.ALLERGY,
                value="No known drug allergies",
                status=EntityStatus.NEGATED,
                confidence=round(confidence, 4),
                source_segment_refs=[segment.ref],
                normalized_value="no known drug allergies",
                terminology_system=None,
                detail="explicit denial of drug allergies",
                matched_text=matched,
            )
        substance = re.sub(r"^(not )?allerg(ic|y) to ", "", normalized).strip()
        status = EntityStatus.NEGATED if normalized.startswith("not allergic") else EntityStatus.PRESENT
        return EntityCandidate(
            entity_type=EntityType.ALLERGY,
            value=substance or normalized,
            status=status,
            confidence=round(confidence, 4),
            source_segment_refs=[segment.ref],
            normalized_value=(substance or normalized).lower(),
            detail="allergy statement",
            matched_text=matched,
        )
