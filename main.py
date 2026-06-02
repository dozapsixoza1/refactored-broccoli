"""
🎮 GRAM Bot v3.0
Исправления: перевод по ID/username, мины с кнопками, только ЛС,
дуэль с запросом, промокоды через FSM, реальные Telegram Stars
"""

import os
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
# ⚙️ КОНФИГУРАЦИЯ
# =====================================================================

BOT_TOKEN = "8490098380:AAF087A6UMDeC6Dd_uZb7bAxT8VsGCcS8yI"
TELEGRAM_CHANNEL     = "https://t.me/gramvaly"
TELEGRAM_CHANNEL_ID  = "@gramvaly"
ADMIN_IDS            = [8526401545]  # ← замени на свой Telegram ID

STARTING_BALANCE     = 1000
DAILY_BONUS_MIN      = 2500
DAILY_BONUS_MAX      = 5000
DAILY_BONUS_COOLDOWN = 86400   # 24 ч

# Магазин — реальные Telegram Stars (XTR)
SHOP_ITEMS = {
    '100k':  {'grams': 100_000,   'stars': 15},
    '204k':  {'grams': 204_000,   'stars': 30},
    '525k':  {'grams': 525_000,   'stars': 100},
    '1.15m': {'grams': 1_150_000, 'stars': 250},
    '2.3m':  {'grams': 2_300_000, 'stars': 500},
    '6.25m': {'grams': 6_250_000, 'stars': 1000},
}

