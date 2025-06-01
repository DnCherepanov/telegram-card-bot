import os
import random
import json
from telegram import Update, InputMediaPhoto, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext
)
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Константы
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Токен бота не найден! Создайте файл .env с TELEGRAM_BOT_TOKEN")

CLIENTS_DIR = "cards/clients"
MANAGERS_DIR = "cards/managers"
STATS_FILE = "bot_stats.json"
ADMIN_ID = 190470202  # Ваш ID Telegram

# Статистика
bot_stats = {
    "total_users": 0,
    "active_users": set(),
    "commands_used": {},
    "cards_shown": {
        "clients": 0,
        "managers": 0
    }
}

# Загрузка сохраненной статистики
def load_stats():
    try:
        with open(STATS_FILE, 'r') as f:
            loaded = json.load(f)
            loaded["active_users"] = set(loaded["active_users"])
            return loaded
    except (FileNotFoundError, json.JSONDecodeError):
        return bot_stats.copy()

# Сохранение статистики
def save_stats():
    with open(STATS_FILE, 'w') as f:
        stats_to_save = bot_stats.copy()
        stats_to_save["active_users"] = list(stats_to_save["active_users"])
        json.dump(stats_to_save, f)

bot_stats = load_stats()

GREETINGS = [
    "Привет! Готов к новым карточкам? 🎲",
    "Снова в деле! 💼", 
    "Раздаю карты как маг! 🎩✨",
    "Кого сегодня удивим? 😏"
]

ERRORS = {
    "no_clients": "❌ В папке клиентов пусто! Добавьте карточек.",
    "no_managers": "❌ Менеджеры все в отпуске! Нужно минимум 6 карточек.",
    "all_used": "ℹ️ Все карты розданы! Нажмите /start для новой игры."
}

ABOUT_TEXT = """🎲 Об игре

Добро пожаловать в настольную обучающую игру, построенную на реальных возражениях клиентов и проверенных аргументах, которые работают.

📚 Она состоит из двух типов карточек:

🃏 Карточки клиентов — на них:
- Фраза, которую говорит клиент,
- Боль, стоящая за этой фразой,
- И вопрос: что вы скажете, чтобы он задумался?

👔 Карточки менеджеров — это варианты ответов. Каждая содержит:
- 🧠 Зерно сомнения — короткую фразу, которая сбивает шаблон клиента
- 🗣️ Речевой модуль — ваш основной ответ
- 🎯 Фокус — на чём делать акцент: гарантия, опыт, монтаж и т.д.

🎮 Как играть?
1️⃣ Берите карточку клиента и читайте вслух
2️⃣ Подбирайте подходящую карточку менеджера
3️⃣ Отвечайте клиенту в два шага:
   - 🧠 Сначала — зерно сомнения (лёгкий «тычок» в его уверенность)
   - 🗣️ Потом — речевой модуль (покажите экспертность)

✨ Гибкость карточек
Карточки менеджеров — не догма! 
- Меняйте слова, формулировки
- Говорите своим языком
- Главное — сохраните структуру:
  🧠 → 🗣️ → 🎯

🏆 Зачем это нужно?
- Тренировка на реальных ситуациях
- Развитие уверенности в разговоре
- Больше закрытых клиентов, меньше уходов к конкурентам

🚀 Удачи в игре!"""

class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.used_manager_cards = set()
        self.current_hand = []
        self.last_used_card = None
        self.last_message_ids = []
        self.last_client_card = None

