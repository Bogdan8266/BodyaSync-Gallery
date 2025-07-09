import os
import random
import requests
import json
from datetime import datetime
from gradio_client import Client, file

# --- Налаштування для обох сервісів ---
HF_SPACE_URL = "bodyapromax2010/bodyasync-image-caption" # "Очі" - для опису
OLLAMA_API_URL = "http://localhost:11434/api/generate"  # "Душа" - для стилізації тексту
OLLAMA_MODEL_NAME = "gemma3:1b"                          # Модель для роботи з текстом
IMAGE_FOLDER = "test_images"

# --- Функція 1: Отримуємо "сирий" опис з Hugging Face ---
def get_raw_english_description(image_path):
    """
    Звертається до HF Space, щоб отримати детальний технічний опис зображення.
    """
    print(f"🕵️ Крок 1: Отримую детальний опис з '{HF_SPACE_URL}'...")
    try:
        client = Client(HF_SPACE_URL)
        result = client.predict(file(image_path), api_name="/predict")
        description = result[0] if isinstance(result, (list, tuple)) else result
        print("✅ Опис отримано.")
        return description.strip()
    except Exception as e:
        print(f"❌ Помилка на Кроці 1 (Hugging Face): {e}")
        return None

# --- Функція 2: Створюємо "теплий" підпис за допомогою Ollama (ВИПРАВЛЕНА ВЕРСІЯ) ---
def create_warm_caption_from_description(english_description, date_info):
    """
    Бере англійський опис, відправляє його на локальну модель (Gemma)
    і просить зробити з нього короткий, гарний підпис українською, ВРАХОВУЮЧИ ДАТУ.
    """
    print(f"✍️ Крок 2: Генерую теплий підпис за допомогою '{OLLAMA_MODEL_NAME}'...")
    
    # Промпт тепер явно включає 'Time context', як ти і хотів.
    prompt_text = f"""
    You are a creative assistant. Your task is to transform a detailed, technical image description into a short, warm, and nostalgic caption in Ukrainian.

    Use this information to create the caption:
    - Technical description (what is in the photo): "{english_description}"
    - Time context (when the photo was taken): "{date_info}"

    Based on this information, do the following:
    1. Translate the main idea into Ukrainian.
    2. Shorten it to 1-2 beautiful, personal-sounding sentences.
    3. Weave the time context into the caption if it feels natural. For example: "Пам'ятаєш цей чудовий зимовий день?" or "Як же тепло було того літа...".
    
    Write ONLY the final Ukrainian caption, nothing else.
    """
    
    payload = {
        "model": OLLAMA_MODEL_NAME,
        "prompt": prompt_text,
        "stream": False
    }
    
    try:
        # Переконайся, що твій сервер Ollama запущено!
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        
        response_data = response.json()
        caption = response_data.get("response", "Чудовий спогад!").strip()
        print("✅ Підпис згенеровано.")
        return caption
    except requests.exceptions.RequestException as e:
        print(f"❌ Помилка на Кроці 2 (Ollama): {e}. Перевір, чи запущено сервер Ollama.")
        return "Просто гарний день!"

# --- Функція 3: Проста перевірка, чи підходить фото для спогаду ---
def is_good_memory(caption):
    if not caption: return False
    stop_words = ["screenshot", "text", "document", "chart", "diagram", "interface", "code"]
    caption_lower = caption.lower()
    return not any(word in caption_lower for word in stop_words)

# --- Основна логіка ---
if __name__ == "__main__":
    if not os.path.isdir(IMAGE_FOLDER):
        print(f"🛑 Папку '{IMAGE_FOLDER}' не знайдено! Створіть її та додайте фото.")
        exit()
        
    all_images = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if not all_images:
        print(f"Не знайдено зображень у папці '{IMAGE_FOLDER}'.")
    else:
        random_image_name = random.choice(all_images)
        image_path = os.path.join(IMAGE_FOLDER, random_image_name)
        
        # КРОК 1: Отримуємо англійський опис
        raw_description = get_raw_english_description(image_path)
        
        if raw_description:
            print(f"\n--- Сирий опис від Florence-2 ---\n{raw_description}\n---------------------------------\n")

            if is_good_memory(raw_description):
                # Отримуємо дату для передачі в промпт
                try:
                    date_info = f"зроблено {datetime.fromtimestamp(os.path.getmtime(image_path)).strftime('%d %B, %Y року')}"
                except Exception:
                    date_info = "колись у минулому"
                
                # КРОК 2: Генеруємо фінальний підпис, передаючи і опис, і дату
                final_caption = create_warm_caption_from_description(raw_description, date_info)
                
                print("\n🎉🎉🎉 ВАШ СЬОГОДНІШНІЙ СПОГАД! 🎉🎉🎉")
                print(f"Фото: {random_image_name}")
                print(f"Підпис: {final_caption}")
                print("🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")
            else:
                print(f"😕 Фото '{random_image_name}' не схоже на хороший спогад (можливо, це скріншот).")
        else:
            print("Не вдалося виконати Крок 1. Перевірте з'єднання та статус Hugging Face Space.")