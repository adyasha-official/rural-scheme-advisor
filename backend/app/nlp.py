"""Scheme catalogue, language / scheme / intent detection, recommendations."""
import json
import re
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def load_schemes() -> list[dict]:
    with open(config.SCHEMES_FILE, encoding="utf-8") as f:
        return json.load(f)["schemes"]


def get_scheme(scheme_id: str | None) -> dict | None:
    return next((s for s in load_schemes() if s["id"] == scheme_id), None)


# ---------- language ----------
LANG_NAMES = {"en": "English", "hi": "Hindi", "or": "Odia"}


def detect_language(text: str) -> str:
    """Script-based detection: Odia block, Devanagari block, else English.
    (Romanised Hindi like 'kaun eligible hai' is treated as English.)"""
    odia = len(re.findall(r"[଀-୿]", text))
    deva = len(re.findall(r"[ऀ-ॿ]", text))
    if odia > deva and odia > 0:
        return "or"
    if deva > 0:
        return "hi"
    return "en"


# ---------- scheme ----------
def detect_scheme(text: str) -> str | None:
    """Alias lookup. Returns a scheme id only if exactly one scheme matches."""
    t = text.lower()
    found = set()
    for s in load_schemes():
        for alias in s["aliases"] + [s["name"].lower()]:
            a = alias.lower()
            if re.search(r"[a-z]", a):
                if re.search(rf"\b{re.escape(a)}\b", t):
                    found.add(s["id"])
            elif a in t:
                found.add(s["id"])
    return found.pop() if len(found) == 1 else None


# ---------- intent ----------
INTENT_KEYWORDS = {
    "eligibility": ["eligible", "eligibility", "who can", "qualify", "पात्र", "योग्य", "ଯୋଗ୍ୟ", "kaun"],
    "documents": ["document", "documents", "papers", "proof", "required", "दस्तावेज", "କାଗଜ", "ଦଲିଲ"],
    "application": ["apply", "application", "register", "registration", "enrol", "आवेदन", "रजिस्ट", "ଆବେଦନ"],
    "benefits": ["benefit", "benefits", "amount", "how much", "installment", "लाभ", "राशि", "ଲାଭ", "ରାଶି"],
    "deadline": ["last date", "deadline", "due date", "अंतिम तिथि", "ଶେଷ ତାରିଖ"],
    "comparison": ["which scheme", "compare", "difference", "कौन सी योजना", "କେଉଁ ଯୋଜନା"],
    "overview": ["what is", "explain", "about", "overview", "क्या है", "କଣ"],
}


def detect_intent(text: str) -> str:
    t = text.lower()
    for intent, words in INTENT_KEYWORDS.items():
        if any(w in t for w in words):
            return intent
    return "overview"


FOLLOW_UPS = {
    "overview": ["Who is eligible?", "What benefits are available?", "How do I apply?"],
    "eligibility": ["What documents are needed?", "How do I apply?", "What benefits are available?"],
    "documents": ["How do I apply?", "Who is eligible?"],
    "application": ["What documents are needed?", "Who is eligible?"],
    "benefits": ["Who is eligible?", "How do I apply?"],
    "deadline": ["How do I apply?", "Who is eligible?"],
    "comparison": ["Who is eligible?", "How do I apply?"],
}


def follow_ups(intent: str) -> list[str]:
    return FOLLOW_UPS.get(intent, FOLLOW_UPS["overview"])


# ---------- recommendations ----------
NEED_TAGS = {
    "farming": ["farming", "agriculture", "income_support"],
    "housing": ["housing", "rural_housing"],
    "health": ["health", "hospital", "insurance"],
    "cooking_fuel": ["cooking_fuel", "lpg"],
    "employment": ["employment", "wage_work", "job_card"],
}
OCCUPATION_TAGS = {
    "farmer": ["farming"],
    "daily_wage": ["employment", "wage_work"],
    "homemaker": ["cooking_fuel", "women"],
    "unemployed": ["employment"],
}
NEED_LABELS = {
    "farming": "farmer income support",
    "housing": "rural housing assistance",
    "health": "health coverage",
    "cooking_fuel": "cooking fuel (LPG)",
    "employment": "rural wage employment",
}


def recommend(needs: list[str], occupation: str | None) -> list[dict]:
    """Transparent rule-based matching. This is NOT an eligibility decision."""
    wanted: dict[str, str] = {}
    for n in needs:
        for tag in NEED_TAGS.get(n, []):
            wanted[tag] = f"you said you are looking for {NEED_LABELS.get(n, n)}"
    for tag in OCCUPATION_TAGS.get(occupation or "", []):
        wanted.setdefault(tag, f"your occupation is '{occupation}'")
    results = []
    for s in load_schemes():
        reasons = sorted({wanted[t] for t in s["tags"] if t in wanted})
        if reasons:
            results.append(
                {
                    "scheme_id": s["id"],
                    "name": s["name"],
                    "category": s["category"],
                    "summary": s["summary"],
                    "reasons": reasons,
                    "official_url": s["official_url"],
                    "note": "Potentially relevant only. Check the official eligibility conditions.",
                }
            )
    results.sort(key=lambda r: -len(r["reasons"]))
    return results
