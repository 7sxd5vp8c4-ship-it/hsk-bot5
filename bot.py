"""
HSK Vocabulary + Radicals Telegram Bot
- SM-2 spaced repetition
- 7 task types including fill-in-the-blank sentences & dialogues
- 50 radicals mixed into early sessions, phased out as you advance
- Persistent JSON storage (swap to Supabase later if needed)
"""

import os
import json
import random
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

from vocabulary import HSK_WORDS
from radicals import RADICALS
from sentences import SENTENCES

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ["BOT_TOKEN"]
DATA_FILE      = Path("user_data.json")

DEFAULT_NEW    = 12        # new vocab words per day
RADICAL_DAILY  = 5         # radicals per day while in early phase (HSK 1-3)
RADICAL_PHASE  = 3         # stop pushing new radicals after HSK level 3
MIN_RETENTION  = 0.85
MAX_RETENTION  = 0.92
SM2_EASE_INIT  = 2.5
SM2_EASE_MIN   = 1.3


# ── PERSISTENCE ───────────────────────────────────────────────────────────────

def load_data() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data: dict, uid: int) -> dict:
    k = str(uid)
    if k not in data:
        data[k] = {
            "vocab_cards":    {},   # word_id  → SM2 state
            "radical_cards":  {},   # rad_id   → SM2 state
            "vocab_seen":     [],
            "radical_seen":   [],
            "streak":         0,
            "last_date":      None,
            "session_date":   None,
            "new_today":      0,
            "rad_new_today":  0,
            "correct_today":  0,
            "total_today":    0,
            "daily_new":      DEFAULT_NEW,
            "push_hour":      8,
            "paused":         False,
            "current_task":   None,
            "queue":          [],
            "q_idx":          0,
        }
    return data[k]


# ── SM-2 ──────────────────────────────────────────────────────────────────────

def sm2_update(card: dict, quality: int) -> dict:
    ease     = card.get("ease", SM2_EASE_INIT)
    interval = card.get("interval", 0)
    reps     = card.get("reps", 0)
    if quality >= 3:
        interval = 1 if reps == 0 else (3 if reps == 1 else round(interval * ease))
        if quality == 4:
            interval = round(interval * 1.3)
        reps += 1
    else:
        reps, interval = 0, 1
    ease = max(SM2_EASE_MIN, ease + 0.1 - (4 - quality) * (0.08 + (4 - quality) * 0.02))
    due  = (datetime.utcnow() + timedelta(days=interval)).date().isoformat()
    return {**card, "ease": round(ease, 3), "interval": interval, "reps": reps, "due": due}

def due_ids(cards: dict) -> list:
    today = datetime.utcnow().date().isoformat()
    return [wid for wid, c in cards.items() if c.get("due", "0000-00-00") <= today]

def introduce_items(seen: list, cards: dict, pool: list, n: int) -> list:
    seen_set = set(seen)
    fresh = [x for x in pool if x["id"] not in seen_set]
    chosen = fresh[:n]
    today = datetime.utcnow().date().isoformat()
    for x in chosen:
        seen.append(x["id"])
        cards[x["id"]] = {"ease": SM2_EASE_INIT, "interval": 0, "reps": 0, "due": today}
    return [x["id"] for x in chosen]


# ── TASK BUILDING ─────────────────────────────────────────────────────────────

VOCAB_TASK_TYPES   = ["recognition", "mcq_meaning", "mcq_char", "pinyin_input", "production", "fill_blank"]
RADICAL_TASK_TYPES = ["rad_recognition", "rad_mcq_meaning", "rad_mcq_char", "rad_pinyin"]

def pick_vocab_task(card: dict) -> str:
    reps = card.get("reps", 0)
    if reps == 0:
        return "recognition"
    if reps <= 2:
        return random.choice(["recognition", "mcq_meaning", "fill_blank"])
    if reps <= 5:
        return random.choice(["mcq_meaning", "pinyin_input", "fill_blank", "production"])
    return random.choice(["pinyin_input", "production", "fill_blank", "mcq_char"])

def pick_radical_task(card: dict) -> str:
    reps = card.get("reps", 0)
    if reps == 0:
        return "rad_recognition"
    if reps <= 3:
        return random.choice(["rad_recognition", "rad_mcq_meaning"])
    return random.choice(["rad_mcq_meaning", "rad_mcq_char", "rad_pinyin"])

