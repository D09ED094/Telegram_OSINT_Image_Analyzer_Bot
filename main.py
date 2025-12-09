import telebot
from PIL import Image, ExifTags, PngImagePlugin
import os
import time
import hashlib
import google.genai as genai
import requests 
import socket 

# ================= КОНФИГУРАЦИЯ =================
# Вставь сюда токен от BotFather
API_TOKEN = 'ТУТ_ТВОЙ_ТОКЕН_TELEGRAM'

# Вставь сюда API ключ от Google (https://aistudio.google.com/)
GOOGLE_API_KEY = 'ТУТ_ТВОЙ_API_KEY_GOOGLE'

# 1. Изменено на английский аналог, как вы просили
CUSTOM_EXIF_MESSAGE = "AHA, want metadata?" 
# ================================================

# Инициализация бота
bot = telebot.TeleBot(API_TOKEN)

# Инициализация клиента Gemini
client = None 

if GOOGLE_API_KEY != '0':
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        print("Клиент Gemini успешно инициализирован.")
    except Exception as e:
        print(f"Ошибка при инициализации клиента Gemini: {e}")
        client = None 
else:
    print("⚠️ GOOGLE_API_KEY не установлен. AI-функции будут недоступны.")

# ================= ФУНКЦИИ ПРОВЕРКИ ИНТЕРНЕТА =================

def check_internet_connection():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        return False

# ================= ОСНОВНЫЕ ФУНКЦИИ =================

def get_file_hashes(file_path):
    md5_hash = hashlib.md5()
    sha256_hash = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
            sha256_hash.update(byte_block)
            
    return md5_hash.hexdigest(), sha256_hash.hexdigest()

def convert_to_degrees(value):
    d = float(value[0])
    m = float(value[1])
    s = float(value[2])
    return d + (m / 60.0) + (s / 3600.0)

def get_gps_details(exif):
    if not exif: return None
    gps_info = {}
    for tag, value in exif.items():
        if ExifTags.TAGS.get(tag, tag) == "GPSInfo":
            gps_info = value; break
    if not gps_info: return None

    gps_decoded = {ExifTags.GPSTAGS.get(t, t): gps_info[t] for t in gps_info}

    try:
        lat = convert_to_degrees(gps_decoded['GPSLatitude'])
        lon = convert_to_degrees(gps_decoded['GPSLongitude'])
        lat = -lat if gps_decoded.get('GPSLatitudeRef') == 'S' else lat
        lon = -lon if gps_decoded.get('GPSLongitudeRef') == 'W' else lon
            
        return f"https://www.google.com/maps?q={lat},{lon}"
    except Exception:
        return None

def get_ai_analysis(image_path, metadata_text=None):
    if not client:
        return "⚠️ Google API Key не настроен или клиент не инициализирован. AI анализ пропущен."
    
    try:
        with Image.open(image_path) as img:
            prompt = (
                "Ты эксперт по OSINT. Проанализируй это изображение максимально подробно. "
                "1. Опиши местоположение, время суток, время года. "
                "2. Найди и перепиши любой видимый текст. "
                "3. Опиши уникальные детали (архитектура, оборудование, одежда и т.д.). "
                "4. Проверь наличие скрытых или кастомных метаданных, например, в поле UserComment или Comment."
            )
            
            if metadata_text:
                prompt += f"\n\nВот извлеченные метаданные изображения:\n{metadata_text}\n\nПроанализируй их вместе с изображением."

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt, img]
            )
            return response.text
    except Exception as e:
        return f"Ошибка AI анализа: {e}"

