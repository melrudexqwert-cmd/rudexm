import os
import sqlite3
import socket
from datetime import datetime
from dotenv import load_dotenv
import telebot
from telebot import types, apihelper

# Загрузка настроек из config.env
load_dotenv("config.env")
TOKEN = os.getenv("BOT_TOKEN", "8500361446:AAHRnLXj4tB38a6HH3jBdHonaMCmv8BnWxE").strip()
ADMIN_ID_RAW = os.getenv("STAROSTA_ID", "1154469594").strip()
DB_NAME = os.getenv("DATABASE_NAME", "study_base.db").strip()
PROXY_URL = os.getenv("PROXY_URL", "").strip()

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    ADMIN_ID = 1154469594

# Настройка прокси для обхода блокировок
if PROXY_URL:
    apihelper.proxy = {"http": PROXY_URL, "https": PROXY_URL}
else:
    detected_port = None
    for test_port in [2081, 10809, 7890]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            try:
                s.connect(("127.0.0.1", test_port))
                detected_port = test_port
                break
            except: continue
    if detected_port:
        apihelper.proxy = {"http": f"http://127.0.0.1:{detected_port}", "https": f"http://127.0.0.1:{detected_port}"}

bot = telebot.TeleBot(TOKEN)
SUBJECTS = ["Математика", "Физика", "Информатика", "Русский язык", "Литература", "Иностранный язык", "История", "Обществознание", "ОБЗР", "Химия", "Биология", "География", "Родной язык", "Проектная деятельность"]
admin_states = {}