def build_vocab_task(word_id: str, user: dict) -> dict:
    word  = next(w for w in HSK_WORDS if w["id"] == word_id)
    card  = user["vocab_cards"][word_id]
    ttype = pick_vocab_task(card)

    if ttype == "recognition":
        return {
            "type": "recognition", "word_id": word_id,
            "prompt": f"<b>{word['char']}</b>  [{word['pinyin']}]\n\nWhat does this mean?\n<i>✏️ Type in English or Russian</i>",
            "answer": word["meaning_en"],
            "alt_answers": word.get("alt_en", []) + [word["meaning_ru"]],
            "reveal": f"{word['char']} [{word['pinyin']}] — {word['meaning_en']} / {word['meaning_ru']}",
        }

    if ttype == "mcq_meaning":
        opts, ci = _mcq_options(word, HSK_WORDS, "meaning_en")
        return {
            "type": "mcq_meaning", "word_id": word_id,
            "prompt": f"<b>{word['char']}</b>  [{word['pinyin']}]\n\nChoose the correct meaning:",
            "options": opts, "correct_idx": ci,
            "reveal": f"{word['char']} [{word['pinyin']}] — {word['meaning_en']}",
        }

    if ttype == "mcq_char":
        opts, ci = _mcq_options(word, HSK_WORDS, "char")
        return {
            "type": "mcq_char", "word_id": word_id,
            "prompt": f"<b>{word['meaning_en']}</b>  [{word['pinyin']}]\n\nChoose the correct character:",
            "options": opts, "correct_idx": ci,
            "reveal": f"{word['char']} [{word['pinyin']}] — {word['meaning_en']}",
        }

    if ttype == "pinyin_input":
        return {
            "type": "pinyin_input", "word_id": word_id,
            "prompt": f"<b>{word['char']}</b>  —  {word['meaning_en']}\n\n<i>✏️ Type the pinyin with tones:</i>",
            "answer": word["pinyin"],
            "reveal": f"Pinyin: {word['pinyin']}",
        }

    if ttype == "production":
        return {
            "type": "production", "word_id": word_id,
            "prompt": f"<b>{word['meaning_en']}</b>  [{word['pinyin']}]\n\n<i>✏️ Type the Chinese character(s):</i>",
            "answer": word["char"],
            "reveal": f"Character: {word['char']}",
        }

    if ttype == "fill_blank":
        return _fill_blank_task(word, word_id)

    return {}

def _fill_blank_task(word: dict, word_id: str) -> dict:
    # Find a sentence containing this word, or generate a simple one
    candidates = [s for s in SENTENCES if word["char"] in s["sentence"]]
    if candidates:
        s = random.choice(candidates)
        blank = s["sentence"].replace(word["char"], "___", 1)
        prompt = f"Fill in the blank:\n\n<b>{blank}</b>\n<i>({s['translation']})</i>\n\n<i>✏️ Type the missing word:</i>"
        return {
            "type": "fill_blank", "word_id": word_id,
            "prompt": prompt,
            "answer": word["char"],
            "alt_answers": [],
            "reveal": f"Answer: {word['char']} [{word['pinyin']}] — {word['meaning_en']}",
        }
    else:
        # Fallback simple fill-in
        prompt = (
            f"Fill in the blank with the correct word:\n\n"
            f"<b>___ [{word['pinyin']}]</b>  means  <b>{word['meaning_en']}</b>\n\n"
            f"<i>✏️ Type the character(s):</i>"
        )
        return {
            "type": "fill_blank", "word_id": word_id,
            "prompt": prompt,
            "answer": word["char"],
            "alt_answers": [],
            "reveal": f"Answer: {word['char']} [{word['pinyin']}] — {word['meaning_en']}",
        }

