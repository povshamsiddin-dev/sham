import os
import asyncio
import aiohttp
import aiofiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message

# =============================================
# SOZLAMALAR - shu yerga o'z tokenlaringizni kiriting
# =============================================
BOT_TOKEN = os.getenv("BOT_TOKEN")        # @BotFather dan oling
AUDD_API_KEY = os.getenv("AUDD_API_KEY") # https://audd.io dan oling (bepul plan bor)
# =============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# /start komandasi
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🎵 *Kuy Navo Bot*'ga xush kelibsiz!\n\n"
        "Men sizga musiqani tanishga yordam beraman.\n\n"
        "📤 *Qanday foydalanish:*\n"
        "• Ovoz xabar yuboring (mikrofon orqali)\n"
        "• Yoki audio/musiqa fayli yuboring\n\n"
        "Men kuy nomini, artistni va boshqa ma'lumotlarni topaman! 🎶",
        parse_mode="Markdown"
    )


# Ovoz xabarlarni qabul qilish
@dp.message(F.voice)
async def handle_voice(message: Message):
    await recognize_music(message, message.voice.file_id)


# Audio fayllarni qabul qilish
@dp.message(F.audio)
async def handle_audio(message: Message):
    await recognize_music(message, message.audio.file_id)


# Video xabarlarni qabul qilish (ba'zan foydalanuvchilar video yuboradi)
@dp.message(F.video_note)
async def handle_video_note(message: Message):
    await recognize_music(message, message.video_note.file_id)


async def recognize_music(message: Message, file_id: str):
    """Asosiy funksiya: faylni yuklab, AudD orqali taniydi"""
    
    processing_msg = await message.answer("🔍 Kuy tanilmoqda... iltimos kuting!")
    
    try:
        # Faylni Telegram'dan yuklab olish
        file = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        
        # AudD API ga yuborish
        async with aiohttp.ClientSession() as session:
            # URL orqali yuborish (faylni yuklamasdan)
            data = {
                "url": file_url,
                "return": "apple_music,spotify",
                "api_token": AUDD_API_KEY
            }
            
            async with session.post("https://api.audd.io/", data=data) as resp:
                result = await resp.json()
        
        await processing_msg.delete()
        
        # Natijani tahlil qilish
        if result.get("status") == "success" and result.get("result"):
            song = result["result"]
            
            title = song.get("title", "Noma'lum")
            artist = song.get("artist", "Noma'lum")
            album = song.get("album", "Noma'lum")
            release_date = song.get("release_date", "Noma'lum")
            
            # Spotify linki
            spotify_link = ""
            if song.get("spotify"):
                spotify_url = song["spotify"].get("external_urls", {}).get("spotify", "")
                if spotify_url:
                    spotify_link = f"\n🎧 [Spotify'da tinglash]({spotify_url})"
            
            # Apple Music linki
            apple_link = ""
            if song.get("apple_music"):
                apple_url = song["apple_music"].get("url", "")
                if apple_url:
                    apple_link = f"\n🍎 [Apple Music'da tinglash]({apple_url})"
            
            response_text = (
                f"✅ *Kuy topildi!*\n\n"
                f"🎵 *Nomi:* {title}\n"
                f"🎤 *Artist:* {artist}\n"
                f"💿 *Albom:* {album}\n"
                f"📅 *Chiqarilgan:* {release_date}"
                f"{spotify_link}"
                f"{apple_link}"
            )
            
            await message.answer(response_text, parse_mode="Markdown")
        
        else:
            await message.answer(
                "😕 *Kuy aniqlanmadi*\n\n"
                "Iltimos:\n"
                "• Ovozroq yozib yuboring (kamida 5-10 soniya)\n"
                "• Fon shovqini kamaytiring\n"
                "• Boshqa bir parcha yuboring",
                parse_mode="Markdown"
            )
    
    except Exception as e:
        await processing_msg.delete()
        await message.answer(
            f"❌ Xatolik yuz berdi. Iltimos qayta urinib ko'ring.\n\n"
            f"_Xato: {str(e)}_",
            parse_mode="Markdown"
        )


# Boshqa xabarlar
@dp.message()
async def handle_other(message: Message):
    await message.answer(
        "🎵 Menga ovoz xabar yoki audio fayl yuboring!\n"
        "Men kuyni tanib, sizga ma'lumot beraman.\n\n"
        "Yordam uchun: /start"
    )


async def main():
    print("🤖 Kuy Navo Bot ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
