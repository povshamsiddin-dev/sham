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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db_pool = None


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
    dp['broadcast_mode'] = True


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
        "• 🔗 Instagram/TikTok/YouTube havolasi — video yuklab beradi\n"
        "• 🔍 Kuy nomi yozing — qidiradi\n\n"
        "Sinab ko'ring! 🚀",
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


async def check_user(message: Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    
    if not await is_bot_active() and user.id != ADMIN_ID:
        await message.answer("🔴 Bot hozir texnik ishlar uchun vaqtincha to'xtatilgan!")
        return False
    
    if await is_user_blocked(user.id):
        await message.answer("🚫 Siz bloklangansiz!")
        return False
    
    return True


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

            await message.answer(
                f"✅ *Kuy topildi!*\n\n"
                f"🎵 *Nomi:* {title}\n"
                f"🎤 *Artist:* {artist}\n"
                f"💿 *Albom:* {album}\n"
                f"📅 *Chiqarilgan:* {release_date}"
                f"{spotify_link}{apple_link}",
                parse_mode="Markdown"
            )
        else:
            await message.answer("😕 Kuy aniqlanmadi\n\n• Kamida 5-10 soniya yuboring")
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer(f"❌ Xatolik: {str(e)}")


@dp.message(F.text)
async def handle_text(message: Message):
    # Admin broadcast mode
    if message.from_user.id == ADMIN_ID and dp.get('broadcast_mode'):
        dp['broadcast_mode'] = False
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
            for i, song in enumerate(songs, 1):
                title = song.get("title", "Noma'lum")
                artist = song.get("artist", "Noma'lum")
                response += f"{i}. 🎤 *{artist}* — {title}\n"
            await message.answer(response, parse_mode="Markdown")
        else:
            await message.answer("😕 Kuy topilmadi\n\n💡 Ovoz xabar yuboring!")
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer(f"❌ Xatolik: {str(e)}")


async def download_video(message: Message, url: str):
    await increment_requests(message.from_user.id)
    processing_msg = await message.answer("⬇️ Video yuklanmoqda... biroz kuting!")
    
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
                        await message.answer_video(input_file, caption="✅ Mana videongiz! 🎬")
                    else:
                        await message.answer("😕 Video hajmi juda katta!")
                else:
                    await processing_msg.delete()
                    await message.answer("😕 Video yuklab olinmadi!")
            else:
                await processing_msg.delete()
                error = stderr.decode()
                if "Private" in error or "Login" in error:
                    await message.answer("🔒 Bu post private! Faqat ochiq postlarni yuklab olish mumkin.")
                else:
                    await message.answer("😕 Video yuklab olinmadi!\n\n• Havola to'g'ri ekanligini tekshiring\n• Post public bo'lishi kerak")
    except asyncio.TimeoutError:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer("⏰ Vaqt tugadi! Video juda katta.")
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer("😕 Xatolik yuz berdi!\n\n• Havola to'g'ri ekanligini tekshiring")


async def main():
    await init_db()
    print("🤖 Kuy Navo Bot ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
