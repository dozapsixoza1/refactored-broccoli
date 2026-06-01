"""
🎮 GRAM Bot v2.0 - Полный функционал в одном файле
С минным полем, казной, магазином, дуэлями, промокодами и админ-панелью
"""

import os
import sqlite3
import json
import random
import string
import logging
import asyncio
import math
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# =====================================================================
# ⚙️ КОНФИГУРАЦИЯ
# =====================================================================

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN', '8490098380:AAF087A6UMDeC6Dd_uZb7bAxT8VsGCcS8yI')
TELEGRAM_CHANNEL = "https://t.me/gramvaly"
TELEGRAM_CHANNEL_ID = "@gramvaly"  # для проверки подписки и отправки промокодов

ADMIN_IDS = [8526401545]
# Настройки игры
STARTING_BALANCE = 1000
DAILY_BONUS_MIN = 2500
DAILY_BONUS_MAX = 5000
DAILY_BONUS_COOLDOWN = 86400  # 24 часа
DUEL_COOLDOWN = 600  # 10 минут
CLAN_BONUS_COOLDOWN = 172800  # 48 часов

# Лимиты передачи
TRANSFER_LIMITS = {1: 5000, 2: 10000, 3: 25000, 4: 50000, 5: float('inf')}
LEVEL_COSTS = {2: 5000, 3: 10000, 4: 25000, 5: 50000}

# Магазин (граммы за звёзды)
SHOP_ITEMS = {
    '100k':  {'grams': 100000,   'stars': 15},
    '204k':  {'grams': 204000,   'stars': 30},
    '525k':  {'grams': 525000,   'stars': 100},
    '1.15m': {'grams': 1150000,  'stars': 250},
    '2.3m':  {'grams': 2300000,  'stars': 500},
    '6.25m': {'grams': 6250000,  'stars': 1000},
}

# Казна
TREASURY_SETUP_COST = 10000
DEFAULT_REWARD = 1000

# Боссы
BOSSES = {
    1:  {'name': 'Гарри Поттер',          'level': 0,   'hp': 1000,      'reward': 50,     'rings': 0},
    2:  {'name': 'Рон Уизли',             'level': 0,   'hp': 5000,      'reward': 80,     'rings': 1},
    3:  {'name': 'Гермиона Грейнджер',    'level': 7,   'hp': 25000,     'reward': 150,    'rings': 2},
    4:  {'name': 'Рубеус Хагрид',         'level': 12,  'hp': 100000,    'reward': 400,    'rings': 3},
    5:  {'name': 'Ремус Люпин',           'level': 20,  'hp': 250000,    'reward': 1000,   'rings': 4},
    6:  {'name': 'Сивилла Трелони',       'level': 27,  'hp': 750000,    'reward': 2500,   'rings': 5},
    7:  {'name': 'Аргус Филч',            'level': 35,  'hp': 2000000,   'reward': 5000,   'rings': 6},
    8:  {'name': 'Сириус Блэк',           'level': 50,  'hp': 5000000,   'reward': 10000,  'rings': 7},
    9:  {'name': 'Минерва МакГонагалл',   'level': 70,  'hp': 15000000,  'reward': 20000,  'rings': 8},
    10: {'name': 'Северус Снейп',         'level': 100, 'hp': 50000000,  'reward': 50000,  'rings': 9},
    11: {'name': 'Альбус Дамблдор',       'level': 150, 'hp': 250000000, 'reward': 150000, 'rings': 10},
}

