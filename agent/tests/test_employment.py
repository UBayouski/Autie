"""Tests for the employment resources directory (no credentials needed).

The content tests are deliberately strict. This directory is served verbatim to
people acting on it, so a typo'd number or a dead entry is a real harm, and the
no-condition-matching rule (docs/employment.md) is the kind of principle that
erodes through well-meaning edits unless something fails loudly.
"""

import re

from app.tools.employment import EMPLOYMENT_RESOURCES, get_employment_resources


def test_tool_returns_the_directory_verbatim():
    assert get_employment_resources() is EMPLOYMENT_RESOURCES


def _all_entries():
    return EMPLOYMENT_RESOURCES["resources"] + EMPLOYMENT_RESOURCES["employer_programs"]


def test_every_resource_is_complete():
    for resource in _all_entries():
        assert resource["name"].strip()
        assert resource["contact"].strip()
        assert resource["note"].strip()
        assert resource["website"].startswith("https://")


def test_federal_programs_are_listed_first():
    # They are free, underused, and unknown to most people who qualify.
    names = [r["name"] for r in EMPLOYMENT_RESOURCES["resources"]]
    assert "Job Accommodation Network (JAN)" in names[:3]
    assert "State Vocational Rehabilitation agency" in names[:3]


def test_verified_contact_details_are_intact():
    """Pins the numbers checked against each source at build time."""
    by_name = {r["name"]: r for r in EMPLOYMENT_RESOURCES["resources"]}
    assert "800-526-7234" in by_name["Job Accommodation Network (JAN)"]["contact"]
    assert "1-866-968-7842" in by_name["Ticket to Work (Social Security)"]["contact"]
    assert "1-877-872-5627" in by_name["American Job Centers (CareerOneStop)"]["contact"]
    assert by_name["State Vocational Rehabilitation agency"]["website"] == (
        "https://rsa.ed.gov/about/states"
    )


def test_no_condition_is_mapped_to_a_kind_of_work():
    """Core principle: we never suggest a diagnosis implies a type of job.

    Guards against a future edit like "great for detail-oriented autistic
    candidates" or a `conditions: [...]` field appearing on an entry.
    """
    blob = str(EMPLOYMENT_RESOURCES).lower()
    for phrase in [
        "suitable for",
        "suited to",
        "good fit for",
        "ideal for",
        "well-suited",
        "best for people with",
        "recommended for",
    ]:
        assert phrase not in blob, f"condition->work framing leaked in: {phrase}"

    for resource in EMPLOYMENT_RESOURCES["resources"]:
        assert "conditions" not in resource
        assert "condition" not in resource


def test_employer_programs_are_separated_and_caveated():
    """Named companies must never read as an Autie endorsement."""
    note = EMPLOYMENT_RESOURCES["employer_programs_note"].lower()
    assert "not recommendations" in note or "not a recommendation" in note

    # Companies stay out of the free-services list.
    service_names = " ".join(r["name"] for r in EMPLOYMENT_RESOURCES["resources"])
    for company in ["Microsoft Neurodiversity Hiring", "SAP Autism at Work"]:
        assert company not in service_names

    # ...and the neutral federal directory is present to defer to.
    assert any(
        "askearn.org" in r["website"] for r in EMPLOYMENT_RESOURCES["resources"]
    ), "EARN directory must stay: it is the maintained list we point at"


def test_employer_programs_describe_process_not_claimed_traits():
    """Employer marketing ("neurodivergent people bring creative thinking")
    is principle 1's stereotype trap wearing a friendly hat. Describe the
    adjusted process instead.
    """
    blob = " ".join(
        p["note"] for p in EMPLOYMENT_RESOURCES["employer_programs"]
    ).lower()
    for phrase in [
        "innovative thinking",
        "creative solutions",
        "attention to detail",
        "pattern recognition",
        "strengths associated",
        "naturally good",
        "excel at",
    ]:
        assert phrase not in blob, f"employer trait-marketing leaked in: {phrase}"


def test_directory_does_not_push_disclosure():
    blob = str(EMPLOYMENT_RESOURCES).lower()
    for phrase in ["you should tell", "be sure to disclose", "always disclose"]:
        assert phrase not in blob


def test_no_placeholder_or_unverified_entries():
    blob = str(EMPLOYMENT_RESOURCES)
    for marker in ["TODO", "example.com", "TBD", "XXX", "FIXME"]:
        assert marker not in blob


def test_phone_numbers_are_plausible_us_numbers():
    contacts = " ".join(r["contact"] for r in EMPLOYMENT_RESOURCES["resources"])
    for number in re.findall(r"\b\d{3}-\d{3}-\d{4}\b|\b1-\d{3}-\d{3}-\d{4}\b", contacts):
        digits = number.replace("-", "").lstrip("1")
        assert len(digits) == 10, f"implausible US number: {number}"
