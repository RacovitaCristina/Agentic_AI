"""Lab 4 - Experiment 3: ask before you plan (STARTER).

    python exp3_interview.py              # you answer the questions
    python exp3_interview.py --vague      # step A: what happens when nobody asks
    python exp3_interview.py --simulate   # a simulated traveler with a hidden profile answers
    python exp3_interview.py --simulate --strict   # stretch: pace and avoid required, dates need a day number
"""
import re
import sys
from typing import Literal

from pydantic import BaseModel, Field

from llm import ask

FIRST_MESSAGE = "Plan me a nice 4-day trip in May."
MAX_QUESTIONS = 8


class TravelBrief(BaseModel):
    origin: str | None = Field(None, description="City the trip starts from")
    destination: str | None = Field(None, description="City or region, or 'open' if the traveler wants suggestions")
    dates: str | None = Field(None, description="Arrival and departure dates, e.g. '12-16 May'")
    travelers: int | None = Field(None, description="How many people travel")
    budget_eur: int | None = Field(None, description="Total budget for the whole trip, in EUR")
    interests: list[str] = Field(default_factory=list, description="What they enjoy doing")
    pace: Literal["relaxed", "balanced", "packed"] | None = None
    avoid: list[str] = Field(default_factory=list, description="Things they do not want")


class InterviewTurn(BaseModel):
    brief: TravelBrief = Field(description="Everything learned so far; unknown fields stay null")
    next_question: str = Field(description="ONE short question about the most important unknown, or '' when done")


REQUIRED = ["origin", "destination", "dates", "travelers", "budget_eur", "interests"]
STRICT_REQUIRED = REQUIRED + ["pace", "avoid"]  # stretch

# The interviewer must NOT plan, must NOT guess or invent defaults, must fill the brief only with what
# the traveler said, and must ask ONE question at a time (empty next_question when nothing is missing).
INTERVIEWER = (
    "You are a travel interviewer, not a trip planner. "
    "Do not generate an itinerary yet. "
    "Extract only information explicitly provided by the traveler. "
    "Do not invent facts, assumptions or default values. "
    "Keep unknown fields empty. "
    "Preserve all previously collected information. "
    "Ask exactly one short question about the most important "
    "missing required field at a time. "
    "The required fields are origin, destination, dates, "
    "travelers, budget_eur and interests. "
    "If all required fields are complete, return an empty next_question."
)
# Stretch: the same interviewer, told about the stricter rules.
STRICT_EXTRA = (
    " Also required: pace (relaxed, balanced or packed) and avoid (things the traveler does not want; "
    "write ['nothing'] if they say there is nothing to avoid). "
    "dates must contain exact day numbers, e.g. '12-16 May', not just a month."
)


def missing_required(brief: TravelBrief, strict: bool = False) -> list[str]:
    """The harness decides when the brief is complete, not the model."""
    missing = []

    for field in (STRICT_REQUIRED if strict else REQUIRED):
        value = getattr(brief, field)

        if value is None or value == "" or value == []:
            missing.append(field)

    # Stretch: "May" is not enough to book a flight - the dates need a day number.
    if strict and brief.dates and not re.search(r"\d", brief.dates):
        missing.append("dates")

    return missing


# --- A simulated traveler for hands-free testing ---------------------------
PERSONA = (
    "You are Ana, a student from Iasi. Hidden facts about your trip: 2 people (you and a friend), "
    "12-16 May, total budget 1000 EUR, you love street food and old history, you hate early mornings, "
    "you have no destination in mind and want a suggestion in Italy. "
    "Answer ONLY the question asked, in one short sentence, like a real person would. Never volunteer extra facts."
)


def simulated_answer(transcript: str, question: str) -> str:
    return ask(f"Conversation so far:\n{transcript}\nThe planner asks: {question}\nYour reply:",
               system=PERSONA, temperature=0.7).text.strip()


def interview(first_message: str, answer_fn, strict: bool = False) -> tuple[TravelBrief, int]:
    transcript = f"Traveler: {first_message}"
    brief = TravelBrief()
    system = INTERVIEWER + STRICT_EXTRA if strict else INTERVIEWER

    # MAX_QUESTIONS + 1 model calls: the last call only reads the answer to the last question.
    for asked in range(MAX_QUESTIONS + 1):
        turn: InterviewTurn = ask(
            f"Conversation so far:\n{transcript}",
            system=system,
            schema=InterviewTurn
        ).parsed

        brief = turn.brief
        missing = missing_required(brief, strict)

        # The HARNESS decides: stop when nothing is missing (whatever next_question says)
        # or when the question budget is used up.
        if not missing or asked == MAX_QUESTIONS:
            return brief, asked

        question = turn.next_question.strip()

        if not question:
            question = f"Could you specify your {missing[0]}?"

        print(f"\n[Planner] {question}")

        reply = answer_fn(transcript, question)

        print(f"[Traveler] {reply}")

        transcript += f"\nPlanner: {question}\nTraveler: {reply}"

    return brief, MAX_QUESTIONS  # not reached: the loop returns at asked == MAX_QUESTIONS


if __name__ == "__main__":
    if "--vague" in sys.argv:
        print(ask(FIRST_MESSAGE).text)
        sys.exit()
    answer_fn = simulated_answer if "--simulate" in sys.argv else (lambda _t, _q: input("> ").strip())
    strict = "--strict" in sys.argv
    print(f"[Traveler] {FIRST_MESSAGE}")
    brief, questions = interview(FIRST_MESSAGE, answer_fn, strict)
    print(f"\n[Brief after {questions} questions] missing: {missing_required(brief, strict) or 'nothing'}")
    print(brief.model_dump_json(indent=2))