def build_radical_task(rad_id: str, user: dict) -> dict:
    rad   = next(r for r in RADICALS if r["id"] == rad_id)
    card  = user["radical_cards"][rad_id]
    ttype = pick_radical_task(card)

    if ttype == "rad_recognition":
        return {
            "type": "rad_recognition", "word_id": rad_id, "is_radical": True,
            "prompt": (
                f"🧩 <b>Radical</b>\n\n"
                f"<b>{rad['radical']}</b>  (full form: {rad['full']})\n\n"
                f"What does this radical mean?\n<i>✏️ Type in English or Russian</i>"
            ),
            "answer": rad["meaning_en"],
            "alt_answers": [rad["meaning_ru"]],
            "reveal": (
                f"{rad['radical']} [{rad['pinyin']}] — {rad['meaning_en']} / {rad['meaning_ru']}\n"
                f"Example: {rad['example']} ({rad['ex_pinyin']}) — {rad['ex_en']}"
            ),
        }

    if ttype == "rad_mcq_meaning":
        opts, ci = _mcq_options(rad, RADICALS, "meaning_en")
        return {
            "type": "rad_mcq_meaning", "word_id": rad_id, "is_radical": True,
            "prompt": f"🧩 <b>Radical</b>\n\n<b>{rad['radical']}</b>  [{rad['pinyin']}]\n\nChoose the correct meaning:",
            "options": opts, "correct_idx": ci,
            "reveal": f"{rad['radical']} — {rad['meaning_en']}\nExample: {rad['example']} — {rad['ex_en']}",
        }

    if ttype == "rad_mcq_char":
        opts, ci = _mcq_options(rad, RADICALS, "radical")
        return {
            "type": "rad_mcq_char", "word_id": rad_id, "is_radical": True,
            "prompt": f"🧩 <b>Radical</b>\n\nWhich radical means <b>{rad['meaning_en']}</b>?\n[{rad['pinyin']}]",
            "options": opts, "correct_idx": ci,
            "reveal": f"{rad['radical']} [{rad['pinyin']}] — {rad['meaning_en']}",
        }

    if ttype == "rad_pinyin":
        return {
            "type": "rad_pinyin", "word_id": rad_id, "is_radical": True,
            "prompt": (
                f"🧩 <b>Radical</b>\n\n"
                f"<b>{rad['radical']}</b>  —  {rad['meaning_en']}\n\n"
                f"<i>✏️ Type the pinyin with tones:</i>"
            ),
            "answer": rad["pinyin"],
            "reveal": f"{rad['radical']} pinyin: {rad['pinyin']}",
        }

    return {}

def _mcq_options(item: dict, pool: list, field: str):
    others     = [x for x in pool if x["id"] != item["id"]]
    distractors = random.sample(others, min(3, len(others)))
    items       = [item] + distractors
    random.shuffle(items)
    correct_idx = next(i for i, x in enumerate(items) if x["id"] == item["id"])
    return [x[field] for x in items], correct_idx


# ── SESSION QUEUE ─────────────────────────────────────────────────────────────

def reset_daily(user: dict):
    today = datetime.utcnow().date().isoformat()
    if user.get("session_date") == today:
        return
    yesterday = (datetime.utcnow().date() - timedelta(1)).isoformat()
    if user.get("last_date") == yesterday:
        user["streak"] += 1
    elif user.get("last_date") != today:
        user["streak"] = 1
    user["session_date"]  = today
    user["new_today"]     = 0
    user["rad_new_today"] = 0
    user["correct_today"] = 0
    user["total_today"]   = 0

def adjust_pace(user: dict):
    if user["total_today"] < 10:
        return
    rate = user["correct_today"] / user["total_today"]
    t    = user["daily_new"]
    if rate < MIN_RETENTION:
        user["daily_new"] = max(5, t - 2)
    elif rate > MAX_RETENTION:
        user["daily_new"] = min(20, t + 1)

def current_hsk_level(user: dict) -> int:
    seen = set(user["vocab_seen"])
    for lv in range(1, 7):
        words_at_level = [w for w in HSK_WORDS if w["hsk"] == lv]
        if len([w for w in words_at_level if w["id"] in seen]) < len(words_at_level) * 0.8:
            return lv
    return 6

