"""Detecting the assistant's own voice coming back through the microphone.

The microphone streams to speech recognition continuously, including while the
assistant is talking — that is what makes interruption possible. On a laptop or
tablet using its own speakers, some of the assistant's audio inevitably leaks
back into the microphone. Browser echo cancellation reduces this but does not
remove it.

Left unhandled, recognition transcribes that leakage as if the patient had
spoken, which cancels the reply mid-sentence and files the assistant's own
words as a patient turn. The patient hears a sentence stop halfway and says
"say that again" — and the same thing happens to the next reply.

These helpers compare an incoming transcript against what the assistant is
currently saying. A confident match is discarded entirely rather than merely
ignored for interruption, so it never reaches the transcript or the medical
record either.
"""
import re
from typing import Optional

# Devanagari and Latin letters, digits and spaces; everything else is noise for
# comparison purposes (punctuation differs between TTS input and STT output).
_KEEP = re.compile(r"[^\w\u0900-\u097F\s]", re.UNICODE)

# Devanagari punctuation lives inside that block, so it survives the filter
# above and has to be removed separately: danda, double danda and the
# abbreviation sign. Synthesis emits them and recognition usually does not,
# which would otherwise make the last word of every sentence fail to match.
_DEVANAGARI_PUNCTUATION = re.compile(r"[\u0964\u0965\u0970]")


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    cleaned = _DEVANAGARI_PUNCTUATION.sub(" ", (text or "").lower())
    cleaned = _KEEP.sub(" ", cleaned)
    return " ".join(cleaned.split())


def longest_common_run(a: str, b: str) -> int:
    """Length, in words, of the longest run of words `a` and `b` share in order.

    Contiguity is what separates echo from a natural reply. Recognition of
    leaked audio reproduces a continuous span of the assistant's sentence,
    whereas a patient answering a question reuses its vocabulary scattered
    among new words — "no no, not taking any medicine, for sugar" borrows
    heavily from "are you taking any medicine for sugar" without ever
    reproducing a long stretch of it.
    """
    words_a = a.split()
    words_b = b.split()
    if not words_a or not words_b:
        return 0
    previous = [0] * (len(words_b) + 1)
    best = 0
    for i in range(1, len(words_a) + 1):
        current = [0] * (len(words_b) + 1)
        for j in range(1, len(words_b) + 1):
            if words_a[i - 1] == words_b[j - 1]:
                current[j] = previous[j - 1] + 1
                if current[j] > best:
                    best = current[j]
        previous = current
    return best


def is_echo(
    utterance: str,
    assistant_text: Optional[str],
    *,
    min_length: int = 4,
    run_ratio: float = 0.6,
    min_run_words: int = 3,
) -> bool:
    """True when `utterance` is probably the assistant's own speech.

    `assistant_text` is what the assistant is currently saying, or said in the
    last moment or two. With nothing being spoken there is no echo to detect,
    so this must only be consulted while the assistant has the floor.
    """
    heard = normalise(utterance)
    if not heard:
        return True  # nothing usable; certainly not worth interrupting for

    spoken = normalise(assistant_text or "")
    if not spoken:
        return False

    # A very short fragment picked up while the assistant is talking is far
    # more likely to be leakage than a real interruption.
    if len(heard) < min_length:
        return True

    # Recognition rarely returns the assistant's sentence verbatim; it usually
    # captures a contiguous piece of it.
    if heard in spoken or spoken in heard:
        return True

    # Otherwise: does most of what was heard appear as one continuous run of
    # the assistant's words? A reply that merely reuses the question's
    # vocabulary will not.
    heard_words = heard.split()
    run = longest_common_run(heard, spoken)
    if run < min_run_words:
        return False
    return run / len(heard_words) >= run_ratio