async def delete_previous_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет предыдущие сообщения с картами"""
    game = context.user_data.get('game')
    if not game or not game.last_message_ids:
        return

    for msg_id in game.last_message_ids:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=msg_id
            )
        except Exception as e:
            print(f"⚠️ Не удалось удалить сообщение {msg_id}: {e}")

    game.last_message_ids = []

async def send_client_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет карточку клиента"""
    game = context.user_data.setdefault('game', GameState())

    try:
        clients = [f for f in os.listdir(CLIENTS_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if not clients:
            await update.message.reply_text(ERRORS["no_clients"])
            return

        client = random.choice(clients)
        game.last_client_card = client
        bot_stats["cards_shown"]["clients"] += 1
        save_stats()

        await update.message.reply_text("👇 Карточка клиента:")
        with open(os.path.join(CLIENTS_DIR, client), 'rb') as photo:
            await context.bot.send_photo(update.effective_chat.id, photo)

        await show_client_controls(update, context)

    except Exception as e:
        print(f"🚨 Ошибка: {e}")
        await update.message.reply_text("⚠️ Ошибка при отправке карты клиента")

async def show_client_controls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает кнопки управления для клиента"""
    keyboard = [
        [KeyboardButton("🔄 Новый клиент"), KeyboardButton("😊 Менеджер")],
        [KeyboardButton("📋 Показать руку"), KeyboardButton("🔄 Новая игра")],
        [KeyboardButton("❓ Об игре")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def show_manager_hand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущие карты менеджеров"""
    game = context.user_data.setdefault('game', GameState())

    await delete_previous_messages(update, context)

    if not game.current_hand:
        await update.message.reply_text("ℹ️ У вас пока нет карт менеджеров")
        return

    media = []
    for i, card in enumerate(game.current_hand, 1):
        try:
            media.append(InputMediaPhoto(
                media=open(os.path.join(MANAGERS_DIR, card), 'rb'),
                caption=f"Карта {i}"
            ))
        except Exception as e:
            print(f"Ошибка загрузки карты {card}: {e}")
            continue

    if not media:
        await update.message.reply_text("⚠️ Не удалось загрузить карты")
        return

    try:
        sent_messages = await context.bot.send_media_group(
            chat_id=update.effective_chat.id,
            media=media
        )
        game.last_message_ids = [msg.message_id for msg in sent_messages]
    except Exception as e:
        print(f"Ошибка при отправке медиагруппы: {e}")
        await update.message.reply_text("⚠️ Не удалось отправить карты")

    keyboard = [
        [KeyboardButton(f"⬆️ Карта {i+1}") for i in range(len(game.current_hand))],
        [KeyboardButton("➕ Добрать карту"), KeyboardButton("👩🏻‍🦳 Клиент")],
        [KeyboardButton("📋 Показать руку"), KeyboardButton("🔄 Новая игра")],
        [KeyboardButton("❓ Об игре")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    control_msg = await update.message.reply_text(
        f"📋 Ваши карты менеджеров ({len(game.current_hand)} шт.):",
        reply_markup=reply_markup
    )
    game.last_message_ids.append(control_msg.message_id)

async def deal_manager_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Раздает стартовые карты менеджера"""
    game = context.user_data.setdefault('game', GameState())

    try:
        managers = [f for f in os.listdir(MANAGERS_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if len(managers) < 6:
            await update.message.reply_text(ERRORS["no_managers"])
            return

        available = [m for m in managers if m not in game.used_manager_cards]
        if len(available) < 6:
            await update.message.reply_text(ERRORS["all_used"])
            return

        game.current_hand = random.sample(available, 6)
        bot_stats["cards_shown"]["managers"] += 6
        save_stats()

        await show_manager_hand(update, context)

    except Exception as e:
        print(f"🚨 Ошибка: {e}")
        await update.message.reply_text("⚠️ Ошибка при раздаче карт")

async def draw_manager_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавляет новую карту менеджера"""
    game = context.user_data.setdefault('game', GameState())

    try:
        managers = [f for f in os.listdir(MANAGERS_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        available = [m for m in managers if m not in game.used_manager_cards and m not in game.current_hand]

        if not available:
            await update.message.reply_text(ERRORS["all_used"])
            return

        new_card = random.choice(available)
        game.current_hand.append(new_card)
        bot_stats["cards_shown"]["managers"] += 1
        save_stats()

        await show_manager_hand(update, context)

    except Exception as e:
        print(f"🚨 Ошибка: {e}")
        await update.message.reply_text("⚠️ Ошибка при доборе карты")

async def discard_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает использование карты"""
    game = context.user_data.setdefault('game', GameState())

    try:
        card_num = int(update.message.text.split()[-1]) - 1
        if 0 <= card_num < len(game.current_hand):
            used_card = game.current_hand.pop(card_num)
            game.used_manager_cards.add(used_card)

            with open(os.path.join(MANAGERS_DIR, used_card), 'rb') as photo:
                await context.bot.send_photo(
                    update.effective_chat.id,
                    photo,
                    caption=f"Карта {card_num+1} использована!"
                )

            await show_manager_hand(update, context)
        else:
            await update.message.reply_text("ℹ️ Некорректный номер карты")

    except Exception as e:
        print(f"🚨 Ошибка: {e}")
        await update.message.reply_text("⚠️ Ошибка при использовании карты")

async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбрасывает игру"""
    game = context.user_data.setdefault('game', GameState())
    await delete_previous_messages(update, context)
    game.reset()
    await update.message.reply_text("🔄 Игра сброшена! Можно начать заново.")

    # Показываем только меню без информации об игре
    keyboard = [
        [KeyboardButton("👩🏻‍🦳 Клиент"), KeyboardButton("😊 Менеджер")],
        [KeyboardButton("📋 Показать руку"), KeyboardButton("🔄 Новая игра")],
        [KeyboardButton("❓ Об игре")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"{random.choice(GREETINGS)}\nВыберите действие:",
        reply_markup=reply_markup
    )

async def about_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию об игре"""
    await update.message.reply_text(ABOUT_TEXT)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику бота"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда доступна только администратору")
        return

    stats_text = (
        "📊 Статистика бота:\n"
        f"👥 Всего пользователей: {bot_stats['total_users']}\n"
        f"🟢 Активных пользователей: {len(bot_stats['active_users'])}\n"
        f"🃏 Карточек клиентов показано: {bot_stats['cards_shown']['clients']}\n"
        f"👔 Карточек менеджеров показано: {bot_stats['cards_shown']['managers']}\n"
        "\n📌 Использование команд:\n"
    )

    for cmd, count in sorted(bot_stats["commands_used"].items()):
        stats_text += f"{cmd}: {count}\n"

    await update.message.reply_text(stats_text)

async def send_welcome(update: Update, context: CallbackContext):
    """Отправляет приветственное сообщение новым пользователям"""
    user_id = update.effective_user.id
    bot_stats["active_users"].add(user_id)
    bot_stats["total_users"] = len(bot_stats["active_users"])
    bot_stats["commands_used"]["welcome"] = bot_stats["commands_used"].get("welcome", 0) + 1
    save_stats()

    await about_game(update, context)

    keyboard = [[KeyboardButton("/start")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Нажмите /start чтобы начать игру!",
        reply_markup=reply_markup
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    bot_stats["active_users"].add(user_id)
    bot_stats["total_users"] = len(bot_stats["active_users"])
    bot_stats["commands_used"]["start"] = bot_stats["commands_used"].get("start", 0) + 1
    save_stats()

    await about_game(update, context)

    keyboard = [
        [KeyboardButton("👩🏻‍🦳 Клиент"), KeyboardButton("😊 Менеджер")],
        [KeyboardButton("📋 Показать руку"), KeyboardButton("🔄 Новая игра")],
        [KeyboardButton("❓ Об игре")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"{random.choice(GREETINGS)}\nВыберите действие:",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    text = update.message.text
    bot_stats["commands_used"][text] = bot_stats["commands_used"].get(text, 0) + 1
    save_stats()

    if text == "👩🏻‍🦳 Клиент":
        await send_client_card(update, context)
    elif text == "😊 Менеджер":
        await deal_manager_cards(update, context)
    elif text == "➕ Добрать карту":
        await draw_manager_card(update, context)
    elif text == "📋 Показать руку":
        await show_manager_hand(update, context)
    elif text.startswith("⬆️ Карта"):
        await discard_card(update, context)
    elif text in ["🔄 Новая игра", "🔄 Сбросить все"]:
        await reset_game(update, context)
    elif text == "🔄 Новый клиент":
        await send_client_card(update, context)
    elif text == "❓ Об игре":
        await about_game(update, context)

def main():
    """Точка входа в приложение"""
    os.makedirs(CLIENTS_DIR, exist_ok=True)
    os.makedirs(MANAGERS_DIR, exist_ok=True)

    app = ApplicationBuilder().token(TOKEN).build()

    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", send_welcome))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, send_welcome))

    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()