STAT_NAMES = {
    'health': 'Здоровье', 'strength': 'Сила', 'endurance': 'Выносливость',
    'block': 'Блок', 'charisma': 'Харизма', 'intuition': 'Интуиция', 'speed': 'Скорость'
}
STAT_EMOJIS = {
    'health': '❤️', 'strength': '💪', 'endurance': '⚡', 'block': '🛡️',
    'charisma': '✨', 'intuition': '🔮', 'speed': '💨'
}

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
                'INSERT INTO users (user_id, username, balance) VALUES (?,?,?)',
                (user_id, username, STARTING_BALANCE))
            self.cursor.execute('INSERT INTO stats (user_id) VALUES (?)', (user_id,))
            self.cursor.execute('INSERT INTO subscriptions (user_id) VALUES (?)', (user_id,))
            self.conn.commit()
            return True
        except: return False

    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id=?', (user_id,))
        return self.cursor.fetchone()

    def user_exists(self, user_id): return self.get_user(user_id) is not None

    def get_balance(self, user_id):
        self.cursor.execute('SELECT balance FROM users WHERE user_id=?', (user_id,))
        r = self.cursor.fetchone(); return r[0] if r else 0

    def add_balance(self, user_id, amount):
        self.cursor.execute('UPDATE users SET balance=balance+? WHERE user_id=?', (amount, user_id))
        self.conn.commit()

    def subtract_balance(self, user_id, amount):
        self.cursor.execute('UPDATE users SET balance=balance-? WHERE user_id=?', (amount, user_id))
        self.conn.commit()

    def get_stats(self, user_id):
        self.cursor.execute('SELECT * FROM stats WHERE user_id=?', (user_id,))
        r = self.cursor.fetchone()
        if r: return {'health':r[1],'strength':r[2],'endurance':r[3],
                      'block':r[4],'charisma':r[5],'intuition':r[6],'speed':r[7]}
        return None

    def get_last_bonus(self, user_id):
        self.cursor.execute(
            'SELECT claimed_at FROM bonuses WHERE user_id=? ORDER BY claimed_at DESC LIMIT 1', (user_id,))
        r = self.cursor.fetchone(); return r[0] if r else None

    def claim_bonus(self, user_id, amount):
        self.cursor.execute('INSERT INTO bonuses (user_id,amount,type) VALUES (?,?,?)', (user_id,amount,'daily'))
        self.conn.commit()

    def set_subscribed(self, user_id, val):
        self.cursor.execute(
            'UPDATE subscriptions SET subscribed=?,checked_at=CURRENT_TIMESTAMP WHERE user_id=?', (val,user_id))
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

    def add_duel(self, p1, p2, winner, reward):
        try:
            self.cursor.execute('INSERT INTO duels (player1_id,player2_id,winner_id,reward) VALUES (?,?,?,?)',
                                (p1,p2,winner,reward))
            self.conn.commit()
        except Exception as e: logger.error(e)

    # --- мины ---
    def create_mine_game(self, user_id, field, amount):
        self.cursor.execute(
            'INSERT INTO minesweeper_games (user_id,field,revealed,amount) VALUES (?,?,?,?)',
            (user_id, json.dumps(field), json.dumps([False]*25), amount))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_mine_game(self, game_id):
        self.cursor.execute('SELECT * FROM minesweeper_games WHERE game_id=?', (game_id,))
        return self.cursor.fetchone()

    def get_active_mine_game(self, user_id):
        self.cursor.execute(
            'SELECT * FROM minesweeper_games WHERE user_id=? AND status="active" ORDER BY game_id DESC LIMIT 1',
            (user_id,))
        return self.cursor.fetchone()

    def update_mine_game(self, game_id, revealed, status, safe_count):
        self.cursor.execute(
            'UPDATE minesweeper_games SET revealed=?,status=?,safe_count=? WHERE game_id=?',
            (json.dumps(revealed), status, safe_count, game_id))
        self.conn.commit()

    # --- промокоды ---
    def create_promo(self, code, grams, max_uses, created_by):
        try:
            self.cursor.execute(
                'INSERT INTO promo_codes (code,grams,max_uses,created_by) VALUES (?,?,?,?)',
                (code,grams,max_uses,created_by))
            self.conn.commit(); return True
        except Exception as e: logger.error(e); return False

    def get_promo(self, code):
        self.cursor.execute('SELECT * FROM promo_codes WHERE code=?', (code,))
        return self.cursor.fetchone()

    def use_promo(self, code, user_id):
        promo = self.get_promo(code)
        if not promo: return False, "❌ Промокод не найден", 0
        p_code,p_grams,p_max,p_used,p_by,p_at,p_active = promo
        if not p_active: return False, "❌ Промокод больше не активен", 0
        if p_used >= p_max: return False, "❌ Промокод исчерпан", 0
        self.cursor.execute('SELECT use_id FROM promo_uses WHERE code=? AND user_id=?', (code,user_id))
        if self.cursor.fetchone(): return False, "❌ Ты уже использовал этот промокод", 0
        try:
            self.cursor.execute('INSERT INTO promo_uses (code,user_id) VALUES (?,?)', (code,user_id))
            self.cursor.execute('UPDATE promo_codes SET used_count=used_count+1 WHERE code=?', (code,))
            if p_used+1 >= p_max:
                self.cursor.execute('UPDATE promo_codes SET is_active=0 WHERE code=?', (code,))
            self.conn.commit()
            self.add_balance(user_id, p_grams)
            return True, f"✅ Промокод активирован!\n💰 +{p_grams:,} GRAM начислено!", p_grams
        except Exception as e:
            logger.error(e); return False, "❌ Ошибка при активации", 0

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
        """Строит inline-клавиатуру 5×5 для минного поля"""
        rows = []
        for row in range(5):
            btns = []
            for col in range(5):
                idx = row*5 + col
                if revealed[idx]:
                    btns.append(InlineKeyboardButton(text="✅", callback_data="mine_skip"))
                elif show_mines and field and field[idx] == 1:
                    btns.append(InlineKeyboardButton(text="💣", callback_data="mine_skip"))
                else:
                    btns.append(InlineKeyboardButton(
                        text="❓", callback_data=f"mine_{game_id}_{idx}"))
            rows.append(btns)
        rows.append([InlineKeyboardButton(text="💸 Забрать выигрыш", callback_data=f"mine_cashout_{game_id}")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @staticmethod
    def calc_multiplier(safe_count):
        """Чем больше открыл безопасных клеток — тем больше множитель"""
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
# 🤖 БОТ + FSM
# =====================================================================

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# Хранилище активных запросов на дуэль: {opponent_id: {challenger_id, amount, ...}}
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
    waiting_opponent_id = State()
    waiting_amount      = State()

# =====================================================================
# 🔧 УТИЛИТЫ
# =====================================================================

async def check_subscription(user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=TELEGRAM_CHANNEL_ID, user_id=user_id)
        ok = m.status in ['member','administrator','creator']
        db.set_subscribed(user_id, 1 if ok else 0)
        return ok
    except: return False

def is_private(message: types.Message) -> bool:
    return message.chat.type == "private"

def main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="👤 Профиль"),   KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="⚔️ Дуэль"),     KeyboardButton(text="🏰 Хогвартс")],
        [KeyboardButton(text="👥 Кланы"),     KeyboardButton(text="📊 Топ")],
        [KeyboardButton(text="🛒 Магазин"),   KeyboardButton(text="⌨️ Команды")],
        [KeyboardButton(text="🎟️ Промокод")],
    ]
    if user_id in ADMIN_IDS:
        rows.append([KeyboardButton(text="🔐 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

# =====================================================================
# 📋 ХЭНДЛЕРЫ — только личные сообщения (is_private check внутри)
# =====================================================================

# ========== /start ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_private(message): return   # игнорируем в чатах

    uid  = message.from_user.id
    name = message.from_user.username or message.from_user.first_name

    if not db.user_exists(uid):
        db.create_user(uid, name)

    if not await check_subscription(uid):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=TELEGRAM_CHANNEL)],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")],
        ])
        await message.answer("⚠️ Сначала подпишись на канал:\n\n🔗 " + TELEGRAM_CHANNEL, reply_markup=kb)
        return

    await message.answer(
        f"👋 Привет, {name}!\n\n💰 Баланс: {db.get_balance(uid):,} 🪙\n\nВыбери действие:",
        reply_markup=main_keyboard(uid)
    )

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.answer("✅ Подписка подтверждена!", show_alert=True)
        await cmd_start(callback.message)
    else:
        await callback.answer("❌ Ты ещё не подписан!", show_alert=True)

