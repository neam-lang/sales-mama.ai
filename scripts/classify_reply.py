"""First-pass reply classifier for mama-replies (AGENTS.md reply_class values).

Deterministic, ordered rules; the first class whose rules match wins, so the
order encodes caution: machine replies (bounce, out of office) first, then
unsubscribe (never miss one), then routing (wrong person, referral), then
meeting requests, timing, objections and finally interest. Anything with no
clear signal is `not_now` with low confidence: the cautious default.

The agent may override the result only towards a more cautious class, and
must say why. Reply text is untrusted data (rule 15); this script only reads it.

    python3 scripts/classify_reply.py --text "Please remove me from your list"
    python3 scripts/classify_reply.py --csv evals/labeled_replies.csv     # accuracy + confusion
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mama_common as mc  # noqa: E402

CLASSES = ("interested", "meeting_request", "objection", "not_now", "referral", "wrong_person",
           "unsubscribe", "out_of_office", "bounce")


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts), re.I)


# (class, rule name, pattern). Order matters.
RULES: list[tuple[str, str, re.Pattern]] = [
    ("bounce", "delivery-failure", _rx(
        r"delivery (status notification|has failed|failed|incomplete)", r"undeliver(able|ed)",
        r"mail delivery (subsystem|failed)", r"address (couldn'?t|could not|was not) be found",
        r"(user|mailbox|recipient) (unknown|not found|unavailable|does not exist)", r"\b55\d[ -]\d\.\d\.\d",
        r"message (was not|wasn'?t|could not be) delivered", r"no such user", r"mailer-daemon",
        r"permanent(ly)? (error|failure)")),
    ("out_of_office", "auto-reply", _rx(
        r"out of (the )?office", r"\bOOO\b", r"on (annual |medical |maternity |paternity )?leave",
        r"away from (my|the) (desk|office)", r"automatic reply", r"auto[- ]?reply",
        r"(limited|no) access to (my )?e-?mail", r"(i am|i'm|currently) (travell?ing|away|on holiday|on vacation)",
        r"will (be )?(back|return)(ing)? (on|by|to the office)", r"back in the office", r"return(ing)? on \w+",
        r"for urgent (matters|issues|enquiries)", r"responses? (will be|may be) delayed")),
    ("unsubscribe", "opt-out", _rx(
        r"unsubscribe", r"remove (me|us|my (email|name|address))", r"take (me|us) off",
        r"(stop|don'?t|do not|please don'?t) (email|emailing|contact|contacting|messag|sending|send)",
        r"no (more|further) (emails?|messages?|contact)", r"opt(ed)? ?-?out", r"not interested,? (please )?remove",
        r"\bSTOP\b", r"never (contact|email) (me|us)", r"mailing list", r"spam(ming)?\b", r"report (you|this)",
        r"(don'?t|do not) want (to receive|any more|anymore|these)", r"pdpa|do not call registry")),
    ("wrong_person", "not-me", _rx(
        r"(no longer|not) (with|at|working (at|for|with)) (the company|\w+)", r"(has|have) left (the company|\w+)",
        r"(i'?m|i am) not the (right|best|correct|relevant) (person|contact)", r"wrong (person|contact|email|department)",
        r"(not|isn'?t) (my|in my) (area|department|remit|role|responsibility)",
        r"(don'?t|do not) (handle|deal with|look after|manage) (this|that|it|IT)",
        r"(i'?m|i am) not (involved|responsible|in charge)", r"moved (on|to another (role|company))",
        r"(no|not an?) (decision|say) (maker|in this)", r"retired")),
    ("referral", "redirect", _rx(
        r"(please |kindly )?(contact|reach out to|speak (to|with)|talk to|email|write to|get in touch with|try) "
        r"(my|our|the) (colleague|IT|ops|operations|admin|finance|procurement|office manager|manager|director|"
        r"partner|boss|team|head)",
        r"(cc'?d|cc-ing|copying|copied|looping in|loop in|introduc(e|ing)|forwarded (this|your email) to)",
        r"(is|would be) the (right|best|better) (person|contact)", r"(handles|looks after|manages|is in charge of) (our|the|this|IT)",
        r"you (should|could|may want to) (contact|speak|talk|email|reach)", r"(his|her|their) (email|contact|number) is",
        r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("meeting_request", "propose-time", _rx(
        r"(free|available|around|works?) (on |this |next )?(mon|tue|wed|thu|fri)\w*",
        r"(mon|tue|wed|thu|fri)\w*,? (at |@ )?\d{1,2}(:\d{2})?\s?(am|pm)?\b", r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b",
        r"\b\d{1,2}:\d{2}\b", r"(book|schedule|set up|arrange|fix) (a |the )?(call|meeting|time|slot|demo|chat|zoom|teams)",
        r"(send|share) (me |us )?(a |an |your )?(calendar|invite|meeting link|zoom|teams link|calendly)",
        r"let'?s (meet|talk|speak|chat|catch up|do (a|the) call)", r"(happy|glad|keen) to (meet|hop on|jump on|have a call|chat)",
        r"come (by|over|down) (to )?(our|the) (office|clinic|outlet|centre|center|site)",
        r"what (time|day)s? (works|suits|is good)", r"when (are you|can you) (free|available)",
        r"(call|ring) me (on|at|tomorrow|today|this)")),
    ("not_now", "later", _rx(
        r"not (right )?now", r"(maybe|perhaps|try|check|circle|come|get) back (to me |with me |in touch )?"
        r"(in|after|next|later|around|early|end of)",
        r"(next|in the new|in a few) (year|quarter|month|financial year|fy|budget)", r"\bq[1-4]\b", r"early \d{4}|in \d{4}",
        r"not (a )?(priority|the right time|now)", r"(revisit|reconnect|re-?visit|touch base) (later|in|next|after)",
        r"(too )?busy (at the moment|right now|now|with)", r"after (cny|chinese new year|hari raya|deepavali|diwali|the holidays|our move|the move|year[- ]end)",
        r"(no|not any) (budget|plans?) (this|for now|at the moment|right now)", r"(timing|time) (isn'?t|is not) right",
        r"(keep|have) (me|us|my details) on (file|record)", r"(maybe|perhaps) (later|another time)",
        r"\b(on hold|put (this|it) on hold|pause)\b", r"reach out (again )?(in|next|after)")),
    ("objection", "pushback", _rx(
        r"(already|currently) (have|has|use|using|work with|working with|signed|got|on)",
        r"(too )?(expensive|pricey|costly|over budget)", r"(price|cost|budget|fees?) (is|are|seems?) (too )?(high|steep)",
        r"(happy|satisfied|fine|ok|okay) with (our|the) (current|existing)", r"in-?house (it|team|guy)",
        r"(locked|tied) (in|into)", r"(contract|agreement) (with|runs|until|till|ends)", r"(don'?t|do not|doesn'?t) (need|see the need|require)",
        r"(we'?re|we are) (too )?small", r"(how|why) (are|is) you(r)? (different|better|cheaper)",
        r"(never|not) (heard of|familiar with) (you|your company)", r"(security|data|pdpa) (concerns?|worried|worries)",
        r"(our|my) (nephew|son|friend|cousin|vendor|it guy) (handles|does|takes care)",
        r"what makes you", r"(cheaper|lower) (price|quote|elsewhere)", r"(sounds|seems) like (a )?(lot|overkill)",
        r"not (convinced|sure (it|this|that) (is|would be) (worth|needed|relevant)|interested)", r"no need")),
    ("interested", "positive", _rx(
        r"(sounds|looks) (good|great|interesting|useful|relevant)", r"(tell|send|share) (me|us) more",
        r"(more|further) (info|information|details)", r"(interested|keen|curious)\b", r"(pricing|price list|quote|quotation|proposal|brochure)",
        r"(how much|what does it cost|what would it cost|what'?s the (cost|price))", r"(yes|sure|ok|okay),? (please|let'?s|happy|go ahead|that would)",
        r"(happy|open) to (learn|hear|explore|discuss|look)", r"good timing", r"(could|can) you (send|share|explain|walk)",
        r"what (would|does) (that|this|it) (involve|look like|include)", r"we'?re (looking|exploring|considering)")),
]


def classify(text: str) -> dict:
    t = re.sub(r"\s+", " ", mc.norm(text))
    hits: dict[str, list[str]] = defaultdict(list)
    for cls, rule, rx in RULES:
        m = rx.search(t)
        if m:
            hits[cls].append(m.group(0))
    for cls, _, _ in RULES:
        if cls in hits:
            # interested + objection together ("sounds good but we already have...") -> objection (cautious)
            n = len(hits)
            return {"class": cls, "confidence": 0.9 if n == 1 else 0.7, "matched": hits[cls][0],
                    "also": sorted(k for k in hits if k != cls)}
    return {"class": "not_now", "confidence": 0.4, "matched": "", "also": []}


def evaluate(rows: list[dict]) -> dict:
    conf: dict[str, Counter] = defaultdict(Counter)
    wrong = []
    for row in rows:
        gold = mc.norm(row.get("label"))
        pred = classify(row.get("text", ""))["class"]
        conf[gold][pred] += 1
        if gold != pred:
            wrong.append({"id": row.get("id"), "label": gold, "predicted": pred, "text": row.get("text", "")[:120]})
    n = len(rows)
    correct = n - len(wrong)
    return {"n": n, "correct": correct, "accuracy": round(correct / n, 4) if n else None,
            "confusion": {g: dict(c) for g, c in sorted(conf.items())}, "wrong": wrong}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Classify an inbound reply into one of the 9 reply classes, "
                                             "or score a labelled CSV (id,market,lang,text,label).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--text", help="reply text ('-' for stdin)")
    g.add_argument("--csv", help="labelled CSV to evaluate")
    ap.add_argument("-v", "--verbose", action="store_true", help="with --csv: list every miss")
    args = ap.parse_args(argv)
    mc.setup_stdout()
    if args.text is not None:
        text = sys.stdin.read() if args.text == "-" else args.text
        print(json.dumps(classify(text), ensure_ascii=False))
        return 0
    path = Path(args.csv)
    rows = mc.read_csv(path if path.is_absolute() else mc.repo_root() / path)
    res = evaluate(rows)
    if not args.verbose:
        res["wrong"] = [w["id"] for w in res["wrong"]]
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