def clean_metadata(input_path, output_path, custom_message=None):
    exif_dict = {}
    metadata = None
    exif_bytes = None

    if custom_message:
        if output_path.lower().endswith(('.png')):
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("Comment", custom_message)
            metadata.add_text("Author", "OSINT_Bot_Custom_Metadata")
        else: 
            USER_COMMENT_ID = 0x9286
            ARTIST_ID = 0x013B
            
            user_comment_bytes = b'ASCII\x00\x00\x00' + custom_message.encode('ascii', errors='ignore')
            
            exif_dict[USER_COMMENT_ID] = user_comment_bytes
            exif_dict[ARTIST_ID] = "OSINT_Bot_Creator"
            
            try:
                exif_obj = Image.Exif()
                for tag_id, value in exif_dict.items():
                    exif_obj[tag_id] = value
                exif_bytes = exif_obj.tobytes()
            except Exception as e:
                import warnings
                warnings.warn(f"Не удалось создать EXIF-объект ({e}).")
                exif_bytes = None

    with Image.open(input_path) as img:
        data = list(img.getdata())
        image_to_save = Image.new(img.mode, img.size)
        image_to_save.putdata(data)

        if output_path.lower().endswith(('.png')) and metadata:
            image_to_save.save(output_path, pnginfo=metadata)
        elif exif_bytes:
            image_to_save.save(output_path, exif=exif_bytes)
        else:
            image_to_save.save(output_path)