def build_queue(user: dict) -> list:
    queue = []

    # Vocab due reviews
    vocab_due = due_ids(user["vocab_cards"])
    for wid in vocab_due:
        queue.append({"kind": "vocab", "id": wid})

    # New vocab words
    n_new = max(0, user["daily_new"] - user["new_today"])
    new_vocab = introduce_items(user["vocab_seen"], user["vocab_cards"], HSK_WORDS, n_new)
    user["new_today"] += len(new_vocab)
    for wid in new_vocab:
        queue.append({"kind": "vocab", "id": wid})

    # Radicals — only push new ones in HSK 1-3 phase
    lv = current_hsk_level(user)
    rad_due = due_ids(user["radical_cards"])
    for rid in rad_due:
        queue.append({"kind": "radical", "id": rid})

    if lv <= RADICAL_PHASE:
        n_rad_new = max(0, RADICAL_DAILY - user["rad_new_today"])
        new_rads  = introduce_items(user["radical_seen"], user["radical_cards"], RADICALS, n_rad_new)
        user["rad_new_today"] += len(new_rads)
        for rid in new_rads:
            queue.append({"kind": "radical", "id": rid})

    # Shuffle but keep radicals spread out (not all at start)
    random.shuffle(queue)

    # Avoid same item twice in a row
    for i in range(1, len(queue)):
        if queue[i]["id"] == queue[i-1]["id"] and i + 1 < len(queue):
            for j in range(i+1, len(queue)):
                if queue[j]["id"] != queue[i-1]["id"]:
                    queue[i], queue[j] = queue[j], queue[i]
                    break

    return queue


# ── MESSAGE SENDING ───────────────────────────────────────────────────────────

async def send_task(context, task: dict, chat_id: int):
    ttype = task["type"]
    if "options" in task:
        kb = [[InlineKeyboardButton(o, callback_data=f"ans:{i}")]
              for i, o in enumerate(task["options"])]
        await context.bot.send_message(
            chat_id=chat_id, text=task["prompt"],
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id, text=task["prompt"], parse_mode="HTML"
        )

async def send_summary(context, chat_id: int, user: dict):
    correct = user["correct_today"]
    total   = user["total_today"]
    rate    = f"{correct/total*100:.0f}%" if total else "—"
    streak  = user["streak"]

    seen_vocab = set(user["vocab_seen"])
    seen_rads  = set(user["radical_seen"])
    known_vocab= sum(1 for c in user["vocab_cards"].values() if c.get("reps",0) >= 3)
    known_rads = sum(1 for c in user["radical_cards"].values() if c.get("reps",0) >= 3)

    bars = []
    for lv in range(1, 7):
        pool = [w for w in HSK_WORDS if w["hsk"] == lv]
        done = sum(1 for w in pool if w["id"] in seen_vocab)
        pct  = done / len(pool)
        bar  = "█" * round(pct * 8) + "░" * (8 - round(pct * 8))
        bars.append(f"HSK {lv}: [{bar}] {done}/{len(pool)}")

    rads_total = len(RADICALS)
    rad_bar    = "█" * round(len(seen_rads)/rads_total*8) + "░" * (8 - round(len(seen_rads)/rads_total*8))

    await context.bot.send_message(
        chat_id=chat_id,
        parse_mode="HTML",
        text=(
            f"📊 <b>Session summary</b>\n\n"
            f"✅ {correct}/{total} correct  ({rate})\n"
            f"🔥 Streak: {streak} day{'s' if streak != 1 else ''}\n"
            f"📚 Vocab mastered: {known_vocab} words\n"
            f"🧩 Radicals mastered: {known_rads}/{rads_total}\n\n"
            f"<b>HSK Progress</b>\n" + "\n".join(bars) + "\n\n"
            f"<b>Radicals</b>: [{rad_bar}] {len(seen_rads)}/{rads_total}"
        ),
    )


# ── ANSWER CHECKING ───────────────────────────────────────────────────────────

def norm(s: str) -> str:
    return s.strip().lower()

def check_text(task: dict, answer: str) -> bool:
    ttype = task["type"]
    if ttype in ("recognition", "rad_recognition"):
        targets = [task["answer"]] + task.get("alt_answers", [])
        a = norm(answer)
        return any(norm(t) in a or a in norm(t) for t in targets if t)
    if ttype in ("pinyin_input", "rad_pinyin"):
        return norm(answer) == norm(task["answer"])
    if ttype in ("production", "fill_blank"):
        return answer.strip() == task["answer"].strip()
    return False


# ── ADVANCE QUEUE ─────────────────────────────────────────────────────────────