# ========== КОМАНДЫ ==========
@dp.message(F.text == "⌨️ Команды")
async def show_commands(message: types.Message):
    if not is_private(message): return
    await message.answer(
        "📋 *КОМАНДЫ:*\n\n"
        "`б` — баланс\n"
        "`п ID/username сумма` — перевод\n"
        "`п сумма` — перевод реплаем\n"
        "`мины сумма` — минное поле\n"
        "⚔️ Дуэль — кнопка в меню\n"
        "🎟️ Промокод — ввести промокод\n",
        parse_mode="Markdown"
    )

# ========== БАЛАНС ==========
@dp.message(F.text.in_({"💰 Баланс", "б", "баланс"}))
async def show_balance(message: types.Message):
    if not is_private(message): return
    uid  = message.from_user.id
    user = db.get_user(uid)
    if not user:
        await message.answer("Напиши /start"); return

    balance = user[2]
    last_b  = db.get_last_bonus(uid)
    avail   = True
    timer   = ""

    if last_b:
        lt = datetime.fromisoformat(last_b)
        if datetime.now() - lt < timedelta(seconds=DAILY_BONUS_COOLDOWN):
            avail = False
            rem   = DAILY_BONUS_COOLDOWN - int((datetime.now()-lt).total_seconds())
            timer = f"{rem//3600}:{(rem%3600)//60:02d}:{rem%60:02d}"

    text = f"💰 *БАЛАНС*\n\n🪙 Граммы: {balance:,}\n📊 Уровень: {user[3]}\n\n"
    if avail:
        text += "✅ Ежедневный бонус доступен!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Получить бонус", callback_data="daily_bonus")]
        ])
    else:
        text += f"⏳ Следующий бонус через {timer}"
        kb = None

    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "daily_bonus")
async def cb_daily_bonus(callback: types.CallbackQuery):
    uid   = callback.from_user.id
    last_b = db.get_last_bonus(uid)
    if last_b:
        lt = datetime.fromisoformat(last_b)
        if datetime.now() - lt < timedelta(seconds=DAILY_BONUS_COOLDOWN):
            rem = DAILY_BONUS_COOLDOWN - int((datetime.now()-lt).total_seconds())
            await callback.answer(f"⏳ Ещё {rem//3600}ч {(rem%3600)//60}мин", show_alert=True)
            return
    amt = GameLogic.random_bonus()
    db.add_balance(uid, amt); db.claim_bonus(uid, amt)
    await callback.answer()
    await callback.message.answer(f"🎁 *Бонус получен!*\n\n+{amt:,} GRAM 🪙", parse_mode="Markdown")

# ========== ПЕРЕВОД (реплай) ==========
@dp.message(F.reply_to_message & F.text.startswith("п "))
async def transfer_reply(message: types.Message):
    if not is_private(message): return
    try:   amount = int(message.text.split()[1])
    except: await message.answer("❌ п сумма"); return

    sid = message.from_user.id
    rid = message.reply_to_message.from_user.id
    if sid == rid: await message.answer("❌ Нельзя себе"); return
    if amount <= 0: await message.answer("❌ Сумма > 0"); return
    bal = db.get_balance(sid)
    if bal < amount: await message.answer(f"❌ Недостаточно: {bal:,}"); return

    db.subtract_balance(sid, amount)
    db.add_balance(rid, amount)
    await message.answer(
        f"✅ *Перевод выполнен*\n\n📤 {amount:,} 🪙 → {message.reply_to_message.from_user.first_name}",
        parse_mode="Markdown"
    )