def get_exif_data(image_path):
    REPORT_TAGS = ['DateTimeOriginal', 'Make', 'Model', 'Artist', 'Software', 'UserComment','OffsetTime']
    report = []
    
    md5, sha256 = get_file_hashes(image_path)
    report.append(f"🔍 <b>OSINT File Analysis</b>")
    report.append(f"<b>MD5:</b> <code>{md5}</code>")
    report.append(f"<b>SHA256:</b> <code>{sha256}</code>")
    report.append("-" * 20)

    try:
        with Image.open(image_path) as image: 
            exif_data = image._getexif()
            
            if exif_data:
                gps_link = get_gps_details(exif_data)
                if gps_link:
                    report.append(f"🌍 <b>GEOLOCATION FOUND:</b>\n<a href='{gps_link}'>Открыть на карте</a>")
                else:
                    report.append("🌍 <b>Geolocation:</b> Не найдена (нет GPS тегов)")
            else:
                report.append("❌ Метаданные (EXIF) не найдены.")
            
            report.append("-" * 20)

            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag_name == "GPSInfo": continue
                    
                    if tag_name in REPORT_TAGS or tag_name not in ExifTags.TAGS.values():
                        if tag_name == 'UserComment':
                            try:
                                if value.startswith(b'ASCII\x00\x00\x00'):
                                    value = value[8:].decode('utf-8', errors='ignore')
                                else:
                                    value = value.decode('utf-8', errors='ignore')
                            except Exception:
                                pass
                        
                        if isinstance(value, bytes) and len(value) > 50:
                            value = f"(Binary data: {len(value)} bytes)"
                        if isinstance(value, tuple) or isinstance(value, list):
                             value = str(value)
                        
                        report.append(f"<b>{tag_name}:</b> {value}")

            if 'title' in image.info or 'comment' in image.info or 'author' in image.info:
                report.append("🖼️ <b>PNG Metadata (INFO) Found:</b>")
                for key, value in image.info.items():
                    if key.lower() in ['title', 'comment', 'author']:
                        report.append(f"<b>{key}:</b> {value}")

        return "\n".join(report)
        
    except Exception as e:
        return f"Ошибка при анализе файла: {e}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 
                 "🕵️‍♂️ <b>OSINT Bot v2.4</b>\n\n"
                 "Функции:\n"
                 "1. 📍 Извлечение GPS и EXIF\n"
                 "2. 🤖 AI Анализ\n"
                 "3. 🧼 **Очистка и СТЕЛС-МЕТА**\n\n"
                 "Отправь фото как <b>Файл (Document)</b>.",
                 parse_mode='HTML')

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if not check_internet_connection():
        bot.reply_to(message, "🚨 **ОШИБКА:** Нет активного интернет-соединения. Бот временно отключен.")
        return 

    src = ""
    files_to_cleanup = []
    status_msg = None
    
    try:
        if 'image' not in message.document.mime_type:
            bot.reply_to(message, "Это не изображение. Жду файл (jpg/png).")
            return

        status_msg = bot.reply_to(message, "🕵️‍♂️ Анализирую метаданные, запускаю AI и очищаю файл...")
        
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        src = message.document.file_name
        with open(src, 'wb') as new_file:
            new_file.write(downloaded_file)
        files_to_cleanup.append(src)

        # =========================================================
        # ШАГ 1: ТЕХНИЧЕСКИЙ ОТЧЕТ (EXIF + Hashes) - ОТПРАВЛЯЕМ СРАЗУ
        # =========================================================
        tech_report_text = get_exif_data(src)
        
        if len(tech_report_text) > 4000:
            tech_filename = f"metadata_{src}.txt"
            with open(tech_filename, "w", encoding="utf-8") as f:
                clean_text = tech_report_text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<a href='", "").replace("'>Открыть на карте</a>", "")
                f.write(clean_text)
            
            with open(tech_filename, "rb") as f:
                bot.send_document(message.chat.id, f, caption="📂 Технические метаданные (слишком большие для сообщения)")
            files_to_cleanup.append(tech_filename)
        else:
            bot.reply_to(message, tech_report_text, parse_mode='HTML', disable_web_page_preview=False)

        # =========================================================
        # ПОДГОТОВКА: СОЗДАЕМ ЧИСТОЕ ФОТО (Но пока не отправляем!)
        # =========================================================
        clean_filename = f"clean_{src}"
        # Генерируем фото с новой мета-информацией "AHA, want metadata?"
        clean_metadata(src, clean_filename, custom_message=CUSTOM_EXIF_MESSAGE) 
        files_to_cleanup.append(clean_filename)

        # =========================================================
        # ШАГ 2: AI АНАЛИЗ (Анализируем чистое фото) - ОТПРАВЛЯЕМ ВТОРЫМ
        # =========================================================
        ai_result = get_ai_analysis(clean_filename, metadata_text=tech_report_text) 
        ai_filename = f"ai_analysis_{src}.txt"
        
        with open(ai_filename, "w", encoding="utf-8") as f:
             f.write(f"🤖 AI ANALYSIS REPORT (GEMINI)\n{'='*30}\n\n{ai_result}")
        
        with open(ai_filename, "rb") as f:
            bot.send_document(message.chat.id, f, caption="🤖 <b>AI Анализ изображения</b> (Gemini)", parse_mode='HTML')
        files_to_cleanup.append(ai_filename)

        # =========================================================
        # ШАГ 3: ОТПРАВЛЯЕМ ЧИСТОЕ ФОТО - ТЕПЕРЬ ПОСЛЕДНИМ
        # =========================================================
        with open(clean_filename, "rb") as clean_file:
            bot.send_document(message.chat.id, clean_file, caption=f"🧼 <b>Чистое фото + Стелс-Мета:</b>\n'{CUSTOM_EXIF_MESSAGE}'", parse_mode='HTML')


    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        
    finally:
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

# ================= ГЛАВНЫЙ ЦИКЛ ПОЛЛИНГА =================
while True:
    try:
        bot.polling(none_stop=True, interval=3) 
    
    except telebot.apihelper.ApiTelegramException as e:
        if 'connection aborted' in str(e).lower() or 'connection reset by peer' in str(e).lower():
            print("🚨 Потеряна связь с Telegram API. Проверяю интернет...")
            if not check_internet_connection():
                print("❌ Интернет-соединение отсутствует. Остановка бота.")
                time.sleep(30)
                continue 

        print(f"Критическая ошибка Telegram API: {e}. Перезапуск через 10 секунд.")
        time.sleep(10)
        
    except requests.exceptions.ReadTimeout:
        print("⚠️ Превышено время ожидания при чтении данных. Проверяю интернет...")
        time.sleep(5)
        
    except requests.exceptions.ConnectionError:
        print("❌ Ошибка соединения (ConnectionError). Проверяю интернет...")
        if not check_internet_connection():
            print("❌ Интернет-соединение отсутствует. Жду 30 секунд...")
            time.sleep(30)
        
    except Exception as e:
        print(f"Неизвестная критическая ошибка: {e}. Перезапуск через 5 секунд.")
        time.sleep(5)
