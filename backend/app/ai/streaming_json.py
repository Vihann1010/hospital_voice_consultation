"""Streams the value of a leading JSON string field out of a token stream.

The Conversation AI replies in structured JSON with `"utterance"` as the first
key. This extractor lets speech synthesis begin the moment characters of that
value arrive — structured output and low latency at the same time.

If the model ignores the JSON contract (first non-space char isn't '{'), the
extractor degrades to passthrough so the patient still hears a reply — but only
if what the model produced actually looks like speech. A model that narrates its
own reasoning ("Setting `topics_addressed`: [\"pain_location\"]...") must never
have that read aloud to a patient, so passthrough is abandoned the moment
machine-facing syntax appears and nothing further is spoken.
"""
import re
from typing import Optional

_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}

# Syntax a person never says out loud. If any of this appears while running in
# passthrough, the model is describing its output rather than speaking to the
# patient, and the whole turn is discarded.
_MACHINE_SYNTAX = re.compile(
    r"[{}\[\]`]"
    r'|"\s*:'
    r"|\b(?:utterance|language|phase|topics_addressed|conversation_complete"
    r"|handoff_note|true|false|null)\b",
    re.IGNORECASE,
)


class UtteranceStreamExtractor:
    def __init__(self, field: str = "utterance") -> None:
        self._needle = f'"{field}"'
        self.raw = ""          # complete raw model output (for final JSON parse)
        self._pos = 0          # scan cursor into raw
        self._state = "detect"  # detect|seek|colon|open|value|done|passthrough
        self._escape = False
        self._unicode: Optional[str] = None

    @property
    def passthrough(self) -> bool:
        return self._state == "passthrough"

    @property
    def suppressed(self) -> bool:
        """True when the model was narrating its output rather than speaking.
        The turn produced no utterance and should be treated as silence."""
        return self._state == "suppressed"

    def finish(self) -> str:
        """Text held back during streaming, once the turn is complete.

        Only passthrough buffers; the JSON path has already streamed. Returns
        "" when machine syntax was found anywhere in the output — better the
        patient hears nothing than hears JSON field names.
        """
        if self._state != "passthrough":
            return ""
        text = self.raw.strip()
        if not text or _MACHINE_SYNTAX.search(text):
            self._state = "suppressed"
            return ""
        self._state = "done"
        return text

    def feed(self, delta: str) -> str:
        """Consume a stream delta, return decoded utterance characters (may be '')."""
        self.raw += delta
        out: list[str] = []

        if self._state == "detect":
            stripped = self.raw.lstrip()
            if not stripped:
                return ""
            if stripped[0] == "{":
                self._state = "seek"
            else:
                self._state = "passthrough"
                return ""

        if self._state == "suppressed":
            return ""

        if self._state == "passthrough":
            # Passthrough buffers rather than streams: machine syntax can
            # appear at any point, and speech already sent to synthesis cannot
            # be unsaid. Released by finish() once the turn is judged. This
            # costs latency only on the abnormal path — well-formed JSON still
            # streams word by word.
            return ""

        if self._state == "seek":
            idx = self.raw.find(self._needle, self._pos)
            if idx == -1:
                # keep cursor just behind the tail so a needle split across
                # deltas is still found on the next feed
                self._pos = max(self._pos, len(self.raw) - len(self._needle))
                return ""
            self._pos = idx + len(self._needle)
            self._state = "colon"

        while self._pos < len(self.raw):
            ch = self.raw[self._pos]

            if self._state == "colon":
                self._pos += 1
                if ch in " \t\r\n":
                    continue
                if ch == ":":
                    self._state = "open"
                    continue
                self._state = "done"  # malformed; stop extracting
                break

            if self._state == "open":
                self._pos += 1
                if ch in " \t\r\n":
                    continue
                if ch == '"':
                    self._state = "value"
                    continue
                self._state = "done"
                break

            if self._state == "value":
                self._pos += 1
                if self._unicode is not None:
                    self._unicode += ch
                    if len(self._unicode) == 4:
                        try:
                            out.append(chr(int(self._unicode, 16)))
                        except ValueError:
                            pass
                        self._unicode = None
                    continue
                if self._escape:
                    self._escape = False
                    if ch == "u":
                        self._unicode = ""
                    else:
                        out.append(_ESCAPES.get(ch, ch))
                    continue
                if ch == "\\":
                    self._escape = True
                    continue
                if ch == '"':
                    self._state = "done"
                    break
                out.append(ch)
                continue

            break  # done

        return "".join(out)
