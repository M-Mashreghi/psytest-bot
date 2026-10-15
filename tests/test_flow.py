"""End-to-end bot flow against a fake Telegram API (no network, no token)."""

import asyncio
import itertools
import random
from datetime import datetime

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.methods import EditMessageText, SendDocument, SendInvoice, SendMediaGroup, SendMessage, SendPhoto
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import instruments  # noqa: F401
from bot.main import build_dispatcher
from core import engine
from core.i18n import LANGS
from core.storage import Storage

USER = User(id=42, is_bot=False, first_name="Test")
CHAT = Chat(id=42, type="private")
ids = itertools.count(1)


def _msg(text=None):
    return Message(message_id=next(ids), date=datetime.now(), chat=CHAT, text=text)


class FakeSession(BaseSession):
    """Records every API call and returns a plausible result."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            m = _msg(method.text)
            return m.model_copy(update={"reply_markup": method.reply_markup})
        if isinstance(method, SendMediaGroup):
            return [_msg() for _ in method.media]
        if isinstance(method, (SendDocument, SendPhoto, SendInvoice)):
            return _msg()
        return True

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass


class Harness:
    def __init__(self, tmp_path, payments=False):
        self.session = FakeSession()
        self.bot = Bot("42:TEST", session=self.session, default=DefaultBotProperties(parse_mode="HTML"))
        self.store = Storage(str(tmp_path / "t.sqlite3"))
        self.dp = build_dispatcher(self.store, enable_payments=payments)
        self.last = None

    def run(self, update):
        self.session.calls.clear()
        asyncio.run(self.dp.feed_update(self.bot, update))
        shown = [c for c in self.session.calls if isinstance(c, (SendMessage, EditMessageText)) and c.reply_markup]
        if shown:
            self.last = shown[-1]
        return self.session.calls

    def command(self, text):
        msg = Message(message_id=next(ids), date=datetime.now(), chat=CHAT, from_user=USER, text=text)
        return self.run(Update(update_id=next(ids), message=msg))

    def press(self, data):
        msg = Message(message_id=next(ids), date=datetime.now(), chat=CHAT, from_user=USER, text="x")
        cb = CallbackQuery(id=str(next(ids)), from_user=USER, chat_instance="c", message=msg, data=data)
        return self.run(Update(update_id=next(ids), callback_query=cb))

    def buttons(self):
        return [b.callback_data for row in self.last.reply_markup.inline_keyboard for b in row]

    def answer_all(self, rng):
        given, calls = {}, []
        while True:
            answers = [b for b in self.buttons() if b.startswith("a:")]
            if not answers:
                return given, calls
            choice = rng.choice(answers)
            _, _, n, v = choice.split(":")
            given[int(n)] = int(v)
            calls = self.press(choice)


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


CASES = [(i.id, f, lang) for i in engine.REGISTRY.values() for f in i.forms
         for lang in (LANGS if f == "short" else ["fa", "en"])]


@pytest.mark.parametrize("test_id,form,lang", CASES)
def test_full_flow(h, test_id, form, lang):
    inst = engine.get(test_id)
    h.command("/start")
    h.press(f"lang:{lang}")
    assert f"cat:{inst.category}" in h.buttons()
    h.press(f"cat:{inst.category}")
    assert f"inst:{test_id}" in h.buttons()
    h.press(f"inst:{test_id}")
    h.press(f"form:{test_id}:{form}")
    if "sex" in inst.needs(form):
        h.press("sex:F")
    if "age" in inst.needs(form):
        h.press("age:30")
    assert "begin" in h.buttons()
    h.press("begin")
    given, calls = h.answer_all(random.Random(f"{test_id}{form}{lang}"))
    assert len(given) == inst.forms[form].n_items
    albums = [c for c in calls if isinstance(c, SendMediaGroup)]
    photos = [c for c in calls if isinstance(c, SendPhoto)]
    docs = [c for c in calls if isinstance(c, SendDocument)]
    texts = [c.text for c in calls if isinstance(c, SendMessage)]
    assert all(2 <= len(a.media) <= 10 for a in albums)
    assert sum(len(a.media) for a in albums) + len(photos) == len(inst.report(h.store.latest_results(USER.id)[0]["result"], lang, with_pdf=False).charts)
    assert len(docs) == 1
    assert all(len(x) < 4096 for x in texts)
    s = h.store.latest_results(USER.id)[0]
    profile = {"sex": "F", "age": 30} if inst.needs(form) else {"sex": "N", "age": 30}
    assert s["result"] == inst.score(form, given, profile)
    # results list can resend the report
    h.press("results")
    assert f"res:{s['id']}" in h.buttons()


def test_back_resume_and_profile(h):
    h.command("/start")
    h.press("lang:fa")
    h.press("form:neo:long")
    h.press("sex:N")
    h.press("age:18")
    h.press("begin")
    first = [b for b in h.buttons() if b.startswith("a:")][0]
    h.press(first)
    h.press([b for b in h.buttons() if b.startswith("a:")][4])
    assert len(h.store.open_session(USER.id)["answers"]) == 2
    h.press([b for b in h.buttons() if b.startswith("back:")][0])
    assert len(h.store.open_session(USER.id)["answers"]) == 1
    h.press(first)  # stale button on an old question is ignored
    assert len(h.store.open_session(USER.id)["answers"]) == 1
    h.command("/start")
    assert "continue" in h.buttons()
    h.press("continue")
    assert "سؤال ۲ از ۳۰۰" in h.last.text
    # sex and age are remembered for the next test
    h.press("menu")
    h.press("new:neo:short")
    assert "begin" in h.buttons() and "profile" in h.buttons()


def test_new_test_warns_about_unfinished(h):
    h.command("/start")
    h.press("lang:en")
    h.press("form:neo:short")
    h.press("sex:M")
    h.press("age:50")
    h.press("begin")
    h.press([b for b in h.buttons() if b.startswith("a:")][0])
    h.press("form:neo:long")
    assert "new:neo:long" in h.buttons()
    h.press("new:neo:long")
    s = h.store.open_session(USER.id)
    assert s["form"] == "long" and s["answers"] == {}
