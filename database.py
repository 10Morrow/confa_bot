from sqlalchemy import BigInteger, Integer, String, select, delete, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


DATABASE_URL = "sqlite+aiosqlite:///raffle.db"


class Base(DeclarativeBase):
    pass


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ID Telegram-чата
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    # Номер участника в этом чате
    number: Mapped[int] = mapped_column(
        Integer,
    )

    # Telegram ID пользователя
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    # Данные пользователя
    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    first_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    last_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Telegram file_id фотографии
    photo_file_id: Mapped[str] = mapped_column(
        String(500),
    )


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """
    Создаёт таблицы, если их ещё нет.
    """

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_next_number(
    session: AsyncSession,
    chat_id: int,
) -> int:
    """
    Возвращает следующий номер участника
    в конкретном чате.
    """

    result = await session.execute(
        select(func.max(Participant.number))
        .where(
            Participant.chat_id == chat_id
        )
    )

    last_number = result.scalar_one_or_none()

    if last_number is None:
        return 1

    return last_number + 1


async def add_participant(
    session: AsyncSession,
    chat_id: int,
    number: int,
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    photo_file_id: str,
):
    """
    Сохраняет участника и его фотографию.
    """

    participant = Participant(
        chat_id=chat_id,
        number=number,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        photo_file_id=photo_file_id,
    )

    session.add(participant)

    await session.commit()

    return participant


async def get_random_participant(
    session: AsyncSession,
    chat_id: int,
):
    """
    Возвращает случайного участника
    из текущего чата.
    """

    result = await session.execute(
        select(Participant)
        .where(
            Participant.chat_id == chat_id
        )
        .order_by(func.random())
        .limit(1)
    )

    return result.scalar_one_or_none()


async def get_participants_count(
    session: AsyncSession,
    chat_id: int,
) -> int:
    """
    Возвращает количество фотографий/участников
    в текущем чате.
    """

    result = await session.execute(
        select(func.count(Participant.id))
        .where(
            Participant.chat_id == chat_id
        )
    )

    return result.scalar_one()


async def reset_chat(
    session: AsyncSession,
    chat_id: int,
):
    """
    Полностью удаляет всех участников
    и фотографии текущего чата.
    """

    await session.execute(
        delete(Participant)
        .where(
            Participant.chat_id == chat_id
        )
    )

    await session.commit()