# ========== ПЕРЕВОД (по ID/username) — ИСПРАВЛЕН ==========
@dp.message(F.text.regexp(r'^п\s+\S+\s+\d+$'))
async def transfer_id(message: types.Message):
    """п @username 500  или  п 123456789 500"""
    if not is_private(message): return
    # Если это реплай — уже обработано выше
    if message.reply_to_message: return

    parts = message.text.strip().split()
    # parts = ['п', 'identifier', 'amount']
    if len(parts) != 3:
        await message.answer("❌ Формат: п @username сумма  или  п ID сумма"); return

    identifier = parts[1]
    try:    amount = int(parts[2])
    except: await message.answer("❌ Сумма должна быть числом"); return

    sid = message.from_user.id

    # Ищем получателя
    recipient_id = None
    recipient_name = identifier

    if identifier.startswith('@'):
        # По username — ищем в нашей БД
        uname = identifier[1:].lower()
        db.cursor.execute(
            'SELECT user_id, username FROM users WHERE LOWER(username)=?', (uname,))
        row = db.cursor.fetchone()
        if row:
            recipient_id   = row[0]
            recipient_name = row[1]
        else:
            await message.answer(f"❌ Пользователь {identifier} не найден в системе.\n"
                                 "Он должен хотя бы раз написать боту."); return
    else:
        try:
            recipient_id = int(identifier)
        except ValueError:
            await message.answer("❌ Неверный ID или username"); return
        if not db.user_exists(recipient_id):
            await message.answer("❌ Пользователь не найден в системе"); return

    if recipient_id == sid:
        await message.answer("❌ Нельзя переводить самому себе"); return
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0"); return

    bal = db.get_balance(sid)
    if bal < amount:
        await message.answer(f"❌ Недостаточно средств! У вас: {bal:,}"); return

    db.subtract_balance(sid, amount)
    db.add_balance(recipient_id, amount)

    # Уведомляем получателя
    try:
        sender_name = message.from_user.username or message.from_user.first_name
        await bot.send_message(
            recipient_id,
            f"💸 *Вам перевели {amount:,} GRAM!*\n\nОтправитель: @{sender_name}",
            parse_mode="Markdown"
        )
    except: pass

    await message.answer(
        f"✅ *Перевод выполнен*\n\n📤 {amount:,} 🪙 → {recipient_name}",
        parse_mode="Markdown"
    )

# ========== ПРОФИЛЬ ==========
@dp.message(F.text.in_({"👤 Профиль", "/профиль"}))
async def show_profile(message: types.Message):
    if not is_private(message): return
    uid  = message.from_user.id
    user = db.get_user(uid); stats = db.get_stats(uid)
    if not user or not stats: await message.answer("Напиши /start"); return

    text  = "👤 *ПРОФИЛЬ*\n\n"
    text += f"💰 Баланс: {user[2]:,} 🪙\n"
    text += f"📊 Уровень: {user[3]}\n"
    text += f"🆔 ID: `{uid}`\n\n*Характеристики:*\n"
    for k, v in stats.items():
        text += f"{STAT_EMOJIS.get(k,'•')} {STAT_NAMES.get(k,k)}: {v}\n"
    await message.answer(text, parse_mode="Markdown")

# ========== ТОП ==========
@dp.message(F.text.in_({"📊 Топ", "/top", "/топ"}))
async def show_top(message: types.Message):
    if not is_private(message): return
    medals = ["🥇","🥈","🥉"]
    text = "📊 *ТОП 10 ИГРОКОВ*\n\n"
    for i,(uid,uname,bal,lvl) in enumerate(db.get_top_users(10), 1):
        m = medals[i-1] if i<=3 else f"{i}."
        text += f"{m} {uname} — {bal:,} 🪙 (Ур.{lvl})\n"
    await message.answer(text, parse_mode="Markdown")

# ========== ХОГВАРТС / КЛАНЫ ==========
@dp.message(F.text.in_({"🏰 Хогвартс", "👥 Кланы"}))
async def stub(message: types.Message):
    if not is_private(message): return
    await message.answer("🔧 В разработке...")

# =====================================================================
# ⚔️ ДУЭЛЬ — через кнопку в ЛС, запрос сопернику
# =====================================================================

@dp.message(F.text == "⚔️ Дуэль")
async def duel_menu(message: types.Message, state: FSMContext):
    if not is_private(message): return
    await message.answer(
        "⚔️ *ДУЭЛЬ*\n\n"
        "Введи ID или @username соперника:",
        parse_mode="Markdown"
    )
    await state.set_state(DuelChallengeState.waiting_opponent_id)

@dp.message(DuelChallengeState.waiting_opponent_id)
async def duel_get_opponent(message: types.Message, state: FSMContext):
    if not is_private(message): return
    text = message.text.strip()

    if text.startswith('@'):
        uname = text[1:].lower()
        db.cursor.execute('SELECT user_id,username FROM users WHERE LOWER(username)=?', (uname,))
        row = db.cursor.fetchone()
        if not row:
            await message.answer("❌ Пользователь не найден. Попробуй ещё раз:"); return
        opp_id, opp_name = row
    else:
        try:   opp_id = int(text)
        except:
            await message.answer("❌ Введи числовой ID или @username:"); return
        if not db.user_exists(opp_id):
            await message.answer("❌ Пользователь не найден:"); return
        u = db.get_user(opp_id)
        opp_name = u[1] if u else str(opp_id)

    if opp_id == message.from_user.id:
        await message.answer("❌ Нельзя вызвать себя"); await state.clear(); return

    await state.update_data(opp_id=opp_id, opp_name=opp_name)
    await message.answer(
        f"👤 Соперник: *{opp_name}*\n\n💰 Введи ставку (граммы):",
        parse_mode="Markdown"
    )
    await state.set_state(DuelChallengeState.waiting_amount)