def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS group_users (user_id INTEGER PRIMARY KEY, username TEXT, registered_at TEXT);
        CREATE TABLE IF NOT EXISTS study_tasks (subject TEXT PRIMARY KEY, content TEXT DEFAULT '', updated_at TEXT DEFAULT '', due_date TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS task_materials (id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT, file_id TEXT, file_type TEXT, caption TEXT DEFAULT '');
        """)

def get_main_kb(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(*[types.KeyboardButton(s) for s in SUBJECTS])
    if int(uid) == ADMIN_ID:
        kb.add(types.KeyboardButton("Панель старосты"), types.KeyboardButton("Массовое оповещение"))
    return kb

def get_admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(*[types.KeyboardButton(f"Редактировать: {s}") for s in SUBJECTS])
    kb.add(types.KeyboardButton("Назад в главное меню"))
    return kb

@bot.message_handler(commands=['start'])
def cmd_start(m):
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO group_users VALUES (?, ?, ?)", (m.from_user.id, m.from_user.username or "", datetime.now().strftime("%d.%m.%Y %H:%M")))
    bot.send_message(m.chat.id, "Информационный сервис группы 11.02.18.\nВыберите дисциплину для получения задания:", reply_markup=get_main_kb(m.from_user.id))

@bot.message_handler(func=lambda m: m.text == "Панель старосты")
def cmd_admin(m):
    if int(m.from_user.id) == ADMIN_ID:
        bot.send_message(m.chat.id, "Выберите дисциплину для редактирования:", reply_markup=get_admin_kb())

@bot.message_handler(func=lambda m: m.text == "Назад в главное меню")
def cmd_back(m):
    admin_states.pop(m.from_user.id, None)
    bot.send_message(m.chat.id, "Главное меню открыто.", reply_markup=get_main_kb(m.from_user.id))

@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() == "массовое оповещение")
def cmd_broadcast(m):
    if int(m.from_user.id) != ADMIN_ID: return
    admin_states[m.from_user.id] = {'step': 'broadcast'}
    bot.send_message(m.chat.id, "Введите текст сообщения для рассылки (для отмены напишите 'отмена'):", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.text in SUBJECTS)
def view_task(m):
    subject = m.text
    with get_db() as conn:
        t = conn.execute("SELECT * FROM study_tasks WHERE subject=?", (subject,)).fetchone()
        files = conn.execute("SELECT * FROM task_materials WHERE subject=?", (subject,)).fetchall()

    if not t and not files:
        bot.send_message(m.chat.id, f"Дисциплина: {subject}\nИнформация отсутствует.", reply_markup=get_main_kb(m.from_user.id))
        return

    header = f"📍 Дисциплина: {subject}\n"
    if t:
        if t['updated_at']: header += f"📅 Дата обновления: {t['updated_at']}\n"
        if t['due_date']: header += f"⌛ Срок сдачи: {t['due_date']}\n"
        if t['content']: header += f"\nЗадание:\n{t['content']}"
    
    bot.send_message(m.chat.id, header)

    for f in files:
        cap = f['caption'] or ""
        if f['file_type'] == 'photo': bot.send_photo(m.chat.id, f['file_id'], caption=cap)
        else: bot.send_document(m.chat.id, f['file_id'], caption=cap)

@bot.message_handler(func=lambda m: m.text.startswith("Редактировать: "))
def edit_start(m):
    if int(m.from_user.id) != ADMIN_ID: return
    sub = m.text.replace("Редактировать: ", "").strip()
    admin_states[m.from_user.id] = {'sub': sub, 'step': 'dates'}
    bot.send_message(m.chat.id, f"Дисциплина: {sub}\nВведите даты в формате: Дата обновления | Срок сдачи\nПример: 05.09 | 10.09", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(content_types=['text', 'photo', 'document'])
def handle_data(m):
    uid = m.from_user.id
    if uid not in admin_states: return
    state = admin_states[uid]

    if m.content_type == 'text' and m.text.lower() == 'отмена':
        admin_states.pop(uid, None)
        bot.send_message(m.chat.id, "Отменено.", reply_markup=get_admin_kb())
        return

    if state.get('step') == 'broadcast':
        admin_states.pop(uid, None)
        broadcast_text = f"Общая информация:\n\n{m.text}"
        with get_db() as conn:
            users = conn.execute("SELECT user_id FROM group_users").fetchall()
        count = 0
        for u in users:
            try: bot.send_message(u['user_id'], broadcast_text); count += 1
            except: pass
        bot.send_message(m.chat.id, f"Рассылка завершена. Доставлено: {count}", reply_markup=get_main_kb(uid))
        return

    sub = state['sub']

    if m.content_type == 'text' and m.text.lower() == 'готово':
        admin_states.pop(uid, None)
        bot.send_message(m.chat.id, f"Задание по дисциплине {sub} сохранено.", reply_markup=get_admin_kb())
        return

    if state['step'] == 'dates':
        if "|" not in m.text:
            bot.send_message(m.chat.id, "Ошибка! Используй разделитель |. Пример: 05.09 | 12.09")
            return
        upd, due = [p.strip() for p in m.text.split("|", 1)]
        with get_db() as conn:
            conn.execute("INSERT INTO study_tasks (subject, updated_at, due_date, content) VALUES (?, ?, ?, '') ON CONFLICT(subject) DO UPDATE SET updated_at=excluded.updated_at, due_date=excluded.due_date", (sub, upd, due))
            conn.execute("DELETE FROM task_materials WHERE subject=?", (sub,))
        state['step'] = 'content'
        bot.send_message(m.chat.id, "Даты сохранены. Теперь отправляй текст задания, фото или файлы по одному. В конце напиши 'готово'.")
        return

    with get_db() as conn:
        if m.content_type == 'text':
            conn.execute("UPDATE study_tasks SET content=? WHERE subject=?", (m.text, sub))
            bot.send_message(m.chat.id, "Текст добавлен. Можешь кинуть файл или написать 'готово'.")
        elif m.content_type == 'photo':
            conn.execute("INSERT INTO task_materials (subject, file_id, file_type, caption) VALUES (?, ?, 'photo', ?)", (sub, m.photo[-1].file_id, m.caption or ""))
            bot.send_message(m.chat.id, "Фото прикреплено. Отправь еще или напиши 'готово'.")
        elif m.content_type == 'document':
            conn.execute("INSERT INTO task_materials (subject, file_id, file_type, caption) VALUES (?, ?, 'doc', ?)", (sub, m.document.file_id, m.caption or ""))
            bot.send_message(m.chat.id, "Файл прикреплен. Отправь еще или напиши 'готово'.")

if __name__ == "__main__":
    init_db()
    print("[СЕРВИС] Бот старосты запущен и готов к работе.")
    bot.infinity_polling(skip_pending=True)
