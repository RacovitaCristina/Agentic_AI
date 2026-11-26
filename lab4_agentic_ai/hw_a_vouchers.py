"""Lab 4 - Homework A: the voucher puzzle. Pay a EUR 24 bill exactly with four vouchers,
combining their values with + - * / and parentheses, each voucher exactly once.

    python hw_a_vouchers.py             # both puzzles: ask directly 5 times, then search once
    python hw_a_vouchers.py --runs 2    # repeat the search 2 times per puzzle
"""
import ast
import operator
import re
import sys
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel

from llm import ask

TARGET = 24
PUZZLES = [(4, 9, 10, 13), (1, 5, 5, 5)]
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
SYMBOLS = {"+": operator.add, "-": operator.sub, "*": operator.mul, "/": operator.truediv}
SCORE = {"sure": 20, "likely": 1, "impossible": 0.001}  # the value scale of Tree of Thoughts

STATS = {"calls": 0, "in": 0, "out": 0}


def call(prompt: str, **kw):
    """ask() + counting, so both strategies are measured the same way."""
    r = ask(prompt, **kw)
    STATS["calls"] += 1
    STATS["in"] += r.in_tokens
    STATS["out"] += r.out_tokens
    return r


def check_expression(expr: str, vouchers) -> bool:
    """Exact check: only numbers, + - * / and parentheses, every voucher exactly once, value 24. Never eval()."""
    used = []

    def walk(node):
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.Constant) and type(node.value) is int:
            used.append(node.value)
            return Fraction(node.value)
        raise ValueError("not allowed")  # unary minus, powers, names, calls, floats ...

    try:
        value = walk(ast.parse(expr.replace("×", "*").replace("÷", "/"), mode="eval").body)
    except (ValueError, SyntaxError, ZeroDivisionError):
        return False
    return sorted(used) == sorted(vouchers) and value == TARGET


def fmt(numbers) -> str:
    return ", ".join(str(n) for n in numbers)  # Fraction(24, 5) prints as 24/5


# --- Strategy 1: ask directly ---------------------------------------------------------------
def direct_prompt(vouchers) -> str:
    return (f"You hold four vouchers worth {fmt(vouchers)} EUR. Combine all four values, each exactly once, "
            f"using only + - * / and parentheses, so that the result is exactly {TARGET}. "
            "End your reply with one line: Expression: <expression>")


def direct(vouchers, n: int = 5) -> None:
    STATS.update({"calls": 0, "in": 0, "out": 0})
    correct = 0
    for _ in range(n):
        text = call(direct_prompt(vouchers), temperature=0.7).text.replace("**", "").replace("`", "")
        found = re.findall(r"Expression:\s*(.+)", text)
        expr = found[-1].split("=")[0].strip() if found else ""
        ok = check_expression(expr, vouchers)
        correct += ok
        print(f"   {'OK   ' if ok else 'WRONG'} {expr or '(no expression line)'}")
    print(f"== direct {vouchers}: {correct}/{n} correct, {STATS['calls']} calls, "
          f"{STATS['in']} input + {STATS['out']} output tokens")


# --- Strategy 2: search (propose -> compute in code -> value -> keep the best 3) ---------------
class Operation(BaseModel):
    a: str
    op: Literal["+", "-", "*", "/"]
    b: str


class Proposals(BaseModel):
    operations: list[Operation]


class Value(BaseModel):
    reason: str
    verdict: Literal["sure", "likely", "impossible"]


def propose(numbers: list[Fraction]) -> list[Operation]:
    """The MODEL proposes 3 next operations."""
    r = call(f"Numbers left: {fmt(numbers)}. Goal: reach exactly {TARGET} using every number exactly once "
             "with + - * / and parentheses. Propose exactly 3 different promising next operations: pick two "
             "of the numbers and one operator. Write the numbers exactly as listed (a fraction as 24/5).",
             schema=Proposals)
    return r.parsed.operations[:3] if r.parsed else []


def apply(state, operation: Operation):
    """The CODE computes the new state exactly, or returns None if the operation is not allowed."""
    numbers, exprs = list(state[0]), list(state[1])
    try:
        a, b = Fraction(operation.a.strip()), Fraction(operation.b.strip())
        i = numbers.index(a)  # ValueError if a is not one of the numbers left
        numbers.pop(i)
        ea = exprs.pop(i)
        j = numbers.index(b)  # b must be ANOTHER number left (a is already removed)
        numbers.pop(j)
        eb = exprs.pop(j)
        result = SYMBOLS[operation.op](a, b)
    except (ValueError, ZeroDivisionError):  # a number that is not in the state, or a division by zero
        return None
    return numbers + [result], exprs + [f"({ea} {operation.op} {eb})"]


def value(numbers: list[Fraction]) -> str:
    """The MODEL rates a state: can these numbers still reach 24?"""
    r = call(f"Numbers: {fmt(numbers)}. Can they reach exactly {TARGET} using every number exactly once "
             "with + - * / and parentheses? Think briefly, then answer sure, likely or impossible.",
             schema=Value)
    return r.parsed.verdict if r.parsed else "impossible"


def solvable(numbers) -> bool:
    """DIAGNOSIS ONLY (never used to choose a state): an exhaustive check, to tell afterwards
    whether a failure came from propose (no good child) or from value (a good child was dropped)."""
    if len(numbers) == 1:
        return numbers[0] == TARGET
    for i in range(len(numbers)):
        for j in range(len(numbers)):
            if i != j:
                rest = [n for k, n in enumerate(numbers) if k not in (i, j)]
                for f in SYMBOLS.values():
                    try:
                        if solvable(rest + [f(numbers[i], numbers[j])]):
                            return True
                    except ZeroDivisionError:
                        pass
    return False


def search(vouchers) -> str | None:
    STATS.update({"calls": 0, "in": 0, "out": 0})
    frontier = [([Fraction(v) for v in vouchers], [str(v) for v in vouchers])]
    for step in range(1, 4):  # three steps: 4 numbers -> 3 -> 2 -> 1
        candidates, seen = [], set()
        for state in frontier:
            for operation in propose(state[0]):
                new = apply(state, operation)
                if new and tuple(sorted(new[0])) not in seen:
                    seen.add(tuple(sorted(new[0])))
                    candidates.append(new)
        if step < 3:  # states with 2+ numbers: the model rates them
            rated = [(SCORE[value(c[0])], c) for c in candidates]
        else:  # one number left: the code knows exactly whether it is 24
            rated = [(1.0 if c[0][0] == TARGET else 0.0, c) for c in candidates]
        rated.sort(key=lambda x: -x[0])
        frontier = [c for _, c in rated[:3]]
        good = sum(solvable(c[0]) for c in candidates)
        kept = sum(solvable(c[0]) for c in frontier)
        print(f"   step {step}: {len(candidates)} new states ({good} still solvable), "
              f"kept {len(frontier)} ({kept} still solvable): " + " | ".join(fmt(c[0]) for c in frontier))
    for numbers, exprs in frontier:
        if numbers[0] == TARGET and check_expression(exprs[0], vouchers):
            return exprs[0]
    return None


if __name__ == "__main__":
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 1
    for vouchers in PUZZLES:
        print(f"\n##### vouchers {vouchers} -> EUR {TARGET}")
        direct(vouchers)
        for _ in range(runs):
            answer = search(vouchers)
            print(f"== search {vouchers}: {answer or 'no solution'}, {STATS['calls']} calls, "
                  f"{STATS['in']} input + {STATS['out']} output tokens")