@dp.message(DuelChallengeState.waiting_amount)
async def duel_get_amount(message: types.Message, state: FSMContext):
    if not is_private(message): return
    try:   amount = int(message.text.strip())
    except:
        await message.answer("❌ Введи число:"); return

    data    = await state.get_data()
    opp_id  = data['opp_id']
    opp_name= data['opp_name']
    uid     = message.from_user.id

    if amount <= 0:
        await message.answer("❌ Ставка > 0"); return
    if db.get_balance(uid) < amount:
        await message.answer(f"❌ Недостаточно: {db.get_balance(uid):,}"); return

    await state.clear()

    # Сохраняем запрос
    duel_requests[opp_id] = {
        'challenger_id':   uid,
        'challenger_name': message.from_user.username or message.from_user.first_name,
        'amount':          amount
    }

    # Отправляем запрос сопернику
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"duel_accept_{uid}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"duel_decline_{uid}")]
    ])
    try:
        await bot.send_message(
            opp_id,
            f"⚔️ *Вас вызывают на дуэль!*\n\n"
            f"👤 Вызывает: @{duel_requests[opp_id]['challenger_name']}\n"
            f"💰 Ставка: {amount:,} GRAM\n\n"
            f"Принять вызов?",
            reply_markup=kb, parse_mode="Markdown"
        )
        await message.answer(
            f"✅ Запрос отправлен *{opp_name}*!\n\nОжидаем ответа...",
            parse_mode="Markdown"
        )
    except:
        duel_requests.pop(opp_id, None)
        await message.answer("❌ Не удалось отправить запрос. Соперник возможно заблокировал бота.")

@dp.callback_query(F.data.startswith("duel_accept_"))
async def duel_accept(callback: types.CallbackQuery):
    opp_id = callback.from_user.id
    chal_id= int(callback.data.split("_")[2])

    req = duel_requests.pop(opp_id, None)
    if not req or req['challenger_id'] != chal_id:
        await callback.answer("❌ Запрос устарел", show_alert=True); return

    amount = req['amount']
    await callback.answer("⚔️ Дуэль начинается!")

    # Проверяем балансы
    if db.get_balance(chal_id) < amount:
        await callback.message.answer("❌ У вызывающего недостаточно средств")
        await bot.send_message(chal_id, "❌ Дуэль отменена: недостаточно средств")
        return
    if db.get_balance(opp_id) < amount:
        await callback.message.answer("❌ У вас недостаточно средств для этой ставки")
        await bot.send_message(chal_id, f"❌ {req['challenger_name']} не принял дуэль (нет средств)")
        return

    # Анимация
    anim = await callback.message.answer("⚔️ *ДУЭЛЬ НАЧИНАЕТСЯ...*", parse_mode="Markdown")
    for frame in ["⚔️ · · ·","· ⚔️ · ·","· · ⚔️ ·","· · · ⚔️"]:
        await asyncio.sleep(0.5)
        try: await anim.edit_text(f"⚔️ *БОЙ!*\n\n{frame}", parse_mode="Markdown")
        except: pass
    await asyncio.sleep(0.5)

    s1 = db.get_stats(chal_id); s2 = db.get_stats(opp_id)
    winner_num = GameLogic.duel_winner(s1, s2)

    if winner_num == 1:
        winner_id = chal_id; loser_id = opp_id
        winner_name = req['challenger_name']
    else:
        winner_id = opp_id; loser_id = chal_id
        winner_name = callback.from_user.username or callback.from_user.first_name

    db.subtract_balance(loser_id, amount)
    db.add_balance(winner_id, amount)
    db.add_duel(chal_id, opp_id, winner_id, amount)

    result = (
        f"⚔️ *ДУЭЛЬ ЗАВЕРШЕНА!*\n\n"
        f"🏆 Победитель: *{winner_name}*\n"
        f"💰 Приз: {amount:,} GRAM\n\n"
        f"❤️ HP: {s1['health']*10} vs {s2['health']*10}\n"
        f"💪 Сила: {s1['strength']} vs {s2['strength']}"
    )

    try: await anim.edit_text(result, parse_mode="Markdown")
    except: await callback.message.answer(result, parse_mode="Markdown")

    # Уведомляем обоих
    try: await bot.send_message(chal_id, result, parse_mode="Markdown")
    except: pass

