"""Telegram bot: categories, tests, question flow, charts, PDF report.

Run:  BOT_TOKEN=... python -m bot.main

Optional Telegram Stars payments: PAYMENTS=1 charges the prices in data/prices.json.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           InputMediaPhoto, LabeledPrice, Message, PreCheckoutQuery)

import instruments  # noqa: F401  (registers every test)
from core import engine
from core.draw import bar_text
from core.i18n import LANGS, num, t
from core.storage import Storage

DB_PATH = os.environ.get("DB_PATH", "neo_bot.sqlite3")
AGES = [("age_lt21", 18), ("age_21_40", 30), ("age_41_60", 50), ("age_gt60", 70)]

PRICES = json.loads((Path(__file__).resolve().parent.parent / "data" / "prices.json").read_text(encoding="utf-8"))
SUPPORT = os.environ.get("SUPPORT_CONTACT", "the bot owner")
ADMINS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(",", " ").split()}

router = Router()
store: Storage = None
payments = False


# --- helpers -------------------------------------------------------------------
def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=x, callback_data=c) for x, c in row]
                                                 for row in rows])


def lang_of(uid):
    return store.user(uid)["lang"] or "en"


def lang_keyboard():
    names = {l: t(l, "lang_name") for l in LANGS}
    return kb([[(names[a], f"lang:{a}"), (names[b], f"lang:{b}")] for a, b in zip(LANGS[::2], LANGS[1::2])])


def age_label(lang, age):
    return t(lang, next(k for k, a in AGES if a == age)) if age in dict((a, k) for k, a in AGES) else num(lang, age)


def profile_text(lang, sex, age):
    return f"{t(lang, 'sex_' + sex)}, {age_label(lang, age)}"


def menu(uid):
    lang = lang_of(uid)
    rows = []
    s = store.open_session(uid)
    if s and s["status"] == "active":
        inst = engine.get(s["test_id"])
        rows.append([(t(lang, "btn_continue", name=inst.short_title(lang), i=len(s["answers"]),
                       n=inst.forms[s["form"]].n_items), "continue")])
    rows += [[(t(lang, f"cat_{c}"), f"cat:{c}")] for c in engine.CATEGORIES]
    if store.latest_results(uid):
        rows.append([(t(lang, "btn_results"), "results")])
    rows.append([(t(lang, "btn_lang"), "chooselang"), (t(lang, "btn_about"), "about")])
    return t(lang, "menu_title"), kb(rows)


def price(test_id, form):
    """Stars needed for this test form (0 = free)."""
    return int(PRICES.get(test_id, {}).get(form, 0)) if payments else 0


def locked(uid, test_id, form):
    return price(test_id, form) > 0 and not store.has_purchase(uid, test_id, form)


def current_index(inst, s):
    for i, item in enumerate(inst.items(s["form"])):
        if item["n"] not in s["answers"]:
            return i
    return None


def question_view(s, lang):
    inst = engine.get(s["test_id"])
    items = inst.items(s["form"])
    i = current_index(inst, s)
    item, total = items[i], len(items)
    pct = round(100 * i / total)
    text = "\n".join([
        f"<b>{inst.short_title(lang)}</b> · {t(lang, 'question_header', i=i + 1, n=total)}",
        f"{bar_text(pct, 12)} {num(lang, pct)}%",
        "",
        f"<i>{item.get('prompt', {}).get(lang) or t(lang, 'question_prompt')}</i>",
        "",
        f"<b>{item['text'][lang]}</b>",
    ])
    rows = [[(c, f"a:{s['id']}:{item['n']}:{v}")] for v, c in enumerate(inst.choices(s["form"], item, lang), start=1)]
    if i > 0:
        rows.append([(t(lang, "btn_back"), f"back:{s['id']}")])
    return text, kb(rows)


async def show(cb: CallbackQuery, text, markup):
    """Edit the message the button belongs to; fall back to a new message."""
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)


async def send_report(message: Message, s, lang):
    inst = engine.get(s["test_id"])
    wait = await message.answer(t(lang, "sending_report"))
    rep = await asyncio.to_thread(inst.report, s["result"], lang)
    for a in rep.alerts:
        await message.answer(a)
    if rep.charts:
        files = [BufferedInputFile(png, f"chart{i}.png") for i, png in enumerate(rep.charts)]
        for k in range(0, len(files), 10):
            chunk = files[k:k + 10]
            if len(chunk) == 1:   # an album needs at least two photos
                await message.answer_photo(chunk[0])
            else:
                await message.answer_media_group([InputMediaPhoto(media=f) for f in chunk])
    for m in rep.messages:
        await message.answer(m)
    if rep.pdf:
        name = f"{inst.id}-{s['form']}-{time.strftime('%Y%m%d', time.localtime(s['finished'] or time.time()))}.pdf"
        await message.answer_document(BufferedInputFile(rep.pdf, name), caption=t(lang, "pdf_caption"))
    try:
        await wait.delete()
    except Exception:
        pass


# --- navigation ----------------------------------------------------------------
@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    if not store.user(uid)["lang"]:
        await message.answer(" · ".join(t(l, "choose_lang") for l in LANGS), reply_markup=lang_keyboard())
        return
    text, markup = menu(uid)
    await message.answer(text, reply_markup=markup)


@router.message(Command("language"))
async def cmd_lang(message: Message):
    await message.answer(t(lang_of(message.from_user.id), "choose_lang"), reply_markup=lang_keyboard())


@router.callback_query(F.data == "chooselang")
async def cb_chooselang(cb: CallbackQuery):
    await show(cb, t(lang_of(cb.from_user.id), "choose_lang"), lang_keyboard())
    await cb.answer()


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(cb: CallbackQuery):
    lang = cb.data.split(":")[1]
    if lang in LANGS:
        store.set_user(cb.from_user.id, lang=lang)
    await show(cb, *menu(cb.from_user.id))
    await cb.answer()


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery):
    await show(cb, *menu(cb.from_user.id))
    await cb.answer()


@router.callback_query(F.data == "about")
async def cb_about(cb: CallbackQuery):
    lang = lang_of(cb.from_user.id)
    await show(cb, t(lang, "about_text"), kb([[(t(lang, "btn_menu"), "menu")]]))
    await cb.answer()


@router.callback_query(F.data.startswith("cat:"))
async def cb_category(cb: CallbackQuery):
    lang = lang_of(cb.from_user.id)
    cat = cb.data.split(":")[1]
    tests = engine.in_category(cat)
    rows = [[(i.title(lang), f"inst:{i.id}")] for i in tests]
    rows.append([(t(lang, "btn_back"), "menu")])
    body = t(lang, "choose_test") if tests else t(lang, "coming_soon")
    await show(cb, f"<b>{t(lang, f'cat_{cat}')}</b>\n\n{body}", kb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("inst:"))
async def cb_instrument(cb: CallbackQuery):
    lang = lang_of(cb.from_user.id)
    inst = engine.get(cb.data.split(":")[1])
    rows = []
    for f in inst.forms.values():
        label = t(lang, "btn_one_form" if len(inst.forms) == 1 else f"btn_{f.key}_form", n=f.n_items, m=f.minutes)
        if locked(cb.from_user.id, inst.id, f.key):
            label += f" · ⭐ {price(inst.id, f.key)}"
        rows.append([(label, f"form:{inst.id}:{f.key}")])
    rows.append([(t(lang, "btn_back"), f"cat:{inst.category}")])
    await show(cb, f"<b>{inst.title(lang)}</b>\n\n{inst.about(lang)}", kb(rows))
    await cb.answer()


@router.callback_query(F.data == "results")
async def cb_results(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = lang_of(uid)
    done = store.latest_results(uid)
    await cb.answer()
    if not done:
        await show(cb, t(lang, "no_results"), kb([[(t(lang, "btn_menu"), "menu")]]))
        return
    lines = [t(lang, "results_list_title"), ""]
    rows = []
    for s in done:
        inst = engine.get(s["test_id"])
        lines.append(f"<b>{inst.short_title(lang)}</b>: {inst.summary_line(s['result'], lang)}")
        rows.append([(f"📊 {inst.short_title(lang)}", f"res:{s['id']}")])
    rows.append([(t(lang, "btn_menu"), "menu")])
    await show(cb, "\n".join(lines), kb(rows))


@router.callback_query(F.data.startswith("res:"))
async def cb_result(cb: CallbackQuery):
    uid = cb.from_user.id
    s = store.get(int(cb.data.split(":")[1]))
    await cb.answer()
    if not s or s["user_id"] != uid or s["status"] != "done":
        return
    await send_report(cb.message, s, lang_of(uid))
    text, markup = menu(uid)
    await cb.message.answer(text, reply_markup=markup)


# --- starting a test -----------------------------------------------------------
def setup_view(uid, s):
    """The next setup screen: whatever the test still needs (sex, age), then the instructions."""
    lang = lang_of(uid)
    inst = engine.get(s["test_id"])
    u = store.user(uid)
    needs = inst.needs(s["form"])
    if "sex" in needs and not u["sex"]:
        return t(lang, "ask_sex"), kb([[(t(lang, "sex_M"), "sex:M"), (t(lang, "sex_F"), "sex:F")],
                                       [(t(lang, "sex_N"), "sex:N")]])
    if "age" in needs and not u["age"]:
        return t(lang, "ask_age"), kb([[(t(lang, k), f"age:{a}")] for k, a in AGES])
    form = inst.forms[s["form"]]
    text = f"<b>{inst.title(lang)}</b>\n\n" + inst.instructions(lang).format(n=num(lang, form.n_items))
    rows = [[(t(lang, "btn_begin"), "begin")]]
    if needs:
        text += "\n\n" + t(lang, "profile_line", profile=profile_text(lang, u["sex"], u["age"]))
        rows.append([(t(lang, "btn_change_profile"), "profile")])
    rows.append([(t(lang, "btn_back"), f"inst:{inst.id}")])
    return text, kb(rows)


async def ask_next_setup(cb: CallbackQuery, s):
    await show(cb, *setup_view(cb.from_user.id, s))


@router.callback_query(F.data.startswith("form:") | F.data.startswith("new:"))
async def cb_form(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = lang_of(uid)
    kind, test_id, form = cb.data.split(":")
    inst = engine.get(test_id)
    await cb.answer()
    s = store.open_session(uid)
    if kind == "form" and s and s["answers"]:
        other = engine.get(s["test_id"])
        await show(cb, t(lang, "unfinished_warning"), kb([
            [(t(lang, "btn_continue", name=other.short_title(lang), i=len(s["answers"]),
                n=other.forms[s["form"]].n_items), "continue")],
            [(t(lang, "btn_confirm_new"), f"new:{inst.id}:{form}")],
        ]))
        return
    if locked(uid, inst.id, form):
        await cb.message.answer_invoice(
            title=t(lang, "invoice_title", test=inst.short_title(lang))[:32],
            description=t(lang, "invoice_desc")[:255],
            payload=f"{inst.id}:{form}",
            currency="XTR",
            prices=[LabeledPrice(label=inst.short_title(lang), amount=price(inst.id, form))],
        )
        return
    store.new_session(uid, inst.id, form)
    await ask_next_setup(cb, store.open_session(uid))


# --- Telegram Stars --------------------------------------------------------------
@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    test_id, _, form = q.invoice_payload.partition(":")
    ok = test_id in engine.REGISTRY and q.currency == "XTR" and q.total_amount == price(test_id, form) > 0
    await q.answer(ok=ok, error_message=None if ok else "This offer has changed. Please open the test again.")


@router.message(F.successful_payment)
async def paid(message: Message):
    uid = message.from_user.id
    lang = lang_of(uid)
    pay = message.successful_payment
    test_id, _, form = pay.invoice_payload.partition(":")
    store.add_purchase(uid, test_id, form, pay.total_amount, pay.telegram_payment_charge_id)
    await message.answer(t(lang, "paid_thanks"))
    store.new_session(uid, test_id, form)
    text, markup = setup_view(uid, store.open_session(uid))
    await message.answer(text, reply_markup=markup)


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message):
    await message.answer(t(lang_of(message.from_user.id), "paysupport", contact=SUPPORT))


@router.message(Command("refund"))
async def cmd_refund(message: Message):
    """Admins only: /refund <telegram_payment_charge_id>"""
    if message.from_user.id not in ADMINS:
        return
    parts = (message.text or "").split()
    p = store.purchase(parts[1]) if len(parts) == 2 else None
    if not p or p["refunded"]:
        await message.answer("Unknown or already refunded charge id.")
        return
    await message.bot.refund_star_payment(user_id=p["user_id"], telegram_payment_charge_id=p["charge_id"])
    store.mark_refunded(p["charge_id"])
    await message.answer(f"Refunded {p['stars']} ⭐ to user {p['user_id']}.")


@router.callback_query(F.data == "profile")
async def cb_profile(cb: CallbackQuery):
    store.set_user(cb.from_user.id, sex=None, age=None)
    await cb.answer()
    s = store.open_session(cb.from_user.id)
    if s:
        await ask_next_setup(cb, s)


@router.callback_query(F.data.startswith("sex:"))
async def cb_sex(cb: CallbackQuery):
    store.set_user(cb.from_user.id, sex=cb.data.split(":")[1])
    await cb.answer()
    s = store.open_session(cb.from_user.id)
    if s:
        await ask_next_setup(cb, s)


@router.callback_query(F.data.startswith("age:"))
async def cb_age(cb: CallbackQuery):
    store.set_user(cb.from_user.id, age=int(cb.data.split(":")[1]))
    await cb.answer()
    s = store.open_session(cb.from_user.id)
    if s:
        await ask_next_setup(cb, s)


@router.callback_query(F.data.in_({"begin", "continue"}))
async def cb_begin(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = lang_of(uid)
    s = store.open_session(uid)
    await cb.answer()
    if not s:
        await show(cb, *menu(uid))
        return
    if s["status"] != "active":
        u = store.user(uid)
        store.update(s["id"], status="active", sex=u["sex"], age=u["age"])
        s = store.get(s["id"])
    await show(cb, *question_view(s, lang))


# --- answering -----------------------------------------------------------------
@router.callback_query(F.data.startswith("back:"))
async def cb_back(cb: CallbackQuery):
    uid = cb.from_user.id
    s = store.open_session(uid)
    await cb.answer()
    if not s or s["id"] != int(cb.data.split(":")[1]) or s["status"] != "active":
        return
    inst = engine.get(s["test_id"])
    items = inst.items(s["form"])
    i = current_index(inst, s)
    i = len(items) if i is None else i
    if i > 0:
        s["answers"].pop(items[i - 1]["n"], None)
        store.update(s["id"], answers=s["answers"])
    await show(cb, *question_view(s, lang_of(uid)))


@router.callback_query(F.data.startswith("a:"))
async def cb_answer(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = lang_of(uid)
    _, sid, n, v = cb.data.split(":")
    s = store.open_session(uid)
    await cb.answer()
    if not s or s["id"] != int(sid) or s["status"] != "active":
        return
    inst = engine.get(s["test_id"])
    item = inst.items(s["form"])[current_index(inst, s)]
    n_choices = len(inst.choices(s["form"], item, lang))
    if item["n"] == int(n) and 1 <= int(v) <= n_choices:
        s["answers"][item["n"]] = int(v)
        store.update(s["id"], answers=s["answers"])
    if current_index(inst, s) is not None:
        await show(cb, *question_view(s, lang))
        return
    result = inst.score(s["form"], s["answers"], {"sex": s["sex"] or "N", "age": s["age"] or 30})
    store.update(s["id"], result=result, status="done", finished=time.time())
    await show(cb, t(lang, "finished"), None)
    await send_report(cb.message, store.get(s["id"]), lang)
    text, markup = menu(uid)
    await cb.message.answer(text, reply_markup=markup)


def build_dispatcher(storage, enable_payments=None):
    global store, payments
    store = storage
    payments = os.environ.get("PAYMENTS") == "1" if enable_payments is None else enable_payments
    dp = Dispatcher()
    router._parent_router = None  # allow rebuilding (tests build one dispatcher per case)
    dp.include_router(router)
    return dp


async def main():
    logging.basicConfig(level=logging.INFO)
    from core.draw import LAYOUT
    from PIL import ImageFont
    if LAYOUT != ImageFont.Layout.RAQM:
        logging.warning("Pillow has no Raqm/FriBiDi: Persian, Arabic and Hindi charts will render incorrectly. "
                        "Install libfribidi (apt install libfribidi0).")
    bot = Bot(os.environ["BOT_TOKEN"], default=DefaultBotProperties(parse_mode="HTML"))
    dp = build_dispatcher(Storage(DB_PATH))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
