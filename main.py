"""
🎮 GRAM Bot v4.0
- В чатах: б/баланс, топ, переводы, дуэли, мины, казна
- В ЛС: всё + профиль, магазин, промокоды, админ-панель
- Бонус в чате → ссылка на ЛС → автозабор по deep link
"""

import sqlite3
import json
import random
import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# =====================================================================
# ⚙️ КОНФИГУРАЦИЯ  — измени под себя
# =====================================================================

BOT_TOKEN           = "8490098380:AAF087A6UMDeC6Dd_uZb7bAxT8VsGCcS8yI"
BOT_USERNAME        = "gramvalybot"   # без @, нужен для deep-link бонуса
TELEGRAM_CHANNEL    = "https://t.me/gramvaly"
TELEGRAM_CHANNEL_ID = "@gramvaly"
ADMIN_IDS           = [8526401545]           # ← свой Telegram ID

STARTING_BALANCE     = 1000
DAILY_BONUS_MIN      = 2500
DAILY_BONUS_MAX      = 5000
DAILY_BONUS_COOLDOWN = 86400  # 24 ч

SHOP_ITEMS = {
    '100k':  {'grams': 100_000,   'stars': 15},
    '204k':  {'grams': 204_000,   'stars': 30},
    '525k':  {'grams': 525_000,   'stars': 100},
    '1.15m': {'grams': 1_150_000, 'stars': 250},
    '2.3m':  {'grams': 2_300_000, 'stars': 500},
    '6.25m': {'grams': 6_250_000, 'stars': 1000},
}

STAT_NAMES  = {'health':'Здоровье','strength':'Сила','endurance':'Выносливость',
               'block':'Блок','charisma':'Харизма','intuition':'Интуиция','speed':'Скорость'}
STAT_EMOJIS = {'health':'❤️','strength':'💪','endurance':'⚡','block':'🛡️',
               'charisma':'✨','intuition':'🔮','speed':'💨'}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =====================================================================
# 💾 БАЗА ДАННЫХ
# =====================================================================

