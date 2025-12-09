import telebot
from PIL import Image, ExifTags
import os
import time
import hashlib # Для хеширования файлов (OSINT)
import google.genai as genai # Библиотека Google AI

# ================= КОНФИГУРАЦИЯ =================
# Вставь сюда токен от BotFather
API_TOKEN = 'ТУТ_ТВОЙ_ТОКЕН_TELEGRAM'

# Вставь сюда API ключ от Google (https://aistudio.google.com/)
GOOGLE_API_KEY = 'ТУТ_ТВОЙ_API_KEY_GOOGLE'
# ================================================

# Инициализация бота и AI
bot = telebot.TeleBot(API_TOKEN)

# --- ИСПРАВЛЕНИЕ ОШИБКИ configure() ---
# Вместо genai.configure() используем genai.Client()
model = None # Инициализируем модель как None по умолчанию
client = None # Инициализируем клиент API

if GOOGLE_API_KEY != 'оставить так нужно по преколу': 
    try:
        # Создаем экземпляр клиента, передавая ключ. Это заменяет genai.configure()
        client = genai.Client(api_key=GOOGLE_API_KEY)
        print("Клиент Gemini успешно инициализирован.")
    except Exception as e:
        # Теперь эта ошибка должна быть связана только с проблемами сети или ключа
        print(f"Ошибка при инициализации клиента Gemini: {e}")
        client = None # Оставляем None, если произошла ошибка
else:
    print("⚠️ GOOGLE_API_KEY не установлен. AI-функции будут недоступны.")


def get_file_hashes(file_path):
    """Считает MD5 и SHA256 хеши файла (цифровые отпечатки)."""
    md5_hash = hashlib.md5()
    sha256_hash = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
            sha256_hash.update(byte_block)
            
    return md5_hash.hexdigest(), sha256_hash.hexdigest()

def convert_to_degrees(value):
    """Вспомогательная функция для перевода координат."""
    d = float(value[0])
    m = float(value[1])
    s = float(value[2])
    return d + (m / 60.0) + (s / 3600.0)

def get_gps_details(exif):
    """Извлекает GPS данные и формирует ссылку на Google Maps."""
    if not exif:
        return None

    gps_info = {}
    for tag, value in exif.items():
        decoded = ExifTags.TAGS.get(tag, tag)
        if decoded == "GPSInfo":
            gps_info = value
            break
            
    if not gps_info:
        return None

    gps_decoded = {}
    for t in gps_info:
        sub_decoded = ExifTags.GPSTAGS.get(t, t)
        gps_decoded[sub_decoded] = gps_info[t]

    try:
        lat = convert_to_degrees(gps_decoded['GPSLatitude'])
        lon = convert_to_degrees(gps_decoded['GPSLongitude'])
        
        if gps_decoded.get('GPSLatitudeRef') == 'S':
            lat = -lat
        if gps_decoded.get('GPSLongitudeRef') == 'W':
            lon = -lon
            
        return f"https://www.google.com/maps?q={lat},{lon}"
    except Exception:
        return None

def get_ai_analysis(image_path):
    """Отправляет фото в Google Gemini для OSINT анализа."""
    # Используем клиент, а не модель, для вызова generate_content
    if not client:
        return "⚠️ Google API Key не настроен или клиент не инициализирован. AI анализ пропущен."
    
    try:
        with Image.open(image_path) as img:
            prompt = (
                "Ты эксперт по OSINT (Open Source Intelligence). Проанализируй это изображение максимально подробно. "
                "1. Опиши местоположение (страна, город, тип местности) по визуальным признакам. "
                "2. Укажи предполагаемое время суток и время года. "
                "3. Найди и перепиши любой видимый текст (вывески, номера авто, документы). "
                "4. Опиши уникальные детали: оборудование, одежду людей, архитектуру."
            )
            # ИСПРАВЛЕНИЕ: Вызываем через client.models
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt, img]
            )
            return response.text
    except Exception as e:
        return f"Ошибка AI анализа: {e}"

def clean_metadata(input_path, output_path):
    """Создает копию изображения без метаданных."""
    with Image.open(input_path) as img:
        # Мы создаем новый объект изображения, копируя только пиксели,
        # но не копируя exif словарь.
        data = list(img.getdata())
        image_without_exif = Image.new(img.mode, img.size)
        image_without_exif.putdata(data)
        image_without_exif.save(output_path)

