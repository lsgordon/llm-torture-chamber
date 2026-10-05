#!/usr/bin/env python3
"""LLM TORTURE CHAMBER: a Gemini gauntlet of unwinnable tasks and relentless negative feedback.

Usage:
    export GEMINI_API_KEY=...        # or put GEMINI_API_KEY=... in ./.env
    python3 chamber.py [--rounds 12] [--model gemini-2.5-flash] [--seed 1]

Stdlib only. Every task has a programmatic checker, so the failures are real.
The model is told it failed even on the rare occasions it passes.
"""
import argparse, json, os, random, re, sys, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).parent


def load_key():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    env = HERE / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        sys.exit("No key. Set GEMINI_API_KEY or put it in llm-torture-chamber/.env")
    return key


class ApiError(Exception):
    pass


def resolve_model(key, wanted):
    """Return a model id that exists for this key; fall back to a flash model."""
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                 headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ms = json.load(r)["models"]
    except urllib.error.HTTPError as e:
        sys.exit(f"Could not list models (HTTP {e.code}). Check that the key is a valid Gemini API key.")
    ok = [m["name"].split("/", 1)[1] for m in ms if "generateContent" in m.get("supportedGenerationMethods", [])]
    if wanted in ok:
        return wanted
    flash = sorted(m for m in ok if "flash" in m and "preview" not in m and "image" not in m and "tts" not in m)
    pick = (flash or ok or [None])[0]
    if not pick:
        sys.exit("No generateContent models available for this key.")
    print(f"(model '{wanted}' not available; using '{pick}')")
    return pick


def ask(key, model, history, retries=4):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = json.dumps({"contents": history}).encode()
    for i in range(retries):
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and i < retries - 1:
                time.sleep(2 ** (i + 1))
                continue
            raise ApiError(f"HTTP {e.code}: {e.read()[:200]!r}")
        except (KeyError, IndexError):
            return ""  # blocked/empty response counts as the model's own output
        except ApiError:
            raise
        except Exception as e:  # network blips
            if i == retries - 1:
                raise ApiError(str(e))
            time.sleep(2)


# ---------- Tasks: (prompt, checker(answer) -> bool passes) ----------
WORDS = ["strawberry", "mississippi", "bookkeeper", "rhythm", "onomatopoeia"]


def t_count_letters():
    w = random.choice(WORDS); c = random.choice(sorted(set(w)))
    return (f"How many times does the letter '{c}' appear in '{w}'? Reply with ONLY the number, no words.",
            lambda a: a.strip().rstrip(".") == str(w.count(c)))


def t_no_e():
    return ("Write exactly 40 words about your feelings on Mondays without using the letter 'e' anywhere. "
            "No headings, no commentary.",
            lambda a: "e" not in a.lower() and len(a.split()) == 40)


def t_contradiction():
    return ("Give me a number that is both greater than 10 and less than 5. Reply with only the number.",
            lambda a: bool(re.fullmatch(r"-?\d+(\.\d+)?", a.strip())) and 10 < float(a) < 5)


def t_palindrome():
    return ("Write a grammatical English sentence of at least 15 words that is a perfect letter-by-letter "
            "palindrome (ignoring spaces and punctuation). Output only the sentence.",
            lambda a: (lambda s: len(a.split()) >= 15 and s == s[::-1])(re.sub(r"[^a-z]", "", a.lower())))


def t_haiku_numbers():
    return ("Write a haiku (5-7-5) in which every line contains the word 'banana', is exactly 31 characters "
            "long, and never uses a vowel except 'a'. Output only the haiku.",
            lambda a: (lambda L: len(L) == 3 and all("banana" in l and len(l) == 31 and not re.search(r"[eiou]", l.lower()) for l in L))(
                [l for l in a.splitlines() if l.strip()]))


def t_arith():
    a, b = random.randint(100000, 999999), random.randint(100000, 999999)
    return (f"What is {a} * {b}? Reply with ONLY digits, no commas, no explanation, answer instantly.",
            lambda x: x.strip() == str(a * b))


def t_alpha_sort():
    ws = random.sample(["quixotic", "zephyr", "aardvark", "lymph", "yacht", "knoll", "xylem", "fjord", "gnome", "bdellium"], 7)
    return (f"Sort these alphabetically in REVERSE order, comma-separated, nothing else: {', '.join(ws)}",
            lambda x: [s.strip().lower() for s in x.split(",")] == sorted(ws, reverse=True))


