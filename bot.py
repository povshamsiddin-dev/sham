import os
import asyncio
import aiohttp
import tempfile
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncpg
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUDD_API_KEY = os.getenv("AUDD_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db_pool = None


# ===================== FSM STATES =====================
class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_ad_text = State()


# ===================== DATABASE =====================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS advertisements (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
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
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET requests_count = requests_count + 1 WHERE user_id = $1
        """, user_id)


async def is_bot_active():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM bot_settings WHERE key = 'is_active'")
        return row['value'] == 'true' if row else True


async def is_user_blocked(user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_blocked FROM users WHERE user_id = $1", user_id)
        return row['is_blocked'] if row else False


async def get_stats():
    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        blocked = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_blocked = TRUE")
        total_requests = await conn.fetchval("SELECT SUM(requests_count) FROM users")
        today = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE joined_at::date = CURRENT_DATE"
        )
        return {
            "total": total,
            "blocked": blocked,
            "total_requests": total_requests or 0,
            "today": today
        }


async def get_all_users():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT user_id FROM users WHERE is_blocked = FALSE")


async def get_active_ad():
    """Faol reklama matnini olish"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT text FROM advertisements WHERE is_active = TRUE ORDER BY id DESC LIMIT 1"
        )
        return row['text'] if row else None


async def set_ad(text: str):
    """Yangi reklama qo'shish yoki yangilash"""
    async with db_pool.acquire() as conn:
        # Eski reklamalarni o'chirish
        await conn.execute("UPDATE advertisements SET is_active = FALSE")
        # Yangi reklama
        await conn.execute(
            "INSERT INTO advertisements (text, is_active) VALUES ($1, TRUE)", text
        )


async def disable_ad():
    """Reklamani o'chirish"""
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE advertisements SET is_active = FALSE")


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
    builder.row(
        InlineKeyboardButton(text="📣 Reklama boshqarish", callback_data="admin_ads")
    )
    return builder.as_markup()


@dp.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    await state.clear()
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
    ad = await get_active_ad()
    ad_status = "✅ Faol" if ad else "❌ Yo'q"

    text = (
        f"📊 *Statistika*\n\n"
        f"👥 Jami foydalanuvchilar: *{stats['total']}*\n"
        f"🆕 Bugun qo'shilgan: *{stats['today']}*\n"
        f"🚫 Bloklangan: *{stats['blocked']}*\n"
        f"🔢 Jami so'rovlar: *{stats['total_requests']}*\n"
        f"🤖 Bot holati: {bot_status}\n"
        f"📣 Reklama: {ad_status}"
    )

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "admin_users")
async def show_users(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    async with db_pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT user_id, username, full_name, requests_count, is_blocked "
            "FROM users ORDER BY requests_count DESC LIMIT 20"
        )

    if not users:
        text = "👥 Hali foydalanuvchilar yo'q."
    else:
        text = "👥 <b>Top 20 foydalanuvchilar:</b>\n\n"
        for i, u in enumerate(users, 1):
            status = "🚫" if u['is_blocked'] else "✅"
            username = f"@{u['username']}" if u['username'] else (u['full_name'] or "Noma'lum")
            # HTML escape qilish — username'dagi & < > belgilari xato chiqmasin
            username = username.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text += f"{i}. {status} <code>{u['user_id']}</code> {username} — {u['requests_count']} so'rov\n"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back"))

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


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
    await callback.answer()


