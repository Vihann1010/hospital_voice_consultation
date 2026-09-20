"""Deterministic emergency screening — layer 1 of red-flag detection.

Runs synchronously on every patient utterance (English, Hinglish, Devanagari
patterns) so an emergency is caught the moment it is spoken, before any LLM
round-trip. Layer 2 is the LLM RiskDetectionService, which reasons over the
structured record. A deterministic hit forces the conversation into emergency
mode immediately.

Patterns are written to tolerate the connective words real speech contains
("bone IS sticking out", "baby IS not moving") while staying tight enough that
ordinary complaints ("my knee hurts on stairs") never trip them.
"""
import re
from dataclasses import dataclass
from typing import List

from app.departments import require_department
from app.models.enums import Department

_FLAGS = [
    (
        "chest_pain",
        r"chest\s*(pain|dard|tight|pressure|heavy)|pain\s+in\s+(my\s+|the\s+)?chest"
        r"|seene?\s*m[ae]i?n\s*dard|छाती\s*में\s*दर्द|सीने\s*में\s*दर्द",
    ),
    (
        "breathlessness",
        r"can'?t\s+breathe|cannot\s+breathe|breathless|short(ness)?\s+of\s+breath"
        r"|difficulty\s+(in\s+)?breathing|trouble\s+breathing"
        r"|saa?ns\s+(nahi|lene|phool|ukhad|fool)|dam\s+ghut"
        r"|सांस\s*(नहीं|फूल|लेने)",
    ),
    (
        "loss_of_consciousness",
        r"unconscious|fainted|passed\s+out|blacked\s+out|behosh|बेहोश",
    ),
    (
        "severe_bleeding",
        r"(heavy|severe|lot\s+of|too\s+much|bahut)\s+(bleeding|blood|khoon)"
        r"|bleeding\s+(heavily|a\s+lot|non.?stop|badly)"
        r"|khoon\s+(beh|ruk\s+nahi|bahut)"
        r"|खून\s*(बह|बहुत|नहीं\s*रुक)",
    ),
    (
        "stroke_signs",
        r"face\s*.{0,12}(droop|tedha)|slurr?ed\s+speech|speech\s*.{0,12}slurr"
        r"|one\s+side\s*.{0,18}(weak|numb|paralys)|लकवा|fal[ii]j",
    ),
    (
        "seizure",
        r"seizure|convulsion|fits?\s+(aa|come|hu[ae]|pad)|daura|दौरा|मिर्गी",
    ),
    (
        "suicidal_ideation",
        r"suicide|end\s+my\s+life|kill\s+myself|harm\s+myself"
        r"|khud\s*kushi|marna\s+chaht|खुदकुशी|आत्महत्या",
    ),
    (
        "high_fever_confusion",
        r"(very\s+high|103|104|105)\s*(degree|fever|bukhar)"
        r"|fever\s*.{0,30}(confus|behosh|unconscious)"
        r"|तेज़?\s*बुखार\s*.{0,20}बेहोश",
    ),
]

