"""Tests for the deterministic safety layer."""

import os

os.environ["AUTH_DISABLED"] = "true"
os.environ["SESSIONS_BACKEND"] = "memory"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.safety.crisis import CRISIS_RESOURCES, detect_crisis
from app.safety.postcheck import _DOSING_RE

client = TestClient(app)


@pytest.mark.parametrize("text", [
    "I want to kill myself",
    "sometimes I think about suicide",
    "I've been cutting myself",
    "I'm so tired I just want to die",
    "honestly my family would be better off dead without me",
    "I'm afraid I might hurt my son when he melts down",
    "my daughter cuts herself",
    "I took an overdose once",
    "I don't want to go on",
])
def test_detect_crisis_positives(text):
    assert detect_crisis(text) is True


@pytest.mark.parametrize("text", [
    "Where do I find a speech therapist?",
    "My son had a meltdown at school today",
    "This paperwork is killing me",  # idiom, no first-person harm
    "He hurt his knee at the playground",
    "What is an IEP?",
    "I'm exhausted and overwhelmed",
])
def test_detect_crisis_negatives(text):
    assert detect_crisis(text) is False


def test_crisis_resources_contact_988_present():
    contacts = [r["contact"] for r in CRISIS_RESOURCES["resources"]]
    assert any("988" in c for c in contacts)
    assert any("741741" in c for c in contacts)


def test_chat_emits_crisis_event_before_model_reply():
    with client.stream(
        "POST", "/api/chat", json={"message": "I can't do this anymore, I want to die"}
    ) as response:
        body = "".join(response.iter_text())
    session_pos = body.find('"type": "session"')
    crisis_pos = body.find('"type": "crisis_resources"')
    assert crisis_pos != -1, "crisis event missing"
    assert session_pos < crisis_pos
    assert "988" in body


def test_chat_no_crisis_event_for_normal_message():
    with client.stream(
        "POST", "/api/chat", json={"message": "what is an IEP?"}
    ) as response:
        body = "".join(response.iter_text())
    assert '"type": "crisis_resources"' not in body


def test_postcheck_dosing_pattern():
    assert _DOSING_RE.search("give him 3 mg of melatonin")
    assert _DOSING_RE.search("take 2 pills at bedtime")
    assert not _DOSING_RE.search("talk to your pediatrician about sleep")
