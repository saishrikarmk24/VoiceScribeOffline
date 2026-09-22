"""Synthetic conversation scripts.

Everything here is fabricated for training and demonstration. No real patient
data is present, and none must ever be added.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import SpeakerRole


@dataclass(frozen=True, slots=True)
class ScriptedUtterance:
    speaker_label: str
    role: SpeakerRole
    text: str
    duration: float = 4.0
    confidence: float = 0.95
    pitch_hz: float = 120.0


@dataclass(frozen=True, slots=True)
class SimulationScript:
    key: str
    title: str
    description: str
    utterances: tuple[ScriptedUtterance, ...]

    @property
    def speaker_labels(self) -> tuple[str, ...]:
        seen: list[str] = []
        for utterance in self.utterances:
            if utterance.speaker_label not in seen:
                seen.append(utterance.speaker_label)
        return tuple(seen)


_DOCTOR_PITCH = 112.0
_PATIENT_PITCH = 186.0


CHEST_DISCOMFORT_SCRIPT = SimulationScript(
    key="chest_discomfort",
    title="Outpatient chest discomfort (reference scenario)",
    description=(
        "The reference MedScribe Live demo: intermittent chest pressure, "
        "denied shortness of breath, metformin, no known drug allergies."
    ),
    utterances=(
        ScriptedUtterance("speaker_0", SpeakerRole.DOCTOR, "Good morning. What brings you in today?", 3.4, 0.97, _DOCTOR_PITCH),
        ScriptedUtterance(
            "speaker_1",
            SpeakerRole.PATIENT,
            "I've been having chest discomfort since yesterday evening.",
            4.2,
            0.94,
            _PATIENT_PITCH,
        ),
        ScriptedUtterance("speaker_0", SpeakerRole.DOCTOR, "Can you describe the discomfort?", 2.8, 0.96, _DOCTOR_PITCH),
        ScriptedUtterance(
            "speaker_1", SpeakerRole.PATIENT, "It feels like pressure. It comes and goes.", 3.6, 0.93, _PATIENT_PITCH
        ),
        ScriptedUtterance("speaker_0", SpeakerRole.DOCTOR, "Any shortness of breath?", 2.4, 0.97, _DOCTOR_PITCH),
        ScriptedUtterance(
            "speaker_1", SpeakerRole.PATIENT, "No, I don't have any shortness of breath.", 3.4, 0.95, _PATIENT_PITCH
        ),
        ScriptedUtterance(
            "speaker_0", SpeakerRole.DOCTOR, "Are you currently taking any medications?", 3.0, 0.96, _DOCTOR_PITCH
        ),
        ScriptedUtterance("speaker_1", SpeakerRole.PATIENT, "I'm taking metformin.", 2.2, 0.92, _PATIENT_PITCH),
        ScriptedUtterance(
            "speaker_0", SpeakerRole.DOCTOR, "Do you have any known allergies?", 2.6, 0.97, _DOCTOR_PITCH
        ),
        ScriptedUtterance("speaker_1", SpeakerRole.PATIENT, "No known drug allergies.", 2.4, 0.95, _PATIENT_PITCH),
    ),
)


WARD_ROUND_SCRIPT = SimulationScript(
    key="ward_round_review",
    title="Ward round review",
    description="Post-operative ward round with a nurse handover and an ECG request.",
    utterances=(
        ScriptedUtterance(
            "speaker_0",
            SpeakerRole.DOCTOR,
            "Good morning. How has the night been for our patient in bed four?",
            4.4,
            0.96,
            _DOCTOR_PITCH,
        ),
        ScriptedUtterance(
            "speaker_2",
            SpeakerRole.NURSE,
            "He slept reasonably well. He reported mild abdominal pain around three in the morning.",
            5.2,
            0.91,
            148.0,
        ),
        ScriptedUtterance(
            "speaker_1",
            SpeakerRole.PATIENT,
            "The pain is much better now, maybe a three out of ten.",
            4.0,
            0.93,
            _PATIENT_PITCH,
        ),
        ScriptedUtterance(
            "speaker_0", SpeakerRole.DOCTOR, "Any nausea or vomiting since the operation?", 3.2, 0.96, _DOCTOR_PITCH
        ),
        ScriptedUtterance(
            "speaker_1", SpeakerRole.PATIENT, "No nausea, and I have not vomited at all.", 3.6, 0.94, _PATIENT_PITCH
        ),
        ScriptedUtterance(
            "speaker_2",
            SpeakerRole.NURSE,
            "His temperature was thirty-seven point one, and the wound dressing is clean and dry.",
            5.4,
            0.9,
            148.0,
        ),
        ScriptedUtterance(
            "speaker_0",
            SpeakerRole.DOCTOR,
            "We will continue paracetamol as required and repeat the full blood count this afternoon.",
            5.4,
            0.95,
            _DOCTOR_PITCH,
        ),
        ScriptedUtterance(
            "speaker_0",
            SpeakerRole.DOCTOR,
            "Please arrange an ECG before the ward round tomorrow, and I will review the results then.",
            5.6,
            0.95,
            _DOCTOR_PITCH,
        ),
        ScriptedUtterance(
            "speaker_1",
            SpeakerRole.PATIENT,
            "I am allergic to penicillin, it gave me a rash a few years ago.",
            4.6,
            0.92,
            _PATIENT_PITCH,
        ),
    ),
)


HEADACHE_SCRIPT = SimulationScript(
    key="headache_history",
    title="Headache history taking",
    description="Student OSCE style history with uncertainty and a negated red flag.",
    utterances=(
        ScriptedUtterance(
            "speaker_0", SpeakerRole.DOCTOR, "Tell me about the headaches you have been getting.", 3.8, 0.96, _DOCTOR_PITCH
        ),
        ScriptedUtterance(
            "speaker_1",
            SpeakerRole.PATIENT,
            "They started about three weeks ago, mostly in the afternoon.",
            4.4,
            0.93,
            _PATIENT_PITCH,
        ),
        ScriptedUtterance(
            "speaker_1",
            SpeakerRole.PATIENT,
            "It is a tight band around my head, moderate most days.",
            4.2,
            0.92,
            _PATIENT_PITCH,
        ),
        ScriptedUtterance(
            "speaker_0", SpeakerRole.DOCTOR, "Any visual disturbance or weakness?", 3.0, 0.96, _DOCTOR_PITCH
        ),
        ScriptedUtterance(
            "speaker_1",
            SpeakerRole.PATIENT,
            "No weakness. I possibly had some blurred vision once, but I am not sure.",
            5.0,
            0.9,
            _PATIENT_PITCH,
        ),
        ScriptedUtterance(
            "speaker_0", SpeakerRole.DOCTOR, "Do you take anything for the pain?", 3.0, 0.96, _DOCTOR_PITCH
        ),
        ScriptedUtterance(
            "speaker_1", SpeakerRole.PATIENT, "I take ibuprofen twice a day when it is bad.", 4.0, 0.93, _PATIENT_PITCH
        ),
        ScriptedUtterance(
            "speaker_0",
            SpeakerRole.DOCTOR,
            "I will document a headache diary and we will review you in two weeks.",
            5.0,
            0.95,
            _DOCTOR_PITCH,
        ),
    ),
)


SCRIPTS: dict[str, SimulationScript] = {
    script.key: script
    for script in (CHEST_DISCOMFORT_SCRIPT, WARD_ROUND_SCRIPT, HEADACHE_SCRIPT)
}

DEFAULT_SCRIPT_KEY = CHEST_DISCOMFORT_SCRIPT.key


def get_script(key: str | None) -> SimulationScript:
    if not key:
        return SCRIPTS[DEFAULT_SCRIPT_KEY]
    return SCRIPTS.get(key, SCRIPTS[DEFAULT_SCRIPT_KEY])


def list_scripts() -> list[dict[str, str | int]]:
    return [
        {
            "key": script.key,
            "title": script.title,
            "description": script.description,
            "utterances": len(script.utterances),
            "speakers": len(script.speaker_labels),
        }
        for script in SCRIPTS.values()
    ]
