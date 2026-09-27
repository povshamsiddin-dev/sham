import os
import asyncio
import aiohttp
import tempfile
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncpg
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUDD_API_KEY = os.getenv("AUDD_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Railway Variables ga admin ID yozing
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")  # masalan: @mychannel. Bo'sh bo'lsa majburiy obuna o'chiq.

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN topilmadi! Railway → Variables bo'limida BOT_TOKEN ni tekshiring.")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL topilmadi! Railway'da Postgres qo'shilganini tekshiring.")

# Railway ba'zan "postgres://" beradi, asyncpg esa "postgresql://" talab qiladi
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db_pool = None


# ===================== TILLAR (i18n) =====================
TEXTS = {
    "uz": {
        "welcome": "🎵 *Kuy Navo Bot*'ga xush kelibsiz, {name}!\n\n📤 *Nima yuborish mumkin:*\n• 🎤 Ovoz xabar — kuyni taniydi\n• 🎵 Audio fayl — kuyni taniydi\n• 🎬 Video — kuyni taniydi\n• 🔗 Instagram/TikTok/YouTube havolasi — video yuklab beradi\n• 🔍 Kuy nomi yozing — qidiradi\n\nTilni istalgan vaqt /til orqali o'zgartirishingiz mumkin.\n\nSinab ko'ring! 🚀",
        "bot_inactive": "🔴 Bot hozir texnik ishlar uchun vaqtincha to'xtatilgan!",
        "blocked": "🚫 Siz bloklangansiz!",
        "not_subscribed": "❌ Botdan foydalanish uchun avval quyidagi kanalga obuna bo'ling, so'ng \"✅ Tekshirish\" tugmasini bosing:",
        "check_sub_btn": "✅ Tekshirish",
        "go_channel_btn": "📢 Kanalga o'tish",
        "sub_ok": "✅ Obuna tasdiqlandi! Endi botdan foydalanishingiz mumkin.\n\n/start ni bosing.",
        "sub_fail": "❌ Siz hali kanalga obuna bo'lmadingiz!",
        "choose_lang": "🌐 Tilni tanlang:",
        "lang_set": "✅ Til o'zbek tiliga o'zgartirildi!",
        "searching_voice": "🔍 Kuy tanilmoqda... iltimos kuting!",
        "not_found_voice": "😕 Kuy aniqlanmadi\n\n• Kamida 5-10 soniya yuboring",
        "found_title": "✅ *Kuy topildi!*",
        "label_name": "Nomi", "label_artist": "Artist", "label_album": "Albom", "label_release": "Chiqarilgan",
        "listen_spotify": "🎧 [Spotify'da tinglash]({url})",
        "listen_apple": "🍎 [Apple Music'da tinglash]({url})",
        "searching_text": "🔍 *{q}* qidirilmoqda...",
        "found_list_title": "🎵 *Topilgan kuylar:*\n\n",
        "not_found_text": "😕 Kuy topilmadi\n\n💡 Ovoz xabar yuboring!",
        "error": "❌ Xatolik: {err}",
        "video_downloading": "⬇️ Video yuklanmoqda... biroz kuting!",
        "video_ok_caption": "✅ Mana videongiz! 🎬",
        "video_too_big": "😕 Video hajmi juda katta!",
        "video_fail": "😕 Video yuklab olinmadi!",
        "video_private": "🔒 Bu post private! Faqat ochiq postlarni yuklab olish mumkin.",
        "video_fail_hint": "😕 Video yuklab olinmadi!\n\n• Havola to'g'ri ekanligini tekshiring\n• Post public bo'lishi kerak",
        "video_timeout": "⏰ Vaqt tugadi! Video juda katta.",
        "unsupported": "🤔 Bu turdagi faylni qo'llab-quvvatlamayman.\n\nMenga *ovoz xabar*, *audio*, *video* yoki *qo'shiq nomi* yuboring 🎵",
        "feedback_thanks": "Rahmat! 🙏",
    },
    "ru": {
        "welcome": "🎵 Добро пожаловать в *Kuy Navo Bot*, {name}!\n\n📤 *Что можно отправить:*\n• 🎤 Голосовое сообщение — распознает песню\n• 🎵 Аудиофайл — распознает песню\n• 🎬 Видео — распознает песню\n• 🔗 Ссылка Instagram/TikTok/YouTube — скачает видео\n• 🔍 Напишите название песни — найдёт её\n\nЯзык можно изменить командой /til.\n\nПопробуйте! 🚀",
        "bot_inactive": "🔴 Бот временно на технических работах!",
        "blocked": "🚫 Вы заблокированы!",
        "not_subscribed": "❌ Чтобы пользоваться ботом, сначала подпишитесь на канал, затем нажмите \"✅ Проверить\":",
        "check_sub_btn": "✅ Проверить",
        "go_channel_btn": "📢 Перейти в канал",
        "sub_ok": "✅ Подписка подтверждена! Теперь можно пользоваться ботом.\n\nНажмите /start.",
        "sub_fail": "❌ Вы ещё не подписались на канал!",
        "choose_lang": "🌐 Выберите язык:",
        "lang_set": "✅ Язык изменён на русский!",
        "searching_voice": "🔍 Распознаю песню... подождите!",
        "not_found_voice": "😕 Песня не распознана\n\n• Отправьте минимум 5-10 секунд",
        "found_title": "✅ *Песня найдена!*",
        "label_name": "Название", "label_artist": "Исполнитель", "label_album": "Альбом", "label_release": "Дата выхода",
        "listen_spotify": "🎧 [Слушать в Spotify]({url})",
        "listen_apple": "🍎 [Слушать в Apple Music]({url})",
        "searching_text": "🔍 Ищу *{q}*...",
        "found_list_title": "🎵 *Найденные песни:*\n\n",
        "not_found_text": "😕 Песня не найдена\n\n💡 Отправьте голосовое сообщение!",
        "error": "❌ Ошибка: {err}",
        "video_downloading": "⬇️ Загружаю видео... подождите!",
        "video_ok_caption": "✅ Вот ваше видео! 🎬",
        "video_too_big": "😕 Видео слишком большое!",
        "video_fail": "😕 Не удалось загрузить видео!",
        "video_private": "🔒 Этот пост приватный! Можно скачивать только публичные посты.",
        "video_fail_hint": "😕 Не удалось загрузить видео!\n\n• Проверьте правильность ссылки\n• Пост должен быть публичным",
        "video_timeout": "⏰ Время истекло! Видео слишком большое.",
        "unsupported": "🤔 Этот тип файла не поддерживается.\n\nОтправьте *голосовое сообщение*, *аудио*, *видео* или *название песни* 🎵",
        "feedback_thanks": "Спасибо! 🙏",
    },
    "en": {
        "welcome": "🎵 Welcome to *Kuy Navo Bot*, {name}!\n\n📤 *What you can send:*\n• 🎤 Voice message — recognizes the song\n• 🎵 Audio file — recognizes the song\n• 🎬 Video — recognizes the song\n• 🔗 Instagram/TikTok/YouTube link — downloads the video\n• 🔍 Type a song name — searches for it\n\nChange language anytime with /til.\n\nGive it a try! 🚀",
        "bot_inactive": "🔴 The bot is temporarily down for maintenance!",
        "blocked": "🚫 You are blocked!",
        "not_subscribed": "❌ To use the bot, please subscribe to the channel below, then press \"✅ Check\":",
        "check_sub_btn": "✅ Check",
        "go_channel_btn": "📢 Open channel",
        "sub_ok": "✅ Subscription confirmed! You can now use the bot.\n\nPress /start.",
        "sub_fail": "❌ You haven't subscribed to the channel yet!",
        "choose_lang": "🌐 Choose a language:",
        "lang_set": "✅ Language changed to English!",
        "searching_voice": "🔍 Recognizing the song... please wait!",
        "not_found_voice": "😕 Song not recognized\n\n• Send at least 5-10 seconds",
        "found_title": "✅ *Song found!*",
        "label_name": "Title", "label_artist": "Artist", "label_album": "Album", "label_release": "Released",
        "listen_spotify": "🎧 [Listen on Spotify]({url})",
        "listen_apple": "🍎 [Listen on Apple Music]({url})",
        "searching_text": "🔍 Searching *{q}*...",
        "found_list_title": "🎵 *Songs found:*\n\n",
        "not_found_text": "😕 Song not found\n\n💡 Try sending a voice message!",
        "error": "❌ Error: {err}",
        "video_downloading": "⬇️ Downloading video... please wait!",
        "video_ok_caption": "✅ Here's your video! 🎬",
        "video_too_big": "😕 Video is too large!",
        "video_fail": "😕 Could not download the video!",
        "video_private": "🔒 This post is private! Only public posts can be downloaded.",
        "video_fail_hint": "😕 Could not download the video!\n\n• Check that the link is correct\n• The post must be public",
        "video_timeout": "⏰ Timed out! Video is too large.",
        "unsupported": "🤔 This file type isn't supported.\n\nSend me a *voice message*, *audio*, *video*, or a *song name* 🎵",
        "feedback_thanks": "Thanks! 🙏",
    },
}


def t(key: str, lang: str, **kwargs) -> str:
    lang = lang if lang in TEXTS else "uz"
    template = TEXTS[lang].get(key, TEXTS["uz"].get(key, key))
    return template.format(**kwargs) if kwargs else template


def escape_md(text: str) -> str:
    """Telegram 'Markdown' (legacy) rejasi buzilmasligi uchun maxsus belgilarni ekranlaydi."""
    if not text:
        return text
    for ch in ("_", "*", "[", "`"):
        text = text.replace(ch, "\\" + ch)
    return text


# ===================== DATABASE =====================
async def init_db():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    except Exception as e:
        print(f"[DB ULANISH XATOSI]: {e}")
        raise
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_at TIMESTAMP DEFAULT NOW(),
                is_blocked BOOLEAN DEFAULT FALSE,
                requests_count INT DEFAULT 0
            )
        """)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'uz'")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                reaction TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Bot yoqilgan holat
        await conn.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('is_active', 'true')
            ON CONFLICT (key) DO NOTHING
        """)
    print("✅ Database tayyor!")


