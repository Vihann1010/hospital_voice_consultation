"""Guards against the two failures that made a live consultation unusable.

Both are regression tests for a real call in which every assistant reply was
cut off mid-sentence and one turn read JSON field names aloud to the patient.
"""
import json

import pytest

from app.ai.echo import is_echo
from app.ai.streaming_json import UtteranceStreamExtractor

pytestmark = pytest.mark.unit


def _run(text: str, chunk: int = 7):
    """Feed text through the extractor the way a token stream arrives."""
    extractor = UtteranceStreamExtractor()
    spoken = ""
    for index in range(0, len(text), chunk):
        spoken += extractor.feed(text[index : index + chunk])
    spoken += extractor.finish()
    return extractor, spoken


def test_model_narrating_its_own_json_is_never_spoken():
    """The exact failure seen live: JSON field names read to the patient."""
    extractor, spoken = _run(
        'I should acknowledge. Setting `topics_addressed`: ["pain_location"] false'
    )
    assert spoken == ""
    assert extractor.suppressed


def test_machine_syntax_appearing_late_is_still_caught():
    """Passthrough buffers, so a giveaway token anywhere suppresses the turn."""
    extractor, spoken = _run("ठीक है। conversation_complete: false")
    assert spoken == ""
    assert extractor.suppressed


def test_well_formed_json_still_streams_incrementally():
    """Speech must begin before the model has finished writing the object."""
    payload = json.dumps(
        {"utterance": "ठीक है, आपके टखने में दर्द है", "language": "hi"},
        ensure_ascii=False,
    )
    extractor = UtteranceStreamExtractor()
    pieces = [
        piece
        for index in range(0, len(payload), 7)
        if (piece := extractor.feed(payload[index : index + 7]))
    ]
    assert len(pieces) > 1, "the JSON path must not have become buffered"
    assert "".join(pieces) + extractor.finish() == "ठीक है, आपके टखने में दर्द है"


def test_genuine_plain_text_reply_is_still_spoken():
    """Suppression must not silence a model that simply skipped the JSON."""
    _, spoken = _run("ठीक है। क्या दर्द चलने पर बढ़ता है?")
    assert spoken == "ठीक है। क्या दर्द चलने पर बढ़ता है?"


def test_cross_language_echo_defeats_text_matching():
    """Why the microphone is gated rather than the transcript filtered.

    The assistant's Hindi audio leaked back in and recognition, in
    auto-detect mode, returned English gibberish. No text comparison can
    connect the two, so echo detection alone cannot prevent a false barge-in
    — which is the reason for half-duplex gating in the orchestrator.
    """
    assistant_said = "ठीक है, आपके टखने में कल रात से दर्द हो रहा है"
    recognition_returned = "Recognize a little anything and alcoholism."
    assert not is_echo(recognition_returned, assistant_said)
