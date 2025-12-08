import telebot
from PIL import Image, ExifTags
import os
import time
import hashlib # Для хеширования файлов (OSINT)

# Вставь сюда токен, полученный от @BotFather
API_TOKEN = 'ТУТ_ТВОЙ_ТОКЕН'

# Инициализация бота
bot = telebot.TeleBot(API_TOKEN)

def get_file_hashes(file_path):
    """Считает MD5 и SHA256 хеши файла (цифровые отпечатки)."""
    md5_hash = hashlib.md5()
    sha256_hash = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        # Читаем файл кусками, чтобы не забить память
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
            sha256_hash.update(byte_block)
            
    return md5_hash.hexdigest(), sha256_hash.hexdigest()

def convert_to_degrees(value):
    """Вспомогательная функция для перевода координат из (градусы, минуты, секунды) в десятичные."""
    d = float(value[0])
    m = float(value[1])
    s = float(value[2])
    return d + (m / 60.0) + (s / 3600.0)

def get_gps_details(exif):
    """Извлекает GPS данные и формирует ссылку на Google Maps."""
    if not exif:
        return None

    gps_info = {}
    
    # Ищем тег GPSInfo (ID 34853)
    for tag, value in exif.items():
        decoded = ExifTags.TAGS.get(tag, tag)
        if decoded == "GPSInfo":
            gps_info = value
            break
            
    if not gps_info:
        return None

    # GPS теги тоже имеют свои ID, декодируем их
    gps_decoded = {}
    for t in gps_info:
        sub_decoded = ExifTags.GPSTAGS.get(t, t)
        gps_decoded[sub_decoded] = gps_info[t]

    # Пытаемся получить широту и долготу
    try:
        lat = convert_to_degrees(gps_decoded['GPSLatitude'])
        lon = convert_to_degrees(gps_decoded['GPSLongitude'])
        
        # Учитываем полушария (S - южное, W - западное -> отрицательные значения)
        if gps_decoded.get('GPSLatitudeRef') == 'S':
            lat = -lat
        if gps_decoded.get('GPSLongitudeRef') == 'W':
            lon = -lon
            
        return f"https://www.google.com/maps?q={lat},{lon}"
    except Exception:
        return None

def get_exif_data(image_path):
    """Основная функция анализа: хеши, GPS, теги."""
    report = []
    
    # 1. Считаем хеши (важно для OSINT)
    md5, sha256 = get_file_hashes(image_path)
    report.append(f"🔍 <b>OSINT File Analysis</b>")
    report.append(f"<b>MD5:</b> <code>{md5}</code>")
    report.append(f"<b>SHA256:</b> <code>{sha256}</code>")
    report.append("-" * 20)

    try:
        with Image.open(image_path) as image: 
            exif_data = image._getexif()
            
            # 2. Пытаемся достать GPS
            if exif_data:
                gps_link = get_gps_details(exif_data)
                if gps_link:
                    report.append(f"🌍 <b>GEOLOCATION FOUND:</b>\n<a href='{gps_link}'>Открыть на карте</a>")
                else:
                    report.append("🌍 <b>Geolocation:</b> Не найдена (нет GPS тегов)")
            else:
                report.append("❌ Метаданные (EXIF) не найдены.")
            
            report.append("-" * 20)

            # 3. Вывод остальных тегов
            if exif_data:
                for tag, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag, tag)
                    
                    # Игнорируем сам блок GPSInfo в общем списке, так как он огромен и нечитаем
                    if tag_name == "GPSInfo":
                        continue
                    
                    # Сокращаем бинарные данные
                    if isinstance(value, bytes) and len(value) > 50:
                        value = f"(Binary data: {len(value)} bytes)"
                    
                    # Преобразуем сложные структуры
                    if isinstance(value, tuple) or isinstance(value, list):
                         value = str(value)

                    report.append(f"<b>{tag_name}:</b> {value}")
        
        return "\n".join(report)
        
    except Exception as e:
        return f"Ошибка при анализе файла: {e}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 
                 "🕵️‍♂️ <b>OSINT Metadata Bot</b>\n\n"
                 "Я извлекаю:\n"
                 "- 📍 GPS координаты (ссылка на карты)\n"
                 "- 🔑 Хеши MD5/SHA256 (для проверки на VirusTotal)\n"
                 "- 📷 Модель камеры и настройки\n\n"
                 "❗ Отправляй фото <b>КАК ФАЙЛ</b> (без сжатия).",
                 parse_mode='HTML')

# Обработчик документов (файлов)
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    src = ""
    status_msg = None
    try:
        if 'image' not in message.document.mime_type:
            bot.reply_to(message, "Это не изображение. Жду файл (jpg/png/tiff).")
            return

        status_msg = bot.reply_to(message, "🕵️‍♂️ Анализирую цифровой след...")
        
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        src = message.document.file_name
        with open(src, 'wb') as new_file:
            new_file.write(downloaded_file)

        report = get_exif_data(src)
        
        # Если отчет слишком большой
        if len(report) > 4000:
            txt_file_path = f"report_{src}.txt"
            with open(txt_file_path, "w", encoding="utf-8") as f:
                f.write(report.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<a href='", "").replace("'>Открыть на карте</a>", ""))
            
            with open(txt_file_path, "rb") as f:
                bot.send_document(message.chat.id, f, caption="⚠️ Данных слишком много. Полный отчет в файле.")
            os.remove(txt_file_path)
        else:
            bot.reply_to(message, report, parse_mode='HTML', disable_web_page_preview=False)
            
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        
    finally:
        if src and os.path.exists(src):
            try:
                time.sleep(0.5) 
                os.remove(src)
            except Exception as remove_e:
                print(f"Error removing {src}: {remove_e}")
                
        if status_msg:
            try:
                bot.delete_message(message.chat.id, status_msg.message_id)
            except Exception:
                pass

@bot.message_handler(content_types=['photo'])
def handle_compressed_photo(message):
    bot.reply_to(message, 
                 "⚠️ <b>ОШИБКА OSINT:</b> Это сжатое фото.\n"
                 "Telegram удалил GPS и EXIF данные.\n"
                 "Отправь фото как <b>Файл (Document)</b>.",
                 parse_mode='HTML')

bot.polling(none_stop=True)