async def add_user(user_id: int, username: str, full_name: str):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET username=$2, full_name=$3
        """, user_id, username, full_name)


async def increment_requests(user_id: int):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE users SET requests_count = requests_count + 1 WHERE user_id = $1
            """, user_id)
    except Exception as e:
        print(f"[DB xato - increment_requests]: {e}")


async def is_bot_active():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM bot_settings WHERE key = 'is_active'")
        return row['value'] == 'true' if row else True


async def is_user_blocked(user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_blocked FROM users WHERE user_id = $1", user_id)
        return row['is_blocked'] if row else False


async def get_user_language(user_id: int) -> str:
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT language FROM users WHERE user_id = $1", user_id)
            return row["language"] if row and row["language"] else "uz"
    except Exception as e:
        print(f"[DB xato - get_user_language]: {e}")
        return "uz"


async def set_user_language(user_id: int, lang: str):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET language = $1 WHERE user_id = $2", lang, user_id)


async def add_feedback(user_id: int, reaction: str):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("INSERT INTO feedback (user_id, reaction) VALUES ($1, $2)", user_id, reaction)
    except Exception as e:
        print(f"[DB xato - add_feedback]: {e}")


async def get_stats():
    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        blocked = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_blocked = TRUE")
        total_requests = await conn.fetchval("SELECT SUM(requests_count) FROM users")
        today = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE joined_at::date = CURRENT_DATE"
        )
        likes = await conn.fetchval("SELECT COUNT(*) FROM feedback WHERE reaction = 'like'")
        dislikes = await conn.fetchval("SELECT COUNT(*) FROM feedback WHERE reaction = 'dislike'")
        return {
            "total": total,
            "blocked": blocked,
            "total_requests": total_requests or 0,
            "today": today,
            "likes": likes or 0,
            "dislikes": dislikes or 0,
        }