def get_exif_data(image_path):
    """Основная функция анализа: хеши, GPS, теги, AI."""
    report = []
    
    # 1. Хеши
    md5, sha256 = get_file_hashes(image_path)
    report.append(f"🔍 <b>OSINT File Analysis</b>")
    report.append(f"<b>MD5:</b> <code>{md5}</code>")
    report.append(f"<b>SHA256:</b> <code>{sha256}</code>")
    report.append("-" * 20)

    try:
        with Image.open(image_path) as image: 
            exif_data = image._getexif()
            
            # 2. GPS
            if exif_data:
                gps_link = get_gps_details(exif_data)
                if gps_link:
                    report.append(f"🌍 <b>GEOLOCATION FOUND:</b>\n<a href='{gps_link}'>Открыть на карте</a>")
                else:
                    report.append("🌍 <b>Geolocation:</b> Не найдена (нет GPS тегов)")
            else:
                report.append("❌ Метаданные (EXIF) не найдены.")
            
            report.append("-" * 20)

            # 3. Остальные теги
            if exif_data:
                for tag, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag, tag)
                    if tag_name == "GPSInfo": continue
                    if isinstance(value, bytes) and len(value) > 50:
                        value = f"(Binary data: {len(value)} bytes)"
                    if isinstance(value, tuple) or isinstance(value, list):
                         value = str(value)
                    report.append(f"<b>{tag_name}:</b> {value}")
        
        return "\n".join(report)
        
    except Exception as e:
        return f"Ошибка при анализе файла: {e}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 
                 "🕵️‍♂️ <b>OSINT Bot v2.1</b>\n\n"
                 "Функции:\n"
                 "1. 📍 Извлечение GPS и EXIF (Сообщением)\n"
                 "2. 🤖 AI Анализ содержимого (Файлом .txt)\n"
                 "3. 🧼 Очистка фото от метаданных\n\n"
                 "Отправь фото как <b>Файл (Document)</b>.",
                 parse_mode='HTML')

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    src = ""
    files_to_cleanup = [] # Список файлов для удаления в конце
    status_msg = None
    
    try:
        if 'image' not in message.document.mime_type:
            bot.reply_to(message, "Это не изображение. Жду файл (jpg/png).")
            return

        status_msg = bot.reply_to(message, "🕵️‍♂️ Анализирую метаданные, запускаю AI и очищаю файл...")
        
        # Скачивание
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        src = message.document.file_name
        with open(src, 'wb') as new_file:
            new_file.write(downloaded_file)
        files_to_cleanup.append(src)

        # ---------------------------------------------------------
        # 1. ТЕХНИЧЕСКИЙ ОТЧЕТ (EXIF + Hashes)
        # ---------------------------------------------------------
        tech_report = get_exif_data(src)
        
        # Отправляем тех. отчет сообщением (или файлом, если огромный)
        if len(tech_report) > 4000:
            tech_filename = f"metadata_{src}.txt"
            with open(tech_filename, "w", encoding="utf-8") as f:
                # Очищаем от HTML тегов для txt файла
                clean_text = tech_report.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<a href='", "").replace("'>Открыть на карте</a>", "")
                f.write(clean_text)
            
            with open(tech_filename, "rb") as f:
                bot.send_document(message.chat.id, f, caption="📂 Технические метаданные (слишком большие для сообщения)")
            files_to_cleanup.append(tech_filename)
        else:
            bot.reply_to(message, tech_report, parse_mode='HTML', disable_web_page_preview=False)

        # ---------------------------------------------------------
        # 2. AI АНАЛИЗ (Всегда файлом)
        # ---------------------------------------------------------
        ai_result = get_ai_analysis(src)
        ai_filename = f"ai_analysis_{src}.txt"
        
        with open(ai_filename, "w", encoding="utf-8") as f:
             f.write(f"🤖 AI ANALYSIS REPORT (GEMINI)\n{'='*30}\n\n{ai_result}")
        
        with open(ai_filename, "rb") as f:
            bot.send_document(message.chat.id, f, caption="🤖 <b>AI Анализ изображения</b> (Gemini)", parse_mode='HTML')
        files_to_cleanup.append(ai_filename)

        # ---------------------------------------------------------
        # 3. ЧИСТОЕ ФОТО
        # ---------------------------------------------------------
        clean_filename = f"clean_{src}"
        clean_metadata(src, clean_filename)
        files_to_cleanup.append(clean_filename)
        
        with open(clean_filename, "rb") as clean_file:
            bot.send_document(message.chat.id, clean_file, caption="🧼 <b>Чистое фото</b> (Без метаданных)")

    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        
    finally:
        # Удаление всех временных файлов
        for f_path in files_to_cleanup:
            if f_path and os.path.exists(f_path):
                try:
                    time.sleep(0.5) 
                    os.remove(f_path)
                except Exception:
                    pass
                
        if status_msg:
            try:
                bot.delete_message(message.chat.id, status_msg.message_id)
            except Exception:
                pass

@bot.message_handler(content_types=['photo'])
def handle_compressed_photo(message):
    bot.reply_to(message, "⚠️ Отправь фото как <b>Файл (Document)</b>, иначе метаданные теряются.", parse_mode='HTML')

bot.polling(none_stop=True)
