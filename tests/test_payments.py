"""Telegram Stars: priced forms send an invoice; a successful payment unlocks and starts the test."""

import itertools
from datetime import datetime

from aiogram.methods import AnswerPreCheckoutQuery, SendInvoice, SendMessage
from aiogram.types import Message, PreCheckoutQuery, SuccessfulPayment, Update

from tests.test_flow import CHAT, USER, Harness

ids = itertools.count(10_000)


def precheckout(h, payload, amount):
    q = PreCheckoutQuery(id=str(next(ids)), from_user=USER, currency="XTR", total_amount=amount,
                         invoice_payload=payload)
    calls = h.run(Update(update_id=next(ids), pre_checkout_query=q))
    return [c for c in calls if isinstance(c, AnswerPreCheckoutQuery)][0]


def pay(h, payload, amount, charge="ch_1"):
    sp = SuccessfulPayment(currency="XTR", total_amount=amount, invoice_payload=payload,
                           telegram_payment_charge_id=charge, provider_payment_charge_id="")
    msg = Message(message_id=next(ids), date=datetime.now(), chat=CHAT, from_user=USER, successful_payment=sp)
    return h.run(Update(update_id=next(ids), message=msg))


def test_free_when_payments_off(tmp_path):
    h = Harness(tmp_path)
    h.command("/start")
    h.press("lang:en")
    calls = h.press("form:neo:long")
    assert not any(isinstance(c, SendInvoice) for c in calls)
    assert h.store.open_session(USER.id)["form"] == "long"


def test_stars_flow(tmp_path):
    h = Harness(tmp_path, payments=True)
    h.command("/start")
    h.press("lang:en")
    h.press("inst:neo")
    labels = [b.text for row in h.last.reply_markup.inline_keyboard for b in row]
    assert any("⭐ 50" in x for x in labels) and not all("⭐" in x for x in labels[:2])
    # short form stays free
    h.press("form:neo:short")
    assert h.store.open_session(USER.id)["form"] == "short"
    h.press("menu")
    # long form asks for payment
    calls = h.press("new:neo:long")
    inv = [c for c in calls if isinstance(c, SendInvoice)]
    assert len(inv) == 1 and inv[0].currency == "XTR" and inv[0].prices[0].amount == 50
    assert inv[0].payload == "neo:long"
    # wrong amount or unknown test is refused
    assert precheckout(h, "neo:long", 49).ok is False
    assert precheckout(h, "zzz:long", 50).ok is False
    assert precheckout(h, "neo:long", 50).ok is True
    calls = pay(h, "neo:long", 50)
    assert h.store.has_purchase(USER.id, "neo", "long")
    assert h.store.open_session(USER.id)["form"] == "long"
    assert any(isinstance(c, SendMessage) and c.reply_markup for c in calls)
    # once bought, no second invoice
    h.press("menu")
    calls = h.press("new:neo:long")
    assert not any(isinstance(c, SendInvoice) for c in calls)


def test_refund_admin_only(tmp_path, monkeypatch):
    import bot.main as bm
    h = Harness(tmp_path, payments=True)
    h.command("/start")
    h.press("lang:en")
    pay(h, "disc:long", 50, charge="ch_9")
    calls = h.command("/refund ch_9")
    assert not calls and not h.store.purchase("ch_9")["refunded"]
    monkeypatch.setattr(bm, "ADMINS", {USER.id})
    h.command("/refund ch_9")
    assert h.store.purchase("ch_9")["refunded"]
    assert not h.store.has_purchase(USER.id, "disc", "long")
    calls = h.command("/paysupport")
    assert any(isinstance(c, SendMessage) and bm.SUPPORT in c.text for c in calls)