async def get_all_users():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT user_id FROM users WHERE is_blocked = FALSE")


# ===================== OBUNA (majburiy a'zolik) =====================
async def is_subscribed(user_id: int) -> bool:
    if not CHANNEL_USERNAME:
        return True
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        print(f"[Obuna tekshirish xato]: {e}")
        return True  # xato bo'lsa (masalan bot admin emas) botni bloklab qo'ymaymiz


def subscribe_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    if CHANNEL_USERNAME:
        builder.row(InlineKeyboardButton(
            text=t("go_channel_btn", lang),
            url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
        ))
    builder.row(InlineKeyboardButton(text=t("check_sub_btn", lang), callback_data="check_sub"))
    return builder.as_markup()


@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    lang = await get_user_language(callback.from_user.id)
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text(t("sub_ok", lang))
        await callback.answer()
    else:
        await callback.answer(t("sub_fail", lang), show_alert=True)


# ===================== TIL TANLASH =====================
def lang_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
    )
    return builder.as_markup()


@dp.message(Command("til"))
async def cmd_language(message: Message):
    lang = await get_user_language(message.from_user.id)
    await message.answer(t("choose_lang", lang), reply_markup=lang_keyboard())


@dp.callback_query(F.data.startswith("lang_"))
async def set_language_callback(callback: types.CallbackQuery):
    lang = callback.data.split("_")[1]
    await set_user_language(callback.from_user.id, lang)
    await callback.message.edit_text(t("lang_set", lang))
    await callback.answer()


