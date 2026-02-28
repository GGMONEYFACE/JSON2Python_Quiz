#!/usr/bin/env python3
"""
CLI Quiz Runner (Immediate Feedback + File Picker + ANSI Colors)

Features
- Lists available JSON quizzes in ./JSON_Files and prompts you to select one
- Immediate feedback after each answer (correct/incorrect) if "answer" exists in JSON
- Works even if no answer key exists (falls back to "Recorded." feedback)
- ANSI colorized output (toggle with --no-color)
- Shuffle, limit, and skip controls

Expected JSON format (minimum):
{
  "title": "...",
  "questions": [
    {"id": 1, "question": "...", "options": {"a":"...", "b":"...", "c":"..."}}
  ]
}

The program no longer assumes exactly three answer choices.  Each question's
"options" object may contain any number of labeled choices ("a","b","c","d",
"1","2", etc.); the runner will display whatever keys are present and only
accept those as valid responses.

Answer key support (optional per-question):
- "answer": "a" | "b" | "c"  # or any other label matching an option
- "explanation": "..."           # optional text shown after the answer

Usage:
  python3 cli_quiz.py
  python3 cli_quiz.py --dir JSON_Files
  python3 cli_quiz.py --shuffle --seed 7
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------- ANSI COLOR CODES ----------------
# Foreground (text) colors
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"

ANSI_BLACK = "\033[30m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_MAGENTA = "\033[35m"
ANSI_CYAN = "\033[36m"
ANSI_WHITE = "\033[37m"

# Bright foreground colors
ANSI_BRIGHT_BLACK = "\033[90m"
ANSI_BRIGHT_RED = "\033[91m"
ANSI_BRIGHT_GREEN = "\033[92m"
ANSI_BRIGHT_YELLOW = "\033[93m"
ANSI_BRIGHT_BLUE = "\033[94m"
ANSI_BRIGHT_MAGENTA = "\033[95m"
ANSI_BRIGHT_CYAN = "\033[96m"
ANSI_BRIGHT_WHITE = "\033[97m"

# Background colors (optional)
ANSI_BG_RED = "\033[41m"
ANSI_BG_GREEN = "\033[42m"
ANSI_BG_YELLOW = "\033[43m"

# only keep control commands globally; valid answer choices are computed per-question
SKIP_QUIT_INPUTS = {"s", "q"}


@dataclass
class QuizQuestion:
    qid: Any
    text: str
    options: Dict[str, str]
    answer: Optional[str] = None  # label of correct choice if present
    explanation: Optional[str] = None  # optional text to show after answering


def supports_color() -> bool:
    # Conservative: enable colors on TTYs unless NO_COLOR is set
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def c(text: str, *codes: str, enable: bool) -> str:
    if not enable or not codes:
        return text
    return "".join(codes) + text + ANSI_RESET


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Error: file not found: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Error: JSON parse failed for {path.name}: {e}")


def normalize_options(opts: Any) -> Dict[str, str]:
    """Return a cleaned mapping of option keys to text.

    The quiz JSON may use arbitrary keys (typically letters), so we accept
    any string key and lowercase it.  Non-string values are ignored.
    """
    out: Dict[str, str] = {}
    if not isinstance(opts, dict):
        return out
    for k, v in opts.items():
        if isinstance(k, str) and isinstance(v, str):
            kk = k.strip().lower()
            if kk:
                out[kk] = v.strip()
    return out


def normalize_answer(ans: Any) -> Optional[str]:
    if isinstance(ans, str):
        a = ans.strip().lower()
        if a:
            return a
    return None


def parse_questions(data: Dict[str, Any]) -> List[QuizQuestion]:
    raw_qs = data.get("questions")
    if not isinstance(raw_qs, list) or not raw_qs:
        raise SystemExit("Error: JSON missing a non-empty 'questions' list.")
    questions: List[QuizQuestion] = []
    for q in raw_qs:
        if not isinstance(q, dict):
            continue
        qid = q.get("id", "?")
        text = str(q.get("question", "")).strip()
        opts = normalize_options(q.get("options"))
        ans = normalize_answer(q.get("answer"))
        # only keep the answer if it matches one of the options
        if ans is not None and ans not in opts:
            ans = None
        expl = None
        if isinstance(q.get("explanation"), str):
            expl = q.get("explanation").strip()
        if text and len(opts) >= 2:
            questions.append(QuizQuestion(qid=qid, text=text, options=opts, answer=ans, explanation=expl))
    if not questions:
        raise SystemExit("Error: no valid questions found in JSON.")
    return questions


def list_json_files(directory: Path) -> List[Path]:
    if not directory.exists() or not directory.is_dir():
        raise SystemExit(f"Error: directory not found: {directory}")
    files = sorted([p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".json"])
    if not files:
        raise SystemExit(f"Error: no .json files found in: {directory}")
    return files


def prompt_select_file(files: List[Path], color_on: bool) -> Path:
    print(c("\nAvailable quizzes:", ANSI_BOLD, enable=color_on))
    for i, p in enumerate(files, start=1):
        print(f"  {c(str(i), ANSI_CYAN, ANSI_BOLD, enable=color_on)}) {p.name}")
    print()

    while True:
        choice = input("Select a file by number (or 'q' to quit): ").strip().lower()
        if choice == "q":
            raise SystemExit("Goodbye.")
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(files):
                return files[idx - 1]
        print(c("Invalid selection. Try again.", ANSI_YELLOW, enable=color_on))


def ask_question(q: QuizQuestion, idx: int, total: int, color_on: bool) -> Tuple[str, Optional[str]]:
    print("\n" + "-" * 72)
    header = f"[{idx}/{total}] Q{q.qid}"
    print(c(header, ANSI_BOLD, enable=color_on))
    print(q.text + "\n")

    # show all available options in sorted order so the output is stable
    sorted_keys = sorted(q.options.keys())
    for key in sorted_keys:
        print(f"  {c(key + ')', ANSI_CYAN, ANSI_BOLD, enable=color_on)} {q.options[key]}")

    # build prompt string dynamically
    opts_display = "/".join(sorted_keys)
    print(f"\nEnter {opts_display}, s=skip, q=quit")

    valid_choices = set(sorted_keys) | SKIP_QUIT_INPUTS
    while True:
        choice = input("> ").strip().lower()
        if choice in valid_choices:
            if choice == "q":
                return ("quit", None)
            if choice == "s":
                return ("skip", None)
            return ("answer", choice)
        prompt = f"Please enter one of: {opts_display}, s, q"
        print(c(prompt, ANSI_YELLOW, enable=color_on))


def immediate_feedback(q: QuizQuestion, user_choice: str, color_on: bool) -> bool:
    """
    Returns True if correct, False if incorrect (or unknown if no answer key: returns False but prints neutral).

    If the question supplies an ``explanation`` string, it will be printed after
    the normal feedback message.
    """
    if q.answer is None:
        print(c("Recorded.", ANSI_BLUE, enable=color_on))
        if q.explanation:
            print(c(q.explanation, ANSI_DIM, enable=color_on))
        return False

    if user_choice == q.answer:
        print(c("Correct!", ANSI_GREEN, ANSI_BOLD, enable=color_on))
        if q.explanation:
            print(c(q.explanation, ANSI_DIM, enable=color_on))
        return True

    correct_text = q.options.get(q.answer, "(missing option text)")
    msg = f"Incorrect. Correct answer: {q.answer}) {correct_text}"
    print(c(msg, ANSI_RED, ANSI_BOLD, enable=color_on))
    if q.explanation:
        print(c(q.explanation, ANSI_DIM, enable=color_on))
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="CLI quiz runner with file picker and immediate feedback.")
    ap.add_argument("--dir", default="JSON_Files", help="Directory containing quiz JSON files (default: JSON_Files)")
    ap.add_argument("--shuffle", action="store_true", help="Shuffle question order")
    ap.add_argument("--seed", type=int, default=None, help="Seed for shuffle RNG")
    ap.add_argument("--limit", type=int, default=None, help="Ask only first N questions (after shuffle)")
    ap.add_argument("--no-return-skips", action="store_true", help="Do not re-ask skipped questions")
    ap.add_argument("--no-color", action="store_true", help="Disable ANSI coloring")
    args = ap.parse_args()

    color_on = supports_color() and (not args.no_color)

    quiz_dir = Path(args.dir)
    files = list_json_files(quiz_dir)
    selected = prompt_select_file(files, color_on=color_on)

    data = load_json(selected)
    title = str(data.get("title", selected.stem))
    questions = parse_questions(data)

    if args.seed is not None:
        random.seed(args.seed)
    if args.shuffle:
        random.shuffle(questions)
    if args.limit is not None:
        if args.limit <= 0:
            raise SystemExit("Error: --limit must be a positive integer.")
        questions = questions[: args.limit]

    # Run quiz
    print("\n" + "=" * 72)
    print(c(title, ANSI_BOLD, enable=color_on))
    print(f"Questions: {len(questions)}")
    print("=" * 72)

    answered: List[Tuple[Any, str, Optional[str], bool]] = []  # (id, chosen, correct_answer, is_correct)
    skipped: List[QuizQuestion] = []

    total = len(questions)
    for idx, q in enumerate(questions, start=1):
        action, user_choice = ask_question(q, idx, total, color_on=color_on)
        if action == "quit":
            print(c("\nQuitting early.", ANSI_YELLOW, enable=color_on))
            break
        if action == "skip":
            skipped.append(q)
            continue

        assert user_choice is not None
        is_correct = immediate_feedback(q, user_choice, color_on=color_on)
        answered.append((q.qid, user_choice, q.answer, is_correct))

    # Optional second pass on skipped
    if skipped and not args.no_return_skips:
        print("\n" + "=" * 72)
        print(c(f"Second pass (skipped): {len(skipped)}", ANSI_BOLD, enable=color_on))
        print("=" * 72)

        remaining: List[QuizQuestion] = []
        total2 = len(skipped)
        for idx, q in enumerate(skipped, start=1):
            action, user_choice = ask_question(q, idx, total2, color_on=color_on)
            if action == "quit":
                remaining.append(q)
                remaining.extend(skipped[idx:])
                print(c("\nQuitting early.", ANSI_YELLOW, enable=color_on))
                break
            if action == "skip":
                remaining.append(q)
                continue

            assert user_choice is not None
            is_correct = immediate_feedback(q, user_choice, color_on=color_on)
            answered.append((q.qid, user_choice, q.answer, is_correct))

        skipped = remaining

    # Summary
    has_key = any(q.answer is not None for q in questions)
    correct_count = sum(1 for _, _, ans, ok in answered if ans is not None and ok)
    graded_count = sum(1 for _, _, ans, _ in answered if ans is not None)

    print("\n" + "-" * 72)
    print(c("Session summary:", ANSI_BOLD, enable=color_on))
    print(f"  Answered: {len(answered)}")
    print(f"  Skipped:  {len(skipped)}")

    if has_key and graded_count:
        pct = (correct_count / graded_count) * 100.0
        print(f"  Scored:   {correct_count}/{graded_count} ({pct:.1f}%)")
    elif not has_key:
        print(c("  Note: No answer key found in JSON; score not available.", ANSI_DIM, enable=color_on))

    print("-" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())