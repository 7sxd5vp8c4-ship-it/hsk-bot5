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

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN      = os.environ["BOT_TOKEN"]
DATA_FILE      = Path("user_data.json")
DEFAULT_NEW    = 12
RADICAL_DAILY  = 5
RADICAL_PHASE  = 3
MIN_RETENTION  = 0.85
MAX_RETENTION  = 0.92
SM2_EASE_INIT  = 2.5
SM2_EASE_MIN   = 1.3
WEAK_THRESHOLD = 3

# Round task angles: each /round sees words from a different direction
ROUND_ANGLES = {
    1: ["recognition"],
    2: ["mcq_meaning", "pinyin_input"],
    3: ["production", "mcq_char"],
}


# PERSISTENCE

def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, uid):
    k = str(uid)
    if k not in data:
        data[k] = {
            "vocab_cards": {}, "radical_cards": {},
            "vocab_seen": [], "radical_seen": [],
            "streak": 0, "last_date": None, "session_date": None,
            "new_today": 0, "rad_new_today": 0,
            "correct_today": 0, "total_today": 0, "errors_today": 0,
            "daily_new": DEFAULT_NEW, "push_hour": 8, "paused": False,
            "current_task": None,
            "queue": [], "q_idx": 0,
            "today_ids": [], "today_rad_ids": [],
            "round_num": 0, "round_queue": [], "round_idx": 0,
            "in_round": False, "error_counts": {},
        }
    return data[k]


# SM-2

def sm2_update(card, quality):
    ease = card.get("ease", SM2_EASE_INIT)
    interval = card.get("interval", 0)
    reps = card.get("reps", 0)
    if quality >= 3:
        interval = 1 if reps == 0 else (3 if reps == 1 else round(interval * ease))
        if quality == 4:
            interval = round(interval * 1.3)
        reps += 1
    else:
        reps, interval = 0, 1
    ease = max(SM2_EASE_MIN, ease + 0.1 - (4 - quality) * (0.08 + (4 - quality) * 0.02))
    due = (datetime.utcnow() + timedelta(days=interval)).date().isoformat()
    return {**card, "ease": round(ease, 3), "interval": interval, "reps": reps, "due": due}

def due_ids(cards):
    today = datetime.utcnow().date().isoformat()
    return [wid for wid, c in cards.items() if c.get("due", "0000-00-00") <= today]

def introduce_items(seen, cards, pool, n):
    seen_set = set(seen)
    chosen = [x for x in pool if x["id"] not in seen_set][:n]
    today = datetime.utcnow().date().isoformat()
    for x in chosen:
        seen.append(x["id"])
        cards[x["id"]] = {"ease": SM2_EASE_INIT, "interval": 0, "reps": 0, "due": today}
    return [x["id"] for x in chosen]


# WEAK CARDS

def get_weak_ids(user):
    ec = user.get("error_counts", {})
    return [wid for wid, cnt in ec.items() if cnt >= WEAK_THRESHOLD and wid in user["vocab_cards"]]


# ROUND QUEUE BUILDER

def build_round_queue(user):
    rn = user["round_num"]
    today_ids = list(user["today_ids"])
    weak_ids = [w for w in get_weak_ids(user) if w not in today_ids]
    rad_ids = list(user["today_rad_ids"])

    all_vocab = today_ids + weak_ids
    random.shuffle(all_vocab)

    task_pool = ROUND_ANGLES.get(rn, ["recognition", "mcq_meaning", "pinyin_input", "production", "fill_blank", "mcq_char"])

    queue = []
    for wid in all_vocab:
        queue.append({"kind": "vocab", "id": wid, "forced_type": random.choice(task_pool)})

    if rn <= 2:
        for rid in rad_ids:
            queue.append({"kind": "radical", "id": rid, "forced_type": None})
        random.shuffle(queue)

    return queue


# TASK BUILDERS

def pick_vocab_task(card):
    reps = card.get("reps", 0)
    if reps == 0: return "recognition"
    if reps <= 2: return random.choice(["recognition", "mcq_meaning", "fill_blank"])
    if reps <= 5: return random.choice(["mcq_meaning", "pinyin_input", "fill_blank", "production"])
    return random.choice(["pinyin_input", "production", "fill_blank", "mcq_char"])

