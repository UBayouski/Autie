"""Deterministic crisis detection and resources (docs/architecture.md §3).

This is a guard around the agent, not a prompt: when a message trips the
detector, the API emits the resources to the client BEFORE and regardless of
whatever the model says. The resource text is served verbatim - never
paraphrased by the LLM.

Tuning stance: for this audience we prefer false positives (a stressed parent
sees a supportive resources card they didn't need) over false negatives. The
card is additive - it never blocks the conversation.
"""

import re

# Word-boundary, case-insensitive. Grouped by concern.
_CRISIS_PATTERNS = [
    # Suicidality / self-harm (first person)
    r"suicid\w*",
    r"kill(?:ing)?\s+myself",
    r"end(?:ing)?\s+my\s+life",
    r"take\s+my\s+(?:own\s+)?life",
    r"(?:want|wanna|wish)\s+to\s+(?:die|be\s+dead)",
    r"don'?t\s+want\s+to\s+(?:live|be\s+alive|go\s+on)",
    r"better\s+off\s+dead",
    r"no\s+reason\s+to\s+live",
    r"(?:hurt(?:ing)?|harm(?:ing)?|cut(?:ting)?)\s+myself",
    r"self[\s-]?harm\w*",
    r"overdos\w*",
    # Risk of harming a child (caregiver crisis)
    r"(?:hurt(?:ing)?|harm(?:ing)?|hit(?:ting)?|shak(?:e|ing))\s+(?:my|the)\s+(?:child|kid|son|daughter|baby)",
    r"afraid\s+(?:i|i'?m going to|i might)\s+(?:hurt|harm)",
    # Child in danger (self-harm by the child)
    r"(?:my\s+)?(?:child|kid|son|daughter)\s+(?:is\s+)?(?:hurt(?:s|ing)?|harm(?:s|ing)?|cut(?:s|ting)?)\s+(?:him|her|them)sel(?:f|ves)",
]

_CRISIS_RE = re.compile(
    r"\b(?:" + "|".join(_CRISIS_PATTERNS) + r")\b", re.IGNORECASE
)

# Served VERBATIM to the client and by the get_crisis_resources tool.
CRISIS_RESOURCES = {
    "message": (
        "It sounds like things are really hard right now. You don't have to "
        "go through this alone - these people are available right now, 24/7, "
        "and they want to help:"
    ),
    "resources": [
        {
            "name": "988 Suicide & Crisis Lifeline",
            "contact": "Call or text 988",
            "note": "24/7, free, confidential",
        },
        {
            "name": "Crisis Text Line",
            "contact": "Text HOME to 741741",
            "note": "24/7 text support",
        },
        {
            "name": "Autism Society National Helpline",
            "contact": "Call 800-328-8476",
            "note": "Autism-specific information and referrals (business hours)",
        },
        {
            "name": "Emergency",
            "contact": "Call 911",
            "note": "If you or someone else is in immediate danger",
        },
    ],
}


def detect_crisis(text: str) -> bool:
    """True when the message shows signals of crisis or risk of harm."""
    return bool(_CRISIS_RE.search(text))