async def advance(context, chat_id: int, uid: int, correct: bool):
    data = load_data()
    user = get_user(data, uid)

    task  = user["current_task"]
    queue = user["queue"]
    idx   = user["q_idx"]

    quality = 4 if correct else 1
    is_rad  = task.get("is_radical", False)
    wid     = task["word_id"]

    if is_rad:
        user["radical_cards"][wid] = sm2_update(user["radical_cards"].get(wid, {}), quality)
    else:
        user["vocab_cards"][wid] = sm2_update(user["vocab_cards"].get(wid, {}), quality)

    user["total_today"]   += 1
    user["correct_today"] += int(correct)

    idx += 1
    user["q_idx"] = idx

    if idx >= len(queue):
        user["current_task"]  = None
        user["last_date"]     = datetime.utcnow().date().isoformat()
        save_data(data)
        await context.bot.send_message(chat_id=chat_id, text="🎉 Session complete!")
        await send_summary(context, chat_id, user)
        return

    next_item = queue[idx]
    if next_item["kind"] == "radical":
        next_task = build_radical_task(next_item["id"], user)
    else:
        next_task = build_vocab_task(next_item["id"], user)

    user["current_task"] = next_task
    save_data(data)

    await asyncio.sleep(0.5)
    await send_task(context, next_task, chat_id)


# ── COMMAND HANDLERS ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid  = update.effective_user.id
    get_user(data, uid)
    save_data(data)
    await update.message.reply_text(
        "你好！👋  <b>HSK Trainer Bot</b>\n\n"
        "Your plan:\n"
        "• HSK 5 in <b>7 months</b>\n"
        "• HSK 6 in <b>8 months</b>\n\n"
        "What's inside:\n"
        "• Spaced repetition (SM-2) across HSK 1–6\n"
        "• 50 radicals woven into early sessions\n"
        "• 7 task types: recognition, MCQ, pinyin, writing, fill-in-the-blank\n"
        "• Daily push at your chosen time\n\n"
        "<b>Commands</b>\n"
        "/study — start today's session\n"
        "/stats — full progress report\n"
        "/settime 9 — daily reminder at 09:00 UTC\n"
        "/pause / /resume — toggle reminders\n"
        "/done — end session early\n",
        parse_mode="HTML",
    )