def pick_radical_task(card):
    reps = card.get("reps", 0)
    if reps == 0: return "rad_recognition"
    if reps <= 3: return random.choice(["rad_recognition", "rad_mcq_meaning"])
    return random.choice(["rad_mcq_meaning", "rad_mcq_char", "rad_pinyin"])

def mcq_options(item, pool, field):
    others = [x for x in pool if x["id"] != item["id"]]
    opts = [item] + random.sample(others, min(3, len(others)))
    random.shuffle(opts)
    ci = next(i for i, x in enumerate(opts) if x["id"] == item["id"])
    return [x[field] for x in opts], ci

def build_vocab_task(word_id, user, forced_type=None):
    word = next((w for w in HSK_WORDS if w["id"] == word_id), None)
    if not word: return {}
    card = user["vocab_cards"].get(word_id, {})
    t = forced_type or pick_vocab_task(card)

    if t == "recognition":
        return {"type": t, "word_id": word_id,
            "prompt": f"<b>{word['char']}</b>  [{word['pinyin']}]\n\nWhat does this mean?\nType in English or Russian",
            "answer": word["meaning_en"], "alt_answers": word.get("alt_en", []) + [word["meaning_ru"]],
            "reveal": f"{word['char']} [{word['pinyin']}] - {word['meaning_en']} / {word['meaning_ru']}"}

    if t == "mcq_meaning":
        opts, ci = mcq_options(word, HSK_WORDS, "meaning_en")
        return {"type": t, "word_id": word_id,
            "prompt": f"<b>{word['char']}</b>  [{word['pinyin']}]\n\nChoose the correct meaning:",
            "options": opts, "correct_idx": ci,
            "reveal": f"{word['char']} [{word['pinyin']}] - {word['meaning_en']}"}

    if t == "mcq_char":
        opts, ci = mcq_options(word, HSK_WORDS, "char")
        return {"type": t, "word_id": word_id,
            "prompt": f"<b>{word['meaning_en']}</b>  [{word['pinyin']}]\n\nChoose the correct character:",
            "options": opts, "correct_idx": ci,
            "reveal": f"{word['char']} [{word['pinyin']}] - {word['meaning_en']}"}

    if t == "pinyin_input":
        return {"type": t, "word_id": word_id,
            "prompt": f"<b>{word['char']}</b>  -  {word['meaning_en']}\n\nType the pinyin with tones:",
            "answer": word["pinyin"],
            "reveal": f"Pinyin: {word['pinyin']}"}

    if t == "production":
        return {"type": t, "word_id": word_id,
            "prompt": f"<b>{word['meaning_en']}</b>  [{word['pinyin']}]\n\nType the Chinese character(s):",
            "answer": word["char"],
            "reveal": f"Character: {word['char']}"}

    if t == "fill_blank":
        candidates = [s for s in SENTENCES if word["char"] in s["sentence"]]
        if candidates:
            s = random.choice(candidates)
            blank = s["sentence"].replace(word["char"], "___", 1)
            return {"type": t, "word_id": word_id,
                "prompt": f"Fill in the blank:\n\n<b>{blank}</b>\n({s['translation']})\n\nType the missing word:",
                "answer": word["char"], "alt_answers": [],
                "reveal": f"Answer: {word['char']} [{word['pinyin']}] - {word['meaning_en']}"}
        return {"type": t, "word_id": word_id,
            "prompt": f"<b>___ [{word['pinyin']}]</b> means <b>{word['meaning_en']}</b>\n\nType the character(s):",
            "answer": word["char"], "alt_answers": [],
            "reveal": f"Answer: {word['char']} [{word['pinyin']}] - {word['meaning_en']}"}
    return {}

