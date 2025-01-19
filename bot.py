from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import speech_recognition as sr
from datetime import datetime
from telebot import TeleBot
from telebot import types
import soundfile as sf
import requests
import sqlite3
import time
import json
import pytz
import uuid
import os
from se import BOT_TOKEN, ADMIN_CHAT_ID, ADMIN_ID

BOT_TOKEN
VOICE_LANGUAGE = 'ru-RU'
MAX_MESSAGE_SIZE = 50 * 1024 * 1024
MAX_MESSAGE_DURATION = 120

bot = TeleBot(BOT_TOKEN)

start_time = time.time()

# Создаём или подключаемся к базе данных пользователей
conn_users = sqlite3.connect("users.db", check_same_thread=False)
cursor_users = conn_users.cursor()

# Создаём таблицу для пользователей, если её ещё нет
cursor_users.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    chat_id TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    username TEXT,
    language TEXT DEFAULT "Unknown",
    joined_at TEXT DEFAULT CURRENT_TIMESTAMP
)
''')
conn_users.commit()

# Создаём или подключаемся к базе данных групп
conn_groups = sqlite3.connect("groups.db", check_same_thread=False)
cursor_groups = conn_groups.cursor()

# Создаём таблицу для групп, если её ещё нет
cursor_groups.execute('''
CREATE TABLE IF NOT EXISTS groups (
    group_id INTEGER PRIMARY KEY,
    group_name TEXT NOT NULL,
    invite_link TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
''')
conn_groups.commit()

# Создаём таблицу пользователей группы (общая для всех групп)
cursor_groups.execute('''
CREATE TABLE IF NOT EXISTS group_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    message_count INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0
)
''')
conn_groups.commit()

# Функция для сохранения данных пользователя
def save_user(message):
    try:
        cursor_users.execute('''
        INSERT OR REPLACE INTO users (user_id, chat_id, first_name, last_name, username, language)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            message.from_user.id,
            message.chat.id,
            message.from_user.first_name,
            message.from_user.last_name,
            message.from_user.username,
            message.from_user.language_code or "Unknown"
        ))
        conn_users.commit()
        print(f"User {message.from_user.id} saved successfully.")
    except Exception as e:
        print(f"Error saving user data: {e}")

# Функция для сохранения данных группы
def save_group(group_id, group_name, invite_link=None):
    try:
        if invite_link is None:
            try:
                invite_link = bot.export_chat_invite_link(group_id)
            except Exception as e:
                print(f"Не удалось получить ссылку для группы {group_name} ({group_id}): {e}")
                invite_link = None
        cursor_groups.execute('''
        INSERT OR REPLACE INTO groups (group_id, group_name, invite_link)
        VALUES (?, ?, ?)
        ''', (group_id, group_name, invite_link))
        conn_groups.commit()
        print(f"Group {group_name} ({group_id}) saved successfully with invite link: {invite_link}")
    except Exception as e:
        print(f"Error saving group data: {e}")

# Функция обновления пользователя в группе
def update_user_in_group(group_id, user_id, username, is_admin):
    try:
        cursor_groups.execute('''
        INSERT INTO group_users (group_id, user_id, username, message_count, is_admin)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(group_id, user_id) DO UPDATE SET
            message_count = message_count + 1,
            is_admin = CASE WHEN is_admin = 0 THEN ? ELSE is_admin END
        ''', (group_id, user_id, username, is_admin, is_admin))
        conn_groups.commit()
    except Exception as e:
        print(f"Error updating user in group: {e}")

# Функция для создания базы данных группы
def create_group_db(group_name):
    db_path = f"{group_name}.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS group_users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        message_count INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS group_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_users INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    return conn, cursor

