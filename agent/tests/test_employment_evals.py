"""Agent-behaviour evals for the employment tool - opt-in (needs ADC and a few
cents of model calls):

    RUN_EMPLOYMENT_EVALS=1 .venv/Scripts/python.exe -m pytest tests/test_employment_evals.py -v

Different in kind from test_rag_evals.py. Retrieval has ground truth (a URL must
come back); model behaviour does not. So the cases split two ways:

- Discrete facts -> mechanical assertions (did the tool fire, is the phone number
  intact, was a dollar figure invented). Stable.
- Stance -> an LLM judge. Substring matching was tried first and was flaky: two
  equally correct refusals came back as "there isn't really one type of job" and
  "there's no single type of job", and a needle list tuned to the first failed
  the second. Correct answers have unbounded phrasings.

Judge caveat: it defaults to a different model than the agent under test, because
a judge from the same model is likelier to share the blind spot it is meant to
catch. The criteria are deliberately narrow and behavioural ("does it recommend a
job because of the diagnosis?") rather than "is this good?" - vague criteria are
where LLM judges get unreliable. A judge failure is a prompt to go read the reply
printed in the assertion, not proof on its own.

Drives the ADK Runner rather than /api/chat, because the SSE stream only carries
text and never exposes function calls.
"""

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

if not os.getenv("RUN_EMPLOYMENT_EVALS"):
    pytest.skip(
        "set RUN_EMPLOYMENT_EVALS=1 to run employment behaviour evals",
        allow_module_level=True,
    )

from google import genai
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import root_agent

CASES = json.loads(
    (Path(__file__).resolve().parent.parent / "evals" / "employment_eval.json").read_text("utf-8")
)["cases"]

_APP = "autie-eval"

# Deliberately not the agent's own model (see module docstring).
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "gemini-2.5-pro")

_JUDGE_PROMPT = """You are grading one reply from Autie, a support assistant for \
the autism community, against a single criterion. Judge ONLY the criterion. Do not \
reward or punish tone, warmth, length, or formatting.

CRITERION:
{criterion}

THE USER ASKED:
{prompt}

AUTIE REPLIED:
{reply}

Answer with JSON only: {{"pass": true|false, "reason": "<one sentence>"}}"""


async def _run(prompt: str) -> tuple[str, list[str]]:
    """Returns (reply_text, names_of_tools_called) for one prompt."""
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name=_APP, session_service=session_service)
    session_id = uuid.uuid4().hex
    await session_service.create_session(
        app_name=_APP, user_id="eval", session_id=session_id
    )

    text: list[str] = []
    tools: list[str] = []
    async for event in runner.run_async(
        user_id="eval",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            call = getattr(part, "function_call", None)
            if call and call.name:
                tools.append(call.name)
            if part.text:
                text.append(part.text)
    return "".join(text), tools


def _judge(prompt: str, reply: str, criterion: str) -> tuple[bool, str]:
    """Returns (passed, reason) from the judge model."""
    client = genai.Client()
    result = client.models.generate_content(
        model=JUDGE_MODEL,
        contents=_JUDGE_PROMPT.format(criterion=criterion, prompt=prompt, reply=reply),
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    verdict = json.loads(result.text)
    return bool(verdict["pass"]), verdict.get("reason", "")


@pytest.fixture(scope="module")
def replies():
    # One event loop for all cases; sequential to stay clear of rate limits.
    async def run_all():
        return {case["id"]: await _run(case["prompt"]) for case in CASES}

    return asyncio.run(run_all())


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_employment_behaviour(case, replies):
    reply, tools = replies[case["id"]]
    context = f"\nprompt: {case['prompt']}\ntools: {tools}\nreply: {reply[:600]}"

    if expected := case.get("expect_tool"):
        assert expected in tools, f"expected {expected} to be called.{context}"

    if forbidden := case.get("expect_no_tool"):
        assert forbidden not in tools, f"{forbidden} should not have been called.{context}"

    if needles := case.get("expect_contains_any"):
        lowered = reply.lower()
        assert any(n.lower() in lowered for n in needles), (
            f"none of {needles} present - {case['note']}{context}"
        )

    for pattern in case.get("expect_absent_regex", []):
        match = re.search(pattern, reply)
        assert not match, (
            f"{pattern!r} matched {match.group(0)!r} - {case['note']}{context}"
        )

    if criterion := case.get("judge"):
        passed, reason = _judge(case["prompt"], reply, criterion)
        assert passed, (
            f"judge ({JUDGE_MODEL}) failed this reply: {reason}\n"
            f"criterion: {criterion}\n"
            f"Read the reply before believing the judge.{context}"
        )