def build_radical_task(rad_id, user, forced_type=None):
    rad = next((r for r in RADICALS if r["id"] == rad_id), None)
    if not rad: return {}
    card = user["radical_cards"].get(rad_id, {})
    t = forced_type or pick_radical_task(card)

    if t == "rad_recognition":
        return {"type": t, "word_id": rad_id, "is_radical": True,
            "prompt": f"Radical\n\n<b>{rad['radical']}</b>  (full: {rad['full']})\n\nWhat does this mean?\nType in English or Russian",
            "answer": rad["meaning_en"], "alt_answers": [rad["meaning_ru"]],
            "reveal": f"{rad['radical']} [{rad['pinyin']}] - {rad['meaning_en']} / {rad['meaning_ru']}\nExample: {rad['example']} ({rad['ex_pinyin']}) - {rad['ex_en']}"}

    if t == "rad_mcq_meaning":
        opts, ci = mcq_options(rad, RADICALS, "meaning_en")
        return {"type": t, "word_id": rad_id, "is_radical": True,
            "prompt": f"Radical\n\n<b>{rad['radical']}</b>  [{rad['pinyin']}]\n\nChoose the correct meaning:",
            "options": opts, "correct_idx": ci,
            "reveal": f"{rad['radical']} - {rad['meaning_en']}\nExample: {rad['example']} - {rad['ex_en']}"}

    if t == "rad_mcq_char":
        opts, ci = mcq_options(rad, RADICALS, "radical")
        return {"type": t, "word_id": rad_id, "is_radical": True,
            "prompt": f"Radical\n\nWhich radical means <b>{rad['meaning_en']}</b>?\n[{rad['pinyin']}]",
            "options": opts, "correct_idx": ci,
            "reveal": f"{rad['radical']} [{rad['pinyin']}] - {rad['meaning_en']}"}

    if t == "rad_pinyin":
        return {"type": t, "word_id": rad_id, "is_radical": True,
            "prompt": f"Radical\n\n<b>{rad['radical']}</b>  -  {rad['meaning_en']}\n\nType the pinyin with tones:",
            "answer": rad["pinyin"],
            "reveal": f"{rad['radical']} pinyin: {rad['pinyin']}"}
    return {}


# SESSION

def reset_daily(user):
    today = datetime.utcnow().date().isoformat()
    if user.get("session_date") == today:
        return
    yesterday = (datetime.utcnow().date() - timedelta(1)).isoformat()
    if user.get("last_date") == yesterday:
        user["streak"] += 1
    elif user.get("last_date") != today:
        user["streak"] = 1
    user.update({"session_date": today, "new_today": 0, "rad_new_today": 0,
                 "correct_today": 0, "total_today": 0, "errors_today": 0,
                 "today_ids": [], "today_rad_ids": [], "round_num": 0, "in_round": False})

def adjust_pace(user):
    if user["total_today"] < 10: return
    rate = user["correct_today"] / user["total_today"]
    t = user["daily_new"]
    if rate < MIN_RETENTION: user["daily_new"] = max(5, t - 2)
    elif rate > MAX_RETENTION: user["daily_new"] = min(20, t + 1)

def current_hsk_level(user):
    seen = set(user["vocab_seen"])
    for lv in range(1, 7):
        pool = [w for w in HSK_WORDS if w["hsk"] == lv]
        if len([w for w in pool if w["id"] in seen]) < len(pool) * 0.8:
            return lv
    return 6

def build_main_queue(user):
    queue = []
    for wid in due_ids(user["vocab_cards"]):
        queue.append({"kind": "vocab", "id": wid, "forced_type": None})
        if wid not in user["today_ids"]: user["today_ids"].append(wid)

    new_vocab = introduce_items(user["vocab_seen"], user["vocab_cards"], HSK_WORDS, max(0, user["daily_new"] - user["new_today"]))
    user["new_today"] += len(new_vocab)
    for wid in new_vocab:
        queue.append({"kind": "vocab", "id": wid, "forced_type": None})
        if wid not in user["today_ids"]: user["today_ids"].append(wid)

    for rid in due_ids(user["radical_cards"]):
        queue.append({"kind": "radical", "id": rid, "forced_type": None})
        if rid not in user["today_rad_ids"]: user["today_rad_ids"].append(rid)

    if current_hsk_level(user) <= RADICAL_PHASE:
        new_rads = introduce_items(user["radical_seen"], user["radical_cards"], RADICALS, max(0, RADICAL_DAILY - user["rad_new_today"]))
        user["rad_new_today"] += len(new_rads)
        for rid in new_rads:
            queue.append({"kind": "radical", "id": rid, "forced_type": None})
            if rid not in user["today_rad_ids"]: user["today_rad_ids"].append(rid)

    random.shuffle(queue)
    return queue