# Функция для добавления или обновления пользователя в базе данных группы
def update_group_user(group_name, user_id, username, is_admin=False):
    db_path = f"{group_name}.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO group_users (user_id, username, message_count, is_admin)
    VALUES (?, ?, 1, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        message_count = message_count + 1,
        is_admin = CASE WHEN is_admin = 0 THEN ? ELSE is_admin END
    ''', (user_id, username, is_admin, is_admin))
    conn.commit()
    cursor.execute('SELECT COUNT(*) FROM group_users')
    total_users = cursor.fetchone()[0]
    cursor.execute('UPDATE group_info SET total_users = ? WHERE id = 1', (total_users,))
    conn.commit()
    conn.close()




# Команда /start
@bot.message_handler(commands=["start"])
def send_welcome(message):
    if message.chat.type in ["group", "supergroup"]:
        group_id = message.chat.id
        group_name = message.chat.title
        invite_link = None

        # Сохраняем данные о группе
        save_group(group_id, group_name, invite_link)
        # Создаём базу данных для группы, если её ещё нет
        conn, cursor = create_group_db(group_name)

        # Проверяем, существует ли запись о группе
        cursor.execute('SELECT COUNT(*) FROM group_info')
        if cursor.fetchone()[0] == 0:
            # Добавляем запись о группе
            cursor.execute('INSERT INTO group_info (total_users) VALUES (0)')
            conn.commit()

        conn.close()

        send_welcome_group = (
            f"<b>Привет, группа {group_name}!</b>\n\n"
            "Спасибо, что добавили меня. Я готов помогать! 😊\n\n"
            "<b>Мои функции:</b>\n"
            "- Преобразование голосовых сообщений в текст.\n\n"
            "Наше семейство NX Ботов - /nx_family\n"
            "Обратная связь с разработчиком - /feedback"
        )


        bot.send_message(message.chat.id, send_welcome_group, parse_mode="HTML")
    else:
        user_id = str(message.from_user.id)
        chat_id = str(message.chat.id)
        # Сохраняем данные пользователя
        save_user(message)

        # Кнопка для добавления бота в группу
        markup = types.InlineKeyboardMarkup()
        add_to_group_button = types.InlineKeyboardButton(
            text="➕ Добавить в группу", url=f"https://t.me/{bot.get_me().username}?startgroup=true"
        )
        markup.add(add_to_group_button)

        welcome_message = (
            f"<b>Привет, {message.from_user.first_name}! 👋</b>\n\n"
            "<b>Мы рады, что Вы теперь с нами. 😊</b>\n\n"
            "<blockquote><b>Этот бот преобразует голосовые сообщения в текст.</b>\n"
            "<b>Это идеально для случаев, когда Вы не можете прослушать сообщения, но можете прочитать.</b></blockquote>\n"
            "Также Вы можете добавить нашего бота в Вашу группу по кнопке ниже.\n"
            "После добавления в группу пропишите /start.\n\n"
            "Наше семейство NX Ботов - /nx_family\n"
            "Обратная связь с разработчиком - /feedback"
        )
        bot.send_message(chat_id, welcome_message, parse_mode="HTML", reply_markup=markup)



















@bot.message_handler(content_types=['voice'])
def echo_voice(message):
    data = message.voice
    if (data.file_size > MAX_MESSAGE_SIZE) or (data.duration > MAX_MESSAGE_DURATION):
        reply = ' '.join((
            "Голосовое сообщение слишком большое.",
            "Максимальная длительность: {} сек.".format(MAX_MESSAGE_DURATION),
            "Попробуйте сказать что-то по короче.",
        ))
        return bot.reply_to(message, reply)

    file_url = "https://api.telegram.org/file/bot{}/{}".format(
        bot.token,
        bot.get_file(data.file_id).file_path
    )

    # Загрузка файла на локальное хранилище
    file_path = download_file(file_url)

    # Преобразование аудиофайла в формат PCM_16
    convert_to_pcm16(file_path)

    # Обработка аудиофайла
    text = process_audio_file("action/new.wav")

    if not text:
        return bot.reply_to(message, "Не понял вас, пожалуйста, повторите.")

    return bot.reply_to(message, text)

def download_file(file_url):
    file_path = "action/voice_message.ogg"
    with open(file_path, 'wb') as f:
        response = requests.get(file_url)
        f.write(response.content)
    return file_path

def convert_to_pcm16(file_path):
    data, samplerate = sf.read(file_path)
    sf.write('action/new.wav', data, samplerate, subtype='PCM_16')

def process_audio_file(file_path):
    recognizer = sr.Recognizer()
    with sr.AudioFile(file_path) as source:
        audio_data = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio_data, language=VOICE_LANGUAGE)
        return text
    except sr.UnknownValueError:
        return None












@bot.message_handler(commands=["ping"])
def send_ping(message):

    try:
        # Измерение времени отправки первого сообщения
        start_time = time.time()
        bot.send_message(message.chat.id, "🏓 <b>Pong!</b>", parse_mode="HTML")
        time.sleep(1)  # Пауза 1 секунда

        # Второе сообщение
        bot.send_message(message.chat.id, "<i>Хм, ладно...</i>", parse_mode="HTML")
        time.sleep(0.5)  # Пауза 0.5 секунды

        # Измерение времени отклика
        end_time = time.time()
        response_time = round((end_time - start_time) * 1000, 2)  # Время в миллисекундах

        # Третье сообщение с информацией
        bot.send_message(
            message.chat.id,
            (
                f"🤖 <b>Состояние:</b> Бот работает стабильно!\n"
                f"⏱ <b>Время отклика:</b> {response_time} мс\n"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {e}")

@bot.message_handler(commands=["uptime"])
def send_uptime(message):

    try:
        # Время текущего запроса
        current_time = time.time()
        uptime_seconds = int(current_time - start_time)  # Время работы в секундах

        # Преобразуем в формат ДД:ЧЧ:ММ:СС
        days = uptime_seconds // 86400  # 1 день = 86400 секунд
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60

        # Формируем сообщение с часами
        uptime_message = (
            f"🤖 <b>Время работы бота:</b>\n"
            f"<b>{hours} ч {minutes} мин {seconds} сек</b>\n"
            f"<b>{days} д {hours} ч {minutes} мин {seconds} сек</b>"
        )
        
        bot.send_message(message.chat.id, uptime_message, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {e}")




















#===============================NX семья==============================================================================

@bot.message_handler(commands=['nx_family'])
def send_support_message(message):
    
    keyboard = types.InlineKeyboardMarkup()
    NX_Louer = types.InlineKeyboardButton(
        text="NX Louer 🌐", url="https://t.me/NX_Louer_bot")
    NX_Support = types.InlineKeyboardButton(
        text="NX Поддержка ⚙️", url="https://t.me/NX_Support_bot")
    NX_News_Trading = types.InlineKeyboardButton(
        text="NX News Trading 📰", url="https://t.me/NXNews_Trading_bot")
    NX_Echo = types.InlineKeyboardButton(
        text="NX Echo 🎙️", url="https://t.me/NX_Echo_bot")
    NX_Searcher = types.InlineKeyboardButton(
        text="NX Searcher AI 🔍", url="https://t.me/NX_Searcher_bot")
    keyboard.add(NX_Echo, NX_Louer)
    keyboard.add(NX_Support)
    keyboard.add(NX_Searcher)
    keyboard.add(NX_News_Trading)

    with open("NX Family.png", "rb") as photo:
        caption_message = (
            f"Доброго времени суток, <b>{message.from_user.first_name}</b>.👋\n"
            "👥 Тут собрано семейство наших NX Ботов, у каждого свои задачи и возможности.\n\n"
            "🔹 <b>NX Echo</b>🎙️ — Преобразовывает голосовые сообщения в текст, удобно и быстро.\n"
            "🔹 <b>NX Louer</b> 🌐 — Ваш многофункциональный помощник для выполнения задач.\n"
            "🔹 <b>NX Поддержка</b> ⚙️ — Техподдержка всегда на связи, чтобы помочь вам.\n"
            "🔹 <b>NX Searcher AI</b> 🔍 — Ответит на любов вопрос, сделан на основе AI.\n"
            "🔹 <b>NX News Trading</b> 📰 — Актуальные новости экономики и аналитика для трейдинга.\n\n"
            "В будущем список будет пополнятся !)\n<b>Выберите нужного бота из списка ниже и начните использовать их <u>прямо сейчас!</u> 🚀</b>"
        )
        bot.send_photo(message.chat.id, photo, caption_message, parse_mode="HTML", reply_markup=keyboard)

#=========================================группы==========================================================================

@bot.message_handler(func=lambda message: message.text.startswith('/nx_family'))
def send_support_message(message):
    if message.chat.type not in ['group', 'supergroup']:
        return

    keyboard = types.InlineKeyboardMarkup()
    NX_Louer = types.InlineKeyboardButton(
        text="NX Louer 🌐", url="https://t.me/NX_Louer_bot")
    NX_Support = types.InlineKeyboardButton(
        text="NX Поддержка ⚙️", url="https://t.me/NX_Support_bot")
    NX_News_Trading = types.InlineKeyboardButton(
        text="NX News Trading 📰", url="https://t.me/NXNews_Trading_bot")
    NX_Echo = types.InlineKeyboardButton(
        text="NX Echo 🎙️", url="https://t.me/NX_Echo_bot")
    NX_Searcher = types.InlineKeyboardButton(
        text="NX Searcher AI 🔍", url="https://t.me/NX_Searcher_bot")
    keyboard.add(NX_Echo, NX_Louer)
    keyboard.add(NX_Support)
    keyboard.add(NX_Searcher)
    keyboard.add(NX_News_Trading)

    with open("NX Family.png", "rb") as photo:
        caption_message = (
            f"Доброго времени суток, <b>{message.from_user.first_name}</b>.👋\n"
            "👥 Тут собрано семейство наших NX Ботов, у каждого свои задачи и возможности.\n\n"
            "🔹 <b>NX Echo</b>🎙️ — Преобразовывает голосовые сообщения в текст, удобно и быстро.\n"
            "🔹 <b>NX Louer</b> 🌐 — Ваш многофункциональный помощник для выполнения задач.\n"
            "🔹 <b>NX Поддержка</b> ⚙️ — Техподдержка всегда на связи, чтобы помочь вам.\n"
            "🔹 <b>NX Searcher AI</b> 🔍 — Ответит на любов вопрос, сделан на основе AI.\n"
            "🔹 <b>NX News Trading</b> 📰 — Актуальные новости экономики и аналитика для трейдинга.\n\n"
            "В будущем список будет пополнятся !)\n<b>Выберите нужного бота из списка ниже и начните использовать их <u>прямо сейчас!</u> 🚀</b>"
        )
        bot.send_photo(message.chat.id, photo, caption_message, parse_mode="HTML", reply_markup=keyboard)



#=========================================NX семья группы конец======================================================================



#==================== рассылка ===============================================

@bot.message_handler(commands=["broadcast"])
def broadcast_message(message):
    user_id = str(message.from_user.id)

    # Проверяем, что команду отправил администратор
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "У вас нет прав для использования этой команды.")
        return

    # Получаем текст для рассылки
    broadcast_text = message.text.replace("/broadcast", "").strip()
    if not broadcast_text:
        bot.reply_to(message, "Пожалуйста, укажите текст сообщения после команды /broadcast.")
        return

    # Загружаем список пользователей из profiles.json
    with open("json/profiles.json", "r") as f:
        users = json.load(f)

    # Рассылаем сообщение каждому пользователю
    success_count = 0
    for user_data in users.values():
        try:
            bot.send_message(user_data["chat_id"], broadcast_text, parse_mode="HTML")
            success_count += 1
        except Exception as e:
            print(f"Ошибка отправки пользователю {user_data['user_id']}: {e}")

    bot.reply_to(message, f"Получили смс - {success_count} пользователей.")

#==================== рассылка конец ===============================================

#========================= фидбек тяжело ====================================



feedback_data = {}

@bot.message_handler(commands=['feedback'])
def feedback_start(message):
    user_id = str(message.from_user.id)
    user_id = message.chat.id
    # Создаем клавиатуру с категориями
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Ошибка", callback_data=f"feedback_category:Ошибка"),
        InlineKeyboardButton("Общее", callback_data=f"feedback_category:Общее")
    )
    markup.row(
        InlineKeyboardButton("Предложение", callback_data=f"feedback_category:Предложение")
    )
    feedback_data[user_id] = {}  # Инициализация данных для пользователя
    bot.send_message(user_id, "Выберите категорию вашего отзыва:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("feedback_category:"))
def feedback_category_selected(call):
    user_id = call.message.chat.id
    category = call.data.split(":")[1]
    feedback_data[user_id]['category'] = category  # Сохраняем категорию
    bot.send_message(user_id, f"Вы выбрали категорию: {category}. Теперь напишите текст отзыва.")
    
    # Переходим к ожиданию текста от пользователя
    bot.register_next_step_handler_by_chat_id(user_id, feedback_text_handler)

def feedback_text_handler(message):
    user_id = message.chat.id
    feedback_text = message.text.strip()  # Убираем лишние пробелы
    
    if feedback_text:
        feedback_data[user_id]['text'] = feedback_text  # Сохраняем текст отзыва

        # Загружаем данные пользователей из users.json
        try:
            with open('json/users.json', 'r') as f:
                users = json.load(f)  # Загружаем как список
        except (FileNotFoundError, json.JSONDecodeError):
            users = []  # Если файл отсутствует или пуст, создаем пустой список

        # Проверяем, есть ли пользователь в базе
        user = next((u for u in users if u["id"] == user_id), None)
        if user:
            user_feedback_count = user.get('feedback_count', 0) + 1
            user['feedback_count'] = user_feedback_count  # Обновляем количество отзывов
        else:
            user_name = message.chat.username or message.chat.first_name
            join_date = time.time()  # Текущая дата в формате UNIX
            users.append({
                "id": user_id,
                "name": user_name,
                "join_date": join_date,
                "feedback_count": 1
            })
            user_feedback_count = 1

        # Сохраняем обновленные данные в users.json
        with open('json/users.json', 'w') as f:
            json.dump(users, f, indent=4)
        
        # Генерируем уникальный ID отзыва
        feedback_id = str(uuid.uuid4())

        # Время по Киеву (UTC+3)
        kiev_tz = pytz.timezone('Europe/Kiev')
        time_in_kiev = datetime.now(kiev_tz)
        formatted_time = time_in_kiev.strftime('%Y-%m-%d %H:%M:%S')
        
        # Формируем информативное сообщение
        category = feedback_data[user_id].get('category', 'Не указана')
        user_name = message.chat.username or message.chat.first_name
        message_to_send = (
            f"<b>🚨 Новый отзыв</b>\n"
            f"<b>👤 Пользователь:</b> <b>{user_name}</b> (<code>{user_id}</code>)\n"
            f"<b>📅 Дата регистрации:</b> {datetime.fromtimestamp(user['join_date'], kiev_tz).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"<b>📈 Всего отзывов:</b> {user_feedback_count}\n"
            f"<b>⏰ Дата и время отзыва:</b> {formatted_time} (Киевское время)\n"
            f"<b>📂 Категория:</b> {category}\n"
            f"<b>🆔 ID отзыва:</b> {feedback_id}\n\n"
            f"<b>📝 Текст отзыва:</b>\n"
            f"<i>{feedback_text}</i>\n\n"
            f"<b>📞 Связь:</b> <a href='tg://user?id={user_id}'>Написать пользователю</a>\n"
            f"<b>👉 Примечание:</b> Ответ на отзыв будет отправлен в личные сообщения."
        )
        
        # Отправляем отзыв в группу
        bot.send_message(ADMIN_CHAT_ID, message_to_send, parse_mode='HTML')
        
        # Ответ пользователю
        bot.send_message(user_id, "Спасибо за ваш отзыв! Мы рассмотрим ваше предложение или ошибку.\n"
                                  "Если нужно, я свяжусь с вами лично.")
        
        # Удаляем временные данные пользователя
        feedback_data.pop(user_id, None)
    else:
        bot.reply_to(message, "Пожалуйста, напишите ваш отзыв после выбора категории.")


#========================= фидбек end ====================================




# Обработка сообщений в группе
@bot.message_handler(func=lambda message: message.chat.type in ["group", "supergroup"])
def handle_group_messages(message):
    group_name = message.chat.title
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    is_admin = 0

    # Определяем, является ли пользователь администратором
    try:
        admins = bot.get_chat_administrators(message.chat.id)
        if any(admin.user.id == user_id for admin in admins):
            is_admin = 1
    except Exception as e:
        print(f"Не удалось получить список администраторов: {e}")

    # Обновляем данные пользователя в базе данных группы
    update_group_user(group_name, user_id, username, is_admin)

if __name__ == "__main__":

    while True:
        try:
            print("Бот запустился")
            bot.polling(none_stop=True)  # Основной запуск polling
        except Exception as e:
            print(f"Ошибка: {e}. Переподключение через 5 секунд...")
            time.sleep(5)  # Ожидание перед повторной попыткой
        else:
            print("Бот успешно подключился и работает.")
            bot.send_message(ADMIN_CHAT_ID, "Бот успешно переподключился и работает.")  # Уведомление администратора