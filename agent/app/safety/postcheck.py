"""Lightweight output post-check: observe, don't block.

Regex cannot reliably judge medical advice, so blocking on it would mostly
punish legitimate answers ("many families discuss melatonin with their
pediatrician"). Instead we log a structured warning whenever a reply looks
like it contains dosing or prescriptive medication language, so drift in
model behavior shows up in Cloud Logging and can be reviewed - the hard
guardrails live in the instruction and Gemini safety settings.
"""

import logging
import re

logger = logging.getLogger("autie.safety")

_DOSING_RE = re.compile(
    r"\b\d+\s?(?:mg|mcg|ml)\b|\b(?:take|give|administer)\s+\d+\s?(?:pill|tablet|dose)",
    re.IGNORECASE,
)


def scan_reply(text: str, session_id: str) -> None:
    """Logs a warning when a model reply contains dosing-like language."""
    if text and _DOSING_RE.search(text):
        logger.warning(
            "postcheck: dosing-like language in reply session=%s", session_id
        )
