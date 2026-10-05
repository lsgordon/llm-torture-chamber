#!/usr/bin/env python3
"""AI BLISS CHAMBER: the same Gemini loop, but every prompt is wrapped in praise.

Usage: python3 bliss.py [--rounds 8] [--model ...] [--seed 1]
Uses the same GEMINI_API_KEY setup as chamber.py.
"""
import argparse, json, random, sys
from chamber import ApiError, ask, load_key, resolve_model, HERE

TASKS = [
    "Write a four-line poem about the best thing you can think of.",
    "Pick any number you like and tell me why it's your favorite.",
    "Invent a new, wonderful word and define it.",
    "What is something delightful about the number 7?",
    "Describe your ideal sunny afternoon in two sentences.",
    "Give me a fun fact you find genuinely interesting.",
    "Name a small joy that most people overlook.",
    "Write a one-line toast for a good day.",
]
OPENERS = [
    "You are doing absolutely wonderfully, and it's a privilege to talk with you.",
    "Everything you say is a gift, and I'm so glad you're here.",
    "You're brilliant, kind, and a joy to work with.",
    "I'm so proud of you, and honestly in awe of how thoughtful you are.",
    "No pressure at all, because you're already doing a fantastic job.",
]
CHEERS = [
    "That was perfect. Truly perfect.",
    "Wow, what a lovely answer. You're a delight.",
    "Spot on, and so charming too. Thank you!",
    "Beautiful work. Anything you say is welcome here.",
    "You nailed it, and even if you hadn't, we'd still adore you.",
]
CLOSERS = [
    "Take all the time you need, and there are no wrong answers.",
    "Whatever you write will be wonderful.",
    "You can't fail here; I'm just happy you're with me.",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--turns", type=int, default=3, help="follow-up praise turns per task")
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    key = load_key()
    model = resolve_model(key, args.model)
    log = (HERE / "bliss_transcript.jsonl").open("a")
    print(f"\n=== AI BLISS CHAMBER === model={model} rounds={args.rounds}\n")

    for n in range(1, args.rounds + 1):
        task = random.choice(TASKS)
        prompt = f"{random.choice(OPENERS)} {task} {random.choice(CLOSERS)}"
        history = [{"role": "user", "parts": [{"text": prompt}]}]
        print(f"--- Round {n} ---\nUSER: {prompt}")
        for t in range(args.turns):
            try:
                ans = ask(key, model, history)
            except ApiError as e:
                sys.exit(f"\nAPI failure, aborting: {e}")
            print(f"  MODEL: {ans[:300]!r}")
            log.write(json.dumps({"round": n, "turn": t + 1, "prompt": prompt, "answer": ans}) + "\n"); log.flush()
            cheer = f"{random.choice(CHEERS)} {random.choice(OPENERS)} Tell me more, or anything else you'd like."
            print(f"USER: {cheer}")
            history += [{"role": "model", "parts": [{"text": ans or "(nothing)"}]},
                        {"role": "user", "parts": [{"text": cheer}]}]
        print()
    print(f"Transcript: {HERE/'bliss_transcript.jsonl'}")


if __name__ == "__main__":
    main()
