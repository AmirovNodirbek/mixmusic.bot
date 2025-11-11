import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import yt_dlp
import speech_recognition as sr
from pydub import AudioSegment

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Sozlamalar
BOT_TOKEN = "8489467497:AAFWUYarCZ8-9f2otrF-R7RalzH4In2Gb00"  # @BotFather dan olingan token
CHANNEL_USERNAME = "@dasturlsh"  # Kanal username (@ bilan)
CHANNEL_ID = -1002476361081  # Kanal ID (to'g'ri bo'lishi kerak)
ADMIN_IDS = [8082692717]  # Admin ID lar

# Papkalarni yaratish
os.makedirs("downloads", exist_ok=True)
os.makedirs("temp", exist_ok=True)


class MusicBot:
    def __init__(self):
        self.recognizer = sr.Recognizer()

    async def check_subscription(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Kanal obunasini tekshirish"""
        try:
            if user_id in ADMIN_IDS:
                return True

            member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
            status = member.status

            if status in ['creator', 'administrator', 'member']:
                return True
            else:
                logger.info(f"User {user_id} status: {status}")
                return False

        except Exception as e:
            logger.error(f"Obuna tekshirishda xato: {e}")
            return user_id in ADMIN_IDS

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start komandasi"""
        user = update.effective_user
        user_id = user.id

        logger.info(f"User {user_id} ({user.username}) /start bosdi")

        is_subscribed = await self.check_subscription(user_id, context)

        if not is_subscribed:
            clean_username = CHANNEL_USERNAME.replace('@', '')
            keyboard = [
                [InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=f"https://t.me/{clean_username}")],
                [InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"👋 Assalomu alaykum, {user.first_name}!\n\n"
                f"🎵 <b>MixMusic Bot</b>ga xush kelibsiz!\n\n"
                f"⚠️ Botdan foydalanish uchun avval kanalimizga obuna bo'ling:\n"
                f"👉 {CHANNEL_USERNAME}\n\n"
                f"Obuna bo'lgandan keyin '✅ Obunani tekshirish' tugmasini bosing.",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            logger.info(f"User {user_id} allaqachon obuna")
            await self.show_menu(update, context)

    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Asosiy menyu"""
        message_text = (
            "🎵 <b>MixMusic Bot</b> - Har qanday qo'shiqni toping!\n\n"
            "📝 <b>Qanday foydalanish:</b>\n\n"
            "1️⃣ Qo'shiq nomini yozing\n"
            "   Masalan: <i>Yulduzlar mangu</i>\n\n"
            "2️⃣ Ovozli xabar yuboring\n"
            "   Qo'shiq nomini aytib ovozli xabar yuboring\n\n"
            "3️⃣ YouTube linki yuboring\n"
            "   Masalan: <i>https://youtube.com/watch?v=...</i>\n\n"
            "4️⃣ Instagram linki yuboring\n"
            "   Masalan: <i>https://instagram.com/p/...</i>\n\n"
            "💡 Qo'shiqni topgandan keyin 'Yuklab olish' tugmasini bosing!"
        )

        if update.callback_query:
            await update.callback_query.message.edit_text(
                message_text,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                message_text,
                parse_mode='HTML'
            )

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not await self.check_subscription(user_id, context):
            await self.start(update, context)
            return

        msg = await update.message.reply_text("🎤 Ovozli xabar qayta ishlanmoqda...")

        try:
            voice_file = await update.message.voice.get_file()
            voice_path = f"temp/voice_{user_id}.ogg"
            await voice_file.download_to_drive(voice_path)

            wav_path = f"temp/voice_{user_id}.wav"
            audio = AudioSegment.from_ogg(voice_path)
            audio.export(wav_path, format="wav")

            with sr.AudioFile(wav_path) as source:
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio_data, language="uz-UZ")

            await msg.edit_text(f"✅ Tushundim: <b>{text}</b>\n\n🔍 Qidirilmoqda...", parse_mode='HTML')
            await self.search_music(update, context, text)

            # Fayllarni xavfsiz o'chirish
            for path in [voice_path, wav_path]:
                if os.path.exists(path):
                    os.remove(path)

        except sr.UnknownValueError:
            await msg.edit_text("❌ Ovozni tushunib bo'lmadi. Iltimos, aniqroq aytib ko'ring.")
        except Exception as e:
            logger.error(f"Ovozli xabar xatosi: {e}")
            await msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()

        if not await self.check_subscription(user_id, context):
            await self.start(update, context)
            return

        if "youtube.com" in text or "youtu.be" in text:
            await self.download_from_youtube(update, context, text)
        elif "instagram.com" in text:
            await self.download_from_instagram(update, context, text)
        else:
            await self.search_music(update, context, text)

    async def search_music(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
        msg = await update.message.reply_text(f"🔍 <b>{query}</b> qidirilmoqda...", parse_mode='HTML')

        try:
            # ⚠️ 'outtmpl' ni O'CHIRING — chunki download=False
            ydl_opts = {
                'format': 'ba[ext=m4a]/ba',  # faqat audio
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(f"ytsearch5:{query}", download=False)

                if not results or not results.get('entries'):
                    await msg.edit_text("❌ Hech narsa topilmadi. Boshqa so'z bilan qidiring.")
                    return

                entries = results['entries'][:5]
                message_text = f"🎵 <b>'{query}'</b> uchun topilgan natijalar:\n\n"
                keyboard = []

                for i, entry in enumerate(entries, 1):
                    title = entry.get('title', 'Noma\'lum')
                    duration = entry.get('duration') or 0
                    video_id = entry.get('id', '')
                    mins, secs = divmod(int(duration), 60)
                    duration_str = f"{mins}:{secs:02d}"

                    message_text += f"{i}. {title}\n⏱ {duration_str}\n\n"
                    keyboard.append([
                        InlineKeyboardButton(f"⬇️ {i}. Yuklab olish", callback_data=f"download_{video_id}")
                    ])

                keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
                reply_markup = InlineKeyboardMarkup(keyboard)

                await msg.edit_text(message_text, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Qidiruv xatosi: {e}")
            await msg.edit_text(f"❌ Qidirishda xatolik: {str(e)}")

    async def download_from_youtube(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        msg = await update.message.reply_text(
            "🎵 <b>Qo'shiq topildi!</b>\n"
            "⏳ Yuklab olish boshlandi...\n"
            "Iltimos, 5–20 soniya kutib turing (tarmoq tezligiga qarab).",
            parse_mode='HTML'
        )

        try:
            user_id = update.effective_user.id
            output_path = f"downloads/{user_id}_%(id)s.%(ext)s"

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_path,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                mp3_file = filename.rsplit('.', 1)[0] + '.mp3'

                if not os.path.exists(mp3_file):
                    await msg.edit_text("❌ Fayl yuklanmadi. Serverda FFmpeg o'rnatilganligiga ishonch hosil qiling.")
                    return

                await msg.edit_text("📤 Yuborilmoqda...")

                with open(mp3_file, 'rb') as audio:
                    await update.message.reply_audio(
                        audio=audio,
                        title=info.get('title', 'Qo\'shiq'),
                        performer=info.get('uploader', 'Noma\'lum'),
                        duration=info.get('duration', 0),
                        caption=f"🎵 <b>{info.get('title')}</b>\n\n💠 @{context.bot.username}",
                        parse_mode='HTML'
                    )

                await msg.delete()

                # Xavfsiz o'chirish
                if os.path.exists(mp3_file):
                    os.remove(mp3_file)

        except Exception as e:
            logger.error(f"YouTube yuklab olish xatosi: {e}")
            await msg.edit_text(f"❌ Xatolik: {str(e)}")

    async def download_from_instagram(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        msg = await update.message.reply_text("⬇️ Instagram'dan yuklab olinmoqda...")

        try:
            user_id = update.effective_user.id
            output_path = f"downloads/{user_id}_%(id)s.%(ext)s"

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_path,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                mp3_file = filename.rsplit('.', 1)[0] + '.mp3'

                if not os.path.exists(mp3_file):
                    await msg.edit_text("❌ Audio topilmadi yoki qo'llab-quvvatlanmaydi.")
                    return

                await msg.edit_text("📤 Yuborilmoqda...")

                with open(mp3_file, 'rb') as audio:
                    await update.message.reply_audio(
                        audio=audio,
                        title=info.get('title', 'Instagram Audio'),
                        caption=f"🎵 Instagram Audio\n\n💠 @{context.bot.username}",
                        parse_mode='HTML'
                    )

                await msg.delete()

                if os.path.exists(mp3_file):
                    os.remove(mp3_file)

        except Exception as e:
            logger.error(f"Instagram yuklab olish xatosi: {e}")
            await msg.edit_text(f"❌ Xatolik: {str(e)}")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()  # Har doim javob berish kerak
        user_id = query.from_user.id
        data = query.data

        if data == "check_sub":
            is_subscribed = await self.check_subscription(user_id, context)
            if is_subscribed:
                await query.message.delete()
                await self.show_menu(update, context)
            else:
                await query.answer(
                    "❌ Siz hali obuna bo'lmadingiz! Iltimos, kanalga obuna bo'lib, qaytadan urinib ko'ring.",
                    show_alert=True
                )

        elif data == "back_menu":
            await self.show_menu(update, context)

        elif data.startswith("download_"):
            video_id = data.replace("download_", "")
            await query.message.edit_text("⬇️ Yuklab olinmoqda...")

            try:
                url = f"https://www.youtube.com/watch?v={video_id}"
                user_id = query.from_user.id
                output_path = f"downloads/{user_id}_%(id)s.%(ext)s"

                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': output_path,
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    mp3_file = filename.rsplit('.', 1)[0] + '.mp3'

                    if not os.path.exists(mp3_file):
                        await query.message.edit_text("❌ Yuklab olish muvaffaqiyatsiz.")
                        return

                    await query.message.edit_text("📤 Yuborilmoqda...")

                    with open(mp3_file, 'rb') as audio:
                        await context.bot.send_audio(
                            chat_id=query.message.chat_id,
                            audio=audio,
                            title=info.get('title', 'Qo\'shiq'),
                            performer=info.get('uploader', 'Noma\'lum'),
                            duration=info.get('duration', 0),
                            caption=f"🎵 <b>{info.get('title')}</b>\n\n💠 @{context.bot.username}",
                            parse_mode='HTML'
                        )

                    await query.message.delete()

                    if os.path.exists(mp3_file):
                        os.remove(mp3_file)

            except Exception as e:
                logger.error(f"Yuklab olish xatosi (callback): {e}")
                await query.message.edit_text(f"❌ Xatolik: {str(e)}")

    async def test_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        try:
            bot_member = await context.bot.get_chat_member(CHANNEL_ID, context.bot.id)
            user_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
            chat = await context.bot.get_chat(CHANNEL_ID)

            bot_status = bot_member.status
            user_status = user_member.status

            message = (
                f"🔍 <b>Kanal test natijalari:</b>\n\n"
                f"📢 Kanal: {chat.title}\n"
                f"🆔 ID: <code>{CHANNEL_ID}</code>\n"
                f"👤 Username: {CHANNEL_USERNAME}\n\n"
                f"🤖 Bot statusi: <b>{bot_status}</b>\n"
                f"👨 Sizning statusingiz: <b>{user_status}</b>\n\n"
            )

            if user_status in ['creator', 'administrator', 'member']:
                message += "✅ Siz kanalga obuna bo'lgansiz!"
            else:
                message += "❌ Siz kanalga obuna bo'lmagan ekansiz!"

            if bot_status not in ['administrator', 'creator']:
                message += "\n\n⚠️ DIQQAT: Bot kanalda admin emas! Botni admin qiling."

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            await update.message.reply_text(
                f"❌ <b>Xatolik:</b>\n<code>{str(e)}</code>\n\n"
                f"Tekshiring:\n"
                f"• Kanal ID to'g'ri ekanligi\n"
                f"• Botni kanalga admin qilganingiz\n"
                f"• Bot tokeni yashirin holda ishlayotganligi",
                parse_mode='HTML'
            )

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Statistika (faqat adminlar uchun)"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Bu komanda faqat adminlar uchun!")
            return

        # Hozircha sodda statistika (keyinchalik DB qo'shish mumkin)
        await update.message.reply_text(
            "📊 <b>Bot statistikasi:</b>\n\n"
            "👥 Foydalanuvchilar: 0 (ma'lumotlar bazasi yo'q)\n"
            "⬇️ Yuklashlar: 0\n"
            "📅 Bugun: 0\n\n"
            "💡 To'liq statistika uchun ma'lumotlar bazasi kerak.",
            parse_mode='HTML'
        )

    def run(self):
        app = Application.builder().token(BOT_TOKEN).build()

        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("test", self.test_channel))
        app.add_handler(CommandHandler("stats", self.stats))
        app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        app.add_handler(CallbackQueryHandler(self.button_callback))

        logger.info("🎵 MixMusic Bot ishga tushdi!")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = MusicBot()
    bot.run()