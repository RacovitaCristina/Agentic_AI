"""Extra offline tests for the code written in Lab 4 (no LLM calls). Run: pytest test_lab4_extra.py -v"""
from fractions import Fraction
from types import SimpleNamespace

import exp3_interview as ex3
from exp3_interview import InterviewTurn, TravelBrief, missing_required
from exp5_tools import sum_eur
from hw_a_vouchers import Operation, apply, check_expression
from hw_b_nights import run_tests, unsafe

FULL = dict(origin="Iasi", destination="open", dates="12-16 May", travelers=2, budget_eur=1000,
            interests=["street food", "history"])


# --- Experiment 3: the harness decides when the brief is complete -------------------------------
def fake_interviewer(monkeypatch, turns):
    """The 'model' returns the given turns in order; counts how often it was called."""
    calls = []

    def fake_ask(prompt, **kw):
        calls.append(prompt)
        return SimpleNamespace(parsed=turns[min(len(calls), len(turns)) - 1])
    monkeypatch.setattr(ex3, "ask", fake_ask)
    return calls


def test_missing_required_lists_empty_fields():
    assert missing_required(TravelBrief()) == ex3.REQUIRED
    assert missing_required(TravelBrief(**FULL)) == []
    assert missing_required(TravelBrief(**{**FULL, "origin": "", "interests": []})) == ["origin", "interests"]


def test_strict_needs_pace_avoid_and_a_day_number():
    brief = TravelBrief(**{**FULL, "dates": "May"})
    assert missing_required(brief) == []
    assert missing_required(brief, strict=True) == ["pace", "avoid", "dates"]


def test_interview_stops_when_the_harness_says_complete(monkeypatch):
    # The model still wants to ask something, but nothing required is missing: the harness stops.
    turns = [InterviewTurn(brief=TravelBrief(origin="Iasi"), next_question="Where to?"),
             InterviewTurn(brief=TravelBrief(**FULL), next_question="Anything else?")]
    calls = fake_interviewer(monkeypatch, turns)
    answers = []
    brief, asked = ex3.interview("hi", lambda t, q: answers.append(q) or "Rome")
    assert asked == 1 and answers == ["Where to?"] and len(calls) == 2
    assert brief.budget_eur == 1000


def test_empty_question_while_missing_falls_back_to_missing0(monkeypatch):
    turns = [InterviewTurn(brief=TravelBrief(**{**FULL, "budget_eur": None}), next_question=""),
             InterviewTurn(brief=TravelBrief(**FULL), next_question="")]
    fake_interviewer(monkeypatch, turns)
    asked_questions = []
    ex3.interview("hi", lambda t, q: asked_questions.append(q) or "1000 EUR")
    assert asked_questions == ["Could you specify your budget_eur?"]


def test_question_limit_is_respected_and_the_last_answer_is_read(monkeypatch):
    never_done = InterviewTurn(brief=TravelBrief(origin="Iasi"), next_question="And?")
    calls = fake_interviewer(monkeypatch, [never_done])
    answers = []
    brief, asked = ex3.interview("hi", lambda t, q: answers.append(q) or f"answer {len(answers)}")
    assert asked == ex3.MAX_QUESTIONS and len(answers) == ex3.MAX_QUESTIONS
    assert len(calls) == ex3.MAX_QUESTIONS + 1           # one last call reads the last answer
    assert f"answer {ex3.MAX_QUESTIONS}" in calls[-1]


# --- Experiment 5 / homework C: sum_eur is exact -------------------------------------------------
def test_sum_eur_is_exact():
    assert '"total_eur": "428"' in sum_eur([39, 167, 222])
    assert '"total_eur": "0.3"' in sum_eur([0.1, 0.2])


# --- Homework A: the exact checker and the code step of the search -------------------------------
def test_check_expression():
    assert check_expression("(10 - 4) * (13 - 9)", (4, 9, 10, 13))
    assert check_expression("5 * (5 - 1 / 5)", (1, 5, 5, 5))      # needs a fraction on the way
    assert not check_expression("(10 - 4) * (13 - 9) + 0", (4, 9, 10, 13))  # an extra number
    assert not check_expression("10 * 4 - 13 - 9", (4, 9, 10, 13))         # 18, not 24
    assert not check_expression("4 ** 2 + 9 - 10 + 9", (4, 9, 10, 13))    # power not allowed
    assert not check_expression("__import__('os')", (4, 9, 10, 13))        # never evaluated


def test_apply_computes_exactly_and_rejects_bad_operations():
    state = ([Fraction(1), Fraction(5), Fraction(5), Fraction(5)], ["1", "5", "5", "5"])
    numbers, exprs = apply(state, Operation(a="1", op="/", b="5"))
    assert sorted(numbers) == [Fraction(1, 5), 5, 5] and "(1 / 5)" in exprs
    assert apply(state, Operation(a="7", op="+", b="5")) is None   # 7 is not a voucher
    assert apply(state, Operation(a="1", op="+", b="1")) is None   # 1 used twice


# --- Homework B: safety check and the separate test process --------------------------------------
GOOD = """from datetime import date
def nights_between(check_in, check_out):
    a, b = date.fromisoformat(check_in), date.fromisoformat(check_out)
    if b < a:
        raise ValueError("check-out before check-in")
    return (b - a).days"""


def test_good_code_passes_and_bad_code_fails():
    assert run_tests(GOOD) == "ALL PASSED"
    no_raise = GOOD.replace('raise ValueError("check-out before check-in")', "pass")
    assert "expected raises" in run_tests(no_raise)


def test_unsafe_code_is_rejected_before_running():
    assert unsafe("import os\ndef nights_between(a, b): return 0")
    assert unsafe("def nights_between(a, b): return open('x').read()")
    assert unsafe("def nights_between(a, b): return ().__class__")
    assert unsafe(GOOD) is None


def test_an_endless_loop_times_out():
    assert run_tests("def nights_between(a, b):\n    while True: pass").startswith("TIMEOUT")
