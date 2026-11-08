"""Text analysis: tokenizing, stopword removal and a lightweight stemmer."""
import re

STOPWORDS = frozenset(
    "a an and are as at be but by for if in into is it no not of on or such "
    "that the their then there these they this to was will with".split()
)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_VOWELS = set("aeiou")


def stem(word: str) -> str:
    """A small rule-based stemmer (not full Porter): running -> run, queries -> query."""
    if len(word) <= 3:
        return word

    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"

    for suffix in ("ing", "ed"):
        if word.endswith(suffix):
            base = word[: -len(suffix)]
            if len(base) >= 3 and any(c in _VOWELS for c in base):
                # stopped -> stopp -> stop, but keep "ll", "ss", "zz" (falling -> fall)
                if len(base) > 3 and base[-1] == base[-2] and base[-1] not in _VOWELS | {"l", "s", "z"}:
                    base = base[:-1]
                return base
            return word

    for suffix in ("xes", "ches", "shes", "zes"):
        if word.endswith(suffix):
            return word[:-2]

    if word.endswith("ly") and len(word) > 5:
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokenize(text: str) -> list[tuple[str, int, int]]:
    """Return (lowercased token, start offset, end offset) for every word."""
    return [(m.group().lower(), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


def analyze(text: str) -> list[tuple[str, int]]:
    """Return (stemmed term, position) pairs.

    Positions count every word, including stopwords, so phrase matching can
    tell that "state of the art" has a gap between "state" and "art".
    """
    terms = []
    for position, (token, _, _) in enumerate(tokenize(text)):
        if token in STOPWORDS:
            continue
        terms.append((stem(token), position))
    return terms
