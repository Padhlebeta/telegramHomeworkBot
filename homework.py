import os
import datetime
import logging
import base64
import requests
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# === CONFIG ===
TELEGRAM_BOT_TOKEN = '7394874359:AAHlPYTl0LItIckjPKYOsEuxWPC1Dnx6aXg'
GOOGLE_SERVICE_JSON = 'service.json'
SHEET_ID = '1CK4OWg7fvFVDMaynhepMP7Nbyml4XpiniWZaL3MMDyI'
STUDENT_SHEET = 'Student Details'
SUBMISSION_SHEET = 'Submissions'
DRIVE_FOLDER_ID = '1GKH2FabFLkAODXh4fgm4vfxU0GV2Oa1q'
DOWNLOADS_DIR = "downloads"

SUBJECTS = ["Physics", "Chemistry", "Botany", "Zoology"]
TYPES = ["Homework", "Classnotes"]
CHAPTERS = {
    "Physics": [
        "Units and Measurements",
        "Mathematical Tools",
        "Motion in a Straight Line",
        "Motion in a Plane",
        "Laws of Motion",
        "Work, Energy and Power",
        "Centre of Mass & System of Particles",
        "Rotational motion",
        "Gravitation",
        "Mechanical Properties of Solids",
        "Mechanical Properties of Fluids",
        "Thermal Properties of Matter",
        "Kinetic Theory",
        "Thermodynamics",
        "Oscillations",
        "Waves"
    ],
    # Add more as needed
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

os.makedirs(DOWNLOADS_DIR, exist_ok=True)

creds = Credentials.from_service_account_file(GOOGLE_SERVICE_JSON, scopes=SCOPES)
gc = gspread.authorize(creds)
student_sheet = gc.open_by_key(SHEET_ID).worksheet(STUDENT_SHEET)
submission_sheet = gc.open_by_key(SHEET_ID).worksheet(SUBMISSION_SHEET)
drive_service = build('drive', 'v3', credentials=creds)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUBJECT, TYPE, CHAPTER, LECTURE, FILES = range(5)

# === Google Drive Folder Structure ===

def create_folder_if_not_exists(name, parent_id):
    results = drive_service.files().list(
        q=f"mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent_id}' in parents and trashed=false",
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    file_metadata = {
        'name': name,
        'parents': [parent_id],
        'mimeType': 'application/vnd.google-apps.folder'
    }
    folder = drive_service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')

def upload_file_to_drive(local_path, file_name, user_folder, type_folder, subject_folder, chapter_folder):
    parent_folder = create_folder_if_not_exists(user_folder, DRIVE_FOLDER_ID)
    type_f = create_folder_if_not_exists(type_folder, parent_folder)
    subject_f = create_folder_if_not_exists(subject_folder, type_f)
    chapter_f = create_folder_if_not_exists(chapter_folder, subject_f)
    file_metadata = {
        'name': file_name,
        'parents': [chapter_f]
    }
    media = MediaFileUpload(local_path, resumable=True)
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id,webViewLink',
        supportsAllDrives=True
    ).execute()
    return file.get('webViewLink')

# === Telegram Handlers ===

def verify_and_save_chat_id(student_id, chat_id):
    students = student_sheet.get_all_records()
    for idx, row in enumerate(students, start=2):
        if str(row['Student ID']) == str(student_id):
            student_sheet.update_cell(idx, 3, chat_id)
            return row
    return None

def get_student_by_chat_id(chat_id):
    students = student_sheet.get_all_records()
    for row in students:
        if str(row.get('Telegram Chat ID')) == str(chat_id):
            return row
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    student = get_student_by_chat_id(chat_id)
    if student:
        context.user_data["student"] = student
        reply_markup = ReplyKeyboardMarkup([[s] for s in SUBJECTS], one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Welcome back! Please select your subject:", reply_markup=reply_markup)
        return SUBJECT
    else:
        await update.message.reply_text("Welcome! Please enter your Student ID to continue.")
        return "WAITING_FOR_ID"

async def receive_student_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    student_id = update.message.text.strip()
    chat_id = update.message.chat_id
    student = verify_and_save_chat_id(student_id, chat_id)
    if student:
        context.user_data["student"] = student
        reply_markup = ReplyKeyboardMarkup([[s] for s in SUBJECTS], one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Registration successful! Please select your subject:", reply_markup=reply_markup)
        return SUBJECT
    else:
        await update.message.reply_text("❌ Invalid Student ID. Please try again or contact your teacher.")
        return "WAITING_FOR_ID"

async def choose_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = update.message.text.strip()
    if subject not in SUBJECTS:
        await update.message.reply_text("Invalid subject. Please select from the given options.")
        return SUBJECT
    context.user_data["subject"] = subject
    reply_markup = ReplyKeyboardMarkup([[t] for t in TYPES], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Select type (Homework/Classnotes):", reply_markup=reply_markup)
    return TYPE

async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upload_type = update.message.text.strip()
    if upload_type not in TYPES:
        await update.message.reply_text("Invalid option. Please select from the given options.")
        return TYPE
    context.user_data["type"] = upload_type
    chapters = CHAPTERS.get(context.user_data.get("subject", ""), [])
    reply_markup = ReplyKeyboardMarkup([[c] for c in chapters], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Select chapter:", reply_markup=reply_markup)
    return CHAPTER

async def choose_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapter = update.message.text.strip()
    context.user_data["chapter"] = chapter
    if context.user_data.get("type") == "Classnotes":
        await update.message.reply_text("Enter Lecture No (numeric):", reply_markup=ReplyKeyboardRemove())
        return LECTURE
    else:
        context.user_data["lecture"] = ""
        await update.message.reply_text(
            "Please upload your PDF or images (max 20 MB per file). Send all images/files, then press 'Submit'.",
            reply_markup=ReplyKeyboardMarkup([["Submit"]], resize_keyboard=True, one_time_keyboard=False)
        )
        return FILES

async def enter_lecture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lecture_no = update.message.text.strip()
    if not lecture_no.isdigit():
        await update.message.reply_text("Please enter a valid numeric lecture number.")
        return LECTURE
    context.user_data["lecture"] = lecture_no
    await update.message.reply_text(
        "Please upload your PDF or images (max 20 MB per file). Send all images/files, then press 'Submit'.",
        reply_markup=ReplyKeyboardMarkup([["Submit"]], resize_keyboard=True, one_time_keyboard=False)
    )
    return FILES

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file_id, file_name = None, None
        if update.message.document:
            if update.message.document.file_size > 20 * 1024 * 1024:
                await update.message.reply_text("File too large! Please send files below 20 MB.")
                return FILES
            file_id = update.message.document.file_id
            file_name = update.message.document.file_name
        elif update.message.photo:
            file_id = update.message.photo[-1].file_id
            file_name = f"{update.message.from_user.id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        else:
            await update.message.reply_text("Please upload a PDF or image only.")
            return FILES

        new_file = await context.bot.get_file(file_id)
        file_path = os.path.join(DOWNLOADS_DIR, file_name)
        await new_file.download_to_drive(file_path)

        student = context.user_data["student"]
        user_folder = student["Name"]
        type_folder = context.user_data["type"]
        subject_folder = context.user_data["subject"]
        chapter_folder = context.user_data["chapter"]

        drive_link = upload_file_to_drive(file_path, file_name, user_folder, type_folder, subject_folder, chapter_folder)
        context.user_data.setdefault("files", []).append(drive_link)
        os.remove(file_path)

        await update.message.reply_text("File received. You can send more or press 'Submit' when done.")
        return FILES
    except Exception as e:
        print(f"File receive error: {e}")
        await update.message.reply_text(f"File upload failed. Please try again. Error: {str(e)}")
        return FILES

async def submit_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = context.user_data.get("files", [])
    if not files:
        await update.message.reply_text("Please upload at least one file before submitting.")
        return FILES
    file_links_str = "\n".join(files)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    student = context.user_data.get("student")
    if not student:
        await update.message.reply_text("Session expired. Please /start again.")
        return ConversationHandler.END
    student_id = student.get("Student ID")
    student_name = student.get("Name")
    subject = context.user_data["subject"]
    upload_type = context.user_data["type"]
    chapter_name = context.user_data.get("chapter", "")
    lecture_no = context.user_data.get("lecture", "")
    chat_id = student.get("Telegram Chat ID")

    row = [
        timestamp,
        student_id,
        student_name,
        subject,
        upload_type,
        chapter_name,
        lecture_no,
        file_links_str,
        '',  # AI Reply
        '',  # Teacher Reply
        '',  # Send
        '',  # Sent?
        chat_id
    ]
    submission_sheet.append_row(row)
    summary = (
        f"Submission Recorded!\n"
        f"Name: {student_name}\n"
        f"Subject: {subject}\n"
        f"Type: {upload_type}\n"
        f"Chapter: {chapter_name}\n"
        f"Total files uploaded: {len(files)}"
    )
    await update.message.reply_text(
        summary,
        reply_markup=ReplyKeyboardMarkup([["Start New Submission"]], one_time_keyboard=True, resize_keyboard=True)
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Submission cancelled.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

async def menu_entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    student = get_student_by_chat_id(chat_id)
    if student:
        context.user_data["student"] = student
        reply_markup = ReplyKeyboardMarkup([[s] for s in SUBJECTS], one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Start new submission. Please select subject:", reply_markup=reply_markup)
        return SUBJECT
    else:
        await update.message.reply_text("Welcome! Please enter your Student ID to continue.")
        return "WAITING_FOR_ID"

def main():
    app = ApplicationBuilder()\
        .token(TELEGRAM_BOT_TOKEN)\
        .read_timeout(60)\
        .write_timeout(60)\
        .build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(
                filters.Regex(r"(?i)^(hi+|hello+|start+|Start New Submission)$"),
                menu_entrypoint
            )
        ],
        states={
            "WAITING_FOR_ID": [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_student_id)],
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_subject)],
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_type)],
            CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_chapter)],
            LECTURE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_lecture)],
            FILES: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, receive_file),
                MessageHandler(filters.Regex("^(Submit)$"), submit_files)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    app.add_handler(conv_handler)

    print("Bot running...")

    app.run_polling()

if __name__ == "__main__":
    main()