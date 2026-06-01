"""
🎮 GRAM Bot v2.0 - Полный функционал в одном файле
С минным полем, казной, магазином, дуэлями и подписками
"""

import os
import sqlite3
import json
import random
import logging
import asyncio
import math
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, Text
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# =====================================================================
# ⚙️ КОНФИГУРАЦИЯ
# =====================================================================

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN', '8490098380:AAF087A6UMDeC6Dd_uZb7bAxT8VsGCcS8yI')
TELEGRAM_CHANNEL = "https://t.me/gramvaly"

# Настройки игры
STARTING_BALANCE = 100
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
    '100k': {'grams': 100000, 'stars': 15},
    '204k': {'grams': 204000, 'stars': 30},
    '525k': {'grams': 525000, 'stars': 100},
    '1.15m': {'grams': 1150000, 'stars': 250},
    '2.3m': {'grams': 2300000, 'stars': 500},
    '6.25m': {'grams': 6250000, 'stars': 1000},
}

# Казна
TREASURY_SETUP_COST = 10000  # звёзд
DEFAULT_REWARD = 1000  # грамм за приглашение

# Боссы
BOSSES = {
    1: {'name': 'Гарри Поттер', 'level': 0, 'hp': 1000, 'reward': 50, 'rings': 0},
    2: {'name': 'Рон Уизли', 'level': 0, 'hp': 5000, 'reward': 80, 'rings': 1},
    3: {'name': 'Гермиона Грейнджер', 'level': 7, 'hp': 25000, 'reward': 150, 'rings': 2},
    4: {'name': 'Рубеус Хагрид', 'level': 12, 'hp': 100000, 'reward': 400, 'rings': 3},
    5: {'name': 'Ремус Люпин', 'level': 20, 'hp': 250000, 'reward': 1000, 'rings': 4},
    6: {'name': 'Сивилла Трелони', 'level': 27, 'hp': 750000, 'reward': 2500, 'rings': 5},
    7: {'name': 'Аргус Филч', 'level': 35, 'hp': 2000000, 'reward': 5000, 'rings': 6},
    8: {'name': 'Сириус Блэк', 'level': 50, 'hp': 5000000, 'reward': 10000, 'rings': 7},
    9: {'name': 'Минерва МакГонагалл', 'level': 70, 'hp': 15000000, 'reward': 20000, 'rings': 8},
    10: {'name': 'Северус Снейп', 'level': 100, 'hp': 50000000, 'reward': 50000, 'rings': 9},
    11: {'name': 'Альбус Дамблдор', 'level': 150, 'hp': 250000000, 'reward': 150000, 'rings': 10},
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
    'charisma': '✨', 'intuition': '🔮', 'speed': '⚡'
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
        # Пользователи
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
        
        # Характеристики
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
        
        # Подписка на канал
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                subscribed INTEGER DEFAULT 0,
                checked_at TIMESTAMP
            )
        ''')
        
        # Казна в чатах
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS treasuries (
                chat_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                balance INTEGER DEFAULT 0,
                reward_per_invite INTEGER DEFAULT 1000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Казна - члены (кто уже получил награду)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS treasury_members (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                inviter_id INTEGER,
                received_reward INTEGER DEFAULT 0,
                UNIQUE(user_id, chat_id)
            )
        ''')
        
        # История бонусов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS bonuses (
                bonus_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # История дуэлей
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
        
        # История передач
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS transfers (
                transfer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER,
                to_user_id INTEGER,
                amount INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Минное поле (игры)
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
        
        # Кланы
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS clans (
                clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_name TEXT UNIQUE,
                owner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Члены клана
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS clan_members (
                user_id INTEGER PRIMARY KEY,
                clan_id INTEGER
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
            self.cursor.execute(
                'INSERT INTO stats (user_id) VALUES (?)', (user_id,)
            )
            self.cursor.execute(
                'INSERT INTO subscriptions (user_id) VALUES (?)', (user_id,)
            )
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

db = Database()

# =====================================================================
# 🎮 ИГРОВАЯ ЛОГИКА
# =====================================================================

class GameLogic:
    @staticmethod
    def generate_minesweeper_field():
        """Генерирует поле для минного поля (5x5)"""
        field = [0] * 25
        mines_count = random.randint(3, 7)
        
        mine_positions = random.sample(range(25), mines_count)
        for pos in mine_positions:
            field[pos] = 1  # 1 = мина
        
        return field
    
    @staticmethod
    def check_minesweeper(field, revealed, position):
        """Проверяет клик по минному полю"""
        if field[position] == 1:
            return False, "МИНА! 💣"  # Проигрыш
        return True, "Безопасно! ✅"  # Выигрыш
    
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

# ========== ПРОВЕРКА ПОДПИСКИ ==========
async def check_subscription(user_id):
    """Проверяет подписку на канал"""
    try:
        member = await bot.get_chat_member(chat_id="@gramvaly", user_id=user_id)
        is_subscribed = member.status in ['member', 'administrator', 'creator']
        db.set_subscribed(user_id, 1 if is_subscribed else 0)
        return is_subscribed
    except:
        return False

# ========== START ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    if not db.user_exists(user_id):
        db.create_user(user_id, username)
    
    # Проверяем подписку
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
    
    # Главное меню
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="⚔️ Дуэль"), KeyboardButton(text="🏰 Хогвартс")],
        [KeyboardButton(text="👥 Кланы"), KeyboardButton(text="📊 Топ")],
        [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="⌨️ Команды")],
    ], resize_keyboard=True)
    
    await message.answer(
        f"👋 Добро пожаловать, {username}!\n\n"
        f"💰 Ваш баланс: {db.get_balance(user_id)} 🪙\n\n"
        f"Выберите действие:",
        reply_markup=keyboard
    )

