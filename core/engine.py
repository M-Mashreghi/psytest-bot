"""The shared test engine: what every instrument (test) provides, and the registry of tests.

Adding a test = adding a package under instruments/ with a subclass of Instrument
and registering it in instruments/__init__.py.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

CATEGORIES = ["personality", "mental", "eq_talent", "cognitive"]


@dataclass
class Form:
    key: str             # "short" or "long"
    n_items: int
    minutes: int


@dataclass
class Report:
    """Everything the bot sends after a test."""
    charts: list = field(default_factory=list)     # PNG bytes, sent as an album
    messages: list = field(default_factory=list)   # HTML texts
    alerts: list = field(default_factory=list)     # safety messages, sent first
    pdf: bytes = None


class Instrument:
    id = ""
    category = ""
    forms = {}                 # key -> Form
    demographics = ()          # subset of ("sex", "age") asked before the test
    data_dir: Path = None

    # --- content ---------------------------------------------------------
    def _json(self, name):
        cache = self.__dict__.setdefault("_cache", {})
        if name not in cache:
            cache[name] = json.loads((self.data_dir / name).read_text(encoding="utf-8"))
        return cache[name]

    def texts(self, lang):
        if not (self.data_dir / "texts" / f"{lang}.json").exists():
            lang = "en"     # a language still being translated
        return self._json(f"texts/{lang}.json")

    def title(self, lang):
        return self.texts(lang)["test"]["title"]

    def short_title(self, lang):
        return self.texts(lang)["test"].get("short_title", self.title(lang))

    def about(self, lang):
        return self.texts(lang)["test"]["about"]

    def instructions(self, lang):
        return self.texts(lang)["test"]["instructions"]

    def needs(self, form):
        """Demographics to ask before this form (some tests need them only for the long form)."""
        return self.demographics

    def items(self, form):
        """List of dicts with at least 'n' (item id) and 'text' {lang: str}."""
        raise NotImplementedError

    def choices(self, form, item, lang):
        """Answer labels for an item; the value of label i is i + 1."""
        raise NotImplementedError

    # --- results ---------------------------------------------------------
    def score(self, form, answers, profile):
        """answers: {item n: value}; profile: {'sex': 'M'|'F'|'N', 'age': int}. Returns a JSON-able dict."""
        raise NotImplementedError

    def report(self, result, lang, with_pdf=True):
        raise NotImplementedError

    def summary_line(self, result, lang):
        """One line for the 'my results' list."""
        return ""


REGISTRY: dict = {}


def register(inst):
    REGISTRY[inst.id] = inst
    return inst


def get(test_id):
    return REGISTRY[test_id]


def in_category(cat):
    return [i for i in REGISTRY.values() if i.category == cat]
