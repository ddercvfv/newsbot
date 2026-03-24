import os
import logging
from anthropic import Anthropic
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)

COLLECTING = 1

SYSTEM_PROMPT = """Ты — профессиональный редактор новостных дайджестов для бизнес-канала CN Bridge (поставки из Китая).

Пользователь пришлёт тебе от 1 до 10 новостных сообщений/заметок. Твоя задача — сформировать красивый пост-дайджест строго в следующем формате:

#Дайджест [тема в 2-3 словах]

[Короткая вводная фраза-цепляшка — 1-2 предложения, задающая тон]

❐ [Заголовок пункта]
→ [Суть новости, факты, цифры]
! [Вывод/последствие для бизнеса]

❐ [Заголовок пункта]
→ [Суть]
! [Вывод]

... (столько пунктов, сколько новостей)

Что это значит для бизнеса:

- [вывод 1]
- [вывод 2]
- [вывод 3]

Вывод от CN Bridge:
[2-3 предложения с позицией и ценностью CN Bridge]

Закупка → документы → логистика — это одна цепочка.
Если ломается один элемент — падает всё.

Команда CN Bridge напоминает:
мы выстраиваем поставки из Китая так, чтобы товар проходил без блокировок и лишних расходов.

Оставить заявку → @alexey_cnbridge

Правила:
- Используй только эмодзи из примера: ❐ → !
- Пиши деловым языком, без воды
- Каждый пункт — отдельная новость
- Тема в заголовке #Дайджест должна отражать суть присланных новостей
- Не добавляй ничего лишнего сверх формата"""


def get_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📰 Создать дайджест")]],
        resize_keyboard=True
    )

def get_done_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("✅ Готово — создать дайджест"), KeyboardButton("❌ Отмена")]],
        resize_keyboard=True
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет! Я бот для создания дайджестов CN Bridge.\n\n"
        "Нажми кнопку ниже, чтобы начать.",
        reply_markup=get_keyboard()
    )


async def start_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["news"] = []
    await update.message.reply_text(
        "📨 Пришлите до 10 сообщений с новостями — каждое отдельно.\n\n"
        "Когда закончите — нажмите «Готово».",
        reply_markup=get_done_keyboard()
    )
    return COLLECTING


async def collect_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "❌ Отмена":
        context.user_data.clear()
        await update.message.reply_text(
            "Отменено. Можете начать заново.",
            reply_markup=get_keyboard()
        )
        return ConversationHandler.END

    if text == "✅ Готово — создать дайджест":
        news = context.user_data.get("news", [])
        if not news:
            await update.message.reply_text("⚠️ Вы не добавили ни одной новости. Пришлите хотя бы одну.")
            return COLLECTING
        return await generate_digest(update, context)

    news = context.user_data.get("news", [])

    if len(news) >= 10:
        await update.message.reply_text(
            "⚠️ Максимум 10 новостей. Нажмите «Готово» для генерации.",
            reply_markup=get_done_keyboard()
        )
        return COLLECTING

    news.append(text)
    context.user_data["news"] = news
    count = len(news)

    if count == 10:
        await update.message.reply_text(
            f"✅ Принято ({count}/10) — достигнут максимум.\nНажмите «Готово» для генерации.",
            reply_markup=get_done_keyboard()
        )
    else:
        await update.message.reply_text(
            f"✅ Принято ({count}/10). Присылайте ещё или нажмите «Готово».",
            reply_markup=get_done_keyboard()
        )

    return COLLECTING


async def generate_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    news = context.user_data.get("news", [])
    await update.message.reply_text("⏳ Генерирую дайджест, подождите...")

    user_content = "\n\n".join(
        f"Новость {i+1}:\n{item}" for i, item in enumerate(news)
    )

    try:
        message = anthropic.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}]
        )
        digest = message.content[0].text.strip()
        await update.message.reply_text(digest, reply_markup=get_keyboard())
    except Exception as e:
        logger.error(f"Anthropic error: {e}")
        await update.message.reply_text(
            f"❌ Ошибка генерации: {str(e)}\n\nПопробуйте ещё раз.",
            reply_markup=get_keyboard()
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=get_keyboard())
    return ConversationHandler.END


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📰 Создать дайджест$"), start_digest),
            CommandHandler("digest", start_digest),
        ],
        states={
            COLLECTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_news)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
