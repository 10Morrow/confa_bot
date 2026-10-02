import asyncio
import html
import logging
import os

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from database import (
    SessionLocal,
    init_db,
    get_next_number,
    add_participant,
    get_random_participant,
    get_participants_count,
    reset_chat,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден в файле .env"
    )


bot = Bot(
    token=BOT_TOKEN,
)

dp = Dispatcher()


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def get_user_display_name(message: Message) -> str:
    """
    Получает отображаемое имя пользователя.
    """

    user = message.from_user

    if not user:
        return "Пользователь"

    if user.username:
        return f"@{html.escape(user.username)}"

    full_name = " ".join(
        part
        for part in [
            user.first_name,
            user.last_name,
        ]
        if part
    ).strip()

    if full_name:
        return html.escape(full_name)

    return "Пользователь"


def get_participant_display_name(participant) -> str:
    """
    Получает отображаемое имя сохранённого участника.
    """

    if participant.username:
        return f"@{html.escape(participant.username)}"

    full_name = " ".join(
        part
        for part in [
            participant.first_name,
            participant.last_name,
        ]
        if part
    ).strip()

    if full_name:
        return html.escape(full_name)

    return "Пользователь"


async def is_admin(message: Message) -> bool:
    """
    Проверяет, является ли отправитель
    администратором или владельцем чата.
    """

    if message.chat.type not in {
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }:
        return False

    if not message.from_user:
        return False

    member = await bot.get_chat_member(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )

    return member.status in {
        "administrator",
        "creator",
    }


# ============================================================
# ОБРАБОТКА ФОТО
# ============================================================

@dp.message(
    F.photo,
    F.chat.type.in_({
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }),
)
async def photo_handler(message: Message):
    """
    Каждая фотография получает следующий номер.
    """

    if not message.from_user:
        return

    # Самая качественная версия фотографии
    photo = message.photo[-1]

    async with SessionLocal() as session:

        # Получаем следующий номер
        number = await get_next_number(
            session=session,
            chat_id=message.chat.id,
        )

        # Сохраняем участника
        await add_participant(
            session=session,
            chat_id=message.chat.id,
            number=number,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            photo_file_id=photo.file_id,
        )

    # Отвечаем на исходное фото
    await message.reply(
        f"🎟 <b>№{number}</b>",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# РОЗЫГРЫШ
# ============================================================

@dp.message(
    Command("розыгрыш"),
    F.chat.type.in_({
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }),
)
async def raffle_handler(message: Message):
    """
    Выбирает случайную фотографию из всех зарегистрированных.
    """

    async with SessionLocal() as session:

        # Сначала узнаём общее количество фотографий
        total = await get_participants_count(
            session=session,
            chat_id=message.chat.id,
        )

        # Если фотографий нет
        if total == 0:
            await message.reply(
                "❌ Пока нет ни одной фотографии для розыгрыша."
            )
            return

        # Выбираем победителя
        participant = await get_random_participant(
            session=session,
            chat_id=message.chat.id,
        )

    if participant is None:
        await message.reply(
            "❌ Не удалось выбрать победителя."
        )
        return

    winner_name = get_participant_display_name(
        participant
    )

    # Формируем подпись к фотографии
    caption = (
        "🎉 <b>Победитель!</b>\n\n"
        f"👤 {winner_name}\n"
        f"🎟 Номер участника: "
        f"<b>№{participant.number} из {total}</b>"
    )

    try:

        await message.answer_photo(
            photo=participant.photo_file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )

    except TelegramBadRequest:

        # Запасной вариант, если Telegram
        # не принимает сохранённый file_id
        await message.answer(
            caption,
            parse_mode=ParseMode.HTML,
        )


# ============================================================
# СТАТУС
# ============================================================

@dp.message(
    Command("статус"),
    F.chat.type.in_({
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }),
)
async def status_handler(message: Message):
    """
    Показывает количество зарегистрированных фотографий.
    """

    async with SessionLocal() as session:

        count = await get_participants_count(
            session=session,
            chat_id=message.chat.id,
        )

    if count == 0:
        await message.reply(
            "📊 Пока нет зарегистрированных фотографий."
        )
        return

    await message.reply(
        f"📊 Всего фотографий: <b>{count}</b>",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# СБРОС
# ============================================================

@dp.message(
    Command("сброс"),
    F.chat.type.in_({
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }),
)
async def reset_handler(message: Message):
    """
    Полностью очищает текущий розыгрыш.
    Доступно только администраторам.
    """

    if not await is_admin(message):
        await message.reply(
            "❌ Команда доступна только администраторам."
        )
        return

    async with SessionLocal() as session:

        old_count = await get_participants_count(
            session=session,
            chat_id=message.chat.id,
        )

        await reset_chat(
            session=session,
            chat_id=message.chat.id,
        )

    await message.reply(
        "♻️ <b>Розыгрыш сброшен.</b>\n\n"
        f"Удалено фотографий: <b>{old_count}</b>\n"
        "Следующая фотография получит номер <b>1</b>.",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ПОМОЩЬ
# ============================================================

@dp.message(
    Command("help", "помощь"),
)
async def help_handler(message: Message):

    await message.reply(
        "<b>Команды бота:</b>\n\n"
        "📸 Каждая фотография получает номер\n\n"
        "/розыгрыш — выбрать победителя\n"
        "/статус — количество фотографий\n"
        "/сброс — очистить текущий розыгрыш "
        "(только администратор)\n"
        "/помощь — показать это сообщение",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ЗАПУСК БОТА
# ============================================================

async def main():

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )

    # Создаём SQLite-таблицы
    await init_db()

    # Удаляем старый webhook
    # и не обрабатываем накопившиеся сообщения
    await bot.delete_webhook(
        drop_pending_updates=True,
    )

    logging.info("Бот запущен")

    # Запускаем polling
    await dp.start_polling(
        bot,
    )


if __name__ == "__main__":
    asyncio.run(main())
