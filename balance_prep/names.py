"""Flip names from "SURNAME GIVEN NAMES" (upper case, no comma) to speaking order.

    GARCIA JUAN CARLOS   ->   Juan Carlos Garcia

Assignment files usually carry the holder name as one upper-case field with the
surname first and no comma. Cutting at the first word fails on compound
surnames ("DE LA FUENTE JUAN"), so instead we look for where the first GIVEN
name starts, using a list of common given names: everything before it is the
surname.

Rules:
  * The search starts at the second word, so a surname that is also a given
    name ("MARTIN GOMEZ JUAN") is never taken as the given name.
  * Names truncated by the source system ("GOMEZ MARIA DEL CAR") are recognised
    when the word is the beginning of a known given name (3+ letters).
  * Lone initials ("SALVO CLARA E") are dropped, unless the initial is all the
    given name there is.
  * Names already in speaking order ("CLARA SALVO") are only re-cased.
  * Anything that cannot be resolved is returned unchanged and reported, never
    guessed.
"""
import os
from pathlib import Path

from . import spreadsheet

PARTICLES = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "DI", "DA", "DOS", "SAN",
             "SANTA", "VAN", "VON", "MC", "MAC", "Y", "I", "LE", "DU"}

DEFAULT_LIST = Path(__file__).resolve().parent.parent / "data" / "first_names.txt"
FALLBACK = {"JUAN", "JOSE", "CARLOS", "MARIA", "ANA", "LUIS", "JORGE", "ROSA",
            "MIGUEL", "PEDRO", "CARMEN", "LAURA", "SILVIA"}

HEADER_ALIASES = ["holder", "name", "full name", "debtor", "customer", "titular", "nombre"]


def load_first_names(path=None):
    """One name per line; '#' starts a comment."""
    path = Path(path or os.environ.get("BALANCE_PREP_FIRST_NAMES_FILE") or DEFAULT_LIST)
    if not path.exists():
        return set(FALLBACK)
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.split("#", 1)[0].strip()
        if clean:
            names.add(spreadsheet.strip_accents(clean).upper())
    return names or set(FALLBACK)


class NameFlipper:
    def __init__(self, first_names=None):
        self.first_names = set(first_names) if first_names is not None else load_first_names()
        self._by_initial = {}
        for n in self.first_names:
            self._by_initial.setdefault(n[0], []).append(n)

    def is_given_name(self, word: str) -> bool:
        if word in self.first_names:
            return True
        if len(word) < 3:                     # lone initials decide nothing
            return False
        return any(n.startswith(word) for n in self._by_initial.get(word[0], ()))

    @staticmethod
    def _words(raw):
        return [w for w in spreadsheet.strip_accents(str(raw)).upper().replace(",", " ").split() if w]

    def split(self, raw):
        """Return (surname, given_names, confident)."""
        words = self._words(raw or "")
        if not words:
            return None, None, False
        if len(words) == 1:
            return words[0], "", False
        for i in range(1, len(words)):
            if words[i] in PARTICLES:
                continue
            if self.is_given_name(words[i]):
                cut = i
                while cut > 1 and words[cut - 1] in PARTICLES:   # a particle right before belongs to the surname
                    cut -= 1
                return " ".join(words[:cut]), " ".join(words[cut:]), True
        return words[0], " ".join(words[1:]), False

    @staticmethod
    def capitalize(text: str, after_given: bool = False) -> str:
        out = []
        for i, w in enumerate(text.split()):
            if len(w) == 1:
                out.append(w.upper())
            elif w in PARTICLES and (i > 0 or after_given):
                out.append(w.lower())
            else:
                out.append(w.capitalize())
        return " ".join(out)

    def fix(self, raw, drop_initials: bool = True):
        """Return (text, status): 'flipped', 'already_ordered' or 'untouched'."""
        words = self._words(raw)
        if (len(words) > 1 and self.is_given_name(words[0]) and not self.is_given_name(words[-1])
                and words[-1] not in PARTICLES):
            if drop_initials:
                whole = [w for w in words if len(w.rstrip(".")) > 1]
                if len(whole) > 1:
                    words = whole
            return self.capitalize(" ".join(words)), "already_ordered"
        surname, given, confident = self.split(raw)
        if confident and given:
            if drop_initials:
                whole = [w for w in given.split() if len(w.rstrip(".")) > 1]
                if whole:
                    given = " ".join(whole)
            return f"{self.capitalize(given)} {self.capitalize(surname, after_given=True)}", "flipped"
        return raw, "untouched"

    def flip(self, raw, drop_initials: bool = True):
        """Return (text, usable). Unresolved names come back unchanged with False."""
        text, status = self.fix(raw, drop_initials)
        return text, status != "untouched"


def transform_rows(headers, rows, column=None, flipper=None):
    """Flip the name column of a sheet. Return (rows, summary)."""
    flipper = flipper or NameFlipper()
    if column:
        idx = next((i for i, h in enumerate(headers)
                    if spreadsheet.normalize(h) == spreadsheet.normalize(column)), None)
    else:
        wanted = {spreadsheet.normalize(a) for a in HEADER_ALIASES}
        idx = next((i for i, h in enumerate(headers) if spreadsheet.normalize(h) in wanted), None)
        if idx is None and len(headers) == 1:
            idx = 0
    if idx is None:
        raise spreadsheet.InvalidSheet("Cannot tell which column holds the names.",
                                       "Columns: " + ", ".join(str(h) for h in headers if h))
    out, untouched = [], []
    counts = {"flipped": 0, "already_ordered": 0, "empty": 0}
    for row in rows:
        row = list(row)
        raw = row[idx]
        if raw is None or not str(raw).strip():
            counts["empty"] += 1
            out.append(row)
            continue
        new, status = flipper.fix(raw)
        row[idx] = new
        if status == "untouched":
            untouched.append(str(raw))
        else:
            counts[status] += 1
        out.append(row)
    summary = dict(counts, read=len(rows), column=str(headers[idx]), untouched=len(untouched))
    return out, summary