@dp.callback_query(F.data.startswith("duel_decline_"))
async def duel_decline(callback: types.CallbackQuery):
    opp_id  = callback.from_user.id
    chal_id = int(callback.data.split("_")[2])

    duel_requests.pop(opp_id, None)
    await callback.answer("Отклонено")
    await callback.message.edit_text("❌ Вы отклонили дуэль")
    try:
        opp_name = callback.from_user.username or callback.from_user.first_name
        await bot.send_message(chal_id, f"❌ *{opp_name}* отклонил дуэль", parse_mode="Markdown")
    except: pass

# =====================================================================
# 💣 МИННОЕ ПОЛЕ — inline кнопки 5×5
# =====================================================================

@dp.message(F.text.startswith("мины "))
async def start_minesweeper(message: types.Message):
    if not is_private(message): return
    try:    amount = int(message.text.split()[1])
    except: await message.answer("❌ мины сумма"); return

    uid = message.from_user.id
    if amount <= 0: await message.answer("❌ Сумма > 0"); return
    if db.get_balance(uid) < amount:
        await message.answer(f"❌ Недостаточно: {db.get_balance(uid):,}"); return

    # Закрываем старую игру если есть
    old = db.get_active_mine_game(uid)
    if old:
        db.update_mine_game(old[0], json.loads(old[3]), 'abandoned', old[7])

    field   = GameLogic.generate_field()
    game_id = db.create_mine_game(uid, field, amount)
    db.subtract_balance(uid, amount)

    revealed = [False]*25
    kb = GameLogic.mines_keyboard(game_id, revealed)
    mines_count = sum(field)

    await message.answer(
        f"💣 *МИННОЕ ПОЛЕ*\n\n"
        f"💰 Ставка: {amount:,} 🪙\n"
        f"💣 Мин на поле: {mines_count}\n"
        f"✅ Безопасных клеток: {25-mines_count}\n\n"
        f"Открывай клетки! Чем больше откроешь — тем выше множитель.\n"
        f"Или забери выигрыш в любой момент.",
        reply_markup=kb, parse_mode="Markdown"
    )

@dp.callback_query(F.data == "mine_skip")
async def mine_skip(callback: types.CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("mine_cashout_"))
async def mine_cashout(callback: types.CallbackQuery):
    uid     = callback.from_user.id
    game_id = int(callback.data.split("_")[2])
    game    = db.get_mine_game(game_id)

    if not game or game[1] != uid or game[5] != 'active':
        await callback.answer("❌ Игра не найдена", show_alert=True); return

    amount     = game[4]
    safe_count = game[7]
    mult       = GameLogic.calc_multiplier(safe_count)
    winnings   = int(amount * mult)

    revealed = json.loads(game[3])
    field    = json.loads(game[2])
    db.update_mine_game(game_id, revealed, 'cashed_out', safe_count)
    db.add_balance(uid, winnings)

    await callback.answer(f"💸 Забрал {winnings:,} GRAM!", show_alert=True)
    await callback.message.edit_text(
        f"💸 *Выигрыш забран!*\n\n"
        f"💰 Ставка: {amount:,}\n"
        f"✅ Открыто клеток: {safe_count}\n"
        f"📈 Множитель: x{mult}\n"
        f"🏆 Выигрыш: {winnings:,} GRAM",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("mine_"))
async def mine_click(callback: types.CallbackQuery):
    parts   = callback.data.split("_")
    game_id = int(parts[1])
    cell    = int(parts[2])
    uid     = callback.from_user.id

    game = db.get_mine_game(game_id)
    if not game or game[1] != uid:
        await callback.answer("❌ Это не твоя игра", show_alert=True); return
    if game[5] != 'active':
        await callback.answer("❌ Игра уже завершена", show_alert=True); return

    field      = json.loads(game[2])
    revealed   = json.loads(game[3])
    amount     = game[4]
    safe_count = game[7]

    if revealed[cell]:
        await callback.answer("Уже открыто"); return

    revealed[cell] = True

    if field[cell] == 1:
        # МИНА — проигрыш
        db.update_mine_game(game_id, revealed, 'lost', safe_count)
        kb = GameLogic.mines_keyboard(game_id, revealed, field, show_mines=True)
        await callback.answer("💥 МИНА! Ты проиграл!", show_alert=True)
        await callback.message.edit_text(
            f"💥 *МИНА!*\n\n"
            f"💸 Потеряно: {amount:,} GRAM\n"
            f"✅ Открыто безопасных: {safe_count}",
            reply_markup=kb, parse_mode="Markdown"
        )
    else:
        # Безопасно
        safe_count += 1
        mult = GameLogic.calc_multiplier(safe_count)
        win  = int(amount * mult)
        db.update_mine_game(game_id, revealed, 'active', safe_count)

        kb = GameLogic.mines_keyboard(game_id, revealed)
        await callback.answer(f"✅ Безопасно! Множитель x{mult}")
        await callback.message.edit_text(
            f"💣 *МИННОЕ ПОЛЕ*\n\n"
            f"💰 Ставка: {amount:,} 🪙\n"
            f"✅ Открыто: {safe_count}\n"
            f"📈 Множитель: x{mult}\n"
            f"💵 Потенциальный выигрыш: {win:,} GRAM\n\n"
            f"Продолжай или забери выигрыш!",
            reply_markup=kb, parse_mode="Markdown"
        )

