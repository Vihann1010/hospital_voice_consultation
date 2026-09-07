"""Recognising the assistant's own voice arriving back through the microphone.

Both directions are load-bearing. Failing to spot echo cuts every reply off
mid-sentence; over-eagerly calling real speech echo means the patient cannot
interrupt and their words vanish from the record.
"""
import pytest

from app.ai.echo import is_echo, longest_common_run, normalise

pytestmark = pytest.mark.unit

ASSISTANT_HI = (
    "क्या आप फिलहाल शुगर के लिए या ब्लड प्रेशर के लिए कोई दवाई ले रहे हैं"
)
ASSISTANT_EN = "Do you have any allergies to medicines or food"


@pytest.mark.parametrize(
    "heard",
    [
        "क्या आप फिलहाल शुगर के लिए",          # opening span
        "शुगर के लिए या ब्लड प्रेशर के लिए",     # middle span
        "कोई दवाई ले रहे हैं",                   # closing span
        "हैं",                                    # single stray word
    ],
)
def test_leaked_assistant_audio_is_discarded(heard):
    assert is_echo(heard, ASSISTANT_HI)


@pytest.mark.parametrize(
    "heard",
    [
        # Answers reuse the question's vocabulary heavily — this is the case a
        # bag-of-words comparison gets wrong, and why contiguity is used.
        "नहीं नहीं, कोई दवाई नहीं ले रहा, शुगर के लिए।",
        "हाँ, शुगर की दवाई लेता हूँ रोज सुबह।",
        "फिर से बोलिए, समझ नहीं आया।",
        "मेरे घुटने में कल रात से बहुत दर्द हो रहा है।",
        "हेलो आप हो?",
    ],
)
def test_genuine_patient_speech_is_kept(heard):
    assert not is_echo(heard, ASSISTANT_HI)


def test_english_behaves_the_same_way():
    assert is_echo("Do you have any allergies to medicines", ASSISTANT_EN)
    assert not is_echo("No I don't have any allergies", ASSISTANT_EN)


def test_nothing_spoken_means_nothing_to_echo():
    """With the assistant silent, patient speech must always pass."""
    for heard in ["ठीक है", "हाँ", "yes"]:
        assert not is_echo(heard, None)
        assert not is_echo(heard, "")


def test_empty_recognition_is_discarded():
    assert is_echo("", ASSISTANT_HI)
    assert is_echo("   ", ASSISTANT_HI)


def test_normalisation_ignores_punctuation_and_case():
    assert normalise("Kya AAP, theek—hain?") == "kya aap theek hain"
    assert normalise("ठीक है।") == "ठीक है"


def test_longest_common_run_measures_contiguity():
    assert longest_common_run("a b c d", "x a b c y") == 3
    assert longest_common_run("a x b x c", "a b c") == 1
    assert longest_common_run("", "a b") == 0