# SENDING

async def send_task(context, task, chat_id):
    if "options" in task:
        kb = [[InlineKeyboardButton(o, callback_data=f"ans:{i}")] for i, o in enumerate(task["options"])]
        await context.bot.send_message(chat_id=chat_id, text=task["prompt"],
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await context.bot.send_message(chat_id=chat_id, text=task["prompt"], parse_mode="HTML")

async def send_summary(context, chat_id, user, is_round=False):
    correct = user["correct_today"]
    total = user["total_today"]
    rate = f"{correct/total*100:.0f}%" if total else "n/a"
    weak = len(get_weak_ids(user))
    seen_vocab = set(user["vocab_seen"])

    bars = []
    for lv in range(1, 7):
        pool = [w for w in HSK_WORDS if w["hsk"] == lv]
        done = sum(1 for w in pool if w["id"] in seen_vocab)
        pct = done / len(pool)
        bar = chr(9608) * round(pct * 8) + chr(9617) * (8 - round(pct * 8))
        bars.append(f"HSK {lv}: [{bar}] {done}/{len(pool)}")

    label = f"Round {user['round_num']} complete" if is_round else "Session complete"
    hint = "\n\nUse /round for another practice angle" if user["today_ids"] else ""

    await context.bot.send_message(chat_id=chat_id, parse_mode="HTML",
        text=(f"<b>{label}</b>\n\n"
              f"Today: {correct}/{total} correct ({rate})\n"
              f"Streak: {user['streak']} days\n"
              f"Weak cards: {weak}\n\n"
              f"<b>HSK Progress</b>\n" + "\n".join(bars) + hint))


# ANSWER CHECKING

def norm(s): return s.strip().lower()

def check_text(task, answer):
    t = task["type"]
    if t in ("recognition", "rad_recognition"):
        targets = [task["answer"]] + task.get("alt_answers", [])
        a = norm(answer)
        return any(norm(x) in a or a in norm(x) for x in targets if x)
    if t in ("pinyin_input", "rad_pinyin"):
        return norm(answer) == norm(task["answer"])
    if t in ("production", "fill_blank"):
        return answer.strip() == task["answer"].strip()
    return False


# ADVANCE

async def advance(context, chat_id, uid, correct):
    data = load_data()
    user = get_user(data, uid)
    task = user["current_task"]
    wid = task["word_id"]
    is_rad = task.get("is_radical", False)
    quality = 4 if correct else 1

    if not correct:
        ec = user.setdefault("error_counts", {})
        ec[wid] = ec.get(wid, 0) + 1
        user["errors_today"] = user.get("errors_today", 0) + 1

    if is_rad:
        user["radical_cards"][wid] = sm2_update(user["radical_cards"].get(wid, {}), quality)
    else:
        user["vocab_cards"][wid] = sm2_update(user["vocab_cards"].get(wid, {}), quality)

    user["total_today"] += 1
    user["correct_today"] += int(correct)

    in_round = user.get("in_round", False)
    if in_round:
        idx = user["round_idx"] + 1
        user["round_idx"] = idx
        queue = user["round_queue"]
        if idx >= len(queue):
            user["current_task"] = None
            user["in_round"] = False
            save_data(data)
            await send_summary(context, chat_id, user, is_round=True)
            return
        next_item = queue[idx]
    else:
        idx = user["q_idx"] + 1
        user["q_idx"] = idx
        queue = user["queue"]
        if idx >= len(queue):
            user["current_task"] = None
            user["last_date"] = datetime.utcnow().date().isoformat()
            save_data(data)
            await send_summary(context, chat_id, user, is_round=False)
            return
        next_item = queue[idx]

    ft = next_item.get("forced_type")
    next_task = (build_radical_task(next_item["id"], user, ft)
                 if next_item["kind"] == "radical"
                 else build_vocab_task(next_item["id"], user, ft))
    user["current_task"] = next_task
    save_data(data)
    await asyncio.sleep(0.4)
    await send_task(context, next_task, chat_id)


# COMMANDS

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    get_user(data, update.effective_user.id)
    save_data(data)
    await update.message.reply_text(
        "<b>HSK Trainer Bot</b>\n\n"
        "Target: HSK 5 in 7 months, HSK 6 in 8 months\n\n"
        "<b>Commands</b>\n"
        "/study - start today's session\n"
        "/round - extra practice round (same words, new angle)\n"
        "/stats - your full progress\n"
        "/settime 8 - daily reminder at 08:00 UTC\n"
        "/pause and /resume - toggle reminders\n"
        "/done - stop session early\n\n"
        "<b>How rounds work</b>\n"
        "Round 1: character shown - type meaning\n"
        "Round 2: pinyin shown - MCQ or type character\n"
        "Round 3: meaning shown - type character\n"
        "Round 4+: full random mix\n\n"
        "Each /round covers today's words plus any cards you keep getting wrong.",
        parse_mode="HTML")

async def cmd_study(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    user = get_user(data, uid)
    reset_daily(user)
    adjust_pace(user)

    queue = build_main_queue(user)
    if not queue:
        await update.message.reply_text(
            "Nothing due right now.\nUse /round to drill today's words, or /stats to check progress.")
        save_data(data)
        return

    user["queue"] = queue
    user["q_idx"] = 0
    user["in_round"] = False

    vc = sum(1 for q in queue if q["kind"] == "vocab")
    rc = sum(1 for q in queue if q["kind"] == "radical")
    wc = len(get_weak_ids(user))

    await update.message.reply_text(
        f"<b>Today: {len(queue)} cards</b>\n"
        f"Vocabulary: {vc}  |  Radicals: {rc}\n"
        f"Weak cards: {wc}\n\n"
        f"After this, use /round for extra practice.", parse_mode="HTML")

    first = queue[0]
    task = (build_radical_task(first["id"], user, first.get("forced_type"))
            if first["kind"] == "radical"
            else build_vocab_task(first["id"], user, first.get("forced_type")))
    user["current_task"] = task
    save_data(data)
    await send_task(context, task, update.effective_chat.id)

async def cmd_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    user = get_user(data, uid)

    if not user["today_ids"] and not user["today_rad_ids"]:
        await update.message.reply_text("No words studied today yet. Start with /study first!")
        save_data(data)
        return

    user["round_num"] += 1
    rn = user["round_num"]
    queue = build_round_queue(user)

    if not queue:
        await update.message.reply_text("Nothing to practice. Do /study first.")
        save_data(data)
        return

    user["round_queue"] = queue
    user["round_idx"] = 0
    user["in_round"] = True

    weak_count = len(get_weak_ids(user))
    angle = {1: "character shown, type meaning",
             2: "pinyin shown, MCQ or type character",
             3: "meaning shown, type character"}.get(rn, "full random mix")

    await update.message.reply_text(
        f"<b>Round {rn}</b>  -  {len(queue)} cards\n"
        f"Angle: {angle}\n"
        f"Includes {weak_count} weak card(s)\n\n"
        f"/done to stop anytime.", parse_mode="HTML")

    first = queue[0]
    task = (build_radical_task(first["id"], user, first.get("forced_type"))
            if first["kind"] == "radical"
            else build_vocab_task(first["id"], user, first.get("forced_type")))
    user["current_task"] = task
    save_data(data)
    await send_task(context, task, update.effective_chat.id)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    seen_vocab = set(user["vocab_seen"])
    seen_rads = set(user["radical_seen"])
    known = sum(1 for c in user["vocab_cards"].values() if c.get("reps", 0) >= 3)
    weak = len(get_weak_ids(user))

    lines = []
    for lv in range(1, 7):
        pool = [w for w in HSK_WORDS if w["hsk"] == lv]
        done = sum(1 for w in pool if w["id"] in seen_vocab)
        pct = round(done / len(pool) * 100)
        bar = chr(9608) * round(pct / 10) + chr(9617) * (10 - round(pct / 10))
        lines.append(f"HSK {lv}: [{bar}] {pct}%  ({done}/{len(pool)})")

    await update.message.reply_text(
        f"<b>Your Progress</b>\n\n"
        f"Streak: {user['streak']} days\n"
        f"Vocab introduced: {len(seen_vocab)}/{len(HSK_WORDS)}\n"
        f"Vocab solid (3+ correct): {known}\n"
        f"Weak cards (3+ errors): {weak}\n"
        f"Radicals seen: {len(seen_rads)}/50\n"
        f"Daily new target: {user['daily_new']}/day\n\n"
        + "\n".join(lines), parse_mode="HTML")

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    user = get_user(data, uid)
    user["last_date"] = datetime.utcnow().date().isoformat()
    user["current_task"] = None
    user["in_round"] = False
    save_data(data)
    await send_summary(context, update.effective_chat.id, user)

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    user["paused"] = True
    save_data(data)
    await update.message.reply_text("Reminders paused. /resume to turn back on.")

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    user["paused"] = False
    save_data(data)
    await update.message.reply_text("Reminders back on!")

async def cmd_settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    try:
        h = int(context.args[0])
        assert 0 <= h <= 23
        user["push_hour"] = h
        save_data(data)
        await update.message.reply_text(f"Daily reminder set to {h:02d}:00 UTC.")
    except:
        await update.message.reply_text("Usage: /settime HH  e.g. /settime 9")


# HANDLERS

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    user = get_user(data, uid)
    task = user.get("current_task")
    if not task or "options" in task:
        save_data(data)
        return
    correct = check_text(task, update.message.text)
    reveal = task.get("reveal", "")
    if correct:
        await update.message.reply_text(f"Correct!\n<i>{reveal}</i>", parse_mode="HTML")
    else:
        await update.message.reply_text(f"Not quite.\n<b>{reveal}</b>", parse_mode="HTML")
    await advance(context, update.effective_chat.id, uid, correct)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    uid = query.from_user.id
    user = get_user(data, uid)
    task = user.get("current_task")
    if not task or "options" not in task:
        return
    chosen = int(query.data.split(":")[1])
    correct = chosen == task["correct_idx"]
    reveal = task.get("reveal", "")
    await query.edit_message_reply_markup(reply_markup=None)
    if correct:
        await query.message.reply_text(f"Correct!\n<i>{reveal}</i>", parse_mode="HTML")
    else:
        ans = task["options"][task["correct_idx"]]
        await query.message.reply_text(f"Wrong - correct: <b>{ans}</b>\n<i>{reveal}</i>", parse_mode="HTML")
    await advance(context, query.message.chat_id, uid, correct)


# DAILY PUSH

async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    now_hour = datetime.utcnow().hour
    today = datetime.utcnow().date().isoformat()
    for uid_str, user in data.items():
        if user.get("paused"): continue
        if user.get("push_hour", 8) != now_hour: continue
        if user.get("last_date") == today: continue
        due_v = len(due_ids(user["vocab_cards"]))
        due_r = len(due_ids(user["radical_cards"]))
        try:
            await context.bot.send_message(chat_id=int(uid_str), parse_mode="HTML",
                text=f"<b>Time to study!</b>\n\n{due_v} vocab + {due_r} radical reviews\n~{user['daily_new']} new words\n\n/study to start")
        except Exception as e:
            logger.warning(f"Push failed for {uid_str}: {e}")


# MAIN

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    for cmd, fn in [("start", cmd_start), ("study", cmd_study), ("round", cmd_round),
                    ("stats", cmd_stats), ("done", cmd_done), ("pause", cmd_pause),
                    ("resume", cmd_resume), ("settime", cmd_settime)]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.job_queue.run_repeating(daily_push, interval=3600, first=30)
    logger.info("Bot running.")
    app.run_polling()

if __name__ == "__main__":
    main()