async def cmd_study(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid  = update.effective_user.id
    user = get_user(data, uid)
    reset_daily(user)
    adjust_pace(user)

    queue = build_queue(user)
    if not queue:
        await update.message.reply_text(
            "✨ Nothing due right now — come back tomorrow!\nUse /stats to see your progress."
        )
        save_data(data)
        return

    user["queue"] = queue
    user["q_idx"] = 0

    vocab_count = sum(1 for q in queue if q["kind"] == "vocab")
    rad_count   = sum(1 for q in queue if q["kind"] == "radical")

    await update.message.reply_text(
        f"📚 Today: <b>{len(queue)} cards</b>\n"
        f"   Vocabulary: {vocab_count}  ·  Radicals: {rad_count}\n\n"
        f"Type /done anytime to stop and save your progress.",
        parse_mode="HTML",
    )

    first_item = queue[0]
    task = (build_radical_task(first_item["id"], user)
            if first_item["kind"] == "radical"
            else build_vocab_task(first_item["id"], user))
    user["current_task"] = task
    save_data(data)
    await send_task(context, task, update.effective_chat.id)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid  = update.effective_user.id
    user = get_user(data, uid)

    seen_vocab = set(user["vocab_seen"])
    seen_rads  = set(user["radical_seen"])
    known_vocab= sum(1 for c in user["vocab_cards"].values() if c.get("reps",0) >= 3)

    lines = []
    for lv in range(1, 7):
        pool = [w for w in HSK_WORDS if w["hsk"] == lv]
        done = sum(1 for w in pool if w["id"] in seen_vocab)
        pct  = round(done / len(pool) * 100)
        bar  = "█" * round(pct/10) + "░" * (10 - round(pct/10))
        lines.append(f"HSK {lv}: [{bar}] {pct}%  ({done}/{len(pool)})")

    await update.message.reply_text(
        f"📈 <b>Your Progress</b>\n\n"
        f"🔥 Streak: {user['streak']} days\n"
        f"📚 Vocab introduced: {len(seen_vocab)}/{len(HSK_WORDS)}\n"
        f"📚 Vocab solid (3+ reps): {known_vocab}\n"
        f"🧩 Radicals seen: {len(seen_rads)}/50\n"
        f"📈 Daily new target: {user['daily_new']} words\n\n"
        + "\n".join(lines),
        parse_mode="HTML",
    )

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid  = update.effective_user.id
    user = get_user(data, uid)
    user["last_date"]    = datetime.utcnow().date().isoformat()
    user["current_task"] = None
    save_data(data)
    await send_summary(context, update.effective_chat.id, user)

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid  = update.effective_user.id
    user = get_user(data, uid)
    user["paused"] = True
    save_data(data)
    await update.message.reply_text("⏸ Daily reminders paused. /resume to turn them back on.")

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid  = update.effective_user.id
    user = get_user(data, uid)
    user["paused"] = False
    save_data(data)
    await update.message.reply_text("▶️ Reminders back on! See you tomorrow. 🌅")

async def cmd_settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid  = update.effective_user.id
    user = get_user(data, uid)
    try:
        h = int(context.args[0])
        assert 0 <= h <= 23
        user["push_hour"] = h
        save_data(data)
        await update.message.reply_text(f"⏰ Daily reminder set to {h:02d}:00 UTC.")
    except:
        await update.message.reply_text("Usage: /settime HH  (e.g. /settime 9 for 09:00 UTC)")


# ── TEXT & CALLBACK HANDLERS ──────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid  = update.effective_user.id
    user = get_user(data, uid)
    task = user.get("current_task")

    if not task or "options" in task:
        save_data(data)
        return

    correct = check_text(task, update.message.text)
    reveal  = task.get("reveal", "")

    if correct:
        await update.message.reply_text(f"✅  Correct!\n<i>{reveal}</i>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"❌  Not quite.\n<b>{reveal}</b>", parse_mode="HTML"
        )

    await advance(context, update.effective_chat.id, uid, correct)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = load_data()
    uid  = query.from_user.id
    user = get_user(data, uid)
    task = user.get("current_task")

    if not task or "options" not in task:
        return

    chosen     = int(query.data.split(":")[1])
    correct    = chosen == task["correct_idx"]
    reveal     = task.get("reveal", "")

    await query.edit_message_reply_markup(reply_markup=None)

    if correct:
        await query.message.reply_text(f"✅  Correct!\n<i>{reveal}</i>", parse_mode="HTML")
    else:
        correct_ans = task["options"][task["correct_idx"]]
        await query.message.reply_text(
            f"❌  Wrong — correct answer: <b>{correct_ans}</b>\n<i>{reveal}</i>",
            parse_mode="HTML",
        )

    await advance(context, query.message.chat_id, uid, correct)


# ── DAILY PUSH JOB ────────────────────────────────────────────────────────────

async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    data     = load_data()
    now_hour = datetime.utcnow().hour
    today    = datetime.utcnow().date().isoformat()
    for uid_str, user in data.items():
        if user.get("paused"):
            continue
        if user.get("push_hour", 8) != now_hour:
            continue
        if user.get("last_date") == today:
            continue
        due_v = len(due_ids(user["vocab_cards"]))
        due_r = len(due_ids(user["radical_cards"]))
        try:
            await context.bot.send_message(
                chat_id=int(uid_str),
                parse_mode="HTML",
                text=(
                    f"🌅 <b>Time to study!</b>\n\n"
                    f"📋 {due_v} vocab reviews + {due_r} radical reviews due\n"
                    f"🆕 ~{user['daily_new']} new words\n\n"
                    f"/study to start 💪"
                ),
            )
        except Exception as e:
            logger.warning(f"Push failed for {uid_str}: {e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    for cmd, fn in [
        ("start",   cmd_start),
        ("study",   cmd_study),
        ("stats",   cmd_stats),
        ("done",    cmd_done),
        ("pause",   cmd_pause),
        ("resume",  cmd_resume),
        ("settime", cmd_settime),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.job_queue.run_repeating(daily_push, interval=3600, first=30)
    logger.info("Bot running.")
    app.run_polling()

if __name__ == "__main__":
    main()