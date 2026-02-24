import asyncio
import aiosqlite
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# === ИЗМЕНИ ЭТИ СТРОКИ ===
TOKEN = "8132455379:AAFXXaYTLIKoqwyzRDq1etEap7bMutanI1I"  # Твой от BotFather
ADMIN_PASSWORD = "jumki1234"   # Измени на свой админ-пароль
GUEST_PASSWORD = "qwerty1234"  # Измени на свой гость-пароль
# ========================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class Auth(StatesGroup):
    password = State()

async def init_db():
    async with aiosqlite.connect("storage.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                caption TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = await cursor.fetchall()
        has_role = any(col[1] == 'role' for col in columns)
        if not has_role:
            await db.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'none'")
        await db.commit()

def guest_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="/start"), KeyboardButton(text="/login")],
        [KeyboardButton(text="/list"), KeyboardButton(text="/get")]
    ])

def admin_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="/start"), KeyboardButton(text="/login")],
        [KeyboardButton(text="/list"), KeyboardButton(text="/get")],
        [KeyboardButton(text="/delete"), KeyboardButton(text="/upload")]
    ])

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("""Привет! Я бот-хранилище с ролями.
Сначала /login""", reply_markup=guest_keyboard())

@dp.message(Command("login"))
async def cmd_login(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    await message.answer("Введи пароль:")
    await state.set_state(Auth.password)

@dp.message(Auth.password)
async def process_password(message: Message, state: FSMContext):
    role = 'none'
    keyboard = None
    msg_text = ""
    if message.text == ADMIN_PASSWORD:
        role = 'admin'
        msg_text = """✅ Вы вошли как Админ. Можешь добавлять (/upload), смотреть (/list, /get <id>), удалять (/delete <id>)."""
        keyboard = admin_keyboard()
    elif message.text == GUEST_PASSWORD:
        role = 'guest'
        msg_text = """✅ Вы вошли как Гость. Только просмотр (/list, /get <id>)."""
        keyboard = guest_keyboard()
    else:
        await message.answer("❌ Неправильный пароль. Попробуй /login заново.")
        await state.clear()
        return

    async with aiosqlite.connect("storage.db") as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, role) VALUES (?, ?)", (message.from_user.id, role))
        await db.commit()
    await message.answer(msg_text, reply_markup=keyboard)
    await state.clear()

async def get_role(user_id: int) -> str:
    async with aiosqlite.connect("storage.db") as db:
        cursor = await db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 'none'

@dp.message(Command("logout"))
async def cmd_logout(message: Message, state: FSMContext):
    async with aiosqlite.connect("storage.db") as db:
        await db.execute("UPDATE users SET role = 'none' WHERE user_id = ?", (message.from_user.id,))
        await db.commit()
    await state.clear()
    await message.answer("Вы вышли. Для входа — /login заново.", reply_markup=guest_keyboard())

@dp.message(Command("upload"))
async def cmd_upload(message: Message):
    role = await get_role(message.from_user.id)
    if role != 'admin':
        await message.answer("Только админ может добавлять медиа.")
        return
    await message.answer("Кидай фото или видео — сохраню как следующий ID.")

@dp.message(lambda m: m.photo or m.video)
async def save_media(message: Message):
    role = await get_role(message.from_user.id)
    if role != 'admin':
        await message.answer("Только админ может добавлять медиа. Если гость — используй /list и /get.")
        return

    file_id = None
    file_type = None
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"

    caption = message.caption or ""

    async with aiosqlite.connect("storage.db") as db:
        await db.execute("INSERT INTO media (file_id, file_type, caption) VALUES (?, ?, ?)",
                         (file_id, file_type, caption))
        await db.commit()

    last_id = await get_last_id()
    await message.answer(f"✅ Сохранено как ID: {last_id}!")

async def get_last_id():
    async with aiosqlite.connect("storage.db") as db:
        cursor = await db.execute("SELECT MAX(id) FROM media")
        row = await cursor.fetchone()
        return row[0] if row and row[0] else 0

@dp.message(Command("list"))
async def cmd_list(message: Message):
    role = await get_role(message.from_user.id)
    if role == 'none':
        await message.answer("Сначала /login")
        return

    async with aiosqlite.connect("storage.db") as db:
        cursor = await db.execute("SELECT id, file_type, caption FROM media WHERE file_type = 'photo'")
        photos = await cursor.fetchall()
        cursor = await db.execute("SELECT id, file_type, caption FROM media WHERE file_type = 'video'")
        videos = await cursor.fetchall()

    text = """📁 Фото:\n""" + "\n".join(f"ID {p[0]}: {p[2]}" for p in photos) + """\n\n🎥 Видео:\n""" + "\n".join(f"ID {v[0]}: {v[2]}" for v in videos)
    if not photos and not videos:
        text = "Пока ничего нет."

    await message.answer(text)

@dp.message(Command("get"))
async def cmd_get(message: Message):
    role = await get_role(message.from_user.id)
    if role == 'none':
        await message.answer("Сначала /login")
        return

    try:
        media_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("Напиши: /get <id> (например /get 1)")
        return

    async with aiosqlite.connect("storage.db") as db:
        cursor = await db.execute("SELECT file_id, file_type, caption FROM media WHERE id = ?", (media_id,))
        row = await cursor.fetchone()

    if not row:
        await message.answer("Такого ID нет.")
        return

    file_id, ftype, cap = row
    if ftype == "photo":
        await bot.send_photo(message.chat.id, file_id, caption=cap)
    else:
        await bot.send_video(message.chat.id, file_id, caption=cap)

@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    role = await get_role(message.from_user.id)
    if role != 'admin':
        await message.answer("Только админ может удалять.")
        return

    try:
        media_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("Напиши: /delete <id> (например /delete 1)")
        return

    async with aiosqlite.connect("storage.db") as db:
        cursor = await db.execute("DELETE FROM media WHERE id = ?", (media_id,))
        await db.commit()

    if cursor.rowcount > 0:
        await message.answer(f"✅ ID {media_id} удалено!")
    else:
        await message.answer("Такого ID нет.")

async def main():
    await init_db()
    print("Бот запущен! Пиши ему в Telegram.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())