"""Lab 4 - Homework B: learn from a failed test.
The model writes nights_between(check_in, check_out) -> int; our own tests check it in a separate process.

    python hw_b_nights.py              # 5 runs of each strategy: plain retries vs retries with lessons
    python hw_b_nights.py --runs 3
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile

from llm import ask

TASK = ("Write a Python function nights_between(check_in: str, check_out: str) -> int that returns the number "
        "of hotel nights between two dates given as YYYY-MM-DD. Reply with only the code in one ```python block.")
MAX_ATTEMPTS = 3

# Our own cases: (check_in, check_out) -> expected nights, or "raises"
TESTS = [
    (("2027-05-12", "2027-05-12"), 0),         # same day
    (("2027-01-30", "2027-02-02"), 3),         # across a month end
    (("2027-12-30", "2028-01-02"), 3),         # across a year end
    (("2028-02-28", "2028-03-01"), 2),         # leap year: 29 February exists
    (("2027-02-28", "2027-03-01"), 1),         # not a leap year
    (("2027-05-16", "2027-05-12"), "raises"),  # check-out before check-in
    (("12/05/2027", "2027-05-16"), "raises"),  # badly formatted date
    (("2027-02-30", "2027-03-02"), "raises"),  # a date that does not exist
]

# Runs in the child process, after the generated code.
RUNNER = """
import json, sys
failures = []
for args, expected in json.loads(sys.argv[1]):
    try:
        got = nights_between(*args)
    except Exception as e:
        ok, got = expected == "raises", f"raised {type(e).__name__}: {e}"
    else:
        ok = expected != "raises" and type(got) is int and got == expected
    if not ok:
        failures.append(f"nights_between{tuple(args)}: expected {expected}, got {got!r}")
print("\\n".join(failures) or "ALL PASSED")
"""

ALLOWED_IMPORTS = {"datetime", "re"}
FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "globals", "locals", "vars",
                   "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "help"}


def unsafe(code: str) -> str | None:
    """Static check BEFORE running: only the imports this problem needs, no files, network or introspection."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            names = []
        if any(n not in ALLOWED_IMPORTS for n in names):
            return f"import not allowed: {names}"
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            return f"name not allowed: {node.id}"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return f"attribute not allowed: {node.attr}"
    return None


def run_tests(code: str) -> str:
    """Run the generated code + our tests in a SEPARATE process, with a timeout and an empty environment."""
    problem = unsafe(code)
    if problem:
        return f"REJECTED before running: {problem}"
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "candidate.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code + "\n" + RUNNER)
        try:
            done = subprocess.run(
                [sys.executable, "-I", path, json.dumps(TESTS)],  # -I: isolated mode, no user site, no PYTHON* vars
                cwd=folder, capture_output=True, text=True, timeout=10,
                env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},  # no GEMINI_API_KEY in the child
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT after 10 s"
    return (done.stdout + done.stderr).strip()[-1500:]


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def attempt(prompt: str, tokens: list[int]) -> tuple[str, str]:
    r = ask(prompt, temperature=0.7)
    tokens[0] += r.in_tokens + r.out_tokens
    code = extract_code(r.text)
    return code, run_tests(code)


def plain(tokens: list[int]) -> int | None:
    """Plain retries: the same prompt again, nothing learned."""
    for n in range(1, MAX_ATTEMPTS + 1):
        _, output = attempt(TASK, tokens)
        print(f"     attempt {n}: {output.splitlines()[0][:110]}")
        if output == "ALL PASSED":
            return n
    return None


def with_lessons(tokens: list[int]) -> int | None:
    """On failure, show the test output, ask why it failed, keep every lesson for the next prompt."""
    lessons: list[str] = []
    for n in range(1, MAX_ATTEMPTS + 1):
        prompt = TASK
        if lessons:
            prompt += "\nLessons from your earlier attempts:\n" + "\n".join(f"- {x}" for x in lessons)
        code, output = attempt(prompt, tokens)
        print(f"     attempt {n}: {output.splitlines()[0][:110]}")
        if output == "ALL PASSED":
            return n
        if n < MAX_ATTEMPTS:  # a lesson is only useful if there is a next attempt
            r = ask(f"{TASK}\n\nYour code:\n```python\n{code}\n```\n\nOur test output:\n{output}\n\n"
                    "Why did it fail, and what will you change? Two sentences.", temperature=0.7)
            tokens[0] += r.in_tokens + r.out_tokens
            lessons.append(" ".join(r.text.split()))
            print(f"       lesson: {lessons[-1][:300]}")
    return None


if __name__ == "__main__":
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 5
    for name, strategy in [("plain retries", plain), ("with lessons", with_lessons)]:
        print(f"\n== {name}")
        results = []
        for run in range(1, runs + 1):
            tokens = [0]
            print(f"   run {run}")
            results.append((strategy(tokens), tokens[0]))
            print(f"   -> {'success after ' + str(results[-1][0]) if results[-1][0] else 'FAILED after 3'} "
                  f"attempts, {tokens[0]} tokens")
        solved = [a for a, _ in results if a]
        print(f"== {name}: {len(solved)}/{runs} solved, attempts until success {solved}, "
              f"tokens on average {sum(t for _, t in results) / runs:.0f}")