# ========== ПРОВЕРКА ПОДПИСКИ (callback) ==========
@dp.callback_query(Text("check_subscription"))
async def check_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed = await check_subscription(user_id)
    
    if is_subscribed:
        await callback.answer("✅ Спасибо за подписку!", show_alert=True)
        await cmd_start(callback.message)
    else:
        await callback.answer("❌ Ты еще не подписан на канал!", show_alert=True)

# ========== КОМАНДЫ ПОМОЩЬ ==========
@dp.message(Text("⌨️ Команды"))
async def show_commands(message: types.Message):
    text = """
📋 **ДОСТУПНЫЕ КОМАНДЫ:**

💰 **Баланс и переводы:**
`б` или `баланс` — проверка вашего баланса 💰
`п` сумма — перевод в ответ на сообщение пользователя
`п` @username сумма — перевод через username
`п` ID сумма — перевод через ID пользователя

👤 **Профиль и история:**
`/профиль` — просмотр вашего профиля
`/история` — история переводов и дуэлей

⚔️ **Дуэли и игры:**
`дуэль` — вызвать соперника в ответ на сообщение
`го` — начать дуэль после выбора соперника
`мины` сумма — начать игру в минное поле

📊 **Рейтинги:**
`/топ` или `/top` n — топ игроков (макс 50)

🌐 **Язык:**
`/lang ru` — русский
`/lang uk` — украинский
`/lang en` — английский

💎 **Казна (в чатах):**
`казна` — подключить казну (10k ⭐️)
`казна` n — пополнить казну на n GRAM
`награда` n — изменить награду за приглашение
"""
    
    await message.answer(text, parse_mode="markdown")

# ========== БАЛАНС ==========
@dp.message(Text(["💰 Баланс", "б", "баланс"]))
async def show_balance(message: types.Message):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    
    if user_data:
        balance = user_data[2]
        stars = user_data[3]
        
        # Проверяем бонус
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
        
        text = f"💰 **ВАШИ ДЕНЬГИ**\n\n"
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
        
        await message.answer(text, reply_markup=keyboard, parse_mode="markdown")

# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
@dp.callback_query(Text("claim_daily_bonus"))
async def claim_daily_bonus(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    last_bonus = db.get_last_bonus(user_id)
    
    if last_bonus:
        last_time = datetime.fromisoformat(last_bonus)
        if datetime.now() - last_time < timedelta(seconds=DAILY_BONUS_COOLDOWN):
            remaining = DAILY_BONUS_COOLDOWN - int((datetime.now() - last_time).total_seconds())
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            
            await callback.answer(f"⏳ Осталось подождать {hours}:{minutes:02d}", show_alert=True)
            return
    
    bonus_amount = GameLogic.get_random_bonus()
    db.add_balance(user_id, bonus_amount)
    db.claim_bonus(user_id, bonus_amount)
    
    # Расчет времени до следующего
    next_bonus_time = datetime.now() + timedelta(seconds=DAILY_BONUS_COOLDOWN)
    time_diff = next_bonus_time - datetime.now()
    hours = time_diff.seconds // 3600
    minutes = (time_diff.seconds % 3600) // 60
    
    text = f"🎁 **БОНУС ПОЛУЧЕН!**\n\n"
    text += f"✅ Вам начислено: {bonus_amount} GRAM\n\n"
    text += f"⏰ Следующий бонус будет доступен через {hours}:{minutes:02d}"
    
    await callback.answer()
    await callback.message.answer(text, parse_mode="markdown")

# ========== ПЕРЕДАЧА ДЕНЕГ (в ответ на сообщение) ==========
@dp.message(F.reply_to_message, Text(startswith="п "))
async def transfer_money_reply(message: types.Message):
    try:
        amount = int(message.text.split()[1])
    except (ValueError, IndexError):
        await message.answer("❌ Используйте: п сумма")
        return
    
    sender_id = message.from_user.id
    recipient_id = message.reply_to_message.from_user.id
    
    sender_balance = db.get_balance(sender_id)
    
    if sender_balance < amount:
        await message.answer(f"❌ Недостаточно денег! У вас: {sender_balance}")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    
    db.subtract_balance(sender_id, amount)
    db.add_balance(recipient_id, amount)
    
    text = f"✅ **ДЕНЬГИ ПЕРЕВЕДЕНЫ**\n\n"
    text += f"📤 Отправлено: {amount} 🪙\n"
    text += f"📥 Получатель: {message.reply_to_message.from_user.first_name}"
    
    await message.answer(text, parse_mode="markdown")

# ========== ПЕРЕДАЧА ДЕНЕГ (по ID или username) ==========
@dp.message(Text(startswith="п "))
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
    
    # Пытаемся получить ID получателя
    recipient_id = None
    
    if identifier.startswith('@'):
        # Поиск по username
        try:
            user_chat = await bot.get_chat(f"https://t.me/{identifier[1:]}")
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
    
    if sender_balance < amount:
        await message.answer(f"❌ Недостаточно денег! У вас: {sender_balance}")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    
    if not db.user_exists(recipient_id):
        await message.answer("❌ Пользователь не найден в системе")
        return
    
    db.subtract_balance(sender_id, amount)
    db.add_balance(recipient_id, amount)
    
    text = f"✅ **ДЕНЬГИ ПЕРЕВЕДЕНЫ**\n\n"
    text += f"📤 Отправлено: {amount} 🪙\n"
    text += f"📥 Получатель: ID {recipient_id}"
    
    await message.answer(text, parse_mode="markdown")

# ========== ПРОФИЛЬ ==========
@dp.message(Text(["👤 Профиль", "/профиль"]))
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    stats = db.get_stats(user_id)
    
    if user_data and stats:
        balance = user_data[2]
        stars = user_data[3]
        level = user_data[4]
        
        text = f"👤 **ПРОФИЛЬ**\n\n"
        text += f"💰 Баланс: {balance:,} 🪙\n"
        text += f"⭐️ Звёзды: {stars}\n"
        text += f"📊 Уровень: {level}\n"
        text += f"🆔 ID: `{user_id}`\n\n"
        
        text += "**Характеристики:**\n"
        for stat_key, stat_value in stats.items():
            emoji = STAT_EMOJIS.get(stat_key, '•')
            name = STAT_NAMES.get(stat_key, stat_key)
            text += f"{emoji} {name}: {stat_value}\n"
        
        await message.answer(text, parse_mode="markdown")

# ========== МАГАЗИН ==========
@dp.message(Text("🛒 Магазин"))
async def show_shop(message: types.Message):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    stars = user_data[3]
    
    text = f"🛒 **МАГАЗИН ГРАММОВ**\n\n"
    text += f"⭐️ Ваши звёзды: {stars}\n\n"
    text += "**Доступные предложения:**\n\n"
    
    buttons = []
    for key, item in SHOP_ITEMS.items():
        grams = item['grams']
        cost = item['stars']
        text += f"💰 {grams:,} GRAM → {cost} ⭐️\n"
        buttons.append([InlineKeyboardButton(
            text=f"{grams:,} GRAM ({cost}⭐️)",
            callback_data=f"buy_grams_{key}"
        )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(text, reply_markup=keyboard, parse_mode="markdown")

# ========== ПОКУПКА ГРАММОВ ==========
@dp.callback_query(Text(startswith="buy_grams_"))
async def buy_grams(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    key = callback.data.split("_")[2]
    
    item = SHOP_ITEMS[key]
    grams = item['grams']
    cost = item['stars']
    
    user_data = db.get_user(user_id)
    stars = user_data[3]
    
    if stars < cost:
        await callback.answer(f"❌ Недостаточно звёзд! Нужно: {cost}", show_alert=True)
        return
    
    db.subtract_stars(user_id, cost)
    db.add_balance(user_id, grams)
    
    text = f"✅ **ПОКУПКА ЗАВЕРШЕНА!**\n\n"
    text += f"💰 Куплено: {grams:,} GRAM\n"
    text += f"⭐️ Потрачено: {cost} звёзд"
    
    await callback.answer()
    await callback.message.answer(text, parse_mode="markdown")

# ========== ДУЭЛЬ ==========
@dp.message(F.reply_to_message, Text("дуэль"))
async def start_duel_reply(message: types.Message):
    """Начать дуэль в ответ на сообщение"""
    opponent_id = message.reply_to_message.from_user.id
    player_id = message.from_user.id
    
    if player_id == opponent_id:
        await message.answer("❌ Не можешь дуэлить сам с собой!")
        return
    
    if not db.user_exists(opponent_id):
        await message.answer("❌ Противник не в системе")
        return
    
    player_stats = db.get_stats(player_id)
    opponent_stats = db.get_stats(opponent_id)
    
    # Анимация дуэли
    animation_text = "⚔️ **БОЕВАЯ СИСТЕМА АКТИВИРОВАНА** ⚔️\n\n"
    animation_frames = ["⚔️", "🗡️ ", " 🗡️", "  ⚔️"]
    
    sent_msg = await message.answer(animation_text + animation_frames[0], parse_mode="markdown")
    
    for frame in animation_frames[1:]:
        await asyncio.sleep(0.5)
        try:
            await sent_msg.edit_text(animation_text + frame, parse_mode="markdown")
        except:
            pass
    
    await asyncio.sleep(1)
    
    # Определяем победителя
    winner_id = GameLogic.calculate_duel_winner(player_stats, opponent_stats)
    
    player_data = db.get_user(player_id)
    opponent_data = db.get_user(opponent_id)
    
    level_diff = abs(player_data[4] - opponent_data[4])
    reward = 50 + (level_diff * 10)
    
    if winner_id == 1:
        db.add_balance(player_id, reward)
        db.add_stars(player_id, 10)
        result_text = f"🎉 **{message.from_user.first_name} ПОБЕДИЛ!**\n\n"
        result_text += f"Награда: +{reward} 🪙 и +10 ⭐️"
    else:
        db.add_balance(opponent_id, reward)
        db.add_stars(opponent_id, 10)
        opponent_name = message.reply_to_message.from_user.first_name
        result_text = f"💔 **{opponent_name} ПОБЕДИЛ!**\n\n"
        result_text += f"Награда: +{reward} 🪙 и +10 ⭐️"
    
    db.add_duel(player_id, opponent_id, winner_id if winner_id == 1 else opponent_id, reward)
    
    duel_text = f"⚔️ **ДУЭЛЬ**\n\n"
    duel_text += f"🥊 {message.from_user.first_name} vs {message.reply_to_message.from_user.first_name}\n\n"
    duel_text += f"❤️ HP: {player_stats['health']*10} vs {opponent_stats['health']*10}\n"
    duel_text += f"💪 Сила: {player_stats['strength']} vs {opponent_stats['strength']}\n\n"
    duel_text += result_text
    
    await sent_msg.edit_text(duel_text, parse_mode="markdown")

# ========== ТОП ИГРОКОВ ==========
@dp.message(Text(["📊 Топ", "/top", "/топ"]))
async def show_top(message: types.Message):
    text = "📊 **ТОП 10 ИГРОКОВ**\n\n"
    
    top_users = db.get_top_users(10)
    
    for i, user in enumerate(top_users, 1):
        user_id, username, balance, level = user
        text += f"{i}. {username} - {balance:,} 🪙 (LVL{level})\n"
    
    await message.answer(text, parse_mode="markdown")

# ========== МИННОЕ ПОЛЕ ==========
@dp.message(Text(startswith="мины "))
async def start_minesweeper(message: types.Message):
    try:
        amount = int(message.text.split()[1])
    except (ValueError, IndexError):
        await message.answer("❌ Используйте: мины сумма")
        return
    
    user_id = message.from_user.id
    user_balance = db.get_balance(user_id)
    
    if user_balance < amount:
        await message.answer(f"❌ Недостаточно денег! У вас: {user_balance}")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0")
        return
    
    # Генерируем поле
    field = GameLogic.generate_minesweeper_field()
    
    # Отображение поля (5x5)
    field_display = "🎮 **МИННОЕ ПОЛЕ 5X5**\n\n"
    for i in range(5):
        for j in range(5):
            field_display += "❓ "
        field_display += "\n"
    
    field_display += f"\n💰 Ставка: {amount} 🪙\n"
    field_display += "нажми на координаты (1-5, 1-5) чтобы открыть ячейку"
    
    # Создаем игру в БД
    stakes = {'total': amount}
    game_id = db.create_minesweeper_game(user_id, message.chat.id, field, stakes)
    
    if not game_id:
        await message.answer("❌ Ошибка при создании игры")
        return
    
    # Вычитаем ставку
    db.subtract_balance(user_id, amount)
    
    await message.answer(field_display, parse_mode="markdown")

# ========== КЛАНЫ ==========
@dp.message(Text(["👥 Кланы", "/клан"]))
async def show_clans(message: types.Message):
    user_id = message.from_user.id
    
    text = "👥 **КЛАНЫ**\n\n"
    text += "Функция кланов в разработке\n"
    
    await message.answer(text, parse_mode="markdown")

# ========== ХОГВАРТС ==========
@dp.message(Text("🏰 Хогвартс"))
async def show_hogwarts(message: types.Message):
    text = "🏰 **ХОГВАРТС**\n\n"
    text += "Функция Хогвартса в разработке\n"
    
    await message.answer(text, parse_mode="markdown")

# ========== ЗАПУСК ==========
async def main():
    logger.info("✅ Bot v2.0 запущен...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
