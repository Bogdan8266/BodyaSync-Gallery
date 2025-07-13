import os
import random
import json
import requests
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from gradio_client import Client, file

# ======================================================================
# БЛОК 1: ЗАГАЛЬНА КОНФІГУРАЦІЯ
# ======================================================================

# --- Налаштування для аналізу фото ---
HF_SPACE_CAPTION_URL = "bodyapromax2010/bodyasync-image-caption"
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL_NAME = "gemma3:1b"

# --- Налаштування для створення колажу ---
HF_SPACE_COLLAGE_URL = "bodyapromax2010/black-forest-labs-FLUX.1-dev2" 
IMAGE_FOLDER = "test_images"
ASSETS_FOLDER = "assets"
FRAMES_CONFIG_FILE = os.path.join(ASSETS_FOLDER, "frames_config.json")
FONT_FILE = os.path.join(ASSETS_FOLDER, "Roboto-Regular.ttf")

# --- Завантаження ресурсів ---
try:
    FONT = ImageFont.truetype(FONT_FILE, 30)
except IOError:
    FONT = ImageFont.load_default()

def load_frames_config():
    if os.path.exists(FRAMES_CONFIG_FILE):
        with open(FRAMES_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    print(f"⚠️ Файл конфігурації рамок '{FRAMES_CONFIG_FILE}' не знайдено.")
    return {}

# ======================================================================
# БЛОК 2: ФУНКЦІЇ ДЛЯ АНАЛІЗУ ТА ОПИСУ ФОТО
# ======================================================================

def get_raw_english_description(image_path):
    """Крок А: Отримуємо "сирий" опис з Hugging Face."""
    print(f"   - Крок А: Аналізую фото '{os.path.basename(image_path)}' на HF Space...")
    try:
        client = Client(HF_SPACE_CAPTION_URL)
        result = client.predict(file(image_path), api_name="/predict")
        return (result[0] if isinstance(result, (list, tuple)) else result).strip()
    except Exception as e:
        print(f"   - ❌ Помилка під час аналізу на HF: {e}"); return None

def create_warm_caption_from_description(english_description, date_info):
    """Крок Б: Створюємо "теплий" підпис за допомогою Ollama."""
    print(f"   - Крок Б: Генерую підпис на локальній моделі '{OLLAMA_MODEL_NAME}'...")
    prompt_text = f"""
    You are a creative assistant. Your task is to transform a detailed, technical image description into a short, warm, and nostalgic caption in Ukrainian.
    Use this information:
    - Technical description: "{english_description}"
    - Time context: "{date_info}"
    Make it sound like a warm memory (1-2 sentences). Write ONLY the final Ukrainian caption.
    """
    payload = {"model": OLLAMA_MODEL_NAME, "prompt": prompt_text, "stream": False}
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        caption = response.json().get("response", "").strip()
        return caption if caption else "Чудовий спогад!"
    except requests.exceptions.RequestException as e:
        print(f"   - ❌ Помилка підключення до Ollama: {e}"); return None

def is_good_memory(caption):
    """Перевіряє, чи не є опис скріншотом або документом."""
    if not caption: return False
    stop_words = ["screenshot", "text", "document", "chart", "diagram", "interface", "code"]
    return not any(word in caption.lower() for word in stop_words)

# ======================================================================
# БЛОК 3: ФУНКЦІЇ ДЛЯ СТВОРЕННЯ КОЛАЖУ
# ======================================================================

def get_dominant_color(image_path):
    img = Image.open(image_path).resize((1, 1), Image.Resampling.LANCZOS)
    color = img.getpixel((0, 0))
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

def apply_frame(photo, frame_path, config):
    """
    Правильно обробляє рамки будь-якого розміру. Якщо рамка більша за фото,
    фінальне зображення розширюється, щоб вмістити всю рамку.
    """
    try:
        frame_template = Image.open(frame_path).convert("RGBA")
        params = config.get(os.path.basename(frame_path), {})
        scale = params.get("scale", 1.0)
        scale_x, scale_y = params.get("scale_x"), params.get("scale_y")
        if scale_x is not None and scale_y is not None:
            new_frame_width, new_frame_height = int(photo.width * scale_x), int(photo.height * scale_y)
        else:
            new_frame_width, new_frame_height = int(photo.width * scale), int(photo.height * scale)
        resized_frame = frame_template.resize((new_frame_width, new_frame_height), Image.Resampling.LANCZOS)
        result_canvas = Image.new("RGBA", resized_frame.size, (0, 0, 0, 0)) 
        photo_pos_x = (resized_frame.width - photo.width) // 2
        photo_pos_y = (resized_frame.height - photo.height) // 2
        offset_x, offset_y = params.get("offset_x", 0), params.get("offset_y", 0)
        photo_pos_x += offset_x
        photo_pos_y += offset_y
        result_canvas.paste(photo, (photo_pos_x, photo_pos_y))
        result_canvas.paste(resized_frame, (0, 0), resized_frame)
        return result_canvas
    except Exception as e:
        print(f"⚠️ Помилка при накладанні рамки: {e}"); return photo

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
BACKGROUND_STRATEGIES = [get_prompt_filmstrip_abstraction, get_prompt_warm_retro_sky, get_prompt_futuristic_geometry, get_prompt_soft_blobs, get_prompt_brushstrokes, get_prompt_symbolic_shapes, get_prompt_abstract_flowers, get_prompt_abstract_windows, get_prompt_watercolor_texture, get_prompt_lines_and_splatters]
# --- Кінець блоку функцій для фону ---

def generate_background_with_hf_space(prompt):
    print(f"🎨 Генеруємо фон для колажу...")
    try:
        client = Client(HF_SPACE_COLLAGE_URL)
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

# ======================================================================
# БЛОК 4: ОСНОВНА ЛОГІКА - ОБ'ЄДНАНИЙ КОНВЕЄР З ПОКРАЩЕННЯМИ
# ======================================================================
if __name__ == "__main__":
    
    # --- ЕТАП 1: ВІДБІР ФОТОГРАФІЙ-СПОГАДІВ ---
    print("🚀 Починаємо процес створення колажу-спогаду...")
    all_images = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    if len(all_images) < 2:
        print("❌ Потрібно мінімум 2 фотографії для роботи."); exit()

    # Повертаємо оригінальну логіку, вона правильна
    num_to_find = random.randint(2, min(5, len(all_images)))
    print(f"🎯 Мета: знайти {num_to_find} хороших фото-спогадів.")
    
    selected_memories, available_images = [], all_images.copy()
    
    while len(selected_memories) < num_to_find and available_images:
        image_name = random.choice(available_images)
        available_images.remove(image_name)
        image_path = os.path.join(IMAGE_FOLDER, image_name)

        raw_description = get_raw_english_description(image_path)
        if raw_description and is_good_memory(raw_description):
            date_info = f"зроблено {datetime.fromtimestamp(os.path.getmtime(image_path)).strftime('%d %B, %Y року')}"
            final_caption = create_warm_caption_from_description(raw_description, date_info)
            if final_caption:
                print(f"✅ Фото '{image_name}' підходить! Додано до колажу.")
                selected_memories.append({"filename": image_name, "caption": final_caption})
        else:
            print(f"❌ Фото '{image_name}' не схоже на спогад. Пропускаємо.")
    
    if not selected_memories:
        print("🛑 Не вдалося знайти жодного підходящого фото. Завершення роботи."); exit()

    # --- ЕТАП 2: ВИВЕДЕННЯ ЗВІТУ ---
    print("\n" + "="*50 + "\n📝 СПИСОК ВІДІБРАНИХ СПОГАДІВ ДЛЯ КОЛАЖУ:\n" + "="*50)
    for i, memory in enumerate(selected_memories, 1):
        print(f"  {i}. Фото: {memory['filename']}\n     Підпис: {memory['caption']}")
    print("="*50 + "\n")

    # --- ЕТАП 3: СТВОРЕННЯ КОЛАЖУ З ПОКРАЩЕНОЮ ЛОГІКОЮ РОЗМІЩЕННЯ ---
    print("🖼️ Починаємо створення колажу...")
    selected_filenames = [m['filename'] for m in selected_memories]
    dominant_colors = [get_dominant_color(os.path.join(IMAGE_FOLDER, name)) for name in selected_filenames]
    
    chosen_strategy = random.choice(BACKGROUND_STRATEGIES)
    prompt = chosen_strategy(dominant_colors)
    collage = generate_background_with_hf_space(prompt).convert("RGBA")
    
    frames_config = load_frames_config()
    chosen_frame_path = None
    frames_folder = os.path.join(ASSETS_FOLDER, "frames")
    if os.path.exists(frames_folder):
        frame_files = [f for f in os.listdir(frames_folder) if f.lower().endswith('.png') and f in frames_config]
        if frame_files:
            chosen_frame = random.choice(frame_files)
            chosen_frame_path = os.path.join(frames_folder, chosen_frame)
            print(f"🎨 Обрано рамку для колажу: {chosen_frame}")

    # <<< ПОКРАЩЕННЯ 2: Змінюємо розмір фото, щоб вони краще вміщалися >>>
    PHOTO_SIZES_BY_COUNT = {
        2: 800,  # Великі
        3: 650,  # Трохи менші
        4: 550,  # Середні
        5: 480   # Компактні
    }
    target_size = PHOTO_SIZES_BY_COUNT.get(len(selected_filenames), 600)
    print(f"ℹ️ Кількість фото: {len(selected_filenames)}. Цільовий розмір: {target_size}px.")

    placed_boxes = []
    for filename in selected_filenames:
        photo = Image.open(os.path.join(IMAGE_FOLDER, filename)).convert("RGBA")
        photo.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
        
        photo_with_frame = photo
        if chosen_frame_path:
            photo_with_frame = apply_frame(photo, chosen_frame_path, frames_config)
            
        angle = random.randint(-20, 20)
        rotated_photo = photo_with_frame.rotate(angle, expand=True, resample=Image.BICUBIC)
        
        # <<< ГОЛОВНЕ ВИПРАВЛЕННЯ: Більше спроб знайти місце >>>
        is_placed = False
        for _ in range(500): # Збільшили кількість спроб до 500
            margin = 30 
            x = random.randint(margin, collage.width - rotated_photo.width - margin)
            y = random.randint(margin, collage.height - rotated_photo.height - margin)
            new_box = (x, y, x + rotated_photo.width, y + rotated_photo.height)
            
            if not any(check_overlap(new_box, box) for box in placed_boxes):
                placed_boxes.append(new_box)
                collage.paste(rotated_photo, (x, y), rotated_photo)
                print(f"📍 Розміщено фото '{filename}' на колажі.")
                is_placed = True
                break
        
        if not is_placed:
            print(f"⚠️ Не вдалося знайти місце для фото '{filename}' після 500 спроб. Воно не буде на колажі.")

    output_path = "memory_collage_output.png"
    collage.save(output_path)
    
    print("\n🎉🎉🎉 КОЛАЖ-СПОГАД УСПІШНО СТВОРЕНО! 🎉🎉🎉")
    print(f"✅ Результат збережено у файлі: {output_path}")