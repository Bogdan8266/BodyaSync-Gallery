# server.py - Фінальна версія з отриманням ОРИГІНАЛЬНОЇ дати

import os
import shutil
import json
import time
import random
import threading
import uuid
import io
import traceback
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form, Body, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from PIL import Image, ImageDraw, ImageFont
import ffmpeg
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata
import requests
from gradio_client import Client as GradioClient, file as gradio_file

try:
    # Новий спосіб (Pillow >= 9.1.0)
    LANCZOS_FILTER = Image.Resampling.LANCZOS
    BICUBIC_FILTER = Image.Resampling.BICUBIC
except AttributeError:
    # Старий спосіб
    print("⚠️ Ваша версія Pillow застаріла. Використовуються старі константи. Рекомендується оновити: pip install --upgrade Pillow")
    LANCZOS_FILTER = Image.LANCZOS
    BICUBIC_FILTER = Image.BICUBIC
# ======================================================================
# БЛОК 1: ЗАГАЛЬНА КОНФІГУРАЦІЯ
# ======================================================================
app = FastAPI(title="My Personal Cloud API")

# --- Шляхи ---
# Використовуємо абсолютні шляхи для надійності
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
STORAGE_PATH = os.path.join(SCRIPT_DIR, "storage")
ASSETS_FOLDER = os.path.join(SCRIPT_DIR, "assets")

ORIGINALS_PATH = os.path.join(STORAGE_PATH, "originals")
THUMBNAILS_PATH = os.path.join(STORAGE_PATH, "thumbnails")
MEMORIES_PATH = os.path.join(STORAGE_PATH, "memories")
MUSIC_FOLDER = os.path.join(STORAGE_PATH, "music")

METADATA_FILE = os.path.join(STORAGE_PATH, "metadata.json")
SETTINGS_FILE = os.path.join(STORAGE_PATH, "settings.json")
FRAMES_CONFIG_FILE = os.path.join(ASSETS_FOLDER, "frames_config.json")
FONT_FILE = os.path.join(ASSETS_FOLDER, "Roboto-Regular.ttf")

for path in [ORIGINALS_PATH, THUMBNAILS_PATH, MEMORIES_PATH, MUSIC_FOLDER, ASSETS_FOLDER]:
    os.makedirs(path, exist_ok=True)

# --- Налаштування AI ---
HF_SPACE_CAPTION_URL = "bodyapromax2010/bodyasync-image-caption"
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL_NAME = "gemma3:4b"
HF_SPACE_COLLAGE_URL = "bodyapromax2010/black-forest-labs-FLUX.1-dev2"

# --- Словник для відстеження асинхронних задач ---
TASKS = {}
try:
    FONT = ImageFont.truetype(FONT_FILE, 30)
except IOError:
    FONT = ImageFont.load_default()