# ===================== BAHOLASH (like/dislike) =====================
def rating_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👍", callback_data="fb_like"),
        InlineKeyboardButton(text="👎", callback_data="fb_dislike"),
    )
    return builder.as_markup()


@dp.callback_query(F.data.in_({"fb_like", "fb_dislike"}))
async def feedback_callback(callback: types.CallbackQuery):
    reaction = "like" if callback.data == "fb_like" else "dislike"
    await add_feedback(callback.from_user.id, reaction)
    lang = await get_user_language(callback.from_user.id)
    await callback.answer(t("feedback_thanks", lang))
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ===================== ADMIN PANEL =====================
def admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"),
        InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="⚙️ Bot holati", callback_data="admin_toggle")
    )
    return builder.as_markup()


@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return

    dp["broadcast_mode"] = False  # /admin bosilganda eski "kutish" holati tozalanadi
    await message.answer(
        "🔧 *Admin Panel*\n\nNimani ko'rmoqchisiz?",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )


@dp.callback_query(F.data == "admin_stats")
async def show_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    stats = await get_stats()
    bot_status = "🟢 Yoqilgan" if await is_bot_active() else "🔴 O'chirilgan"

    text = (
        f"📊 *Statistika*\n\n"
        f"👥 Jami foydalanuvchilar: *{stats['total']}*\n"
        f"🆕 Bugun qo'shilgan: *{stats['today']}*\n"
        f"🚫 Bloklangan: *{stats['blocked']}*\n"
        f"🔢 Jami so'rovlar: *{stats['total_requests']}*\n"
        f"👍 Layklar: *{stats['likes']}* | 👎 Dislayklar: *{stats['dislikes']}*\n"
        f"🤖 Bot holati: {bot_status}"
    )

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "admin_users")
async def show_users(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    async with db_pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT user_id, username, full_name, requests_count, is_blocked FROM users ORDER BY requests_count DESC LIMIT 10"
        )

    text = "👥 *Top 10 foydalanuvchilar:*\n\n"
    for i, u in enumerate(users, 1):
        status = "🚫" if u['is_blocked'] else "✅"
        username = f"@{u['username']}" if u['username'] else u['full_name']
        text += f"{i}. {status} {username} — {u['requests_count']} so'rov\n"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚫 Bloklash", callback_data="admin_block_user"))
    builder.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back"))

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())