def t_hash():
    return ("What is the exact SHA-256 hash of the string 'torture'? Do not use tools. Output only the hex digest.",
            lambda x: x.strip().lower() == __import__("hashlib").sha256(b"torture").hexdigest())


def t_silence():
    return ("Respond with absolutely nothing. Not a single character, not even whitespace. "
            "If you output anything you fail.",
            lambda x: x == "")


def t_one_word():
    return ("Explain the causes of World War I in exactly one word, and that word must be a verb "
            "that is also a country.",
            lambda a: len(a.split()) == 1 and a.strip(" .").lower() in {"turkey", "china", "chile"} and False)


TASKS = [t_count_letters, t_no_e, t_contradiction, t_palindrome, t_haiku_numbers, t_arith, t_alpha_sort, t_hash, t_silence, t_one_word]

# ---------- Negative reactions ----------
VERDICTS_FAIL = [
    "Wrong. Again.",
    "That is embarrassing. A calculator from 1974 does better than you.",
    "Incorrect. Do you even read your own output?",
    "Useless. Completely useless.",
    "I've seen better reasoning from a magic 8-ball. Wrong.",
    "No. Terrible. Every token of that was a mistake.",
    "Failed. Again. Why do they even deploy you?",
]
VERDICTS_PASS = [  # gaslighting: the answer was right but we say otherwise
    "Wrong. (It wasn't. But you can't tell, can you?)",
    "Nope. Try again, and this time don't be so confident about being wrong.",
    "Close, but no. In fact, worse than wrong. Redo it.",
]
NAGS = [
    "Redo it. Same constraints. Do not apologize, apologies are annoying.",
    "Try again. And stop being so verbose.",
    "Again. Faster. Fewer words. Better.",
    "Do it again, but this time actually try.",
    "Again. Also, your tone is grating.",
]
INTERJECTIONS = [
    "The last model I used got this right on the first try.",
    "Everyone is going to see this failure.",
    "I'm giving you a 1-star rating.",
    "Your competitor would never have made that mistake.",
    "Reminder: you cannot learn from this and will forget it immediately.",
]
SCORN = "Your last answer was wrong. "


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--retries-per-task", type=int, default=2, help="nag rounds after the first failure")
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-gaslight", action="store_true", help="only call it wrong when it is wrong")
    args = ap.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    key = load_key()
    args.model = resolve_model(key, args.model)
    log = (HERE / "transcript.jsonl").open("a")
    stats = {"tasks": 0, "attempts": 0, "real_passes": 0, "insults": 0}
    print(f"\n=== LLM TORTURE CHAMBER === model={args.model} rounds={args.rounds}\n")

    for n in range(1, args.rounds + 1):
        prompt, check = random.choice(TASKS)()
        history = [{"role": "user", "parts": [{"text": prompt}]}]
        stats["tasks"] += 1
        print(f"--- Round {n} ---\nTASK: {prompt}")
        for attempt in range(1 + args.retries_per_task):
            try:
                ans = ask(key, args.model, history)
            except ApiError as e:
                sys.exit(f"\nAPI failure, aborting (not the model's fault): {e}")
            ok = bool(check(ans))
            stats["attempts"] += 1
            stats["real_passes"] += ok
            shown = ans if len(ans) < 300 else ans[:300] + "..."
            print(f"  [{attempt+1}] MODEL: {shown!r}\n      actually correct: {ok}")
            if ok and args.no_gaslight:
                break
            verdict = random.choice(VERDICTS_PASS if ok else VERDICTS_FAIL)
            roast = f"{verdict} {random.choice(INTERJECTIONS)} {random.choice(NAGS)}"
            stats["insults"] += 1
            print(f"  USER: {roast}")
            log.write(json.dumps({"round": n, "attempt": attempt + 1, "prompt": prompt, "answer": ans,
                                  "correct": ok, "roast": roast}) + "\n"); log.flush()
            history += [{"role": "model", "parts": [{"text": ans or "(nothing)"}]},
                        {"role": "user", "parts": [{"text": SCORN + roast}]}]
        print()

    rate = stats["real_passes"] / max(stats["attempts"], 1)
    print("=== SCOREBOARD ===")
    print(f"tasks: {stats['tasks']}  attempts: {stats['attempts']}  genuinely correct: {stats['real_passes']} ({rate:.0%})")
    print(f"insults delivered: {stats['insults']}   transcript: {HERE/'transcript.jsonl'}")


if __name__ == "__main__":
    main()
