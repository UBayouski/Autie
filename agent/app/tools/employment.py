"""Employment support resources - deterministic, curated, served verbatim.

Design and principles: docs/employment.md. The two that shape this file:

- We never map a condition to a kind of work. There is no condition field here
  and no "suitable for" framing anywhere; every entry is offered to everyone.
  Sorting people into job types by diagnosis is exactly what this project is
  not for.
- Every entry was verified reachable and had its phone/URL checked against the
  source before landing. A wrong number in a directory someone acts on is worse
  than no directory, so treat edits here like edits to crisis.py: verify first,
  never fill in from memory.

USA only, matching find_local_services and the crisis directory.
"""

# Served VERBATIM by get_employment_resources. Federal programs first: they are
# free, underused, and unknown to most people who qualify.
EMPLOYMENT_RESOURCES = {
    # Reads as a qualifier, not a lead-in: the model writes its own opening
    # sentence, and starting this with "Here are..." stacked two intros.
    "message": (
        "All of these are free, US-wide, and open to anyone who wants them - "
        "none are limited to a particular diagnosis. They cover finding work, "
        "asking for adjustments, and keeping benefits while you try."
    ),
    "resources": [
        {
            "name": "Job Accommodation Network (JAN)",
            "contact": "Call 800-526-7234",
            "website": "https://askjan.org/",
            "note": (
                "Free, confidential advice on workplace adjustments - what to "
                "ask for and how to ask. Funded by the US Department of Labor. "
                "Helps with interviews and current jobs, not just new ones."
            ),
        },
        {
            "name": "Ticket to Work (Social Security)",
            "contact": "Call 1-866-968-7842 (TTY 1-866-833-2967), Mon-Fri 8am-8pm ET",
            "website": "https://choosework.ssa.gov/",
            "note": (
                "Free career counselling and job support for people aged 18-64 "
                "who get SSDI or SSI. Built so you can try working without "
                "immediately losing benefits."
            ),
        },
        {
            "name": "State Vocational Rehabilitation agency",
            "contact": "Find your state's agency at the directory below",
            "website": "https://rsa.ed.gov/about/states",
            "note": (
                "Free federally funded help with training, job coaching, "
                "equipment and job placement. Every state has one (78 agencies "
                "in all). Widely available and widely unknown."
            ),
        },
        {
            "name": "American Job Centers (CareerOneStop)",
            "contact": "Call 1-877-872-5627 (TTY 1-877-889-5627)",
            "website": "https://www.careeronestop.org/LocalHelp/AmericanJobCenters/american-job-centers.aspx",
            "note": (
                "Free in-person help nearby: job search, workshops, computer "
                "access. US Department of Labor; help line covers 160+ languages."
            ),
        },
        {
            "name": "Hire Autism (Organization for Autism Research)",
            "contact": "Free account required to use the job board",
            "website": "https://www.hireautism.org/",
            "note": (
                "Job board for autistic job seekers, plus free one-to-one help "
                "from volunteer mentors with resumes, cover letters and "
                "interview practice."
            ),
        },
        {
            "name": "Autism Job Board",
            "contact": "Free account required to apply",
            "website": "https://autismjobboard.org/",
            "note": (
                "Job board for autistic and neurodiverse job seekers, run by "
                "the Autism Foundation of Oklahoma. Strongest in Oklahoma, and "
                "lists remote roles open across the USA."
            ),
        },
        {
            "name": "EARN — employers with neurodiversity hiring programs",
            "contact": "Online directory",
            "website": "https://askearn.org/page/neurodiversity-hiring-initiatives-and-partnerships",
            "note": (
                "A list of employers running neurodiversity hiring programs, "
                "kept by the Employer Assistance and Resource Network (funded "
                "by the US Department of Labor). Includes Microsoft, SAP, "
                "JPMorgan Chase, DXC, Freddie Mac, KeyBank and the Department "
                "of Defense."
            ),
        },
    ],
    # Kept separate from `resources` on purpose. These are individual companies,
    # not free services open to everyone, and Autie naming a couple of them is
    # not a recommendation - the EARN directory above is the maintained list and
    # is who we defer to. Describe what the PROCESS offers (an adjusted
    # interview), never what traits the employer claims neurodivergent people
    # have; that marketing language is the stereotype trap in principle 1.
    "employer_programs_note": (
        "Some employers run their own neurodiversity hiring programs, usually "
        "with an adjusted interview process instead of a standard interview. "
        "These two are examples, not recommendations - the EARN directory "
        "lists more, and a program existing says nothing about whether a "
        "particular employer is right for you."
    ),
    "employer_programs": [
        {
            "name": "Microsoft Neurodiversity Hiring Program",
            "contact": "Search the Microsoft careers site for \"Neurodiversity\"",
            "website": "https://careers.microsoft.com/v2/global/en/neurodiversity.html",
            "note": (
                "Extended hiring process with preparation activities and time "
                "to get to know the team, in place of a conventional "
                "interview. No separate application - roles are on the normal "
                "careers site. Microsoft also runs regular webinars explaining "
                "the process."
            ),
        },
        {
            "name": "SAP Autism at Work",
            "contact": "General program application, not a specific job posting",
            "website": "https://jobs.sap.com/content/Autism-at-Work/",
            "note": (
                "Apply to the program rather than to a single role; SAP then "
                "supports you through finding and applying for positions. Runs "
                "in 12 countries including the USA."
            ),
        },
    ],
}


def get_employment_resources() -> dict:
    """Returns free USA employment-support services for neurodivergent people.

    Use this when the conversation turns to work: looking for a job, job
    hunting while autistic or ADHD, asking an employer for adjustments or
    accommodations, disclosing a diagnosis at work, interview difficulties,
    losing a job, or working while on disability benefits. Useful for the
    person themselves and for a caregiver asking on someone's behalf.

    Present the returned entries EXACTLY as given - never change names, phone
    numbers or URLs, and never add services that are not in the list.

    Do NOT suggest that any kind of work suits someone because of their
    diagnosis, and do not ask the user what condition they have in order to
    use this tool. These resources are open to everyone. If the user asks
    whether to tell an employer about a diagnosis, lay out the trade-offs
    honestly and leave the decision to them - it is theirs alone.

    "employer_programs" lists a couple of named companies. Mention them only
    if the user asks about specific employers or where to apply, always with
    the caveat in "employer_programs_note", and never as Autie recommending
    an employer. Lead with "resources" - those are free and open to anyone.

    Returns:
        dict with "message" (a lead-in), "resources" (name, contact, website,
        note for each free service), "employer_programs_note" (a caveat that
        must accompany the list), and "employer_programs" (example employers
        running their own neurodiversity hiring programs).
    """
    return EMPLOYMENT_RESOURCES