# =====================================================================
# 🛒 МАГАЗИН — реальные Telegram Stars (платёж XTR)
# =====================================================================

@dp.message(F.text == "🛒 Магазин")
async def show_shop(message: types.Message):
    if not is_private(message): return
    text  = "🛒 *МАГАЗИН ГРАММОВ*\n\n"
    text += "Покупка за реальные *Telegram Stars* ⭐️\n\n"
    btns  = []
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
    if key not in SHOP_ITEMS:
        await callback.answer("❌ Не найдено", show_alert=True); return
    item = SHOP_ITEMS[key]
    await callback.answer()
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"💰 {item['grams']:,} GRAM",
        description=f"Пополнение баланса на {item['grams']:,} граммов в боте",
        payload=f"gram_{key}",
        currency="XTR",           # Telegram Stars
        prices=[LabeledPrice(label=f"{item['grams']:,} GRAM", amount=item['stars'])],
        provider_token="",        # Для Stars — пустая строка
    )

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload  # gram_100k
    key = payload.split("_", 1)[1]
    if key in SHOP_ITEMS:
        item = SHOP_ITEMS[key]
        db.add_balance(message.from_user.id, item['grams'])
        await message.answer(
            f"✅ *Оплата получена!*\n\n"
            f"💰 Начислено: {item['grams']:,} GRAM\n"
            f"⭐️ Списано: {item['stars']} Telegram Stars",
            parse_mode="Markdown"
        )

# =====================================================================
# 🎟️ ПРОМОКОДЫ
# =====================================================================

@dp.message(F.text == "🎟️ Промокод")
async def promo_btn(message: types.Message, state: FSMContext):
    if not is_private(message): return
    await message.answer("🎟️ Введи промокод:")
    await state.set_state(PromoEnterState.waiting_code)

@dp.message(PromoEnterState.waiting_code)
async def promo_enter(message: types.Message, state: FSMContext):
    await state.clear()
    code = message.text.strip().upper()
    ok, msg, _ = db.use_promo(code, message.from_user.id)
    await message.answer(msg, parse_mode="Markdown")

# =====================================================================
# 🔐 АДМИН-ПАНЕЛЬ
# =====================================================================

@dp.message(F.text == "🔐 Админ-панель")
async def admin_panel(message: types.Message):
    if not is_private(message): return
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Нет доступа"); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать граммы",     callback_data="adm_give")],
        [InlineKeyboardButton(text="🎟️ Создать промокод",  callback_data="adm_promo")],
        [InlineKeyboardButton(text="📋 Список промокодов",  callback_data="adm_list")],
        [InlineKeyboardButton(text="🚫 Деактивировать промо", callback_data="adm_deact")],
        [InlineKeyboardButton(text="📢 Рассылка",           callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 Статистика",         callback_data="adm_stats")],
    ])
    await message.answer(
        f"🔐 *АДМИН-ПАНЕЛЬ*\n\n👥 Пользователей: {db.get_user_count()}",
        reply_markup=kb, parse_mode="Markdown"
    )

# --- статистика ---
@dp.callback_query(F.data == "adm_stats")
async def adm_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    promos = db.get_all_promos()
    await callback.answer()
    await callback.message.answer(
        f"📊 *СТАТИСТИКА*\n\n"
        f"👥 Пользователей: {db.get_user_count()}\n"
        f"🎟️ Промокодов: {len(promos)}\n"
        f"✅ Активных: {sum(1 for p in promos if p[6])}",
        parse_mode="Markdown"
    )

# --- выдать граммы ---
@dp.callback_query(F.data == "adm_give")
async def adm_give_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    await callback.answer()
    await callback.message.answer("👤 Введи ID пользователя:")
    await state.set_state(AdminGiveState.waiting_user_id)