# --- Функції для роботи з метаданими (без змін) ---
# ... (load_metadata, save_metadata) ...
def load_metadata():
    if not os.path.exists(METADATA_FILE): return {}
    try:
        with open(METADATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return {}

def save_metadata(data):
    with open(METADATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)


# --- Функції для створення прев'ю (без змін) ---
# ... (create_photo_thumbnail, create_video_thumbnail) ...
def create_photo_thumbnail(image_path: str, thumbnail_path: str):
    try:
        settings = load_settings()
        size = (settings.get("preview_size", 400), settings.get("preview_size", 400))
        quality = settings.get("preview_quality", 80)
        with Image.open(image_path) as img:
            if img.format and img.format.upper() in ['HEIC', 'HEIF']:
                from pillow_heif import register_heif_opener
                register_heif_opener()
                img = Image.open(image_path)
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            img.thumbnail(size)
            img.save(thumbnail_path, "JPEG", quality=quality, optimize=True)
        return True
    except Exception as e:
        print(f"❌ Помилка фото-прев'ю для {os.path.basename(image_path)}: {e}")
        return False

def create_video_thumbnail(video_path: str, thumbnail_path: str):
    try:
        settings = load_settings()
        size = settings.get("preview_size", 400)
        (ffmpeg.input(video_path, ss=1).filter('scale', size, -1).output(thumbnail_path, vframes=1).overwrite_output().run(capture_stdout=True, capture_stderr=True))
        return True
    except ffmpeg.Error as e:
        print(f"❌ Помилка FFmpeg для {os.path.basename(video_path)}: {e.stderr.decode()}")
        return False


# =================================================================
# НОВА ФУНКЦІЯ ДЛЯ ОТРИМАННЯ ОРИГІНАЛЬНОЇ ДАТИ
# =================================================================
def get_original_date(file_path: str) -> float:
    """
    Намагається отримати оригінальну дату створення з метаданих файлу.
    Якщо не вдається, повертає дату зміни файлу в системі.
    """
    try:
        # Для фотографій (JPEG/HEIC)
        if file_path.lower().endswith(('.jpg', '.jpeg', '.heic')):
            with Image.open(file_path) as img:
                exif_data = img._getexif()
                if exif_data:
                    for tag, value in exif_data.items():
                        tag_name = TAGS.get(tag, tag)
                        if tag_name == 'DateTimeOriginal':
                            # Формат 'YYYY:MM:DD HH:MM:SS'
                            dt_obj = datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                            print(f"✅ Знайдено дату в EXIF: {dt_obj}")
                            return dt_obj.timestamp()
    except Exception:
        pass # Просто ігноруємо помилки читання EXIF

    try:
        # Для відео (MP4/MOV) за допомогою Hachoir
        parser = createParser(file_path)
        if parser:
            with parser:
                metadata = extractMetadata(parser)
            if metadata and metadata.has('creation_date'):
                dt_obj = metadata.get('creation_date')
                print(f"✅ Знайдено дату в метаданих відео: {dt_obj}")
                return dt_obj.timestamp()
    except Exception:
        pass # Ігноруємо помилки Hachoir

    # Якщо нічого не знайдено, повертаємо час останньої зміни файлу
    fallback_timestamp = os.path.getmtime(file_path)
    print(f"⚠️ Не вдалося знайти оригінальну дату, використовую fallback: {datetime.fromtimestamp(fallback_timestamp)}")
    return fallback_timestamp


def get_raw_english_description(image_path):
    print(f"   - Крок А: Аналізую фото '{os.path.basename(image_path)}'...")
    try:
        client = GradioClient(HF_SPACE_CAPTION_URL)
        result = client.predict(gradio_file(image_path), api_name="/predict")
        print(result)
        return (result[0] if isinstance(result, (list, tuple)) else result).strip()
        
    except Exception as e:
        print(f"   - ❌ Помилка аналізу на HF: {e}"); return None

def create_warm_caption_from_description(english_description, date_info):
    prompt_text = f"""
    Ви створюєте підпис для спогаду. Ваше завдання — створити підпис для фотоспогадів. Він має бути довжиною 15-25 слів. Ви повинні створити його на основі технічного опису зображення. Технічний опис зображення — це все, що зображено на фотографії. Ви повинні зробити його текстом спогаду, але так, щоб була конкретика щодо того, що саме є в технічному описі зображення: теплий та ностальгічний підпис українською мовою.

Використовуйте цю інформацію:
- Технічний опис: "{english_description}"
- Часовий контекст: "{date_info}"

Зробіть так, щоб це звучало як теплий спогад (1 речення) 15-25 слів. Пишіть ТІЛЬКИ останній підпис українською мовою.

Важливо:
- Пишіть лише останній підпис українською мовою.
- Не перекладайте сам опис.
- Не додавайте жодних додаткових коментарів, приміток чи вітань.
- Уникайте загальних фраз на кшталт "який гарний день". Будьте конкретними щодо змісту.
- Якщо в описі згадується об'єкт (наприклад, графічний процесор, старий телефон, люди, кімната, будь-які речі або міська пам'ятка), зосередьте підпис на ньому з теплим особистим відтінком.
- Якщо опис описує людей, тварин або місця, передайте атмосферу та емоції того моменту.
- Викликає емоційність та ностальгію, ніби людина згадує саме цей момент або об'єкт.
Використовуйте наступний опис фотографії: "{english_description}" та інформацію про дату "{date_info}". 
    """
    payload = {"model": OLLAMA_MODEL_NAME, "prompt": prompt_text, "stream": False}
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        caption = response.json().get("response", "").strip().strip('"').strip("'")
        return caption if caption else "Чудовий спогад!"
    except requests.exceptions.RequestException as e:
        print(f"   - ❌ Помилка Ollama: {e}"); return "Помилка генерації підпису"

# ... і решта твоїх функцій (я їх не буду повторювати) ...
# Ми припускаємо, що всі твої функції для створення колажу тут присутні

# <--- НОВЕ: Функція-заглушка для вибору музики
def select_random_music():
    """Вибирає випадковий трек, використовуючи абсолютний шлях."""
    try:
        music_folder_path = os.path.join(SCRIPT_DIR, MUSIC_FOLDER)
        print(f"🔍 Шукаю музику в: '{music_folder_path}'")
        if not os.path.exists(music_folder_path) or not os.listdir(music_folder_path):
            print("⚠️ Папка з музикою порожня."); return None
        music_files = [f for f in os.listdir(music_folder_path) if f.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a'))]
        if not music_files:
            print("❌ Не знайдено підходящих аудіофайлів."); return None
        chosen_file = random.choice(music_files)
        print(f"🎵 Обрано музичний трек: {chosen_file}"); return chosen_file
    except Exception as e:
        print(f"🛑 Помилка пошуку музики: {e}"); return None

def create_memory_story_worker(task_id: str):
    """Головний процес, що керує всім."""
    try:
        TASKS[task_id] = {"status": "processing", "message": "Selecting photos..."}
        all_images = [f for f in os.listdir(ORIGINALS_PATH) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if len(all_images) < 2: raise Exception("Потрібно мінімум 2 фотографії.")
        
        num_to_find = random.randint(2, min(5, len(all_images)))
        selected_memories, available_images = [], all_images.copy()

        while len(selected_memories) < num_to_find and available_images:
            image_name = random.choice(available_images)
            available_images.remove(image_name)
            image_path = os.path.join(ORIGINALS_PATH, image_name)
            raw_description = get_raw_english_description(image_path)
            if raw_description and is_good_memory(raw_description):
                date_info = f"зроблено {datetime.fromtimestamp(os.path.getmtime(image_path)).strftime('%d %B, %Y')}"
                final_caption = create_warm_caption_from_description(raw_description, date_info)
                if final_caption:
                    selected_memories.append({"filename": image_name, "caption": final_caption})

        if not selected_memories: raise Exception("Не вдалося знайти підходящі фото.")
        TASKS[task_id]["message"] = "Creating collage..."
        
        collage_filename = f"collage_{task_id}.png"
        collage_output_path = os.path.join(MEMORIES_PATH, collage_filename)
        
        # Викликаємо функцію, що створює колаж
        collage_created = create_collage_and_save(selected_memories, collage_output_path)
        if not collage_created:
             # Можна обробити помилку, але поки просто продовжимо
             print("⚠️ Створення колажу не вдалося, спогад буде без нього.")

        TASKS[task_id]["message"] = "Finalizing..."
        music_file = select_random_music()
        
        story_items = [{"type": "image", "imageUrl": f"/original/{m['filename']}", "caption": m['caption']} for m in selected_memories]
        if collage_created:
            story_items.append({"type": "collage", "imageUrl": f"/memories/{collage_filename}", "caption": "Ваші найкращі моменти разом!"})

        final_result = {
            "id": task_id,
            "title": f"Спогад від {datetime.now().strftime('%d %B')}",
            "musicUrl": f"/music/{music_file}" if music_file else None,
            "items": story_items,
            # Додаємо обкладинку для каруселі в Flutter
            "coverImageUrl": f"/memories/{collage_filename}" if collage_created else f"/original/{selected_memories[0]['filename']}"
        }
        
        result_filepath = os.path.join(MEMORIES_PATH, f"{task_id}.json")
        with open(result_filepath, 'w', encoding='utf-8') as f: json.dump(final_result, f, ensure_ascii=False, indent=2)

        TASKS[task_id] = {"status": "complete", "result": final_result}
        print(f"[{task_id}] ✅ Спогад успішно створено!")

    except Exception as e:
        print(f"[{task_id}] 🛑 Помилка під час генерації: {e}")
        traceback.print_exc()
        TASKS[task_id] = {"status": "failed", "error": str(e)}


# server.py

# ... (всі твої імпорти та функції-хелпери) ...
# server.py

# ... (інші функції в цьому блоці) ...
# def apply_frame(...): ...

# <--- ВСТАВ ЦЕЙ БЛОК ПОВНІСТЮ
# --- Повний набір функцій для генерації фону ---
def get_prompt_filmstrip_abstraction(c): return (f"A minimalist abstract background, vintage 35mm filmstrip, soft gradients, {random.choice(c)} and pastel palette, light leaks, cinematic, fine grain, 8k.")
def get_prompt_warm_retro_sky(c): return (f"A dreamy, retro-style abstract background, 70s sunset, warm {random.choice(c)} palette, smooth gradients, hazy clouds, sunburst effect, nostalgic film grain, ethereal, high resolution.")
def get_prompt_futuristic_geometry(c): return (f"A modern, tech-style abstract background, clean layered dynamic curved and straight lines, monochrome base with sharp vibrant {random.choice(c)} accents, holographic elements, smooth highlights, minimalist vector art, Behance HD.")
def get_prompt_soft_blobs(c): return (f"A serene minimalist organic background, large soft amorphous shapes like liquid ink bleeds, blended with smooth gradients in a soft {random.choice(c)} palette, subtle paper texture, bokeh effect, calm, high quality.")
def get_prompt_brushstrokes(c): return (f"An artistic abstract background, modern canvas painting style, energetic broad textured brushstrokes, calligraphic linear patterns, harmonious {random.choice(c)} scheme, light canvas texture, balanced composition.")
def get_prompt_symbolic_shapes(c): return (f"A clean modern graphic design background, soft gradient {random.choice(c)} base, simple icon-like vector shapes (thin circles, planet outlines), sparsely placed with gentle drop shadows, fine grain texture, rule of thirds.")
def get_prompt_abstract_flowers(c): return (f"A soft pastel abstract background, delicate minimalist botanical illustrations, simple line-art flower silhouettes, smoothly blended {random.choice(c)} gradient, subtle grain, ethereal glow for depth.")
def get_prompt_abstract_windows(c): return (f"A minimal architectural-style abstract background, layered framed square and rectangle shapes of varying opacities, on a smooth gradient {random.choice(c)} base, soft shadows, light grain, sharp highlights on edges.")
def get_prompt_watercolor_texture(c): return (f"A beautiful watercolor-style abstract background, heavily blended textured brushstrokes in {random.choice(c)} palette, organic gradient transitions, visible high-quality paper grain, realistic water smudges, artistic.")
def get_prompt_lines_and_splatters(c): return (f"A minimal abstract composition, modern art style, random organic ink splatters, irregular hand-drawn stripes, on a soft off-white paper texture, limited palette of black, gold, and one accent color (teal or rust), delicate grain.")

BACKGROUND_STRATEGIES = [
    get_prompt_filmstrip_abstraction, get_prompt_warm_retro_sky, get_prompt_futuristic_geometry, 
    get_prompt_soft_blobs, get_prompt_brushstrokes, get_prompt_symbolic_shapes, 
    get_prompt_abstract_flowers, get_prompt_abstract_windows, get_prompt_watercolor_texture, 
    get_prompt_lines_and_splatters
]
# --- Кінець блоку функцій для фону ---

# ... (далі йдуть інші твої функції, такі як generate_background_with_hf_space)
def generate_background_with_hf_space(prompt):
    print(f"🎨 Генеруємо фон для колажу...")
    try:
        client = GradioClient(HF_SPACE_COLLAGE_URL)
        result = client.predict(prompt, "low quality, blurry, text, watermark, logo, ugly", api_name="/infer")
        return Image.open(result[0]).resize((1080, 1920), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"🛑 Помилка генерації фону: {e}. Створюю запасний фон."); return Image.new("RGB", (1080, 1920), (128, 0, 128))

def check_overlap(box1, box2, max_overlap_ratio=0.15):
    inter_left, inter_top = max(box1[0], box2[0]), max(box1[1], box2[1])
    inter_right, inter_bottom = min(box1[2], box2[2]), min(box1[3], box2[3])
    if inter_right > inter_left and inter_bottom > inter_top:
        inter_area = (inter_right - inter_left) * (inter_bottom - inter_top)
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        if box1_area > 0 and inter_area / box1_area > max_overlap_ratio: return True
    return False
# <--- НОВА, ПРАВИЛЬНА ФУНКЦІЯ ДЛЯ СТВОРЕННЯ КОЛАЖУ
# server.py
def apply_frame(photo, frame_path, config):
    try:
        frame_template = Image.open(frame_path).convert("RGBA")
        params = config.get(os.path.basename(frame_path), {})
        scale = params.get("scale", 1.0)
        scale_x, scale_y = params.get("scale_x"), params.get("scale_y")
        if scale_x is not None and scale_y is not None: new_frame_width, new_frame_height = int(photo.width * scale_x), int(photo.height * scale_y)
        else: new_frame_width, new_frame_height = int(photo.width * scale), int(photo.height * scale)
        resized_frame = frame_template.resize((new_frame_width, new_frame_height), Image.Resampling.LANCZOS)
        result_canvas = Image.new("RGBA", resized_frame.size, (0, 0, 0, 0)) 
        photo_pos_x = (resized_frame.width - photo.width) // 2 + params.get("offset_x", 0)
        photo_pos_y = (resized_frame.height - photo.height) // 2 + params.get("offset_y", 0)
        result_canvas.paste(photo, (photo_pos_x, photo_pos_y))
        result_canvas.paste(resized_frame, (0, 0), resized_frame)
        return result_canvas
    except Exception as e:
        print(f"⚠️ Помилка рамки: {e}"); return photo
def is_good_memory(caption):
    if not caption: return False
    stop_words = ["screenshot", "text", "document", "chart", "diagram", "interface", "code"]
    return not any(word in caption.lower() for word in stop_words)


def get_dominant_color(image_path):
    img = Image.open(image_path).resize((1, 1), Image.Resampling.LANCZOS)
    return f"#{img.getpixel((0, 0))[0]:02x}{img.getpixel((0, 0))[1]:02x}{img.getpixel((0, 0))[2]:02x}"




# server.py

# ... (інші функції в цьому блоці) ...
# def apply_frame(...): ...

# <--- ВСТАВ ЦЕЙ БЛОК ПОВНІСТЮ
# --- Повний набір функцій для генерації фону ---
def get_prompt_filmstrip_abstraction(c): return (f"A minimalist abstract background, vintage 35mm filmstrip, soft gradients, {random.choice(c)} and pastel palette, light leaks, cinematic, fine grain, 8k.")
def get_prompt_warm_retro_sky(c): return (f"A dreamy, retro-style abstract background, 70s sunset, warm {random.choice(c)} palette, smooth gradients, hazy clouds, sunburst effect, nostalgic film grain, ethereal, high resolution.")
def get_prompt_futuristic_geometry(c): return (f"A modern, tech-style abstract background, clean layered dynamic curved and straight lines, monochrome base with sharp vibrant {random.choice(c)} accents, holographic elements, smooth highlights, minimalist vector art, Behance HD.")
def get_prompt_soft_blobs(c): return (f"A serene minimalist organic background, large soft amorphous shapes like liquid ink bleeds, blended with smooth gradients in a soft {random.choice(c)} palette, subtle paper texture, bokeh effect, calm, high quality.")
def get_prompt_brushstrokes(c): return (f"An artistic abstract background, modern canvas painting style, energetic broad textured brushstrokes, calligraphic linear patterns, harmonious {random.choice(c)} scheme, light canvas texture, balanced composition.")
def get_prompt_symbolic_shapes(c): return (f"A clean modern graphic design background, soft gradient {random.choice(c)} base, simple icon-like vector shapes (thin circles, planet outlines), sparsely placed with gentle drop shadows, fine grain texture, rule of thirds.")
def get_prompt_abstract_flowers(c): return (f"A soft pastel abstract background, delicate minimalist botanical illustrations, simple line-art flower silhouettes, smoothly blended {random.choice(c)} gradient, subtle grain, ethereal glow for depth.")
def get_prompt_abstract_windows(c): return (f"A minimal architectural-style abstract background, layered framed square and rectangle shapes of varying opacities, on a smooth gradient {random.choice(c)} base, soft shadows, light grain, sharp highlights on edges.")
def get_prompt_watercolor_texture(c): return (f"A beautiful watercolor-style abstract background, heavily blended textured brushstrokes in {random.choice(c)} palette, organic gradient transitions, visible high-quality paper grain, realistic water smudges, artistic.")
def get_prompt_lines_and_splatters(c): return (f"A minimal abstract composition, modern art style, random organic ink splatters, irregular hand-drawn stripes, on a soft off-white paper texture, limited palette of black, gold, and one accent color (teal or rust), delicate grain.")

BACKGROUND_STRATEGIES = [
    get_prompt_filmstrip_abstraction, get_prompt_warm_retro_sky, get_prompt_futuristic_geometry, 
    get_prompt_soft_blobs, get_prompt_brushstrokes, get_prompt_symbolic_shapes, 
    get_prompt_abstract_flowers, get_prompt_abstract_windows, get_prompt_watercolor_texture, 
    get_prompt_lines_and_splatters
]
# --- Кінець блоку функцій для фону ---

# ... (далі йдуть інші твої функції, такі як generate_background_with_hf_space)



def create_collage_and_save(selected_memories: list, output_path: str):
    """Приймає ВЖЕ ВІДІБРАНИЙ список фото і шлях для збереження."""
    print("🖼️ Починаємо створення колажу...")
    try:
        selected_filenames = [m['filename'] for m in selected_memories]
        
        # <--- КЛЮЧОВЕ ВИПРАВЛЕННЯ: Використовуємо твою логіку
        # 1. Отримуємо домінантні кольори з фото
        print("   - Аналізуємо домінантні кольори...")
        dominant_colors = [get_dominant_color(os.path.join(ORIGINALS_PATH, name)) for name in selected_filenames]
        
        # 2. Випадковим чином обираємо ОДНУ З ТВОЇХ функцій-стратегій
        print("   - Вибираємо стратегію для фону...")
        chosen_strategy = random.choice(BACKGROUND_STRATEGIES)
        
        # 3. Викликаємо обрану функцію, передаючи їй кольори, щоб отримати унікальний промпт
        prompt = chosen_strategy(dominant_colors)
        print(f"   - Згенеровано промпт для фону: \"{prompt[:80]}...\"")
        
        # 4. Генеруємо фон за цим промптом
        collage = generate_background_with_hf_space(prompt).convert("RGBA")
        
        # --- Решта твого коду для розміщення фото, рамок і т.д. залишається тут ---
        frames_folder = os.path.join(ASSETS_FOLDER, "frames")
        frames_config = {}
        if os.path.exists(FRAMES_CONFIG_FILE):
             with open(FRAMES_CONFIG_FILE, 'r') as f: frames_config = json.load(f)

        chosen_frame_path = None
        if os.path.exists(frames_folder):
            frame_files = [f for f in os.listdir(frames_folder) if f.lower().endswith('.png') and f in frames_config]
            if frame_files: chosen_frame_path = os.path.join(frames_folder, random.choice(frame_files))

        PHOTO_SIZES_BY_COUNT = {2: 800, 3: 650, 4: 550, 5: 480}
        target_size = PHOTO_SIZES_BY_COUNT.get(len(selected_filenames), 600)
        
        placed_boxes = []
        for filename in selected_filenames:
            photo_path = os.path.join(ORIGINALS_PATH, filename)
            if not os.path.exists(photo_path):
                print(f"⚠️ Фото {filename} не знайдено, пропускаємо.")
                continue

            photo = Image.open(photo_path).convert("RGBA")
            photo.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
            
            photo_with_frame = apply_frame(photo, chosen_frame_path, frames_config) if chosen_frame_path else photo
            rotated_photo = photo_with_frame.rotate(random.randint(-20, 20), expand=True, resample=Image.BICUBIC)
            
            is_placed = False
            for _ in range(500):
                margin = 30 
                x = random.randint(margin, collage.width - rotated_photo.width - margin)
                y = random.randint(margin, collage.height - rotated_photo.height - margin)
                new_box = (x, y, x + rotated_photo.width, y + rotated_photo.height)
                if not any(check_overlap(new_box, box) for box in placed_boxes):
                    placed_boxes.append(new_box)
                    collage.paste(rotated_photo, (x, y), rotated_photo)
                    is_placed = True
                    break
            if not is_placed: print(f"⚠️ Не вдалося знайти місце для {filename}")

        collage.save(output_path)
        print(f"✅ Колаж успішно збережено у: {output_path}")
        return True

    except Exception as e:
        print(f"🛑🛑🛑 КРИТИЧНА ПОМИЛКА під час створення колажу!")
        traceback.print_exc()
        return False
# ... (решта твоїх функцій, напр. select_random_music)

# =================================================================
# ОНОВЛЕНІ ГОЛОВНІ ЕНДПОІНТИ
# =================================================================
# server.py

# ... (всі імпорти та функції-хелпери без змін) ...

# <--- ЗМІНА: Модифікуємо існуючий ендпоінт
@app.get("/files/list/")
async def list_files_in_path(path: str = ""):
    base_path = os.path.abspath(ORIGINALS_PATH)
    requested_path = os.path.abspath(os.path.join(base_path, path))

    if not requested_path.startswith(base_path):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isdir(requested_path):
        raise HTTPException(status_code=404, detail="Directory not found")

    items = []
    # <--- ЗМІНА: Завантажуємо метадані, щоб знати, які файли є частиною галереї
    gallery_metadata = load_metadata()
    gallery_files = set(gallery_metadata.keys()) # Використовуємо set для швидкого пошуку

    # Додаємо віртуальну папку "Галерея" тільки в корені
    if not path:
        items.append({"name": "Галерея", "type": "virtual_gallery"})

    try:
        for item_name in os.listdir(requested_path):
            item_path = os.path.join(requested_path, item_name)
            
            # <--- ЗМІНА: Фільтруємо файли, які є частиною галереї
            # Показуємо їх тільки якщо ми НЕ в кореневій папці
            if os.path.isfile(item_path) and item_name in gallery_files and not path:
                continue # Пропускаємо файли галереї в кореневій директорії

            if os.path.isdir(item_path):
                items.append({"name": item_name, "type": "directory"})
            else:
                size = os.path.getsize(item_path)
                items.append({"name": item_name, "type": "file", "size": size})
        
        # Сортування залишається тим самим
        items.sort(key=lambda x: (
            0 if x['type'] == 'virtual_gallery' else 1 if x['type'] == 'directory' else 2,
            x['name'].lower()
        ))
        return JSONResponse(content={"path": path, "items": items})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ... (решта коду сервера без змін) ...

@app.post("/files/create_folder/")
async def create_folder(path: str = Form(...), folder_name: str = Form(...)):
    base_path = os.path.abspath(ORIGINALS_PATH)
    target_dir_path = os.path.abspath(os.path.join(base_path, path))

    if not target_dir_path.startswith(base_path):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isdir(target_dir_path):
        raise HTTPException(status_code=404, detail="Parent directory not found")

    new_folder_path = os.path.join(target_dir_path, folder_name)
    if os.path.exists(new_folder_path):
        raise HTTPException(status_code=409, detail="Folder with this name already exists")
    
    try:
        os.makedirs(new_folder_path)
        return {"status": "success", "message": f"Folder '{folder_name}' created."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# <--- НОВЕ: Ендпоінт для завантаження файлу в конкретну папку
@app.post("/files/upload_to_path/")
async def upload_file_to_path(file: UploadFile = File(...), path: str = Form("")):
    base_path = os.path.abspath(ORIGINALS_PATH)
    target_dir_path = os.path.abspath(os.path.join(base_path, path))

    if not target_dir_path.startswith(base_path):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isdir(target_dir_path):
        raise HTTPException(status_code=404, detail="Target directory not found")

    file_location = os.path.join(target_dir_path, file.filename)
    
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)

    # Якщо це медіафайл, оновлюємо метадані для галереї
    file_extension = os.path.splitext(file.filename.lower())[1]
    if file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov']:
        # Викликаємо логіку з твого головного ендпоінта /upload/
        # (це спрощення, в ідеалі цю логіку треба винести в окрему функцію)
        thumbnail_filename = f"{os.path.splitext(file.filename)[0]}.jpg"
        thumbnail_path = os.path.join(THUMBNAILS_PATH, thumbnail_filename)
        metadata = load_metadata()
        metadata[file.filename] = {
            "type": "image" if file_extension in ['.jpg', '.jpeg', '.png', '.gif'] else "video",
            "thumbnail": thumbnail_filename,
            "timestamp": get_original_date(file_location)
        }
        save_metadata(metadata)
        if metadata[file.filename]["type"] == "image":
             create_photo_thumbnail(file_location, thumbnail_path)
        else:
             create_video_thumbnail(file_location, thumbnail_path)


    return {"status": "success", "filename": file.filename}

@app.post("/memories/generate")
async def generate_memory_story(background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    TASKS[task_id] = {"status": "starting"}
    background_tasks.add_task(create_memory_story_worker, task_id)
    return {"task_id": task_id}

@app.get("/memories/status/{task_id}")
async def get_memory_status(task_id: str):
    task = TASKS.get(task_id)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.get("/memories/")
async def get_all_memories():
    memory_files = sorted([f for f in os.listdir(MEMORIES_PATH) if f.endswith('.json')], reverse=True)
    all_memories = []
    for filename in memory_files:
        try:
            with open(os.path.join(MEMORIES_PATH, filename), 'r', encoding='utf-8') as f: all_memories.append(json.load(f))
        except: continue
    return all_memories

@app.get("/memories/{filename}")
async def get_memory_asset(filename: str):
    file_path = os.path.join(MEMORIES_PATH, filename)
    if os.path.exists(file_path): return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Asset not found")

@app.get("/music/{filename}")
async def get_music_asset(filename: str):
    file_path = os.path.join(MUSIC_FOLDER, filename)
    if os.path.exists(file_path): return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Asset not found")


@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    # ... (код визначення типів та збереження файлу залишається тим самим) ...
    supported_image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', 'webp']
    supported_video_extensions = ['.mp4', '.mov', '.avi', '.mkv', 'webm']
    original_file_path = os.path.join(ORIGINALS_PATH, file.filename)
    with open(original_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    file_extension = os.path.splitext(file.filename.lower())[1]
    file_type = None
    if file_extension in supported_image_extensions: file_type = "image"
    elif file_extension in supported_video_extensions: file_type = "video"
    else: return {"filename": file.filename, "status": "skipped", "message": "Unsupported file type"}

    # ... (код створення прев'ю залишається тим самим) ...
    thumbnail_filename = f"{os.path.splitext(file.filename)[0]}.jpg"
    thumbnail_file_path = os.path.join(THUMBNAILS_PATH, thumbnail_filename)
    thumbnail_created = False
    if file_type == "image": thumbnail_created = create_photo_thumbnail(original_file_path, thumbnail_file_path)
    elif file_type == "video": thumbnail_created = create_video_thumbnail(original_file_path, thumbnail_file_path)

    if thumbnail_created:
        metadata = load_metadata()
        metadata[file.filename] = {
            "type": file_type,
            "thumbnail": thumbnail_filename,
            # --- ВИКОРИСТОВУЄМО НОВУ ФУНКЦІЮ ---
            "timestamp": get_original_date(original_file_path)
        }
        save_metadata(metadata)
        return {"filename": file.filename, "type": file_type, "status": "success"}
    else:
        raise HTTPException(status_code=500, detail="Could not create thumbnail")


# --- ЕНДПОІНТ get_gallery/ ЗАЛИШАЄТЬСЯ БЕЗ ЗМІН, він вже готовий ---
@app.get("/gallery/")
async def get_gallery_list():
    metadata = load_metadata()
    if not metadata: return []
    # Використовуємо .get() для безпечного отримання timestamp, на випадок старих записів
    sorted_items = sorted(metadata.items(), key=lambda item: item[1].get('timestamp', 0), reverse=True)
    gallery_list = [
        {"filename": key, "type": value["type"], "thumbnail": value["thumbnail"], "timestamp": value.get("timestamp")}
        for key, value in sorted_items if value.get("timestamp") # Віддаємо тільки ті, де є timestamp
    ]
    return JSONResponse(content=gallery_list)


@app.get("/thumbnail/{filename}")
# ... (без змін) ...
async def get_thumbnail(filename: str):
    file_path = os.path.join(THUMBNAILS_PATH, filename)
    if os.path.exists(file_path): return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Thumbnail not found")

@app.get("/original/{filename}")
# ... (без змін) ...
async def get_original_file(filename: str):
    file_path = os.path.join(ORIGINALS_PATH, filename)
    if os.path.exists(file_path): return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")

@app.post("/gallery/rescan")
async def rescan_storage():
    # ... (цей код треба теж оновити, щоб він використовував get_original_date) ...
    supported_image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', 'webp']
    supported_video_extensions = ['.mp4', '.mov', '.avi', '.mkv', 'webm']
    metadata = load_metadata()
    original_files = os.listdir(ORIGINALS_PATH)
    processed_count, updated_count = 0, 0
    
    for filename in original_files:
        original_file_path = os.path.join(ORIGINALS_PATH, filename)
        # Перескануємо, тільки якщо запис неповний (немає timestamp)
        if filename in metadata and 'timestamp' in metadata[filename]: continue
            
        if filename in metadata: updated_count += 1
        else: processed_count += 1

        file_extension = os.path.splitext(filename.lower())[1]
        file_type = None
        if file_extension in supported_image_extensions: file_type = "image"
        elif file_extension in supported_video_extensions: file_type = "video"
        else: continue

        thumbnail_filename = f"{os.path.splitext(filename)[0]}.jpg"
        thumbnail_file_path = os.path.join(THUMBNAILS_PATH, thumbnail_filename)
        
        if not os.path.exists(thumbnail_file_path):
            created = False
            if file_type == "image": created = create_photo_thumbnail(original_file_path, thumbnail_file_path)
            elif file_type == "video": created = create_video_thumbnail(original_file_path, thumbnail_file_path)
            if not created: continue

        # --- ВИКОРИСТОВУЄМО НОВУ ФУНКЦІЮ І ТУТ ---
        metadata[filename] = {
            "type": file_type,
            "thumbnail": thumbnail_filename,
            "timestamp": get_original_date(original_file_path)
        }

    save_metadata(metadata)
    message = f"Scan complete. New: {processed_count}. Updated: {updated_count}."
    return {"status": "success", "message": message}

# --- Глобальні налаштування ---
SETTINGS_FILE = os.path.join(STORAGE_PATH, "settings.json")
DEFAULT_SETTINGS = {
    "preview_size": 400,
    "preview_quality": 80,
    "photo_size": 0,      # 0 = оригінал
    "photo_quality": 100,
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

@app.get("/settings/")
async def get_settings():
    return load_settings()

@app.post("/settings/")
async def update_settings(data: dict = Body(...)):
    settings = load_settings()
    for key in DEFAULT_SETTINGS:
        if key in data:
            settings[key] = data[key]
    save_settings(settings)
    return {"status": "success", "settings": settings}

@app.post("/thumbnails/clear_cache/")
async def clear_thumbnails_cache():
    try:
        for fname in os.listdir(THUMBNAILS_PATH):
            fpath = os.path.join(THUMBNAILS_PATH, fname)
            if os.path.isfile(fpath):
                os.remove(fpath)
        return {"status": "success", "message": "Thumbnail cache cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

print("🚀 Сервер готовий до роботи! (v_final, з оригінальною датою)")

@app.get("/original_resized/{filename}")
async def get_resized_original(filename: str):
    file_path = os.path.join(ORIGINALS_PATH, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    settings = load_settings()
    max_size = settings.get("photo_size", 0)
    quality = settings.get("photo_quality", 100)
    ext = os.path.splitext(filename.lower())[1]
    # Якщо не зображення — просто віддаємо файл
    if ext not in [".jpg", ".jpeg", ".png", ".heic", ".webp"]:
        return FileResponse(file_path)
    try:
        with Image.open(file_path) as img:
            # HEIC/HEIF підтримка
            if img.format and img.format.upper() in ['HEIC', 'HEIF']:
                from pillow_heif import register_heif_opener
                register_heif_opener()
                img = Image.open(file_path)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            # Якщо max_size > 0 — змінюємо розмір
            if max_size and max_size > 0:
                img.thumbnail((max_size, max_size))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)
            buf.seek(0)
            return StreamingResponse(buf, media_type="image/jpeg")
    except Exception as e:
        print(f"Помилка стискання: {e}")
        return FileResponse(file_path)

@app.post("/thumbnails/generate_all/")
async def generate_all_thumbnails():
    """
    Генерує мініатюри для всіх медіафайлів у ORIGINALS_PATH згідно з поточними налаштуваннями.
    """
    supported_image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', 'webp']
    supported_video_extensions = ['.mp4', '.mov', '.avi', '.mkv', 'webm']
    metadata = load_metadata()
    original_files = os.listdir(ORIGINALS_PATH)
    generated, failed = 0, 0

    for filename in original_files:
        original_file_path = os.path.join(ORIGINALS_PATH, filename)
        file_extension = os.path.splitext(filename.lower())[1]
        file_type = None
        if file_extension in supported_image_extensions:
            file_type = "image"
        elif file_extension in supported_video_extensions:
            file_type = "video"
        else:
            continue

        thumbnail_filename = f"{os.path.splitext(filename)[0]}.jpg"
        thumbnail_file_path = os.path.join(THUMBNAILS_PATH, thumbnail_filename)

        try:
            if file_type == "image":
                created = create_photo_thumbnail(original_file_path, thumbnail_file_path)
            else:
                created = create_video_thumbnail(original_file_path, thumbnail_file_path)
            if created:
                generated += 1
            else:
                failed += 1
        except Exception as e:
            print(f"Помилка при створенні мініатюри для {filename}: {e}")
            failed += 1

    return {"status": "success", "generated": generated, "failed": failed}

@app.get("/original_with_path/")
async def get_original_with_path(path: str = Query(...)):
    base_path = os.path.abspath(ORIGINALS_PATH)
    requested_file = os.path.abspath(os.path.join(base_path, path))
    if not requested_file.startswith(base_path):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(requested_file):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(requested_file)