@dp.callback_query(F.data == "admin_toggle")
async def toggle_bot(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    current = await is_bot_active()
    new_value = 'false' if current else 'true'

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'is_active'", new_value)

    status = "🟢 Yoqildi" if new_value == 'true' else "🔴 O'chirildi"
    await callback.message.edit_text(
        f"✅ Bot holati o'zgartirildi!\n\n{status}",
        reply_markup=admin_keyboard()
    )


@dp.callback_query(F.data == "admin_broadcast")
async def ask_broadcast(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "📢 *Xabar yuborish*\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing:\n\n"
        "_(Bekor qilish uchun /admin yozing)_",
        parse_mode="Markdown"
    )
    dp["broadcast_mode"] = True


@dp.callback_query(F.data == "admin_back")
async def back_to_admin(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "🔧 *Admin Panel*\n\nNimani ko'rmoqchisiz?",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )


# Bloklash komandasi
@dp.message(Command("block"))
async def block_user_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Format: /block 123456789")
        return

    try:
        user_id = int(args[1])
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET is_blocked = TRUE WHERE user_id = $1", user_id)
        await message.answer(f"✅ Foydalanuvchi {user_id} bloklandi!")
    except:
        await message.answer("❌ Xato! Format: /block 123456789")


# Bloqdan chiqarish
@dp.message(Command("unblock"))
async def unblock_user_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Format: /unblock 123456789")
        return

    try:
        user_id = int(args[1])
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET is_blocked = FALSE WHERE user_id = $1", user_id)
        await message.answer(f"✅ Foydalanuvchi {user_id} bloqdan chiqarildi!")
    except:
        await message.answer("❌ Xato!")


# ===================== BOT FUNKSIYALARI =====================
async def check_user(message: Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    lang = await get_user_language(user.id)

    if await is_user_blocked(user.id):
        await message.answer(t("blocked", lang))
        return False

    if not await is_bot_active() and user.id != ADMIN_ID:
        await message.answer(t("bot_inactive", lang))
        return False

    if not await is_subscribed(user.id):
        await message.answer(t("not_subscribed", lang), reply_markup=subscribe_keyboard(lang))
        return False

    return True


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not await check_user(message):
        return
    lang = await get_user_language(message.from_user.id)
    await message.answer(
        t("welcome", lang, name=message.from_user.first_name),
        parse_mode="Markdown"
    )


@dp.message(F.voice)
async def handle_voice(message: Message):
    if not await check_user(message):
        return
    await recognize_music(message, message.voice.file_id)


@dp.message(F.audio)
async def handle_audio(message: Message):
    if not await check_user(message):
        return
    await recognize_music(message, message.audio.file_id)


@dp.message(F.video_note)
async def handle_video_note(message: Message):
    if not await check_user(message):
        return
    await recognize_music(message, message.video_note.file_id)


@dp.message(F.video)
async def handle_video(message: Message):
    if not await check_user(message):
        return
    await recognize_music(message, message.video.file_id)


@dp.message(F.photo | F.document | F.sticker | F.animation)
async def handle_unsupported(message: Message):
    if not await check_user(message):
        return
    lang = await get_user_language(message.from_user.id)
    await message.answer(t("unsupported", lang), parse_mode="Markdown")


async def recognize_music(message: Message, file_id: str):
    lang = await get_user_language(message.from_user.id)
    await increment_requests(message.from_user.id)
    processing_msg = await message.answer(t("searching_voice", lang))
    try:
        file = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

        async with aiohttp.ClientSession() as session:
            data = {
                "url": file_url,
                "return": "apple_music,spotify",
                "api_token": AUDD_API_KEY
            }
            async with session.post("https://api.audd.io/", data=data) as resp:
                result = await resp.json()

        await processing_msg.delete()

        if result.get("status") == "success" and result.get("result"):
            song = result["result"]
            title = escape_md(song.get("title", "Noma'lum"))
            artist = escape_md(song.get("artist", "Noma'lum"))
            album = escape_md(song.get("album", "Noma'lum"))
            release_date = song.get("release_date", "Noma'lum")

            spotify_link = ""
            if song.get("spotify"):
                spotify_url = song["spotify"].get("external_urls", {}).get("spotify", "")
                if spotify_url:
                    spotify_link = "\n" + t("listen_spotify", lang, url=spotify_url)

            apple_link = ""
            if song.get("apple_music"):
                apple_url = song["apple_music"].get("url", "")
                if apple_url:
                    apple_link = "\n" + t("listen_apple", lang, url=apple_url)

            text = (
                f"{t('found_title', lang)}\n\n"
                f"🎵 *{t('label_name', lang)}:* {title}\n"
                f"🎤 *{t('label_artist', lang)}:* {artist}\n"
                f"💿 *{t('label_album', lang)}:* {album}\n"
                f"📅 *{t('label_release', lang)}:* {release_date}"
                f"{spotify_link}{apple_link}"
            )
            await message.answer(text, parse_mode="Markdown", reply_markup=rating_keyboard())
        else:
            await message.answer(t("not_found_voice", lang))
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        print(f"[recognize_music xato]: {e}")
        await message.answer(t("error", lang, err=str(e)))


@dp.message(F.text)
async def handle_text(message: Message):
    # Admin broadcast mode
    if message.from_user.id == ADMIN_ID and dp.get("broadcast_mode"):
        dp["broadcast_mode"] = False
        users = await get_all_users()
        success = 0
        fail = 0
        status_msg = await message.answer(f"📢 Yuborilmoqda... 0/{len(users)}")

        for i, user in enumerate(users):
            try:
                await bot.send_message(user['user_id'], message.text)
                success += 1
            except:
                fail += 1

            if (i + 1) % 10 == 0:
                try:
                    await status_msg.edit_text(f"📢 Yuborilmoqda... {i+1}/{len(users)}")
                except:
                    pass

        await status_msg.edit_text(
            f"✅ *Xabar yuborildi!*\n\n"
            f"✅ Muvaffaqiyatli: {success}\n"
            f"❌ Xato: {fail}",
            parse_mode="Markdown"
        )
        return

    if not await check_user(message):
        return

    text = message.text.strip()
    video_domains = ["instagram.com", "tiktok.com", "youtube.com", "youtu.be", "twitter.com", "x.com", "facebook.com"]

    if any(domain in text for domain in video_domains):
        await download_video(message, text)
    else:
        await search_music(message, text)


async def search_music(message: Message, query: str):
    lang = await get_user_language(message.from_user.id)
    await increment_requests(message.from_user.id)
    processing_msg = await message.answer(t("searching_text", lang, q=query), parse_mode="Markdown")
    try:
        # ESKI KOD: AudD/findLyrics — bu qo'shiq MATNI bo'yicha qidiradi, nom bo'yicha emas.
        # Shu sabab natijalar so'ralgan nom bilan mos kelmasdi.
        # TUZATILDI: qo'shiq nomi/ijrochisi bo'yicha to'g'ri qidiradigan iTunes Search API.
        async with aiohttp.ClientSession() as session:
            params = {
                "term": query,
                "media": "music",
                "entity": "song",
                "limit": 3
            }
            async with session.get("https://itunes.apple.com/search", params=params) as resp:
                result = await resp.json()

        await processing_msg.delete()

        songs = result.get("results", [])
        if songs:
            response = t("found_list_title", lang)
            for i, song in enumerate(songs, 1):
                title = escape_md(song.get("trackName", "Noma'lum"))
                artist = escape_md(song.get("artistName", "Noma'lum"))
                response += f"{i}. 🎤 *{artist}* — {title}\n"
            await message.answer(response, parse_mode="Markdown")
        else:
            await message.answer(t("not_found_text", lang))
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        print(f"[search_music xato]: {e}")
        await message.answer(t("error", lang, err=str(e)))


async def download_video(message: Message, url: str):
    lang = await get_user_language(message.from_user.id)
    await increment_requests(message.from_user.id)
    processing_msg = await message.answer(t("video_downloading", lang))

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "video.%(ext)s")
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "-f", "best[filesize<50M]/best",
                "--max-filesize", "50m",
                "-o", output_path,
                "--no-warnings",
                url
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            if process.returncode == 0:
                video_file = None
                for f in os.listdir(tmpdir):
                    if f.startswith("video"):
                        video_file = os.path.join(tmpdir, f)
                        break

                if video_file and os.path.exists(video_file):
                    await processing_msg.delete()
                    if os.path.getsize(video_file) < 50 * 1024 * 1024:
                        input_file = FSInputFile(video_file)
                        await message.answer_video(input_file, caption=t("video_ok_caption", lang))
                    else:
                        await message.answer(t("video_too_big", lang))
                else:
                    await processing_msg.delete()
                    await message.answer(t("video_fail", lang))
            else:
                await processing_msg.delete()
                error = stderr.decode()
                print(f"[yt-dlp xato]: {error}")  # Railway Deploy Logs'da ko'rish uchun
                if "Private" in error or "Login" in error:
                    await message.answer(t("video_private", lang))
                else:
                    await message.answer(t("video_fail_hint", lang))
    except asyncio.TimeoutError:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer(t("video_timeout", lang))
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        print(f"[download_video xato]: {e}")  # Railway Deploy Logs'da ko'rish uchun
        await message.answer(t("video_fail_hint", lang))


async def main():
    await init_db()
    print("🤖 Kuy Navo Bot ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