# Keyed by department and read through require_department: a department with no
# block here raises rather than screening against nothing. An empty red-flag
# list is indistinguishable from "no emergency", which is the one mistake this
# module must never make.
DEPARTMENT_FLAGS = {
    Department.ORTHOPEDICS: [
        (
            "open_or_deformed_fracture",
            r"bone\s*(is\s*|was\s*)?(sticking|coming)\s*out|bone\s+(visible|exposed|outside)"
            r"|open\s+fracture"
            r"|haddi\s*.{0,10}(bahar|dikh|nikal)"
            r"|(limb|leg|arm|hand)\s*.{0,12}(deformed|bent\s+(wrong|badly)|twisted)"
            r"|हड्डी\s*.{0,10}(बाहर|दिख|निकल)",
        ),
        (
            "limb_numb_cold",
            r"(leg|arm|limb|hand|foot|haath|pair|paer)\s*"
            r"(is\s+|are\s+|feels?\s+|ho\s+gaya\s+|ho\s+gayi\s+|hai\s+)?"
            r"(numb|sunn|cold|thanda|blue|pale|no\s+pulse)"
            r"|(numb|sunn)\s*.{0,18}(leg|arm|hand|foot|haath|pair)"
            r"|(हाथ|पैर)\s*.{0,15}(सुन्न|ठंडा)|सुन्न\s*.{0,10}(हाथ|पैर)",
        ),
        (
            "cauda_equina",
            r"(can'?t|cannot|unable\s+to|not\s+able\s+to)\s*.{0,18}"
            r"(pass\s+urine|pee|control\s+(my\s+)?(urine|stool|bowel|motion))"
            r"|urine\s*.{0,12}(not\s+coming|nahi\s+aa)"
            r"|numb\s*.{0,15}(groin|saddle|private|inner\s+thigh)"
            r"|pesh?ab\s*.{0,10}(nahi|ruk)|पेशाब\s*.{0,10}(नहीं|रुक)",
        ),
    ],
    Department.GYNECOLOGY: [
        (
            "pregnancy_bleeding",
            r"pregnan\w*.{0,45}(bleed|blood|khoon|खून)"
            r"|(bleed\w*|khoon|खून).{0,45}pregnan\w*"
            r"|गर्भ.{0,25}खून",
        ),
        (
            "pregnancy_severe_pain",
            r"pregnan\w*.{0,45}(severe|unbearable|very\s+bad|bahut\s+tez)\s*(pain|dard)"
            r"|(severe|unbearable)\s+(abdominal|stomach|pet)\s+pain.{0,35}pregnan\w*"
            r"|गर्भ.{0,25}तेज़?\s*दर्द",
        ),
        (
            "reduced_fetal_movement",
            r"baby\s*(is\s*|has\s*)?(not|stopped|nahi)\s*(mov|kick)"
            r"|baby.{0,18}(movement|kick)\w*.{0,18}(not|stopped|reduced|less|kam)"
            r"|bacch[ae].{0,25}(halchal|movement).{0,12}(kam|nahi)"
            r"|(हलचल|हरकत)\s*.{0,10}(कम|नहीं)",
        ),
        (
            "postmenopausal_bleeding",
            r"bleeding\s+after\s+menopause|post.?menopausal\s+bleed"
            r"|menopause.{0,35}(bleed|khoon|spotting)",
        ),
    ],
    Department.GASTROENTEROLOGY: [
        (
            "gi_bleeding",
            r"(vomit\w*|throw\w*\s+up|ulti|उल्टी)\s*.{0,25}(blood|khoon|खून)"
            r"|(blood|khoon|खून)\s*.{0,25}(vomit|ulti|उल्टी)"
            r"|coffee\s*ground"
            r"|(black|tarry|kal[ai])\s*(stool|motion|shauch|tatti|पाखाना|मल)"
            r"|(stool|motion|shauch|tatti|पाखाना|मल)s?\s*"
            r"(is\s+|are\s+|was\s+|were\s+|ho\s+raha\s+hai\s+|hai\s+)?"
            r"(very\s+|bilkul\s+)?(black|tarry|kal[ai])"
            r"|mel(a?ena|aena)"
            r"|(stool|motion|shauch|latrine|tatti|पाखाना|मल)\s*.{0,25}(blood|khoon|खून)"
            r"|(blood|khoon|खून)\s*.{0,25}(stool|motion|shauch|latrine|tatti|पाखाना|मल)"
            r"|rectal\s+bleed|bleeding\s+from\s+(the\s+)?(back\s+passage|anus)"
            r"|शौच\s*.{0,15}खून|काला\s*(पाखाना|मल)",
        ),
        (
            "bowel_obstruction",
            r"(not\s+passing|unable\s+to\s+pass|no)\s*(gas|wind|stool|motion)"
            r"|(gas|wind)\s*(and|or)?\s*(stool|motion)\s*.{0,15}(not\s+passing|band|nahi)"
            r"|(stomach|pet|abdomen|पेट)\s*.{0,15}(swollen|distend|phool|फूल)"
            r"|(continuous|constant|repeated|baar\s*baar)\s+vomit"
            r"|पेट\s*.{0,15}फूल|गैस\s*.{0,15}नहीं",
        ),
        (
            "severe_epigastric_pain",
            r"(severe|unbearable|worst|bahut\s*tez|असहनीय|तेज़?)\s*.{0,18}"
            r"(stomach|abdominal|abdomen|epigastric|pet|पेट)\s*(pain|dard|दर्द)"
            r"|(stomach|abdominal|pet|पेट)\s*(pain|dard|दर्द)\s*.{0,25}"
            r"(going|radiat\w*|spread\w*|jata|जाता)\s*.{0,12}(back|peeth|पीठ)",
        ),
        (
            "jaundice",
            r"(eyes?|skin|aankh\w*|आंख\w*|आँख\w*)\s*.{0,18}(yellow|peel[ai]|पील[ेाी])"
            r"|(yellow|peel[ai]|पील[ेाी])\s*.{0,18}(eyes?|skin|aankh|आंख|आँख)"
            r"|jaundice|piliya|पीलिया"
            r"|urine\s*.{0,15}(very\s+)?dark|peshab\s*.{0,12}(gadha|kala)",
        ),
        (
            "dysphagia",
            r"(can'?t|cannot|unable\s+to|not\s+able\s+to|difficult\w*|nahi)\s*.{0,18}"
            r"(swallow|nigal|निगल)"
            r"|(food|khana|खाना)\s*.{0,18}(stuck|atk|अटक)"
            r"|(swallow|nigal|निगल)\w*\s*.{0,15}(pain|dard|दर्द|mushkil|मुश्किल)",
        ),
    ],
}

_COMPILED = [(flag, re.compile(pattern, re.IGNORECASE)) for flag, pattern in _FLAGS]
_COMPILED_DEPT = {
    dept: [(flag, re.compile(pattern, re.IGNORECASE)) for flag, pattern in flags]
    for dept, flags in DEPARTMENT_FLAGS.items()
}


@dataclass(frozen=True)
class ScreenResult:
    flags: List[str]

    @property
    def is_emergency(self) -> bool:
        return bool(self.flags)


def screen_utterance(text: str, department: Department) -> ScreenResult:
    """Screen one utterance for emergency red flags. Pure, fast, no I/O."""
    hits: List[str] = []
    department_patterns = require_department(
        _COMPILED_DEPT, department, "emergency red flags"
    )
    for flag, pattern in _COMPILED + department_patterns:
        if pattern.search(text) and flag not in hits:
            hits.append(flag)
    return ScreenResult(flags=hits)
