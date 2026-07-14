"""Crisis resources as an agent tool - content is deterministic and verbatim."""

from ..safety.crisis import CRISIS_RESOURCES


def get_crisis_resources() -> dict:
    """Returns crisis support hotlines for the USA.

    Use this whenever the conversation touches on suicide, self-harm, harm to
    a child, or a caregiver at a breaking point. Present the returned contacts
    EXACTLY as given - never change, shorten, or paraphrase names or numbers.

    Returns:
        dict with "message" (a supportive lead-in) and "resources" (name,
        contact, note for each hotline).
    """
    return CRISIS_RESOURCES