class Database:
    def __init__(self, db_path='game_data.db'):
        self.conn   = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                balance    INTEGER DEFAULT 0,
                level      INTEGER DEFAULT 1,
                exp        INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS stats (
                user_id   INTEGER PRIMARY KEY,
                health    INTEGER DEFAULT 9,
                strength  INTEGER DEFAULT 12,
                endurance INTEGER DEFAULT 9,
                block     INTEGER DEFAULT 8,
                charisma  INTEGER DEFAULT 8,
                intuition INTEGER DEFAULT 7,
                speed     INTEGER DEFAULT 6
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id    INTEGER PRIMARY KEY,
                subscribed INTEGER DEFAULT 0,
                checked_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS bonuses (
                bonus_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                amount     INTEGER,
                type       TEXT,
                claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS duels (
                duel_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                player1_id INTEGER,
                player2_id INTEGER,
                winner_id  INTEGER,
                reward     INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS minesweeper_games (
                game_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                field      TEXT,
                revealed   TEXT,
                amount     INTEGER,
                status     TEXT DEFAULT 'active',
                safe_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS treasuries (
                chat_id    INTEGER PRIMARY KEY,
                owner_id   INTEGER,
                balance    INTEGER DEFAULT 0,
                reward     INTEGER DEFAULT 1000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS treasury_members (
                user_id  INTEGER,
                chat_id  INTEGER,
                rewarded INTEGER DEFAULT 0,
                UNIQUE(user_id, chat_id)
            );
            CREATE TABLE IF NOT EXISTS promo_codes (
                code       TEXT PRIMARY KEY,
                grams      INTEGER NOT NULL,
                max_uses   INTEGER NOT NULL,
                used_count INTEGER DEFAULT 0,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active  INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS promo_uses (
                use_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                code    TEXT,
                user_id INTEGER,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, user_id)
            );
        ''')
        self.conn.commit()

    # --- пользователи ---
    def create_user(self, user_id, username):
        try:
            self.cursor.execute(
                'INSERT INTO users (user_id,username,balance) VALUES (?,?,?)',
                (user_id, username, STARTING_BALANCE))
            self.cursor.execute('INSERT INTO stats (user_id) VALUES (?)', (user_id,))
            self.cursor.execute('INSERT INTO subscriptions (user_id) VALUES (?)', (user_id,))
            self.conn.commit(); return True
        except: return False

    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id=?', (user_id,))
        return self.cursor.fetchone()

    def user_exists(self, uid): return self.get_user(uid) is not None

    def get_balance(self, uid):
        self.cursor.execute('SELECT balance FROM users WHERE user_id=?', (uid,))
        r = self.cursor.fetchone(); return r[0] if r else 0

    def add_balance(self, uid, amt):
        self.cursor.execute('UPDATE users SET balance=balance+? WHERE user_id=?', (amt, uid))
        self.conn.commit()

    def subtract_balance(self, uid, amt):
        self.cursor.execute('UPDATE users SET balance=balance-? WHERE user_id=?', (amt, uid))
        self.conn.commit()

    def get_stats(self, uid):
        self.cursor.execute('SELECT * FROM stats WHERE user_id=?', (uid,))
        r = self.cursor.fetchone()
        if r: return {'health':r[1],'strength':r[2],'endurance':r[3],
                      'block':r[4],'charisma':r[5],'intuition':r[6],'speed':r[7]}
        return None

    def get_last_bonus(self, uid):
        self.cursor.execute(
            'SELECT claimed_at FROM bonuses WHERE user_id=? ORDER BY claimed_at DESC LIMIT 1', (uid,))
        r = self.cursor.fetchone(); return r[0] if r else None

    def claim_bonus(self, uid, amt):
        self.cursor.execute('INSERT INTO bonuses (user_id,amount,type) VALUES (?,?,?)', (uid,amt,'daily'))
        self.conn.commit()

    def set_subscribed(self, uid, val):
        self.cursor.execute(
            'UPDATE subscriptions SET subscribed=?,checked_at=CURRENT_TIMESTAMP WHERE user_id=?', (val,uid))
        self.conn.commit()

    def get_top_users(self, limit=10):
        self.cursor.execute(
            'SELECT user_id,username,balance,level FROM users ORDER BY balance DESC LIMIT ?', (limit,))
        return self.cursor.fetchall()

    def get_all_users(self):
        self.cursor.execute('SELECT user_id FROM users')
        return [r[0] for r in self.cursor.fetchall()]

    def get_user_count(self):
        self.cursor.execute('SELECT COUNT(*) FROM users'); return self.cursor.fetchone()[0]

    def find_by_username(self, uname):
        self.cursor.execute(
            'SELECT user_id,username FROM users WHERE LOWER(username)=?', (uname.lower(),))
        return self.cursor.fetchone()

    def add_duel(self, p1, p2, winner, reward):
        try:
            self.cursor.execute(
                'INSERT INTO duels (player1_id,player2_id,winner_id,reward) VALUES (?,?,?,?)',
                (p1,p2,winner,reward))
            self.conn.commit()
        except Exception as e: logger.error(e)

    # --- казна ---
    def get_treasury(self, chat_id):
        self.cursor.execute('SELECT * FROM treasuries WHERE chat_id=?', (chat_id,))
        return self.cursor.fetchone()

    def create_treasury(self, chat_id, owner_id):
        try:
            self.cursor.execute('INSERT INTO treasuries (chat_id,owner_id) VALUES (?,?)', (chat_id,owner_id))
            self.conn.commit(); return True
        except: return False

    def add_to_treasury(self, chat_id, amt):
        self.cursor.execute('UPDATE treasuries SET balance=balance+? WHERE chat_id=?', (amt,chat_id))
        self.conn.commit()

    def treasury_member_rewarded(self, uid, chat_id):
        self.cursor.execute('SELECT rewarded FROM treasury_members WHERE user_id=? AND chat_id=?', (uid,chat_id))
        r = self.cursor.fetchone(); return r and r[0]

    def reward_treasury_member(self, uid, chat_id):
        try:
            self.cursor.execute('INSERT INTO treasury_members (user_id,chat_id,rewarded) VALUES (?,?,1)', (uid,chat_id))
        except:
            self.cursor.execute('UPDATE treasury_members SET rewarded=1 WHERE user_id=? AND chat_id=?', (uid,chat_id))
        self.cursor.execute('UPDATE treasuries SET balance=balance-reward WHERE chat_id=?', (chat_id,))
        self.conn.commit()

    # --- мины ---
    def create_mine_game(self, uid, field, amount):
        self.cursor.execute(
            'INSERT INTO minesweeper_games (user_id,field,revealed,amount) VALUES (?,?,?,?)',
            (uid, json.dumps(field), json.dumps([False]*25), amount))
        self.conn.commit(); return self.cursor.lastrowid

    def get_mine_game(self, game_id):
        self.cursor.execute('SELECT * FROM minesweeper_games WHERE game_id=?', (game_id,))
        return self.cursor.fetchone()

    def get_active_mine_game(self, uid):
        self.cursor.execute(
            'SELECT * FROM minesweeper_games WHERE user_id=? AND status="active" ORDER BY game_id DESC LIMIT 1', (uid,))
        return self.cursor.fetchone()

    def update_mine_game(self, game_id, revealed, status, safe_count):
        self.cursor.execute(
            'UPDATE minesweeper_games SET revealed=?,status=?,safe_count=? WHERE game_id=?',
            (json.dumps(revealed), status, safe_count, game_id))
        self.conn.commit()

    # --- промокоды ---
    def create_promo(self, code, grams, max_uses, by):
        try:
            self.cursor.execute(
                'INSERT INTO promo_codes (code,grams,max_uses,created_by) VALUES (?,?,?,?)',
                (code,grams,max_uses,by))
            self.conn.commit(); return True
        except Exception as e: logger.error(e); return False

    def get_promo(self, code):
        self.cursor.execute('SELECT * FROM promo_codes WHERE code=?', (code,))
        return self.cursor.fetchone()

    def use_promo(self, code, uid):
        p = self.get_promo(code)
        if not p: return False,"❌ Промокод не найден",0
        _,grams,mu,used,_,_,active = p
        if not active: return False,"❌ Промокод больше не активен",0
        if used >= mu: return False,"❌ Промокод исчерпан",0
        self.cursor.execute('SELECT use_id FROM promo_uses WHERE code=? AND user_id=?', (code,uid))
        if self.cursor.fetchone(): return False,"❌ Ты уже использовал этот промокод",0
        try:
            self.cursor.execute('INSERT INTO promo_uses (code,user_id) VALUES (?,?)', (code,uid))
            self.cursor.execute('UPDATE promo_codes SET used_count=used_count+1 WHERE code=?', (code,))
            if used+1 >= mu:
                self.cursor.execute('UPDATE promo_codes SET is_active=0 WHERE code=?', (code,))
            self.conn.commit()
            self.add_balance(uid, grams)
            return True,f"✅ Промокод активирован!\n💰 +{grams:,} GRAM начислено!",grams
        except Exception as e: logger.error(e); return False,"❌ Ошибка",0

    def get_all_promos(self):
        self.cursor.execute('SELECT * FROM promo_codes ORDER BY created_at DESC')
        return self.cursor.fetchall()

    def deactivate_promo(self, code):
        self.cursor.execute('UPDATE promo_codes SET is_active=0 WHERE code=?', (code,))
        self.conn.commit()


db = Database()

# =====================================================================
# 🎮 ИГРОВАЯ ЛОГИКА
# =====================================================================

class GameLogic:
    @staticmethod
    def generate_field():
        field = [0]*25
        for pos in random.sample(range(25), random.randint(3,7)):
            field[pos] = 1
        return field

    @staticmethod
    def mines_keyboard(game_id, revealed, field=None, show_mines=False):
        rows = []
        for row in range(5):
            btns = []
            for col in range(5):
                idx = row*5+col
                if revealed[idx]:
                    btns.append(InlineKeyboardButton(text="✅", callback_data="ms_skip"))
                elif show_mines and field and field[idx]==1:
                    btns.append(InlineKeyboardButton(text="💣", callback_data="ms_skip"))
                else:
                    btns.append(InlineKeyboardButton(text="❓", callback_data=f"ms_{game_id}_{idx}"))
            rows.append(btns)
        rows.append([InlineKeyboardButton(text="💸 Забрать выигрыш", callback_data=f"ms_co_{game_id}")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @staticmethod
    def calc_mult(safe_count):
        return round(1.0 + safe_count * 0.3, 2)

    @staticmethod
    def duel_winner(s1, s2):
        hp1, hp2 = s1['health']*10, s2['health']*10
        for _ in range(20):
            hp2 -= max(1, s1['strength']*10 + random.randint(-5,15) - s2['block']*5)
            if hp2 <= 0: return 1
            hp1 -= max(1, s2['strength']*10 + random.randint(-5,15) - s1['block']*5)
            if hp1 <= 0: return 2
        return 1 if hp1 > hp2 else 2

    @staticmethod
    def gen_promo_code():
        adj  = ['MEGA','SUPER','GOLD','EPIC','LUCKY','GRAM','FIRE','STAR','WIN','RICH']
        noun = ['BOOST','DROP','GIFT','BONUS','CASH','LOOT','PRIZE','GRAMS','PAY','FUND']
        return f"{random.choice(adj)}{random.choice(noun)}{random.randint(10,99)}"

    @staticmethod
    def random_bonus():
        return random.randint(DAILY_BONUS_MIN, DAILY_BONUS_MAX)


# =====================================================================
# 🤖 БОТ
# =====================================================================

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# Активные запросы дуэлей: {opponent_id: {challenger_id, name, amount}}
duel_requests: dict = {}

class PromoEnterState(StatesGroup):
    waiting_code = State()

class PromoCreateState(StatesGroup):
    waiting_grams    = State()
    waiting_max_uses = State()

class AdminGiveState(StatesGroup):
    waiting_user_id = State()
    waiting_amount  = State()

class AdminDeactState(StatesGroup):
    waiting_code = State()

class AdminBroadcastState(StatesGroup):
    waiting_text = State()

class DuelChallengeState(StatesGroup):
    waiting_opponent = State()
    waiting_amount   = State()

# =====================================================================
# 🔧 УТИЛИТЫ
# =====================================================================

async def check_subscription(uid: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=TELEGRAM_CHANNEL_ID, user_id=uid)
        ok = m.status in ['member','administrator','creator']
        db.set_subscribed(uid, 1 if ok else 0)
        return ok
    except: return False

def is_private(msg: types.Message) -> bool:
    return msg.chat.type == "private"

def ensure_registered(uid, name):
    """Создаёт пользователя если его нет"""
    if not db.user_exists(uid):
        db.create_user(uid, name)

def main_keyboard(uid: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="👤 Профиль"),  KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="⚔️ Дуэль"),    KeyboardButton(text="🏰 Хогвартс")],
        [KeyboardButton(text="👥 Кланы"),    KeyboardButton(text="📊 Топ")],
        [KeyboardButton(text="🛒 Магазин"),  KeyboardButton(text="⌨️ Команды")],
        [KeyboardButton(text="🎟️ Промокод")],
    ]
    if uid in ADMIN_IDS:
        rows.append([KeyboardButton(text="🔐 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def bonus_status(uid):
    """Возвращает (доступен:bool, таймер:str)"""
    last = db.get_last_bonus(uid)
    if not last: return True, ""
    lt = datetime.fromisoformat(last)
    if datetime.now() - lt >= timedelta(seconds=DAILY_BONUS_COOLDOWN):
        return True, ""
    rem = DAILY_BONUS_COOLDOWN - int((datetime.now()-lt).total_seconds())
    return False, f"{rem//3600}:{(rem%3600)//60:02d}:{rem%60:02d}"

# =====================================================================
# /start  — работает везде, меню только в ЛС
# =====================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid  = message.from_user.id
    name = message.from_user.username or message.from_user.first_name
    ensure_registered(uid, name)

    # Deep-link автобонус: /start bonus
    args = message.text.split()
    if len(args) > 1 and args[1] == "bonus" and is_private(message):
        avail, timer = bonus_status(uid)
        if avail:
            amt = GameLogic.random_bonus()
            db.add_balance(uid, amt); db.claim_bonus(uid, amt)
            await message.answer(
                f"🎁 *Бонус получен!*\n\n+{amt:,} GRAM 🪙\n\n⏰ Следующий через 24 часа",
                parse_mode="Markdown", reply_markup=main_keyboard(uid)
            )
        else:
            await message.answer(
                f"⏳ Бонус уже получен.\nСледующий через {timer}",
                reply_markup=main_keyboard(uid)
            )
        return

    if not is_private(message): return  # в чатах /start без реакции

    if not await check_subscription(uid):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=TELEGRAM_CHANNEL)],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")],
        ])
        await message.answer("⚠️ Подпишись на канал:\n\n🔗 " + TELEGRAM_CHANNEL, reply_markup=kb)
        return

    await message.answer(
        f"👋 Привет, {name}!\n💰 Баланс: {db.get_balance(uid):,} 🪙\n\nВыбери действие:",
        reply_markup=main_keyboard(uid)
    )

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.answer("✅ Подписка подтверждена!", show_alert=True)
        await cmd_start(callback.message)
    else:
        await callback.answer("❌ Ты ещё не подписан!", show_alert=True)

# =====================================================================
# 💰 БАЛАНС — работает везде
# =====================================================================

@dp.message(F.text.in_({"💰 Баланс", "б", "баланс"}))
async def show_balance(message: types.Message):
    uid  = message.from_user.id
    name = message.from_user.username or message.from_user.first_name
    ensure_registered(uid, name)
    user = db.get_user(uid)

    avail, timer = bonus_status(uid)

    text  = f"💰 *БАЛАНС*\n\n🪙 Граммы: {user[2]:,}\n📊 Уровень: {user[3]}\n\n"

    if avail:
        text += "✅ Ежедневный бонус доступен!"
        if is_private(message):
            # В ЛС — inline кнопка прямо тут
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎁 Получить бонус", callback_data="daily_bonus")]
            ])
        else:
            # В чате — ссылка на ЛС с deep-link
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🎁 Получить бонус в ЛС",
                    url=f"https://t.me/{BOT_USERNAME}?start=bonus"
                )]
            ])
    else:
        text += f"⏳ Следующий бонус через {timer}"
        kb = None

    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "daily_bonus")
async def cb_daily_bonus(callback: types.CallbackQuery):
    uid = callback.from_user.id
    avail, timer = bonus_status(uid)
    if not avail:
        await callback.answer(f"⏳ Ещё {timer}", show_alert=True); return
    amt = GameLogic.random_bonus()
    db.add_balance(uid, amt); db.claim_bonus(uid, amt)
    await callback.answer()
    await callback.message.answer(f"🎁 *Бонус получен!*\n\n+{amt:,} GRAM 🪙", parse_mode="Markdown")

# =====================================================================
# 📊 ТОП — работает везде
# =====================================================================

@dp.message(F.text.in_({"📊 Топ", "/top", "/топ"}))
async def show_top(message: types.Message):
    medals = ["🥇","🥈","🥉"]
    text = "📊 *ТОП 10 ИГРОКОВ*\n\n"
    for i,(uid,uname,bal,lvl) in enumerate(db.get_top_users(10), 1):
        m = medals[i-1] if i<=3 else f"{i}."
        text += f"{m} {uname} — {bal:,} 🪙 (Ур.{lvl})\n"
    await message.answer(text, parse_mode="Markdown")

# =====================================================================
# 💸 ПЕРЕВОДЫ — работают везде
# =====================================================================

# Реплай: п 500
@dp.message(F.reply_to_message & F.text.regexp(r'^п\s+\d+$'))
async def transfer_reply(message: types.Message):
    uid  = message.from_user.id
    name = message.from_user.username or message.from_user.first_name
    ensure_registered(uid, name)

    try:   amount = int(message.text.split()[1])
    except: await message.answer("❌ Формат: п сумма"); return

    rid = message.reply_to_message.from_user.id
    rname = message.reply_to_message.from_user.first_name
    ensure_registered(rid, message.reply_to_message.from_user.username or rname)

    if uid == rid: await message.answer("❌ Нельзя переводить себе"); return
    if amount <= 0: await message.answer("❌ Сумма > 0"); return
    bal = db.get_balance(uid)
    if bal < amount: await message.answer(f"❌ Недостаточно: {bal:,}"); return

    db.subtract_balance(uid, amount)
    db.add_balance(rid, amount)
    await message.answer(
        f"✅ *Перевод выполнен*\n📤 {amount:,} 🪙 → {rname}",
        parse_mode="Markdown"
    )

# По ID или @username: п @user 500  /  п 123456 500
@dp.message(F.text.regexp(r'^п\s+\S+\s+\d+$'))
async def transfer_id(message: types.Message):
    if message.reply_to_message: return  # уже обработано выше
    uid  = message.from_user.id
    name = message.from_user.username or message.from_user.first_name
    ensure_registered(uid, name)

    parts = message.text.strip().split()
    identifier = parts[1]
    try:    amount = int(parts[2])
    except: await message.answer("❌ Сумма должна быть числом"); return

    # Ищем получателя
    rid = None; rname = identifier
    if identifier.startswith('@'):
        row = db.find_by_username(identifier[1:])
        if not row:
            await message.answer(f"❌ {identifier} не найден. Он должен хотя бы раз написать боту."); return
        rid, rname = row
    else:
        try:   rid = int(identifier)
        except: await message.answer("❌ Неверный ID или @username"); return
        if not db.user_exists(rid):
            await message.answer("❌ Пользователь не найден в системе"); return
        u = db.get_user(rid); rname = u[1] if u else str(rid)

    if rid == uid: await message.answer("❌ Нельзя переводить себе"); return
    if amount <= 0: await message.answer("❌ Сумма > 0"); return
    bal = db.get_balance(uid)
    if bal < amount: await message.answer(f"❌ Недостаточно: {bal:,}"); return

    db.subtract_balance(uid, amount)
    db.add_balance(rid, amount)

    try:
        sname = message.from_user.username or message.from_user.first_name
        await bot.send_message(rid, f"💸 *Вам перевели {amount:,} GRAM!*\nОт: @{sname}", parse_mode="Markdown")
    except: pass

    await message.answer(f"✅ *Перевод выполнен*\n📤 {amount:,} 🪙 → {rname}", parse_mode="Markdown")

# =====================================================================
# ⚔️ ДУЭЛЬ — в чате реплаем, в ЛС через меню
# =====================================================================

# --- В ЧАТЕ: реплай «дуэль» или «дуэль 500» ---
@dp.message(F.reply_to_message & F.text.regexp(r'^дуэль(\s+\d+)?$'))
async def duel_chat_reply(message: types.Message):
    parts  = message.text.strip().split()
    amount = int(parts[1]) if len(parts) > 1 else 100

    cid  = message.from_user.id
    cname = message.from_user.username or message.from_user.first_name
    oid  = message.reply_to_message.from_user.id
    oname = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name

    ensure_registered(cid, cname)
    ensure_registered(oid, oname)

    if cid == oid: await message.answer("❌ Нельзя вызвать себя"); return
    if amount <= 0: await message.answer("❌ Ставка > 0"); return
    if db.get_balance(cid) < amount:
        await message.answer(f"❌ Недостаточно: {db.get_balance(cid):,}"); return

    duel_requests[oid] = {'challenger_id': cid, 'challenger_name': cname, 'amount': amount}

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"da_{cid}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dd_{cid}")
    ]])
    await message.answer(
        f"⚔️ *{cname}* вызывает *{oname}* на дуэль!\n💰 Ставка: {amount:,} GRAM\n\n{oname}, принимаешь?",
        reply_markup=kb, parse_mode="Markdown"
    )

# --- В ЛС: через кнопку меню ---
@dp.message(F.text == "⚔️ Дуэль")
async def duel_menu(message: types.Message, state: FSMContext):
    if not is_private(message): return
    await message.answer("⚔️ Введи @username или ID соперника:")
    await state.set_state(DuelChallengeState.waiting_opponent)

@dp.message(DuelChallengeState.waiting_opponent)
async def duel_get_opp(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text.startswith('@'):
        row = db.find_by_username(text[1:])
        if not row: await message.answer("❌ Не найден. Попробуй ещё:"); return
        oid, oname = row
    else:
        try:   oid = int(text)
        except: await message.answer("❌ Числовой ID или @username:"); return
        if not db.user_exists(oid): await message.answer("❌ Не найден:"); return
        u = db.get_user(oid); oname = u[1] if u else str(oid)

    if oid == message.from_user.id:
        await message.answer("❌ Нельзя вызвать себя"); await state.clear(); return

    await state.update_data(oid=oid, oname=oname)
    await message.answer(f"👤 Соперник: *{oname}*\n💰 Введи ставку:", parse_mode="Markdown")
    await state.set_state(DuelChallengeState.waiting_amount)

@dp.message(DuelChallengeState.waiting_amount)
async def duel_get_amt(message: types.Message, state: FSMContext):
    try:   amount = int(message.text.strip())
    except: await message.answer("❌ Введи число:"); return

    data  = await state.get_data()
    oid   = data['oid']; oname = data['oname']
    cid   = message.from_user.id
    cname = message.from_user.username or message.from_user.first_name

    if amount <= 0: await message.answer("❌ > 0"); return
    if db.get_balance(cid) < amount:
        await message.answer(f"❌ Недостаточно: {db.get_balance(cid):,}"); return

    await state.clear()
    duel_requests[oid] = {'challenger_id': cid, 'challenger_name': cname, 'amount': amount}

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"da_{cid}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dd_{cid}")
    ]])
    try:
        await bot.send_message(
            oid,
            f"⚔️ *{cname}* вызывает тебя на дуэль!\n💰 Ставка: {amount:,} GRAM\n\nПринимаешь?",
            reply_markup=kb, parse_mode="Markdown"
        )
        await message.answer(f"✅ Запрос отправлен *{oname}*!", parse_mode="Markdown")
    except:
        duel_requests.pop(oid, None)
        await message.answer("❌ Не удалось отправить запрос (соперник заблокировал бота)")

# --- Принять / Отклонить дуэль ---
@dp.callback_query(F.data.startswith("da_"))
async def duel_accept(callback: types.CallbackQuery):
    oid  = callback.from_user.id
    cid  = int(callback.data[3:])
    req  = duel_requests.pop(oid, None)
    if not req or req['challenger_id'] != cid:
        await callback.answer("❌ Запрос устарел", show_alert=True); return

    amount = req['amount']
    await callback.answer("⚔️ Дуэль начинается!")

    if db.get_balance(cid) < amount:
        await callback.message.answer("❌ У вызывающего не хватает средств")
        await bot.send_message(cid, "❌ Дуэль отменена: недостаточно средств"); return
    if db.get_balance(oid) < amount:
        await callback.message.answer(f"❌ У вас нет {amount:,} GRAM для этой ставки"); return

    # Анимация
    anim = await callback.message.answer("⚔️ *БОЙ!*\n\n⚔️ · · ·", parse_mode="Markdown")
    for f in ["· ⚔️ · ·","· · ⚔️ ·","· · · ⚔️","⚔️ · · ·"]:
        await asyncio.sleep(0.4)
        try: await anim.edit_text(f"⚔️ *БОЙ!*\n\n{f}", parse_mode="Markdown")
        except: pass
    await asyncio.sleep(0.5)

    s1 = db.get_stats(cid); s2 = db.get_stats(oid)
    wnum = GameLogic.duel_winner(s1, s2)
    wid  = cid if wnum==1 else oid
    lid  = oid if wnum==1 else cid
    wname = req['challenger_name'] if wnum==1 else (callback.from_user.username or callback.from_user.first_name)

    db.subtract_balance(lid, amount)
    db.add_balance(wid, amount)
    db.add_duel(cid, oid, wid, amount)

    result = (
        f"⚔️ *ДУЭЛЬ ЗАВЕРШЕНА!*\n\n"
        f"🏆 Победитель: *{wname}*\n"
        f"💰 Приз: {amount:,} GRAM\n\n"
        f"❤️ HP: {s1['health']*10} vs {s2['health']*10}\n"
        f"💪 Сила: {s1['strength']} vs {s2['strength']}"
    )
    try: await anim.edit_text(result, parse_mode="Markdown")
    except: await callback.message.answer(result, parse_mode="Markdown")
    try: await bot.send_message(cid, result, parse_mode="Markdown")
    except: pass

@dp.callback_query(F.data.startswith("dd_"))
async def duel_decline(callback: types.CallbackQuery):
    oid  = callback.from_user.id
    cid  = int(callback.data[3:])
    duel_requests.pop(oid, None)
    await callback.answer("Отклонено")
    await callback.message.edit_text("❌ Дуэль отклонена")
    oname = callback.from_user.username or callback.from_user.first_name
    try: await bot.send_message(cid, f"❌ *{oname}* отклонил дуэль", parse_mode="Markdown")
    except: pass

# =====================================================================
# 💣 МИНЫ — работают везде
# =====================================================================

@dp.message(F.text.regexp(r'^мины\s+\d+$'))
async def start_minesweeper(message: types.Message):
    uid  = message.from_user.id
    name = message.from_user.username or message.from_user.first_name
    ensure_registered(uid, name)

    try:   amount = int(message.text.split()[1])
    except: await message.answer("❌ мины сумма"); return

    if amount <= 0: await message.answer("❌ Сумма > 0"); return
    if db.get_balance(uid) < amount:
        await message.answer(f"❌ Недостаточно: {db.get_balance(uid):,}"); return

    old = db.get_active_mine_game(uid)
    if old: db.update_mine_game(old[0], json.loads(old[3]), 'abandoned', old[6])

    field   = GameLogic.generate_field()
    game_id = db.create_mine_game(uid, field, amount)
    db.subtract_balance(uid, amount)

    revealed = [False]*25
    kb = GameLogic.mines_keyboard(game_id, revealed)
    await message.answer(
        f"💣 *МИННОЕ ПОЛЕ*\n\n"
        f"💰 Ставка: {amount:,} 🪙  |  💣 Мин: {sum(field)}\n\n"
        f"Открывай клетки. Чем больше — тем выше множитель.\n"
        f"Забери выигрыш в любой момент!",
        reply_markup=kb, parse_mode="Markdown"
    )

@dp.callback_query(F.data == "ms_skip")
async def ms_skip(callback: types.CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("ms_co_"))
async def ms_cashout(callback: types.CallbackQuery):
    uid     = callback.from_user.id
    game_id = int(callback.data[6:])
    game    = db.get_mine_game(game_id)

    if not game or game[1]!=uid or game[5]!='active':
        await callback.answer("❌ Игра не найдена", show_alert=True); return

    amount     = game[4]; safe_count = game[6]
    mult       = GameLogic.calc_mult(safe_count)
    winnings   = int(amount * mult)

    db.update_mine_game(game_id, json.loads(game[3]), 'cashed_out', safe_count)
    db.add_balance(uid, winnings)
    await callback.answer(f"💸 Забрал {winnings:,} GRAM!", show_alert=True)
    await callback.message.edit_text(
        f"💸 *Выигрыш забран!*\n\n"
        f"💰 Ставка: {amount:,} | ✅ Открыто: {safe_count}\n"
        f"📈 x{mult} | 🏆 {winnings:,} GRAM",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.regexp(r'^ms_\d+_\d+$'))
async def ms_click(callback: types.CallbackQuery):
    _, gid, cidx = callback.data.split("_")
    game_id = int(gid); cell = int(cidx)
    uid     = callback.from_user.id
    game    = db.get_mine_game(game_id)

    if not game or game[1]!=uid:
        await callback.answer("❌ Это не твоя игра", show_alert=True); return
    if game[5]!='active':
        await callback.answer("❌ Игра завершена", show_alert=True); return

    field      = json.loads(game[2])
    revealed   = json.loads(game[3])
    amount     = game[4]; safe_count = game[6]

    if revealed[cell]: await callback.answer("Уже открыто"); return
    revealed[cell] = True

    if field[cell]==1:
        db.update_mine_game(game_id, revealed, 'lost', safe_count)
        kb = GameLogic.mines_keyboard(game_id, revealed, field, show_mines=True)
        await callback.answer("💥 МИНА! Проигрыш!", show_alert=True)
        await callback.message.edit_text(
            f"💥 *МИНА!*\n\n💸 Потеряно: {amount:,} GRAM\n✅ Открыто: {safe_count}",
            reply_markup=kb, parse_mode="Markdown"
        )
    else:
        safe_count += 1
        mult = GameLogic.calc_mult(safe_count)
        win  = int(amount * mult)
        db.update_mine_game(game_id, revealed, 'active', safe_count)
        kb = GameLogic.mines_keyboard(game_id, revealed)
        await callback.answer(f"✅ Безопасно! x{mult}")
        await callback.message.edit_text(
            f"💣 *МИННОЕ ПОЛЕ*\n\n"
            f"💰 Ставка: {amount:,} | ✅ Открыто: {safe_count}\n"
            f"📈 Множитель: x{mult} | 💵 Выигрыш: {win:,}\n\n"
            f"Продолжай или забирай!",
            reply_markup=kb, parse_mode="Markdown"
        )

# =====================================================================
# 🏦 КАЗНА — работает в чатах
# =====================================================================

@dp.message(F.text.regexp(r'^казна(\s+\d+)?$'))
async def treasury_cmd(message: types.Message):
    if is_private(message):
        await message.answer("💼 Казна работает только в групповых чатах"); return

    uid     = message.from_user.id
    chat_id = message.chat.id
    name    = message.from_user.username or message.from_user.first_name
    ensure_registered(uid, name)

    parts = message.text.strip().split()
    t = db.get_treasury(chat_id)

    if not t:
        # Создаём казну бесплатно
        db.create_treasury(chat_id, uid)
        await message.answer(
            "🏦 *Казна создана!*\n\n"
            "Каждый новый участник чата получит 1000 GRAM.\n"
            "Пополни казну командой: `казна сумма`\n"
            "Изменить награду: `награда сумма`",
            parse_mode="Markdown"
        )
        return

    if len(parts) > 1:
        # Пополнение казны
        amt = int(parts[1])
        if db.get_balance(uid) < amt:
            await message.answer(f"❌ Недостаточно: {db.get_balance(uid):,}"); return
        db.subtract_balance(uid, amt)
        db.add_to_treasury(chat_id, amt)
        t = db.get_treasury(chat_id)
        await message.answer(f"✅ Казна пополнена на {amt:,} GRAM\n💰 Баланс казны: {t[2]:,}", parse_mode="Markdown")
    else:
        # Показать состояние
        await message.answer(
            f"🏦 *КАЗНА ЧАТА*\n\n"
            f"💰 Баланс: {t[2]:,} GRAM\n"
            f"🎁 Награда новичку: {t[3]:,} GRAM\n\n"
            f"Пополнить: `казна сумма`",
            parse_mode="Markdown"
        )

@dp.message(F.text.regexp(r'^награда\s+\d+$'))
async def treasury_reward(message: types.Message):
    if is_private(message): return
    uid     = message.from_user.id
    chat_id = message.chat.id
    t = db.get_treasury(chat_id)
    if not t: await message.answer("❌ Казны нет. Создай: `казна`", parse_mode="Markdown"); return
    if t[1] != uid: await message.answer("❌ Только создатель казны может менять награду"); return
    amt = int(message.text.split()[1])
    if amt <= 0: await message.answer("❌ > 0"); return
    db.cursor.execute('UPDATE treasuries SET reward=? WHERE chat_id=?', (amt, chat_id))
    db.conn.commit()
    await message.answer(f"✅ Награда за вступление: {amt:,} GRAM", parse_mode="Markdown")

@dp.message(F.new_chat_members)
async def new_member(message: types.Message):
    chat_id = message.chat.id
    t = db.get_treasury(chat_id)
    if not t or t[2] < t[3]: return

    for member in message.new_chat_members:
        if member.is_bot: continue
        uid  = member.id
        name = member.username or member.first_name
        ensure_registered(uid, name)
        if not db.treasury_member_rewarded(uid, chat_id):
            db.reward_treasury_member(uid, chat_id)
            await message.answer(
                f"🎁 Добро пожаловать, {name}!\n"
                f"Тебе начислено {t[3]:,} GRAM из казны чата!",
                parse_mode="Markdown"
            )

# =====================================================================
# 👤 ПРОФИЛЬ — только ЛС
# =====================================================================

@dp.message(F.text.in_({"👤 Профиль", "/профиль"}))
async def show_profile(message: types.Message):
    if not is_private(message): return
    uid  = message.from_user.id
    user = db.get_user(uid); stats = db.get_stats(uid)
    if not user or not stats: await message.answer("Напиши /start"); return
    text  = "👤 *ПРОФИЛЬ*\n\n"
    text += f"💰 Баланс: {user[2]:,} 🪙\n📊 Уровень: {user[3]}\n🆔 ID: `{uid}`\n\n*Характеристики:*\n"
    for k,v in stats.items():
        text += f"{STAT_EMOJIS.get(k,'•')} {STAT_NAMES.get(k,k)}: {v}\n"
    await message.answer(text, parse_mode="Markdown")

# =====================================================================
# 🛒 МАГАЗИН — только ЛС (реальные Telegram Stars)
# =====================================================================

@dp.message(F.text == "🛒 Магазин")
async def show_shop(message: types.Message):
    if not is_private(message): return
    text = "🛒 *МАГАЗИН ГРАММОВ*\n\nПокупка за реальные *Telegram Stars* ⭐️\n\n"
    btns = []
    for key, item in SHOP_ITEMS.items():
        text += f"💰 {item['grams']:,} GRAM → {item['stars']} ⭐️\n"
        btns.append([InlineKeyboardButton(
            text=f"{item['grams']:,} GRAM — {item['stars']}⭐️",
            callback_data=f"shop_{key}"
        )])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=btns), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("shop_"))
async def shop_buy(callback: types.CallbackQuery):
    key = callback.data[5:]
    if key not in SHOP_ITEMS: await callback.answer("❌ Не найдено", show_alert=True); return
    item = SHOP_ITEMS[key]
    await callback.answer()
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"💰 {item['grams']:,} GRAM",
        description=f"Пополнение баланса на {item['grams']:,} граммов",
        payload=f"gram_{key}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{item['grams']:,} GRAM", amount=item['stars'])],
        provider_token="",
    )

@dp.pre_checkout_query()
async def pre_checkout(pcq: PreCheckoutQuery):
    await pcq.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    key = message.successful_payment.invoice_payload.split("_",1)[1]
    if key in SHOP_ITEMS:
        item = SHOP_ITEMS[key]
        db.add_balance(message.from_user.id, item['grams'])
        await message.answer(
            f"✅ *Оплата принята!*\n\n💰 +{item['grams']:,} GRAM\n⭐️ Списано: {item['stars']} Stars",
            parse_mode="Markdown"
        )

# =====================================================================
# 🎟️ ПРОМОКОДЫ — только ЛС
# =====================================================================

@dp.message(F.text == "🎟️ Промокод")
async def promo_btn(message: types.Message, state: FSMContext):
    if not is_private(message): return
    await message.answer("🎟️ Введи промокод:")
    await state.set_state(PromoEnterState.waiting_code)

@dp.message(PromoEnterState.waiting_code)
async def promo_enter(message: types.Message, state: FSMContext):
    await state.clear()
    ok, msg, _ = db.use_promo(message.text.strip().upper(), message.from_user.id)
    await message.answer(msg, parse_mode="Markdown")

# =====================================================================
# ⌨️ КОМАНДЫ
# =====================================================================

@dp.message(F.text == "⌨️ Команды")
async def show_commands(message: types.Message):
    if not is_private(message): return
    await message.answer(
        "📋 *КОМАНДЫ:*\n\n"
        "💰 `б` — баланс\n"
        "💸 `п сумма` — перевод (реплаем)\n"
        "💸 `п @user сумма` — перевод по username\n"
        "⚔️ `дуэль` или `дуэль сумма` — вызов реплаем\n"
        "💣 `мины сумма` — минное поле\n"
        "🏦 `казна` — казна чата\n"
        "📊 `топ` или `/топ` — рейтинг\n"
        "🎟️ Промокод — ввести промокод (ЛС)\n",
        parse_mode="Markdown"
    )

@dp.message(F.text.in_({"🏰 Хогвартс","👥 Кланы"}))
async def stubs(message: types.Message):
    if not is_private(message): return
    await message.answer("🔧 В разработке...")

# =====================================================================
# 🔐 АДМИН-ПАНЕЛЬ — только ЛС
# =====================================================================

@dp.message(F.text == "🔐 Админ-панель")
async def admin_panel(message: types.Message):
    if not is_private(message): return
    if message.from_user.id not in ADMIN_IDS: await message.answer("❌ Нет доступа"); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать граммы",      callback_data="adm_give")],
        [InlineKeyboardButton(text="🎟️ Создать промокод",   callback_data="adm_promo")],
        [InlineKeyboardButton(text="📋 Список промокодов",   callback_data="adm_list")],
        [InlineKeyboardButton(text="🚫 Деактивировать промо", callback_data="adm_deact")],
        [InlineKeyboardButton(text="📢 Рассылка",            callback_data="adm_bc")],
        [InlineKeyboardButton(text="📊 Статистика",          callback_data="adm_stats")],
    ])
    await message.answer(f"🔐 *АДМИН-ПАНЕЛЬ*\n\n👥 Пользователей: {db.get_user_count()}",
                         reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "adm_stats")
async def adm_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    promos = db.get_all_promos()
    await callback.answer()
    await callback.message.answer(
        f"📊 *СТАТИСТИКА*\n\n👥 {db.get_user_count()} пользователей\n"
        f"🎟️ {len(promos)} промокодов ({sum(1 for p in promos if p[6])} активных)",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "adm_give")
async def adm_give(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    await callback.answer()
    await callback.message.answer("👤 Введи ID пользователя:")
    await state.set_state(AdminGiveState.waiting_user_id)

@dp.message(AdminGiveState.waiting_user_id)
async def adm_give_uid(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    try:   tid = int(message.text.strip())
    except: await message.answer("❌ Числовой ID:"); return
    if not db.user_exists(tid): await message.answer("❌ Не найден"); await state.clear(); return
    await state.update_data(tid=tid)
    await message.answer("💰 Введи количество GRAM:")
    await state.set_state(AdminGiveState.waiting_amount)

@dp.message(AdminGiveState.waiting_amount)
async def adm_give_amt(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    try:   amt = int(message.text.strip())
    except: await message.answer("❌ Число:"); return
    if amt <= 0: await message.answer("❌ > 0"); await state.clear(); return
    tid = (await state.get_data())['tid']
    db.add_balance(tid, amt); await state.clear()
    try: await bot.send_message(tid, f"🎁 Администратор выдал *{amt:,} GRAM*!", parse_mode="Markdown")
    except: pass
    await message.answer(f"✅ Выдано {amt:,} GRAM → {tid}")

@dp.callback_query(F.data == "adm_promo")
async def adm_promo(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    await callback.answer()
    await callback.message.answer("💰 Введи количество GRAM за промокод:")
    await state.set_state(PromoCreateState.waiting_grams)

@dp.message(PromoCreateState.waiting_grams)
async def adm_promo_g(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    try:   g = int(message.text.strip())
    except: await message.answer("❌ Число:"); return
    if g <= 0: await message.answer("❌ > 0"); await state.clear(); return
    await state.update_data(grams=g)
    await message.answer("👥 Введи макс. кол-во использований:")
    await state.set_state(PromoCreateState.waiting_max_uses)

@dp.message(PromoCreateState.waiting_max_uses)
async def adm_promo_u(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    try:   mu = int(message.text.strip())
    except: await message.answer("❌ Число:"); return
    if mu <= 0: await message.answer("❌ > 0"); await state.clear(); return
    grams = (await state.get_data())['grams']; await state.clear()

    code = GameLogic.gen_promo_code()
    for _ in range(10):
        if not db.get_promo(code): break
        code = GameLogic.gen_promo_code()

    if not db.create_promo(code, grams, mu, message.from_user.id):
        await message.answer("❌ Ошибка"); return

    await message.answer(
        f"🎟️ *Промокод создан!*\n\n🔑 `{code}`\n💰 {grams:,} GRAM\n👥 {mu} использований",
        parse_mode="Markdown"
    )
    try:
        await bot.send_message(
            TELEGRAM_CHANNEL_ID,
            f"🎟️ *НОВЫЙ ПРОМОКОД!*\n\n🔑 `{code}`\n💰 {grams:,} GRAM каждому!\n"
            f"👥 Активаций: {mu}\n\n⚡️ Вводи в боте → «🎟️ Промокод»",
            parse_mode="Markdown"
        )
        await message.answer("✅ Опубликовано в канале!")
    except Exception as e:
        await message.answer(f"⚠️ Создан, но не опубликован: {e}")

@dp.callback_query(F.data == "adm_list")
async def adm_list(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    promos = db.get_all_promos(); await callback.answer()
    if not promos: await callback.message.answer("Промокодов нет"); return
    text = "📋 *ПРОМОКОДЫ:*\n\n"
    for p in promos[:20]:
        code,grams,mu,used,_,_,active = p
        text += f"{'✅' if active else '❌'} `{code}` | {grams:,}💰 | {used}/{mu}👥\n"
    await callback.message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data == "adm_deact")
async def adm_deact(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    await callback.answer()
    await callback.message.answer("Введи код промокода:")
    await state.set_state(AdminDeactState.waiting_code)

@dp.message(AdminDeactState.waiting_code)
async def adm_deact_code(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    code = message.text.strip().upper()
    if not db.get_promo(code): await message.answer("❌ Не найден"); await state.clear(); return
    db.deactivate_promo(code); await state.clear()
    await message.answer(f"✅ `{code}` деактивирован", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_bc")
async def adm_bc(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    await callback.answer()
    await callback.message.answer("📢 Введи текст рассылки:")
    await state.set_state(AdminBroadcastState.waiting_text)

@dp.message(AdminBroadcastState.waiting_text)
async def adm_bc_send(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    text = message.text; await state.clear()
    users = db.get_all_users(); sent = failed = 0
    sm = await message.answer(f"📢 Рассылка {len(users)} пользователям...")
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 *От администратора:*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except: failed += 1
        await asyncio.sleep(0.05)
    await sm.edit_text(f"✅ Доставлено: {sent}\n❌ Не доставлено: {failed}")

# =====================================================================
# 🚀 ЗАПУСК
# =====================================================================

async def main():
    logger.info("✅ Бот запущен")
    if ADMIN_IDS == [123456789]:
        logger.warning("⚠️  Замени ADMIN_IDS на свой реальный Telegram ID!")
    if BOT_USERNAME == "your_bot_username":
        logger.warning("⚠️  Замени BOT_USERNAME на username своего бота (без @)!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