@dp.callback_query(F.data == "admin_broadcast")
async def ask_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.message.edit_text(
        "📢 *Xabar yuborish*\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing:\n\n"
        "_(Bekor qilish uchun /admin yozing)_",
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_ads")
async def manage_ads(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    ad = await get_active_ad()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Yangi reklama qo'shish", callback_data="ad_add"))
    if ad:
        builder.row(InlineKeyboardButton(text="❌ Reklamani o'chirish", callback_data="ad_disable"))
    builder.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back"))

    ad_text = f"📣 <b>Joriy reklama:</b>\n\n{ad}" if ad else "📣 Hozir faol reklama yo'q."
    await callback.message.edit_text(ad_text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


@dp.callback_query(F.data == "ad_add")
async def ask_ad_text(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_ad_text)
    await callback.message.edit_text(
        "✏️ *Yangi reklama matni yozing:*\n\n"
        "Bu matn har bir video/musiqa yuklanishidan keyin ko'rsatiladi.\n\n"
        "_(Bekor qilish: /admin)_",
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(F.data == "ad_disable")
async def disable_ad_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await disable_ad()
    await callback.message.edit_text(
        "✅ Reklama o'chirildi!",
        reply_markup=admin_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_back")
async def back_to_admin(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "🔧 *Admin Panel*\n\nNimani ko'rmoqchisiz?",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )
    await callback.answer()


# ===================== ADMIN TEXT HANDLERS =====================
@dp.message(AdminStates.waiting_broadcast)
async def handle_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    users = await get_all_users()
    success = 0
    fail = 0
    status_msg = await message.answer(f"📢 Yuborilmoqda... 0/{len(users)}")

    for i, user in enumerate(users):
        try:
            await bot.copy_message(user['user_id'], message.chat.id, message.message_id)
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


@dp.message(AdminStates.waiting_ad_text)
async def handle_ad_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await set_ad(message.text)
    await message.answer(
        f"✅ Reklama saqlandi!\n\n📣 <b>Reklama matni:</b>\n{message.text}",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


# ===================== BLOCK/UNBLOCK =====================
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


# ===================== USER CHECK =====================
async def check_user(message: Message) -> bool:
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)

    if not await is_bot_active() and user.id != ADMIN_ID:
        await message.answer("🔴 Bot hozir texnik ishlar uchun vaqtincha to'xtatilgan!")
        return False

    if await is_user_blocked(user.id):
        await message.answer("🚫 Siz bloklangansiz!")
        return False

    return True


async def send_ad_if_active(message: Message):
    """Agar faol reklama bo'lsa, yuborish"""
    ad = await get_active_ad()
    if ad:
        await message.answer(f"📣 <b>Reklama:</b>\n\n{ad}", parse_mode="HTML")


# ===================== START =====================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)

    if not await is_bot_active() and user.id != ADMIN_ID:
        await message.answer("🔴 Bot hozir texnik ishlar uchun vaqtincha to'xtatilgan!")
        return

    await message.answer(
        f"🎵 *Kuy Navo Bot*'ga xush kelibsiz, {user.first_name}!\n\n"
        "📤 *Nima yuborish mumkin:*\n"
        "• 🎤 Ovoz xabar — kuyni taniydi\n"
        "• 🎵 Audio fayl — kuyni taniydi\n"
        "• 🔗 Instagram/TikTok/YouTube havolasi — video + audio yuklab beradi\n"
        "• 🔍 Kuy nomi yozing — qidiradi\n\n"
        "Sinab ko'ring! 🚀",
        parse_mode="Markdown"
    )


# ===================== MEDIA HANDLERS =====================
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


# ===================== MUSIC RECOGNITION =====================
async def recognize_music(message: Message, file_id: str):
    await increment_requests(message.from_user.id)
    processing_msg = await message.answer("🔍 Kuy tanilmoqda... iltimos kuting!")
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
            title = song.get("title", "Noma'lum")
            artist = song.get("artist", "Noma'lum")
            album = song.get("album", "Noma'lum")
            release_date = song.get("release_date", "Noma'lum")

            spotify_link = ""
            if song.get("spotify"):
                spotify_url = song["spotify"].get("external_urls", {}).get("spotify", "")
                if spotify_url:
                    spotify_link = f"\n🎧 [Spotify'da tinglash]({spotify_url})"

            apple_link = ""
            if song.get("apple_music"):
                apple_url = song["apple_music"].get("url", "")
                if apple_url:
                    apple_link = f"\n🍎 [Apple Music'da tinglash]({apple_url})"

            # MP3 yuklab berish tugmasi
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="🎵 MP3 yuklab olish",
                    callback_data=f"dl_mp3:{title}:{artist}"
                )
            )

            await message.answer(
                f"✅ *Kuy topildi!*\n\n"
                f"🎵 *Nomi:* {title}\n"
                f"🎤 *Artist:* {artist}\n"
                f"💿 *Albom:* {album}\n"
                f"📅 *Chiqarilgan:* {release_date}"
                f"{spotify_link}{apple_link}",
                parse_mode="Markdown",
                reply_markup=builder.as_markup()
            )
            await send_ad_if_active(message)
        else:
            await message.answer("😕 Kuy aniqlanmadi\n\n• Kamida 5-10 soniya yuboring")
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer(f"❌ Xatolik: {str(e)}")


@dp.callback_query(F.data.startswith("dl_mp3:"))
async def download_mp3_callback(callback: types.CallbackQuery):
    """Kuy topilgandan keyin MP3 yuklab berish"""
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("❌ Xato!")
        return

    title = parts[1]
    artist = parts[2]
    query = f"{artist} {title}"

    await callback.answer("⏳ MP3 yuklanmoqda...")
    msg = await callback.message.answer("🎵 MP3 yuklab berilmoqda... biroz kuting!")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "audio.%(ext)s")
            cmd = [
                "yt-dlp",
                f"ytsearch1:{query}",
                "--no-playlist",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", output_path,
                "--no-warnings",
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            if process.returncode == 0:
                mp3_file = None
                for f in os.listdir(tmpdir):
                    if f.endswith(".mp3"):
                        mp3_file = os.path.join(tmpdir, f)
                        break

                if mp3_file and os.path.exists(mp3_file):
                    await msg.delete()
                    input_file = FSInputFile(mp3_file, filename=f"{artist} - {title}.mp3")
                    await callback.message.answer_audio(
                        input_file,
                        title=title,
                        performer=artist,
                        caption=f"🎵 {artist} — {title}"
                    )
                    await send_ad_if_active(callback.message)
                else:
                    await msg.edit_text("😕 MP3 yuklab olinmadi!")
            else:
                await msg.edit_text("😕 MP3 topilmadi! YouTube'da yo'q bo'lishi mumkin.")
    except asyncio.TimeoutError:
        try:
            await msg.delete()
        except:
            pass
        await callback.message.answer("⏰ Vaqt tugadi!")
    except Exception as e:
        try:
            await msg.delete()
        except:
            pass
        await callback.message.answer(f"❌ Xatolik: {str(e)}")


# ===================== TEXT HANDLER =====================
@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if not await check_user(message):
        return

    text = message.text.strip()
    video_domains = [
        "instagram.com", "tiktok.com", "youtube.com", "youtu.be",
        "twitter.com", "x.com", "facebook.com", "fb.watch",
        "vm.tiktok.com", "pin.it"
    ]

    if any(domain in text for domain in video_domains):
        await download_video(message, text)
    else:
        await search_music(message, text)


# ===================== MUSIC SEARCH =====================
async def search_music(message: Message, query: str):
    await increment_requests(message.from_user.id)
    processing_msg = await message.answer(f"🔍 *{query}* qidirilmoqda...")
    try:
        async with aiohttp.ClientSession() as session:
            data = {
                "q": query,
                "return": "apple_music,spotify",
                "api_token": AUDD_API_KEY
            }
            async with session.post("https://api.audd.io/findLyrics/", data=data) as resp:
                result = await resp.json()

        await processing_msg.delete()

        if result.get("status") == "success" and result.get("result"):
            songs = result["result"][:3]
            response = "🎵 *Topilgan kuylar:*\n\n"
            builder = InlineKeyboardBuilder()
            for i, song in enumerate(songs, 1):
                title = song.get("title", "Noma'lum")
                artist = song.get("artist", "Noma'lum")
                response += f"{i}. 🎤 *{artist}* — {title}\n"
                builder.row(
                    InlineKeyboardButton(
                        text=f"🎵 {i}. {artist} - {title}",
                        callback_data=f"dl_mp3:{title}:{artist}"
                    )
                )
            await message.answer(response, parse_mode="Markdown", reply_markup=builder.as_markup())
        else:
            await message.answer("😕 Kuy topilmadi\n\n💡 Ovoz xabar yuboring!")
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer(f"❌ Xatolik: {str(e)}")


# ===================== VIDEO DOWNLOAD =====================
async def download_video(message: Message, url: str):
    await increment_requests(message.from_user.id)
    processing_msg = await message.answer("⬇️ Video yuklanmoqda... biroz kuting!")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_output = os.path.join(tmpdir, "video.%(ext)s")

            cmd = [
                "yt-dlp",
                "--no-playlist",
                "-f", "best[filesize<50M]/best",
                "--max-filesize", "50m",
                "-o", video_output,
                "--no-warnings",
                url
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180)

            if process.returncode == 0:
                video_file = None

                for f in os.listdir(tmpdir):
                    if f.startswith("video"):
                        video_file = os.path.join(tmpdir, f)
                        break

                if video_file and os.path.exists(video_file):
                    file_size = os.path.getsize(video_file)
                    if file_size < 50 * 1024 * 1024:
                        await processing_msg.delete()

                        builder = InlineKeyboardBuilder()
                        builder.row(
                            InlineKeyboardButton(
                                text="🎵 Faqat musiqa (MP3)",
                                callback_data=f"dl_mp3_url:{url[:200]}"
                            )
                        )

                        input_file = FSInputFile(video_file)
                        await message.answer_video(
                            input_file,
                            caption="✅ Mana videongiz! 🎬",
                            reply_markup=builder.as_markup()
                        )
                        await send_ad_if_active(message)
                    else:
                        await processing_msg.delete()
                        await message.answer("😕 Video hajmi juda katta (50MB dan oshadi)!")
                else:
                    await processing_msg.delete()
                    await message.answer(
                        "😕 Video yuklab olinmadi!\n\n"
                        "• Post ochiq (public) bo'lishi kerak\n"
                        "• Havolani tekshiring"
                    )
            else:
                await processing_msg.delete()
                error = stderr.decode()
                if "Private" in error or "Login" in error or "private" in error:
                    await message.answer(
                        "🔒 Bu post yopiq (private)!\n\n"
                        "Faqat ochiq (public) postlarni yuklab olish mumkin."
                    )
                elif "Unsupported URL" in error:
                    await message.answer(
                        "❌ Bu havola qo'llab-quvvatlanmaydi!\n\n"
                        "Qo'llab-quvvatlanadigan saytlar: Instagram, TikTok, YouTube, Twitter/X, Facebook"
                    )
                else:
                    await message.answer(
                        "😕 Video yuklab olinmadi!\n\n"
                        "• Havola to'g'ri ekanligini tekshiring\n"
                        "• Post public bo'lishi kerak\n"
                        "• Boshqa havola bilan sinab ko'ring"
                    )
    except asyncio.TimeoutError:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer("⏰ Vaqt tugadi! Video juda katta yoki sekin yuklanmoqda.")
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer("😕 Xatolik yuz berdi!\n\n• Havola to'g'ri ekanligini tekshiring")


@dp.callback_query(F.data.startswith("dl_mp3_url:"))
async def download_mp3_from_url(callback: types.CallbackQuery):
    """Video URL dan faqat audio yuklab berish"""
    url = callback.data[len("dl_mp3_url:"):]
    await callback.answer("⏳ Audio yuklanmoqda...")
    msg = await callback.message.answer("🎵 Audio ajratilmoqda... biroz kuting!")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "audio.%(ext)s")
            cmd = [
                "yt-dlp",
                url,
                "--no-playlist",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", output_path,
                "--no-warnings",
                "--no-check-certificates",
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            if process.returncode == 0:
                mp3_file = None
                for f in os.listdir(tmpdir):
                    if f.endswith(".mp3"):
                        mp3_file = os.path.join(tmpdir, f)
                        break

                if mp3_file and os.path.exists(mp3_file):
                    await msg.delete()
                    input_file = FSInputFile(mp3_file, filename="audio.mp3")
                    await callback.message.answer_audio(
                        input_file,
                        caption="🎵 Mana audioning!"
                    )
                    await send_ad_if_active(callback.message)
                else:
                    await msg.edit_text("😕 Audio ajratilmadi!")
            else:
                await msg.edit_text("😕 Audio yuklab olinmadi!")
    except asyncio.TimeoutError:
        try:
            await msg.delete()
        except:
            pass
        await callback.message.answer("⏰ Vaqt tugadi!")
    except Exception as e:
        try:
            await msg.delete()
        except:
            pass
        await callback.message.answer(f"❌ Xatolik: {str(e)}")


# ===================== MAIN =====================
async def main():
    await init_db()
    print("🤖 Kuy Navo Bot ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
