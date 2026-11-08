"""Query parsing.

Syntax:
    python tutorial      ranked OR search (documents matching more terms rank higher)
    +python +tutorial    both terms are required
    python -java         exclude documents containing "java"
    "state of the art"   exact phrase
    -"machine learning"  exclude documents containing the phrase
"""
import re
from dataclasses import dataclass, field

from minisearch.text import analyze

_QUERY_TOKEN = re.compile(r'([+-]?)"([^"]*)"|([+-]?)(\S+)')

Phrase = list[tuple[str, int]]  # (term, offset from the phrase start)


@dataclass
class ParsedQuery:
    should: list[str] = field(default_factory=list)
    must: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)
    phrases: list[Phrase] = field(default_factory=list)
    not_phrases: list[Phrase] = field(default_factory=list)

    @property
    def scoring_terms(self) -> list[str]:
        """Unique terms that contribute to a document's score, in query order."""
        seen: dict[str, None] = {}
        for term in self.should + self.must:
            seen.setdefault(term)
        for phrase in self.phrases:
            for term, _ in phrase:
                seen.setdefault(term)
        return list(seen)

    @property
    def is_empty(self) -> bool:
        return not self.scoring_terms


def parse_query(query: str) -> ParsedQuery:
    parsed = ParsedQuery()
    for match in _QUERY_TOKEN.finditer(query):
        if match.group(2) is not None:  # quoted phrase
            sign, body = match.group(1), match.group(2)
            analyzed = analyze(body)
            if not analyzed:
                continue
            base = analyzed[0][1]
            phrase = [(term, pos - base) for term, pos in analyzed]
            (parsed.not_phrases if sign == "-" else parsed.phrases).append(phrase)
        else:
            sign, body = match.group(3), match.group(4)
            terms = [term for term, _ in analyze(body)]
            target = {"+": parsed.must, "-": parsed.must_not}.get(sign, parsed.should)
            target.extend(terms)
    return parsed