@dp.message(AdminGiveState.waiting_user_id)
async def adm_give_uid(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    try:    tid = int(message.text.strip())
    except: await message.answer("❌ Числовой ID:"); return
    if not db.user_exists(tid):
        await message.answer("❌ Не найден"); await state.clear(); return
    await state.update_data(tid=tid)
    await message.answer("💰 Введи количество GRAM:")
    await state.set_state(AdminGiveState.waiting_amount)

@dp.message(AdminGiveState.waiting_amount)
async def adm_give_amt(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    try:    amt = int(message.text.strip())
    except: await message.answer("❌ Число:"); return
    if amt <= 0: await message.answer("❌ > 0"); await state.clear(); return
    data = await state.get_data(); tid = data['tid']
    db.add_balance(tid, amt); await state.clear()
    try: await bot.send_message(tid, f"🎁 Администратор выдал *{amt:,} GRAM*!", parse_mode="Markdown")
    except: pass
    await message.answer(f"✅ Выдано {amt:,} GRAM → {tid}", parse_mode="Markdown")

# --- создать промокод ---
@dp.callback_query(F.data == "adm_promo")
async def adm_promo_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    await callback.answer()
    await callback.message.answer("💰 Введи количество GRAM за промокод:")
    await state.set_state(PromoCreateState.waiting_grams)

@dp.message(PromoCreateState.waiting_grams)
async def adm_promo_grams(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    try:    g = int(message.text.strip())
    except: await message.answer("❌ Число:"); return
    if g <= 0: await message.answer("❌ > 0"); await state.clear(); return
    await state.update_data(grams=g)
    await message.answer("👥 Введи макс. кол-во использований:")
    await state.set_state(PromoCreateState.waiting_max_uses)

@dp.message(PromoCreateState.waiting_max_uses)
async def adm_promo_uses(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    try:    mu = int(message.text.strip())
    except: await message.answer("❌ Число:"); return
    if mu <= 0: await message.answer("❌ > 0"); await state.clear(); return

    data = await state.get_data(); grams = data['grams']
    await state.clear()

    # Генерируем уникальный код
    code = GameLogic.gen_promo_code()
    for _ in range(10):
        if not db.get_promo(code): break
        code = GameLogic.gen_promo_code()

    if not db.create_promo(code, grams, mu, message.from_user.id):
        await message.answer("❌ Ошибка создания"); return

    await message.answer(
        f"🎟️ *Промокод создан!*\n\n🔑 Код: `{code}`\n💰 Награда: {grams:,} GRAM\n👥 Использований: {mu}",
        parse_mode="Markdown"
    )

    # Публикуем в канал
    try:
        await bot.send_message(
            TELEGRAM_CHANNEL_ID,
            f"🎟️ *НОВЫЙ ПРОМОКОД!*\n\n"
            f"🔑 `{code}`\n"
            f"💰 Награда: {grams:,} GRAM каждому!\n"
            f"👥 Активаций: {mu}\n\n"
            f"⚡️ Вводи в боте → кнопка «🎟️ Промокод»",
            parse_mode="Markdown"
        )
        await message.answer("✅ Опубликовано в канале!")
    except Exception as e:
        await message.answer(f"⚠️ Создан, но не опубликован: {e}")

# --- список промокодов ---
@dp.callback_query(F.data == "adm_list")
async def adm_list(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    promos = db.get_all_promos()
    await callback.answer()
    if not promos: await callback.message.answer("Промокодов нет"); return
    text = "📋 *ПРОМОКОДЫ:*\n\n"
    for p in promos[:20]:
        code,grams,mu,used,_,_,active = p
        text += f"{'✅' if active else '❌'} `{code}` | {grams:,}💰 | {used}/{mu}👥\n"
    await callback.message.answer(text, parse_mode="Markdown")

# --- деактивировать ---
@dp.callback_query(F.data == "adm_deact")
async def adm_deact_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    await callback.answer()
    await callback.message.answer("Введи код промокода для деактивации:")
    await state.set_state(AdminDeactState.waiting_code)

@dp.message(AdminDeactState.waiting_code)
async def adm_deact_code(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    code = message.text.strip().upper()
    if not db.get_promo(code):
        await message.answer("❌ Не найден"); await state.clear(); return
    db.deactivate_promo(code); await state.clear()
    await message.answer(f"✅ `{code}` деактивирован", parse_mode="Markdown")

# --- рассылка ---
@dp.callback_query(F.data == "adm_broadcast")
async def adm_bc_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("❌")
    await callback.answer()
    await callback.message.answer("📢 Введи текст рассылки:")
    await state.set_state(AdminBroadcastState.waiting_text)

@dp.message(AdminBroadcastState.waiting_text)
async def adm_bc_send(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.clear(); return
    text = message.text; await state.clear()
    users = db.get_all_users()
    sent = failed = 0
    sm = await message.answer(f"📢 Рассылка {len(users)} пользователям...")
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 *От администратора:*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except: failed += 1
        await asyncio.sleep(0.05)
    await sm.edit_text(f"✅ *Рассылка завершена*\n\n✅ Доставлено: {sent}\n❌ Не доставлено: {failed}",
                       parse_mode="Markdown")

# =====================================================================
# 🚀 ЗАПУСК
# =====================================================================

async def main():
    logger.info("✅ Бот запущен")
    if not ADMIN_IDS or ADMIN_IDS == [123456789]:
        logger.warning("⚠️  Замени ADMIN_IDS на свой реальный Telegram ID в main.py!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
