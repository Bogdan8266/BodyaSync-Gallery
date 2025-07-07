import os
import random
import json
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from gradio_client import Client

# --- Конфігурація ---
HF_SPACE_URL = "bodyapromax2010/black-forest-labs-FLUX.1-dev22"
IMAGE_FOLDER = "test_images"
ASSETS_FOLDER = "assets"
FRAMES_CONFIG = os.path.join(ASSETS_FOLDER, "frames_config.json")
FONT_FILE = os.path.join(ASSETS_FOLDER, "Roboto-Regular.ttf")

# Завантажуємо шрифт
try:
    FONT = ImageFont.truetype(FONT_FILE, 30)
except IOError:
    FONT = ImageFont.load_default()

# Завантажуємо конфігурацію рамок
def load_frames_config():
    if os.path.exists(FRAMES_CONFIG):
        with open(FRAMES_CONFIG, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "frame1.png": {"scale": 1.0, "offset_x": 0, "offset_y": 0},
        "frame2.png": {"scale": 1.1, "offset_x": -10, "offset_y": -5}
    }

# Зберігаємо конфігурацію рамок
def save_frames_config(config):
    with open(FRAMES_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

# --- Допоміжні функції ---

def get_dominant_color(image_path):
    """Визначає домінуючий колір зображення."""
    img = Image.open(image_path)
    img = img.resize((1, 1), Image.Resampling.LANCZOS)
    color = img.getpixel((0, 0))
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

def apply_frame(photo, frame_path, config):
    """
    Накладає рамку на фото з розширеними опціями масштабування.
    Підтримує пропорційний 'scale' та незалежні 'scale_x', 'scale_y'.
    """
    try:
        # Завантажуємо шаблон рамки
        frame_template = Image.open(frame_path).convert("RGBA")
        
        # Отримуємо параметри з конфігурації
        params = config.get(os.path.basename(frame_path), {})
        
        # <<< ПОЧАТОК НОВОЇ ЛОГІКИ МАСШТАБУВАННЯ >>>
        
        # Отримуємо всі можливі параметри масштабування
        scale = params.get("scale", 1.0)
        scale_x = params.get("scale_x") # За замовчуванням буде None, якщо немає
        scale_y = params.get("scale_y") # За замовчуванням буде None, якщо немає
        
        # Визначаємо фінальний розмір рамки
        # Пріоритет у незалежного масштабування
        if scale_x is not None and scale_y is not None:
            # Використовуємо незалежне розтягування
            print(f"   - Використовуємо незалежне масштабування: x={scale_x}, y={scale_y}")
            new_frame_width = int(photo.width * scale_x)
            new_frame_height = int(photo.height * scale_y)
        else:
            # Використовуємо звичайне пропорційне масштабування
            print(f"   - Використовуємо пропорційне масштабування: {scale}")
            new_frame_width = int(photo.width * scale)
            new_frame_height = int(photo.height * scale)
        
        # <<< КІНЕЦЬ НОВОЇ ЛОГІКИ МАСШТАБУВАННЯ >>>
            
        # Отримуємо зміщення
        offset_x = params.get("offset_x", 0)
        offset_y = params.get("offset_y", 0)
        
        # Змінюємо розмір рамки
        resized_frame = frame_template.resize((new_frame_width, new_frame_height), Image.Resampling.LANCZOS)
        
        # Створюємо нове, прозоре полотно розміром з нашу рамку
        result_canvas = Image.new("RGBA", resized_frame.size, (0, 0, 0, 0))
        
        # Розраховуємо позицію для ФОТОГРАФІЇ, щоб вона була в центрі полотна
        photo_x = (resized_frame.width - photo.width) // 2 + offset_x
        photo_y = (resized_frame.height - photo.height) // 2 + offset_y
        
        # Вставляємо фото на прозоре полотно
        result_canvas.paste(photo, (photo_x, photo_y))
        
        # Вставляємо РАМКУ поверх усього
        result_canvas.paste(resized_frame, (0, 0), resized_frame)
        
        return result_canvas
        
    except Exception as e:
        print(f"⚠️ Помилка при накладанні рамки: {e}")
        return photo

# --- Функції для генерації фону ---

def get_prompt_filmstrip_abstraction(colors_hex): return (f"A minimalist abstract background, vintage 35mm filmstrip, soft gradients, {random.choice(colors_hex)} and pastel palette, light leaks, cinematic, fine grain, 8k.")
def get_prompt_warm_retro_sky(colors_hex): return (f"A dreamy, retro-style abstract background, 70s sunset, warm {random.choice(colors_hex)} palette, smooth gradients, hazy clouds, sunburst effect, nostalgic film grain, ethereal, high resolution.")
def get_prompt_futuristic_geometry(colors_hex): return (f"A modern, tech-style abstract background, clean layered dynamic curved and straight lines, monochrome base with sharp vibrant {random.choice(colors_hex)} accents, holographic elements, smooth highlights, minimalist vector art, Behance HD.")
def get_prompt_soft_blobs(colors_hex): return (f"A serene minimalist organic background, large soft amorphous shapes like liquid ink bleeds, blended with smooth gradients in a soft {random.choice(colors_hex)} palette, subtle paper texture, bokeh effect, calm, high quality.")
def get_prompt_brushstrokes(colors_hex): return (f"An artistic abstract background, modern canvas painting style, energetic broad textured brushstrokes, calligraphic linear patterns, harmonious {random.choice(colors_hex)} scheme, light canvas texture, balanced composition.")
def get_prompt_symbolic_shapes(colors_hex): return (f"A clean modern graphic design background, soft gradient {random.choice(colors_hex)} base, simple icon-like vector shapes (thin circles, planet outlines), sparsely placed with gentle drop shadows, fine grain texture, rule of thirds.")
def get_prompt_abstract_flowers(colors_hex): return (f"A soft pastel abstract background, delicate minimalist botanical illustrations, simple line-art flower silhouettes, smoothly blended {random.choice(colors_hex)} gradient, subtle grain, ethereal glow for depth.")
def get_prompt_abstract_windows(colors_hex): return (f"A minimal architectural-style abstract background, layered framed square and rectangle shapes of varying opacities, on a smooth gradient {random.choice(colors_hex)} base, soft shadows, light grain, sharp highlights on edges.")
def get_prompt_watercolor_texture(colors_hex): return (f"A beautiful watercolor-style abstract background, heavily blended textured brushstrokes in {random.choice(colors_hex)} palette, organic gradient transitions, visible high-quality paper grain, realistic water smudges, artistic.")
def get_prompt_lines_and_splatters(colors_hex): return (f"A minimal abstract composition, modern art style, random organic ink splatters, irregular hand-drawn stripes, on a soft off-white paper texture, limited palette of black, gold, and one accent color (teal or rust), delicate grain.")
BACKGROUND_STRATEGIES = [get_prompt_filmstrip_abstraction, get_prompt_warm_retro_sky, get_prompt_futuristic_geometry, get_prompt_soft_blobs, get_prompt_brushstrokes, get_prompt_symbolic_shapes, get_prompt_abstract_flowers, get_prompt_abstract_windows, get_prompt_watercolor_texture, get_prompt_lines_and_splatters]

# --- Генерація фона ---

def generate_background_with_hf_space(prompt):
    """Генерує фон за допомогою Hugging Face Space."""
    print(f"🤖 Генеруємо фон за промптом: {prompt[:120]}...")
    
    try:
        client = Client(HF_SPACE_URL)
        result = client.predict(
            prompt, 
            "low quality, blurry, text, watermark, logo, ugly", 
            api_name="/infer"
        )
        image_path = result[0]
        return Image.open(image_path).resize((1080, 1920), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"🛑 Помилка генерації фону: {e}")
        return Image.new("RGB", (1080, 1920), (128, 0, 128))  # Фіолетовий фон

# --- Перевірка перетину ---

def check_overlap(box1, box2, max_overlap_ratio=0.25):
    """Перевіряє чи перетинаються області фотографій."""
    inter_left = max(box1[0], box2[0])
    inter_top = max(box1[1], box2[1])
    inter_right = min(box1[2], box2[2])
    inter_bottom = min(box1[3], box2[3])
    
    if inter_right > inter_left and inter_bottom > inter_top:
        inter_area = (inter_right - inter_left) * (inter_bottom - inter_top)
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        if box1_area > 0 and inter_area / box1_area > max_overlap_ratio:
            return True
    return False

# --- Основна логіка ---
# --- Основна логіка ---
if __name__ == "__main__":
    # Завантажуємо конфігурацію рамок
    frames_config = load_frames_config()

    # Перевірка папки з зображеннями
    if not os.path.exists(IMAGE_FOLDER):
        os.makedirs(IMAGE_FOLDER)
        print(f"📁 Створено папку для зображень: {IMAGE_FOLDER}")
        print("ℹ️ Додайте фотографії в папку та запустіть скрипт знову")
        exit()

    # Отримуємо список фотографій
    all_images = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    if len(all_images) < 2:
        print("❌ Потрібно мінімум 2 фотографії для колажу")
        exit()

    # Вибираємо випадкові фотографії
    num_photos = random.randint(2, min(5, len(all_images)))
    selected_images = random.sample(all_images, num_photos)
    print(f"📸 Обрано {num_photos} фотографій: {', '.join(selected_images)}")

    # Визначаємо домінуючі кольори
    dominant_colors = [get_dominant_color(os.path.join(IMAGE_FOLDER, img)) for img in selected_images]
    print(f"🎨 Домінуючі кольори: {', '.join(dominant_colors)}")

    # Генеруємо фон
    chosen_strategy = random.choice(BACKGROUND_STRATEGIES)
    prompt = chosen_strategy(dominant_colors)
    collage = generate_background_with_hf_space(prompt).convert("RGBA")

    # Обробляємо фотографії
    processed_photos = []
    for img_name in selected_images:
        img_path = os.path.join(IMAGE_FOLDER, img_name)
        photo = Image.open(img_path).convert("RGBA")
        processed_photos.append(photo)

    # --- ЗМІНЕНО: Логіка розміщення фото та рамок об'єднана ---

    # Спочатку вибираємо одну рамку для всього колажу, щоб було стильно
    chosen_frame_path = None
    frames_folder = os.path.join(ASSETS_FOLDER, "frames")
    if os.path.exists(frames_folder):
        frame_files = [f for f in os.listdir(frames_folder) if f.lower().endswith('.png')]
        if frame_files:
            chosen_frame = random.choice(frame_files)
            chosen_frame_path = os.path.join(frames_folder, chosen_frame)
            print(f"🖼️ Обрано рамку для колажу: {chosen_frame}")

    placed_boxes = []
    # Використовуємо enumerate для зручного відстеження індексу
    for i, photo in enumerate(processed_photos):
        # 1. Зменшуємо розмір фото
        photo.thumbnail((600, 600))

        # 2. НАКЛАДАЄМО РАМКУ НА ПРЯМЕ ФОТО (якщо рамка є)
        photo_with_frame = photo
        if chosen_frame_path:
            photo_with_frame = apply_frame(photo, chosen_frame_path, frames_config) # НОВИЙ ВИКЛИК

        # 3. ОБЕРТАЄМО ВЖЕ ФОТО З РАМКОЮ
        angle = random.randint(-15, 15)
        rotated_photo = photo_with_frame.rotate(angle, expand=True, resample=Image.BICUBIC)

        # 4. Шукаємо позицію без перетинів і розміщуємо
        for _ in range(50): # 50 спроб знайти місце
            x = random.randint(50, collage.width - rotated_photo.width - 50)
            y = random.randint(50, collage.height - rotated_photo.height - 50)
            new_box = (x, y, x + rotated_photo.width, y + rotated_photo.height)

            if not any(check_overlap(new_box, box) for box in placed_boxes):
                placed_boxes.append(new_box)
                collage.paste(rotated_photo, (x, y), rotated_photo)
                print(f"📍 Розміщено фото {i+1}/{len(processed_photos)}")
                break
    
    # --- ВИДАЛЕНО: Старий блок накладання рамок, він більше не потрібен ---
    # Тут був старий цикл `for i, box in enumerate(placed_boxes):`, який ми видалили.

    # Додаємо дату
    date_str = datetime.now().strftime("%d.%m.%Y")
    draw = ImageDraw.Draw(collage)
    try:
        text = f"All rights reserved you: {date_str}"
        # Використовуємо getbbox для більш точного розрахунку розміру тексту
        bbox = draw.textbbox((0, 0), text, font=FONT)
        text_width = bbox[2] - bbox[0]
        x = (collage.width - text_width) // 8
        y = collage.height - 60
        # Малюємо тінь
       # draw.text((x+0, y+0), text, font=FONT, fill="#0000000E")
        # Малюємо основний текст
        draw.text((x, y), text, font=FONT, fill="#0F0F0F01")
    except Exception as e:
        print(f"⚠️ Помилка при додаванні дати: {e}")

    # Зберігаємо результат
    output_path = "collage_output.png"
    collage.save(output_path)
    print(f"💾 Результат збережено: {output_path}")

    # Рекомендація музики
    music_folder = os.path.join(ASSETS_FOLDER, "music")
    if os.path.exists(music_folder):
        music_files = [f for f in os.listdir(music_folder) if f.endswith('.mp3')]
        if music_files:
            chosen_music = random.choice(music_files)
            print(f"\n🎵 Рекомендована музика: {chosen_music}")

    print("\n🎉 КОЛАЖ УСПІШНО СТВОРЕНО! 🎉")