BASE_STATS = {
    'health': 9, 'strength': 12, 'endurance': 9, 'block': 8,
    'charisma': 8, 'intuition': 7, 'speed': 6
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
# 💾 БАЗА ДАННЫХ v2
# =====================================================================

class Database:
    def __init__(self, db_path='game_data.db'):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 0,
                stars INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                user_id INTEGER PRIMARY KEY,
                health INTEGER DEFAULT 9,
                strength INTEGER DEFAULT 12,
                endurance INTEGER DEFAULT 9,
                block INTEGER DEFAULT 8,
                charisma INTEGER DEFAULT 8,
                intuition INTEGER DEFAULT 7,
                speed INTEGER DEFAULT 6
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                subscribed INTEGER DEFAULT 0,
                checked_at TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS treasuries (
                chat_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                balance INTEGER DEFAULT 0,
                reward_per_invite INTEGER DEFAULT 1000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS treasury_members (
                user_id INTEGER,
                chat_id INTEGER,
                inviter_id INTEGER,
                received_reward INTEGER DEFAULT 0,
                UNIQUE(user_id, chat_id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS bonuses (
                bonus_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS duels (
                duel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player1_id INTEGER,
                player2_id INTEGER,
                winner_id INTEGER,
                reward INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS transfers (
                transfer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER,
                to_user_id INTEGER,
                amount INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS minesweeper_games (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                field TEXT,
                revealed TEXT,
                stakes TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS clans (
                clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_name TEXT UNIQUE,
                owner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS clan_members (
                user_id INTEGER PRIMARY KEY,
                clan_id INTEGER
            )
        ''')

        # ===== ПРОМОКОДЫ =====
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                grams INTEGER NOT NULL,
                max_uses INTEGER NOT NULL,
                used_count INTEGER DEFAULT 0,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        ''')

        # Кто уже использовал промокод
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS promo_uses (
                use_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                user_id INTEGER,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, user_id)
            )
        ''')

        self.conn.commit()

    # ========== ПОЛЬЗОВАТЕЛИ ==========
    def create_user(self, user_id, username):
        try:
            self.cursor.execute(
                'INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)',
                (user_id, username, STARTING_BALANCE)
            )
            self.cursor.execute('INSERT INTO stats (user_id) VALUES (?)', (user_id,))
            self.cursor.execute('INSERT INTO subscriptions (user_id) VALUES (?)', (user_id,))
            self.conn.commit()
            return True
        except:
            return False

    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone()

    def user_exists(self, user_id):
        return self.get_user(user_id) is not None

    def get_balance(self, user_id):
        self.cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def add_balance(self, user_id, amount):
        self.cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        self.conn.commit()

    def subtract_balance(self, user_id, amount):
        self.cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
        self.conn.commit()

    def add_stars(self, user_id, amount):
        self.cursor.execute('UPDATE users SET stars = stars + ? WHERE user_id = ?', (amount, user_id))
        self.conn.commit()

    def subtract_stars(self, user_id, amount):
        self.cursor.execute('UPDATE users SET stars = stars - ? WHERE user_id = ?', (amount, user_id))
        self.conn.commit()

    def get_stats(self, user_id):
        self.cursor.execute('SELECT * FROM stats WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        if result:
            return {
                'health': result[1], 'strength': result[2], 'endurance': result[3],
                'block': result[4], 'charisma': result[5], 'intuition': result[6], 'speed': result[7]
            }
        return None

    def get_last_bonus(self, user_id):
        self.cursor.execute(
            'SELECT claimed_at FROM bonuses WHERE user_id = ? ORDER BY claimed_at DESC LIMIT 1',
            (user_id,)
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    def claim_bonus(self, user_id, amount):
        self.cursor.execute(
            'INSERT INTO bonuses (user_id, amount, type) VALUES (?, ?, ?)',
            (user_id, amount, 'daily')
        )
        self.conn.commit()

    def is_subscribed(self, user_id):
        self.cursor.execute('SELECT subscribed FROM subscriptions WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def set_subscribed(self, user_id, subscribed):
        self.cursor.execute(
            'UPDATE subscriptions SET subscribed = ?, checked_at = CURRENT_TIMESTAMP WHERE user_id = ?',
            (subscribed, user_id)
        )
        self.conn.commit()

    def get_top_users(self, limit=10):
        self.cursor.execute(
            'SELECT user_id, username, balance, level FROM users ORDER BY balance DESC LIMIT ?',
            (limit,)
        )
        return self.cursor.fetchall()

    def get_all_users(self):
        self.cursor.execute('SELECT user_id FROM users')
        return [row[0] for row in self.cursor.fetchall()]

    def get_user_count(self):
        self.cursor.execute('SELECT COUNT(*) FROM users')
        return self.cursor.fetchone()[0]

    def add_duel(self, player1_id, player2_id, winner_id, reward):
        try:
            self.cursor.execute(
                'INSERT INTO duels (player1_id, player2_id, winner_id, reward) VALUES (?, ?, ?, ?)',
                (player1_id, player2_id, winner_id, reward)
            )
            self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения дуэли: {e}")

    # ========== КАЗНА ==========
    def create_treasury(self, chat_id, owner_id):
        try:
            self.cursor.execute(
                'INSERT INTO treasuries (chat_id, owner_id) VALUES (?, ?)',
                (chat_id, owner_id)
            )
            self.conn.commit()
            return True
        except:
            return False

    def get_treasury(self, chat_id):
        self.cursor.execute('SELECT * FROM treasuries WHERE chat_id = ?', (chat_id,))
        return self.cursor.fetchone()

    def add_to_treasury(self, chat_id, amount):
        self.cursor.execute('UPDATE treasuries SET balance = balance + ? WHERE chat_id = ?', (amount, chat_id))
        self.conn.commit()

    def set_reward(self, chat_id, reward):
        self.cursor.execute('UPDATE treasuries SET reward_per_invite = ? WHERE chat_id = ?', (reward, chat_id))
        self.conn.commit()

    # ========== МИННОЕ ПОЛЕ ==========
    def create_minesweeper_game(self, user_id, chat_id, field, stakes):
        try:
            field_json = json.dumps(field)
            stakes_json = json.dumps(stakes)
            revealed = json.dumps([False] * 25)
            self.cursor.execute(
                'INSERT INTO minesweeper_games (user_id, chat_id, field, revealed, stakes, status) VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, chat_id, field_json, revealed, stakes_json, 'active')
            )
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при создании игры в минах: {e}")
            return None

    # ========== ПРОМОКОДЫ ==========
    def create_promo(self, code, grams, max_uses, created_by):
        try:
            self.cursor.execute(
                'INSERT INTO promo_codes (code, grams, max_uses, created_by) VALUES (?, ?, ?, ?)',
                (code, grams, max_uses, created_by)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка создания промокода: {e}")
            return False

    def get_promo(self, code):
        self.cursor.execute('SELECT * FROM promo_codes WHERE code = ?', (code,))
        return self.cursor.fetchone()

    def use_promo(self, code, user_id):
        """Возвращает (успех, сообщение, граммы)"""
        promo = self.get_promo(code)
        if not promo:
            return False, "❌ Промокод не найден", 0

        # promo: code, grams, max_uses, used_count, created_by, created_at, is_active
        p_code, p_grams, p_max_uses, p_used_count, p_created_by, p_created_at, p_is_active = promo

        if not p_is_active:
            return False, "❌ Промокод больше не активен", 0

        if p_used_count >= p_max_uses:
            return False, "❌ Промокод уже использован максимальное количество раз", 0

        # Проверяем, не использовал ли этот юзер
        self.cursor.execute(
            'SELECT use_id FROM promo_uses WHERE code = ? AND user_id = ?',
            (code, user_id)
        )
        if self.cursor.fetchone():
            return False, "❌ Ты уже использовал этот промокод", 0

        # Применяем
        try:
            self.cursor.execute(
                'INSERT INTO promo_uses (code, user_id) VALUES (?, ?)',
                (code, user_id)
            )
            self.cursor.execute(
                'UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?',
                (code,)
            )
            # Деактивируем если достигли лимита
            if p_used_count + 1 >= p_max_uses:
                self.cursor.execute(
                    'UPDATE promo_codes SET is_active = 0 WHERE code = ?',
                    (code,)
                )
            self.conn.commit()
            self.add_balance(user_id, p_grams)
            return True, f"✅ Промокод активирован! +{p_grams:,} GRAM", p_grams
        except Exception as e:
            logger.error(f"Ошибка активации промокода: {e}")
            return False, "❌ Ошибка при активации промокода", 0

    def get_all_promos(self):
        self.cursor.execute('SELECT * FROM promo_codes ORDER BY created_at DESC')
        return self.cursor.fetchall()

    def deactivate_promo(self, code):
        self.cursor.execute('UPDATE promo_codes SET is_active = 0 WHERE code = ?', (code,))
        self.conn.commit()


db = Database()

# =====================================================================
# 🎮 ИГРОВАЯ ЛОГИКА
# =====================================================================

class GameLogic:
    @staticmethod
    def generate_minesweeper_field():
        field = [0] * 25
        mines_count = random.randint(3, 7)
        mine_positions = random.sample(range(25), mines_count)
        for pos in mine_positions:
            field[pos] = 1
        return field

    @staticmethod
    def generate_promo_code():
        """Генерирует случайный красивый промокод"""
        adjectives = ['MEGA', 'SUPER', 'GOLD', 'EPIC', 'LUCKY', 'GRAM', 'FIRE', 'STAR', 'WIN', 'RICH']
        nouns = ['BOOST', 'DROP', 'GIFT', 'BONUS', 'CASH', 'LOOT', 'PRIZE', 'GRAMS', 'PAY', 'FUND']
        adj = random.choice(adjectives)
        noun = random.choice(nouns)
        num = random.randint(10, 99)
        return f"{adj}{noun}{num}"

    @staticmethod
    def calculate_duel_damage(attacker_stats, defender_stats):
        base_damage = attacker_stats['strength'] * 10
        luck = random.randint(-5, 15)
        defense = defender_stats['block'] * 5
        return max(1, base_damage + luck - defense)

    @staticmethod
    def calculate_duel_winner(player1_stats, player2_stats):
        player1_hp = player1_stats['health'] * 10
        player2_hp = player2_stats['health'] * 10
        rounds = 0
        while player1_hp > 0 and player2_hp > 0 and rounds < 20:
            damage = GameLogic.calculate_duel_damage(player1_stats, player2_stats)
            player2_hp -= damage
            if player2_hp <= 0:
                return 1
            damage = GameLogic.calculate_duel_damage(player2_stats, player1_stats)
            player1_hp -= damage
            if player1_hp <= 0:
                return 2
            rounds += 1
        return 1 if player1_hp > player2_hp else 2

    @staticmethod
    def get_random_bonus():
        return random.randint(DAILY_BONUS_MIN, DAILY_BONUS_MAX)

# =====================================================================
# 🤖 БОТ
# =====================================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class DuelState(StatesGroup):
    waiting_opponent = State()

class TransferState(StatesGroup):
    waiting_amount = State()

class MinesState(StatesGroup):
    choosing_cell = State()

# FSM для создания промокода (для админа)
class PromoCreateState(StatesGroup):
    waiting_grams = State()
    waiting_max_uses = State()

# FSM для выдачи граммов (для админа)
class AdminGiveState(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()

# =====================================================================
# 🛡️ ДЕКОРАТОРЫ
# =====================================================================

def admin_only(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("❌ У тебя нет прав администратора")
            return
        return await func(message, *args, **kwargs)
    return wrapper

# =====================================================================
# 🔔 ПРОВЕРКА ПОДПИСКИ
# =====================================================================

async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(chat_id=TELEGRAM_CHANNEL_ID, user_id=user_id)
        is_subscribed = member.status in ['member', 'administrator', 'creator']
        db.set_subscribed(user_id, 1 if is_subscribed else 0)
        return is_subscribed
    except:
        return False

# =====================================================================
# 📋 ХЭНДЛЕРЫ
# =====================================================================

# ========== START ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    if not db.user_exists(user_id):
        db.create_user(user_id, username)

    is_subscribed = await check_subscription(user_id)

    if not is_subscribed:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=TELEGRAM_CHANNEL)],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription")],
        ])
        await message.answer(
            "⚠️ Сначала подпишись на канал:\n\n"
            f"🔗 {TELEGRAM_CHANNEL}",
            reply_markup=keyboard
        )
        return

    # Кнопки главного меню
    kb_rows = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="⚔️ Дуэль"), KeyboardButton(text="🏰 Хогвартс")],
        [KeyboardButton(text="👥 Кланы"), KeyboardButton(text="📊 Топ")],
        [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="⌨️ Команды")],
        [KeyboardButton(text="🎟️ Промокод")],
    ]

    # Добавляем кнопку admin если нужно
    if user_id in ADMIN_IDS:
        kb_rows.append([KeyboardButton(text="🔐 Админ-панель")])

    keyboard = ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True)

    await message.answer(
        f"👋 Добро пожаловать, {username}!\n\n"
        f"💰 Ваш баланс: {db.get_balance(user_id):,} 🪙\n\n"
        f"Выберите действие:",
        reply_markup=keyboard
    )

# ========== ПРОВЕРКА ПОДПИСКИ (callback) ==========
@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed = await check_subscription(user_id)

    if is_subscribed:
        await callback.answer("✅ Спасибо за подписку!", show_alert=True)
        await cmd_start(callback.message)
    else:
        await callback.answer("❌ Ты еще не подписан на канал!", show_alert=True)

# ========== КОМАНДЫ ==========
@dp.message(F.text == "⌨️ Команды")
async def show_commands(message: types.Message):
    text = (
        "📋 *ДОСТУПНЫЕ КОМАНДЫ:*\n\n"
        "💰 *Баланс и переводы:*\n"
        "`б` или `баланс` — проверка баланса\n"
        "`п сумма` — перевод в ответ на сообщение\n"
        "`п @username сумма` — перевод по username\n"
        "`п ID сумма` — перевод по ID\n\n"
        "👤 *Профиль:*\n"
        "`/профиль` — просмотр профиля\n\n"
        "⚔️ *Дуэли:*\n"
        "`дуэль` — вызов соперника (в ответ на сообщение)\n\n"
        "💣 *Минное поле:*\n"
        "`мины сумма` — игра в минное поле\n\n"
        "📊 *Рейтинги:*\n"
        "`/топ` или `/top` — топ 10 игроков\n\n"
        "🎟️ *Промокоды:*\n"
        "Кнопка «🎟️ Промокод» — ввести промокод\n"
    )
    await message.answer(text, parse_mode="Markdown")

# ========== БАЛАНС ==========
@dp.message(F.text.in_({"💰 Баланс", "б", "баланс"}))
async def show_balance(message: types.Message):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)

    if not user_data:
        await message.answer("❌ Профиль не найден. Напиши /start")
        return

    balance = user_data[2]
    stars = user_data[3]

    last_bonus = db.get_last_bonus(user_id)
    bonus_available = True
    time_remaining = None

    if last_bonus:
        last_time = datetime.fromisoformat(last_bonus)
        if datetime.now() - last_time < timedelta(seconds=DAILY_BONUS_COOLDOWN):
            bonus_available = False
            remaining = DAILY_BONUS_COOLDOWN - int((datetime.now() - last_time).total_seconds())
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            time_remaining = f"{hours}:{minutes:02d}:{seconds:02d}"

    text = "💰 *ВАШИ ДЕНЬГИ*\n\n"
    text += f"🪙 Граммы: {balance:,}\n"
    text += f"⭐️ Звёзды: {stars}\n"
    text += f"📊 Уровень: {user_data[4]}\n\n"

    if bonus_available:
        text += "✅ Бонус доступен! Нажми кнопку ниже"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Получить бонус", callback_data="claim_daily_bonus")],
        ])
    else:
        text += f"⏳ Следующий бонус через {time_remaining}"
        keyboard = None

    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
@dp.callback_query(F.data == "claim_daily_bonus")
async def claim_daily_bonus(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    last_bonus = db.get_last_bonus(user_id)

    if last_bonus:
        last_time = datetime.fromisoformat(last_bonus)
        if datetime.now() - last_time < timedelta(seconds=DAILY_BONUS_COOLDOWN):
            remaining = DAILY_BONUS_COOLDOWN - int((datetime.now() - last_time).total_seconds())
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            await callback.answer(f"⏳ Осталось {hours}:{minutes:02d}", show_alert=True)
            return

    bonus_amount = GameLogic.get_random_bonus()
    db.add_balance(user_id, bonus_amount)
    db.claim_bonus(user_id, bonus_amount)

    text = (
        "🎁 *БОНУС ПОЛУЧЕН!*\n\n"
        f"✅ Начислено: {bonus_amount:,} GRAM\n\n"
        "⏰ Следующий бонус через 24 часа"
    )
    await callback.answer()
    await callback.message.answer(text, parse_mode="Markdown")

# ========== ПЕРЕДАЧА (в ответ) ==========
@dp.message(F.reply_to_message & F.text.startswith("п "))
async def transfer_money_reply(message: types.Message):
    try:
        amount = int(message.text.split()[1])
    except (ValueError, IndexError):
        await message.answer("❌ Используйте: п сумма")
        return

    sender_id = message.from_user.id
    recipient_id = message.reply_to_message.from_user.id

    if sender_id == recipient_id:
        await message.answer("❌ Нельзя переводить самому себе")
        return

    sender_balance = db.get_balance(sender_id)
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    if sender_balance < amount:
        await message.answer(f"❌ Недостаточно! У вас: {sender_balance:,}")
        return

    db.subtract_balance(sender_id, amount)
    db.add_balance(recipient_id, amount)

    text = (
        "✅ *ДЕНЬГИ ПЕРЕВЕДЕНЫ*\n\n"
        f"📤 Отправлено: {amount:,} 🪙\n"
        f"📥 Получатель: {message.reply_to_message.from_user.first_name}"
    )
    await message.answer(text, parse_mode="Markdown")

# ========== ПЕРЕДАЧА (по ID/username) ==========
@dp.message(F.text.startswith("п ") & ~F.reply_to_message)
async def transfer_money_id(message: types.Message):
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Используйте: п @username сумма или п ID сумма")
        return

    try:
        amount = int(parts[-1])
        identifier = parts[1]
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return

    recipient_id = None
    if identifier.startswith('@'):
        try:
            user_chat = await bot.get_chat(identifier)
            recipient_id = user_chat.id
        except:
            await message.answer(f"❌ Пользователь {identifier} не найден")
            return
    else:
        try:
            recipient_id = int(identifier)
        except ValueError:
            await message.answer("❌ Неверный ID или username")
            return

    sender_id = message.from_user.id
    sender_balance = db.get_balance(sender_id)

    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    if sender_balance < amount:
        await message.answer(f"❌ Недостаточно! У вас: {sender_balance:,}")
        return
    if not db.user_exists(recipient_id):
        await message.answer("❌ Получатель не найден в системе")
        return

    db.subtract_balance(sender_id, amount)
    db.add_balance(recipient_id, amount)

    text = (
        "✅ *ДЕНЬГИ ПЕРЕВЕДЕНЫ*\n\n"
        f"📤 Отправлено: {amount:,} 🪙\n"
        f"📥 Получатель: ID {recipient_id}"
    )
    await message.answer(text, parse_mode="Markdown")

# ========== ПРОФИЛЬ ==========
@dp.message(F.text.in_({"👤 Профиль", "/профиль"}))
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    stats = db.get_stats(user_id)

    if not user_data or not stats:
        await message.answer("❌ Профиль не найден. Напиши /start")
        return

    balance = user_data[2]
    stars = user_data[3]
    level = user_data[4]

    text = "👤 *ПРОФИЛЬ*\n\n"
    text += f"💰 Баланс: {balance:,} 🪙\n"
    text += f"⭐️ Звёзды: {stars}\n"
    text += f"📊 Уровень: {level}\n"
    text += f"🆔 ID: `{user_id}`\n\n"
    text += "*Характеристики:*\n"
    for stat_key, stat_value in stats.items():
        emoji = STAT_EMOJIS.get(stat_key, '•')
        name = STAT_NAMES.get(stat_key, stat_key)
        text += f"{emoji} {name}: {stat_value}\n"

    await message.answer(text, parse_mode="Markdown")

# ========== МАГАЗИН ==========
@dp.message(F.text == "🛒 Магазин")
async def show_shop(message: types.Message):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    stars = user_data[3] if user_data else 0

    text = "🛒 *МАГАЗИН ГРАММОВ*\n\n"
    text += f"⭐️ Ваши звёзды: {stars}\n\n"
    text += "*Доступные предложения:*\n\n"

    buttons = []
    for key, item in SHOP_ITEMS.items():
        grams = item['grams']
        cost = item['stars']
        text += f"💰 {grams:,} GRAM → {cost} ⭐️\n"
        buttons.append([InlineKeyboardButton(
            text=f"{grams:,} GRAM ({cost}⭐️)",
            callback_data=f"buy_{key}"
        )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("buy_"))
async def buy_grams(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    key = callback.data[4:]

    if key not in SHOP_ITEMS:
        await callback.answer("❌ Товар не найден", show_alert=True)
        return

    item = SHOP_ITEMS[key]
    grams = item['grams']
    cost = item['stars']

    user_data = db.get_user(user_id)
    stars = user_data[3] if user_data else 0

    if stars < cost:
        await callback.answer(f"❌ Нужно {cost} ⭐️, у вас {stars}", show_alert=True)
        return

    db.subtract_stars(user_id, cost)
    db.add_balance(user_id, grams)

    text = (
        "✅ *ПОКУПКА ЗАВЕРШЕНА!*\n\n"
        f"💰 Куплено: {grams:,} GRAM\n"
        f"⭐️ Потрачено: {cost} звёзд"
    )
    await callback.answer()
    await callback.message.answer(text, parse_mode="Markdown")

# ========== ДУЭЛЬ ==========
@dp.message(F.reply_to_message & F.text == "дуэль")
async def start_duel_reply(message: types.Message):
    opponent_id = message.reply_to_message.from_user.id
    player_id = message.from_user.id

    if player_id == opponent_id:
        await message.answer("❌ Нельзя дуэлиться самому с собой!")
        return
    if not db.user_exists(opponent_id):
        await message.answer("❌ Противник не в системе")
        return

    player_stats = db.get_stats(player_id)
    opponent_stats = db.get_stats(opponent_id)

    animation_text = "⚔️ *БОЕВАЯ СИСТЕМА АКТИВИРОВАНА* ⚔️\n\n"
    frames = ["⚔️ ·  ·  ·", "· ⚔️ ·  ·", "·  · ⚔️ ·", "·  ·  · ⚔️"]

    sent_msg = await message.answer(animation_text + frames[0], parse_mode="Markdown")
    for frame in frames[1:]:
        await asyncio.sleep(0.5)
        try:
            await sent_msg.edit_text(animation_text + frame, parse_mode="Markdown")
        except:
            pass

    await asyncio.sleep(1)

    winner_id = GameLogic.calculate_duel_winner(player_stats, opponent_stats)
    player_data = db.get_user(player_id)
    opponent_data = db.get_user(opponent_id)
    level_diff = abs(player_data[4] - opponent_data[4])
    reward = 50 + (level_diff * 10)

    if winner_id == 1:
        db.add_balance(player_id, reward)
        db.add_stars(player_id, 10)
        result_text = f"🎉 *{message.from_user.first_name} ПОБЕДИЛ!*\n\nНаграда: +{reward:,} 🪙 и +10 ⭐️"
    else:
        db.add_balance(opponent_id, reward)
        db.add_stars(opponent_id, 10)
        opponent_name = message.reply_to_message.from_user.first_name
        result_text = f"💔 *{opponent_name} ПОБЕДИЛ!*\n\nНаграда: +{reward:,} 🪙 и +10 ⭐️"

    db.add_duel(player_id, opponent_id,
                player_id if winner_id == 1 else opponent_id, reward)

    duel_text = (
        "⚔️ *ДУЭЛЬ*\n\n"
        f"🥊 {message.from_user.first_name} vs {message.reply_to_message.from_user.first_name}\n\n"
        f"❤️ HP: {player_stats['health']*10} vs {opponent_stats['health']*10}\n"
        f"💪 Сила: {player_stats['strength']} vs {opponent_stats['strength']}\n\n"
        + result_text
    )
    await sent_msg.edit_text(duel_text, parse_mode="Markdown")

# ========== ТОП ==========
@dp.message(F.text.in_({"📊 Топ", "/top", "/топ"}))
async def show_top(message: types.Message):
    text = "📊 *ТОП 10 ИГРОКОВ*\n\n"
    medals = ["🥇", "🥈", "🥉"]
    top_users = db.get_top_users(10)

    for i, user in enumerate(top_users, 1):
        user_id, username, balance, level = user
        medal = medals[i-1] if i <= 3 else f"{i}."
        text += f"{medal} {username} — {balance:,} 🪙 (Ур.{level})\n"

    await message.answer(text, parse_mode="Markdown")

# ========== МИННОЕ ПОЛЕ ==========
@dp.message(F.text.startswith("мины "))
async def start_minesweeper(message: types.Message):
    try:
        amount = int(message.text.split()[1])
    except (ValueError, IndexError):
        await message.answer("❌ Используйте: мины сумма")
        return

    user_id = message.from_user.id
    user_balance = db.get_balance(user_id)

    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    if user_balance < amount:
        await message.answer(f"❌ Недостаточно! У вас: {user_balance:,}")
        return

    field = GameLogic.generate_minesweeper_field()
    field_display = "🎮 *МИННОЕ ПОЛЕ 5×5*\n\n"
    for i in range(5):
        field_display += "❓ " * 5 + "\n"
    field_display += f"\n💰 Ставка: {amount:,} 🪙\n"
    field_display += "Введи координаты от 1 до 25, чтобы открыть ячейку"

    stakes = {'total': amount}
    game_id = db.create_minesweeper_game(user_id, message.chat.id, field, stakes)

    if not game_id:
        await message.answer("❌ Ошибка при создании игры")
        return

    db.subtract_balance(user_id, amount)
    await message.answer(field_display, parse_mode="Markdown")

# ========== КЛАНЫ ==========
@dp.message(F.text.in_({"👥 Кланы", "/клан"}))
async def show_clans(message: types.Message):
    await message.answer("👥 *КЛАНЫ*\n\nФункция кланов в разработке 🔧", parse_mode="Markdown")

# ========== ХОГВАРТС ==========
@dp.message(F.text == "🏰 Хогвартс")
async def show_hogwarts(message: types.Message):
    await message.answer("🏰 *ХОГВАРТС*\n\nФункция Хогвартса в разработке 🔧", parse_mode="Markdown")

# =====================================================================
# 🎟️ ПРОМОКОДЫ
# =====================================================================

@dp.message(F.text == "🎟️ Промокод")
async def promo_menu(message: types.Message, state: FSMContext):
    await message.answer(
        "🎟️ *ПРОМОКОДЫ*\n\n"
        "Введи промокод чтобы получить граммы!\n\n"
        "Напиши промокод:",
        parse_mode="Markdown"
    )
    await state.set_state(PromoCreateState.waiting_grams)  # Переиспользуем State как ввод промо

# Отдельный хэндлер для ввода промокода (любой текст после нажатия кнопки)
@dp.message(F.text == "🎟️ Промокод")
async def promo_menu_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟️ Ввести промокод", callback_data="enter_promo")]
    ])
    await message.answer(
        "🎟️ *ПРОМОКОДЫ*\n\n"
        "Нажми кнопку чтобы ввести промокод:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "enter_promo")
async def enter_promo_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Введи промокод:")
    await state.set_state(PromoEnterState.waiting_code)

class PromoEnterState(StatesGroup):
    waiting_code = State()

@dp.message(PromoEnterState.waiting_code)
async def process_promo_code(message: types.Message, state: FSMContext):
    await state.clear()
    code = message.text.strip().upper()
    user_id = message.from_user.id

    success, msg, grams = db.use_promo(code, user_id)
    await message.answer(msg, parse_mode="Markdown")

# =====================================================================
# 🔐 АДМИН-ПАНЕЛЬ
# =====================================================================

@dp.message(F.text == "🔐 Админ-панель")
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Нет доступа")
        return

    user_count = db.get_user_count()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать граммы",   callback_data="admin_give_grams")],
        [InlineKeyboardButton(text="🎟️ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin_list_promos")],
        [InlineKeyboardButton(text="🚫 Деактивировать промо", callback_data="admin_deact_promo")],
        [InlineKeyboardButton(text="📢 Рассылка",        callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 Статистика",      callback_data="admin_stats")],
    ])
    await message.answer(
        f"🔐 *АДМИН-ПАНЕЛЬ*\n\n"
        f"👥 Пользователей: {user_count}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ---- Статистика ----
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Нет доступа")

    user_count = db.get_user_count()
    promos = db.get_all_promos()
    active_promos = sum(1 for p in promos if p[6])

    await callback.answer()
    await callback.message.answer(
        f"📊 *СТАТИСТИКА*\n\n"
        f"👥 Всего пользователей: {user_count}\n"
        f"🎟️ Всего промокодов: {len(promos)}\n"
        f"✅ Активных промокодов: {active_promos}",
        parse_mode="Markdown"
    )

# ---- Выдать граммы ----
@dp.callback_query(F.data == "admin_give_grams")
async def admin_give_grams_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Нет доступа")
    await callback.answer()
    await callback.message.answer("👤 Введи ID пользователя которому выдать граммы:")
    await state.set_state(AdminGiveState.waiting_user_id)

@dp.message(AdminGiveState.waiting_user_id)
async def admin_give_grams_user(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовой ID")
        return

    if not db.user_exists(target_id):
        await message.answer("❌ Пользователь не найден в системе")
        await state.clear()
        return

    await state.update_data(target_id=target_id)
    await message.answer(f"💰 Введи количество граммов для выдачи пользователю {target_id}:")
    await state.set_state(AdminGiveState.waiting_amount)

@dp.message(AdminGiveState.waiting_amount)
async def admin_give_grams_amount(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return

    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовое количество")
        return

    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        await state.clear()
        return

    data = await state.get_data()
    target_id = data['target_id']

    db.add_balance(target_id, amount)
    await state.clear()

    # Уведомляем получателя
    try:
        await bot.send_message(
            target_id,
            f"🎁 Администратор выдал вам *{amount:,} GRAM*!",
            parse_mode="Markdown"
        )
    except:
        pass

    await message.answer(
        f"✅ *Выдано!*\n\n"
        f"👤 Пользователь: {target_id}\n"
        f"💰 Сумма: {amount:,} GRAM",
        parse_mode="Markdown"
    )

# ---- Создать промокод ----
@dp.callback_query(F.data == "admin_create_promo")
async def admin_create_promo_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Нет доступа")
    await callback.answer()
    await callback.message.answer("💰 Введи количество GRAM которое получит каждый пользователь по промокоду:")
    await state.set_state(PromoCreateState.waiting_grams)

@dp.message(PromoCreateState.waiting_grams)
async def admin_promo_grams(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return

    try:
        grams = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовое количество граммов")
        return

    if grams <= 0:
        await message.answer("❌ Количество граммов должно быть больше 0")
        await state.clear()
        return

    await state.update_data(grams=grams)
    await message.answer("👥 Введи максимальное количество пользователей которые могут использовать промокод:")
    await state.set_state(PromoCreateState.waiting_max_uses)

@dp.message(PromoCreateState.waiting_max_uses)
async def admin_promo_max_uses(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return

    try:
        max_uses = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовое количество")
        return

    if max_uses <= 0:
        await message.answer("❌ Количество использований должно быть больше 0")
        await state.clear()
        return

    data = await state.get_data()
    grams = data['grams']

    # Генерируем уникальный код
    code = GameLogic.generate_promo_code()
    # На случай коллизии
    attempts = 0
    while db.get_promo(code) and attempts < 10:
        code = GameLogic.generate_promo_code()
        attempts += 1

    success = db.create_promo(code, grams, max_uses, message.from_user.id)
    await state.clear()

    if not success:
        await message.answer("❌ Ошибка при создании промокода")
        return

    promo_text = (
        f"🎟️ *НОВЫЙ ПРОМОКОД СОЗДАН!*\n\n"
        f"🔑 Код: `{code}`\n"
        f"💰 Награда: {grams:,} GRAM\n"
        f"👥 Макс. использований: {max_uses}\n\n"
        f"Нажми на код чтобы скопировать!"
    )

    await message.answer(promo_text, parse_mode="Markdown")

    # Публикуем в канал
    channel_text = (
        f"🎟️ *ПРОМОКОД ДЛЯ ВСЕХ!*\n\n"
        f"🔑 Код: `{code}`\n"
        f"💰 Награда: {grams:,} GRAM каждому!\n"
        f"👥 Количество активаций: {max_uses}\n\n"
        f"⚡️ Торопись — количество ограничено!\n"
        f"👉 Введи код в боте: кнопка «🎟️ Промокод»"
    )
    try:
        await bot.send_message(TELEGRAM_CHANNEL_ID, channel_text, parse_mode="Markdown")
        await message.answer("✅ Промокод опубликован в канале!")
    except Exception as e:
        await message.answer(f"⚠️ Промокод создан, но не удалось опубликовать в канале: {e}")

# ---- Список промокодов ----
@dp.callback_query(F.data == "admin_list_promos")
async def admin_list_promos(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Нет доступа")

    promos = db.get_all_promos()
    await callback.answer()

    if not promos:
        await callback.message.answer("📋 Промокодов пока нет")
        return

    text = "📋 *СПИСОК ПРОМОКОДОВ:*\n\n"
    for p in promos[:20]:  # Показываем не больше 20
        code, grams, max_uses, used_count, created_by, created_at, is_active = p
        status = "✅" if is_active else "❌"
        text += f"{status} `{code}` | {grams:,}💰 | {used_count}/{max_uses}👥\n"

    await callback.message.answer(text, parse_mode="Markdown")

# ---- Деактивировать промокод ----
@dp.callback_query(F.data == "admin_deact_promo")
async def admin_deact_promo_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Нет доступа")
    await callback.answer()
    await callback.message.answer("Введи код промокода который нужно деактивировать:")
    await state.set_state(AdminDeactState.waiting_code)

class AdminDeactState(StatesGroup):
    waiting_code = State()

@dp.message(AdminDeactState.waiting_code)
async def admin_deact_promo_code(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return

    code = message.text.strip().upper()
    promo = db.get_promo(code)

    if not promo:
        await message.answer("❌ Промокод не найден")
        await state.clear()
        return

    db.deactivate_promo(code)
    await state.clear()
    await message.answer(f"✅ Промокод `{code}` деактивирован", parse_mode="Markdown")

# ---- Рассылка ----
class AdminBroadcastState(StatesGroup):
    waiting_text = State()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Нет доступа")
    await callback.answer()
    await callback.message.answer("📢 Введи текст рассылки (отправится всем пользователям):")
    await state.set_state(AdminBroadcastState.waiting_text)

@dp.message(AdminBroadcastState.waiting_text)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return

    text = message.text
    await state.clear()

    all_users = db.get_all_users()
    sent = 0
    failed = 0

    status_msg = await message.answer(f"📢 Начинаю рассылку для {len(all_users)} пользователей...")

    for uid in all_users:
        try:
            await bot.send_message(uid, f"📢 *Сообщение от администратора:*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)  # Антифлуд

    await status_msg.edit_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"✅ Доставлено: {sent}\n"
        f"❌ Не доставлено: {failed}",
        parse_mode="Markdown"
    )

# =====================================================================
# 🚀 ЗАПУСК
# =====================================================================

async def main():
    logger.info("✅ Bot v2.0 запущен...")
    if not ADMIN_IDS:
        logger.warning("⚠️  ADMIN_IDS не задан в .env! Добавь ADMIN_IDS=твой_telegram_id")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
