# 🎵 Kuy Navo Bot

Telegram uchun Shazam-ga o'xshash musiqa tanish boti.

---

## 🚀 O'rnatish va ishga tushirish

### 1. Token olish

**Telegram Bot Token:**
1. Telegram'da `@BotFather` ni oching
2. `/newbot` yuboring
3. Bot uchun nom va username kiriting
4. Token oling → `bot.py` dagi `BOT_TOKEN` ga yozing

**AudD API Key (bepul!):**
1. https://audd.io ga kiring
2. Ro'yxatdan o'ting (bepul plan: 100 so'rov/kun)
3. API key oling → `bot.py` dagi `AUDD_API_KEY` ga yozing

---

### 2. Kutubxonalarni o'rnatish

```bash
pip install -r requirements.txt
```

---

### 3. Botni ishga tushirish

```bash
python bot.py
```

---

## 📖 Foydalanish

1. Botni Telegram'da oching
2. `/start` yuboring
3. Ovoz xabar yoki audio fayl yuboring
4. Bot kuy nomi, artist va boshqa ma'lumotlarni qaytaradi!

---

## 🛠 Texnik tafsilotlar

- **Kutubxona:** aiogram 3.x (Python)
- **Musiqa tanish API:** AudD.io
- **Qo'llab-quvvatlaydi:** Ovoz xabar, MP3, WAV, OGG va boshqa audio formatlar

---

## 💡 Maslahat

AudD bepul plani kuniga 100 so'rovga ruxsat beradi.
Ko'proq kerak bo'lsa, to'lov plani mavjud.
