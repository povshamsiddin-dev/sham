import os
import asyncio
import aiohttp
import subprocess
import tempfile
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUDD_API_KEY = os.getenv("AUDD_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🎵 *Kuy Navo Bot*'ga xush kelibsiz!\n\n"
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
    await recognize_music(message, message.voice.file_id)


@dp.message(F.audio)
async def handle_audio(message: Message):
    await recognize_music(message, message.audio.file_id)


@dp.message(F.video_note)
async def handle_video_note(message: Message):
    await recognize_music(message, message.video_note.file_id)


async def recognize_music(message: Message, file_id: str):
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
                "• Kamida 5-10 soniya yozib yuboring\n"
                "• Fon shovqinini kamaytiring",
                parse_mode="Markdown"
            )
    except Exception as e:
        await processing_msg.delete()
        await message.answer(f"❌ Xatolik: {str(e)}")


@dp.message(F.text)
async def handle_text(message: Message):
    text = message.text.strip()

    video_domains = ["instagram.com", "tiktok.com", "youtube.com", "youtu.be", "twitter.com", "x.com", "facebook.com", "t.me"]
    if any(domain in text for domain in video_domains):
        await download_video(message, text)
    else:
        await search_music(message, text)


async def search_music(message: Message, query: str):
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
        await processing_msg.delete()
        await message.answer(f"❌ Xatolik: {str(e)}")


async def download_video(message: Message, url: str):
    processing_msg = await message.answer("⬇️ Video yuklanmoqda... biroz kuting! (1-2 daqiqa)")
    
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
                # Faylni top
                video_file = None
                for f in os.listdir(tmpdir):
                    if f.startswith("video"):
                        video_file = os.path.join(tmpdir, f)
                        break
                
                if video_file and os.path.exists(video_file):
                    await processing_msg.delete()
                    file_size = os.path.getsize(video_file)
                    
                    if file_size < 50 * 1024 * 1024:  # 50MB
                        input_file = FSInputFile(video_file)
                        await message.answer_video(
                            input_file,
                            caption="✅ Mana videongiz! 🎬\n\n🤖 @KuyNavoBot"
                        )
                    else:
                        await message.answer("😕 Video hajmi juda katta (50MB dan oshiq)!")
                else:
                    await processing_msg.delete()
                    await message.answer("😕 Video yuklab olinmadi!")
            else:
                await processing_msg.delete()
                error = stderr.decode()
                if "Private" in error or "Login" in error:
                    await message.answer(
                        "🔒 *Bu post private!*\n\n"
                        "Faqat ochiq (public) postlarni yuklab olish mumkin.",
                        parse_mode="Markdown"
                    )
                else:
                    await message.answer(
                        "😕 *Video yuklab olinmadi*\n\n"
                        "• Havola to'g'ri ekanligini tekshiring\n"
                        "• Post public bo'lishi kerak",
                        parse_mode="Markdown"
                    )
    except asyncio.TimeoutError:
        await processing_msg.delete()
        await message.answer("⏰ Vaqt tugadi! Video juda katta yoki sekin internet.")
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer(
            "😕 *Xatolik yuz berdi*\n\n"
            "• Havola to'g'ri ekanligini tekshiring\n"
            "• Post public bo'lishi kerak",
            parse_mode="Markdown"
        )


async def main():
    print("🤖 Kuy Navo Bot ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
