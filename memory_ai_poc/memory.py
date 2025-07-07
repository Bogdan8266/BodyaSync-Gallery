import os
import random
import requests
import json
import base64
from datetime import datetime

# --- Налаштування ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"  # Адреса твого локального сервера Ollama
MODEL_NAME = "gemma3:4b"                           # Назва моделі, яку ми завантажили
IMAGE_FOLDER = "test_images"                            # Папка з тестовими фото

# --- Функція 1: Кодування зображення ---
# Ollama API вимагає, щоб зображення були у форматі Base64
def encode_image_to_base64(image_path):
    """Кодує зображення в рядок Base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# --- Функція 2: Аналіз зображення за допомогою AI ---
# Це серце нашої системи. Вона відправляє фото і промпт до нейромережі.
def analyze_image(image_path):
    """
    Аналізує зображення, визначає його вміст, оцінку
    і чи підходить воно для "спогаду".
    """
    print(f"🕵️ Аналізую зображення: {os.path.basename(image_path)}...")
    
    encoded_image = encode_image_to_base64(image_path)
    
    # Це найважливіша частина - наш "промпт" (завдання для нейромережі).
    # Ми просимо її повернути відповідь у форматі JSON, щоб її було легко обробити.
    prompt_text = """
    Analyze the image and provide a response in JSON format.
    The JSON object must contain these keys:
    - "description": A short, three-sentence description of what's in the image.
    - "is_memory_candidate": A boolean (true or false). It should be true for photos of people, animals, nature, events, and false for screenshots, documents, or boring images.
    - "emotional_score": An integer from 1 to 10, where 10 is a very emotional or interesting photo.
    - "tags": A list of 8-16 relevant string tags in Ukrainian (e.g., ["собака", "парк", "літо"]).
    
    Provide only the JSON object in your response.
    """
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt_text,
        "images": [encoded_image],
        "stream": False,
        "format": "json" # Просимо Ollama повернути гарантований JSON
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status() # Перевірка на помилки HTTP (4xx, 5xx)
        
        # Відповідь від Ollama приходить у вигляді JSON рядка, який треба ще раз розпарсити
        response_data = response.json()
        analysis_json = json.loads(response_data.get("response", "{}"))
        
        return analysis_json
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Помилка підключення до Ollama: {e}")
        return None
    except json.JSONDecodeError:
        print("❌ Не вдалося розпарсити JSON відповідь від моделі.")
        return None

# --- Функція 3: Генерація красивого підпису ---
def generate_caption(analysis_data, date_info):
    """Генерує теплий підпис для спогаду на основі аналізу."""
    print("✍️ Генерую підпис для спогаду...")
    
    description = analysis_data.get("description", "a nice moment")
    tags = ", ".join(analysis_data.get("tags", []))
    
    # Створюємо новий промпт, тепер для генерації тексту
    prompt_text = f"""
    You are a friendly assistant who creates warm memories. 
    Write a short, nostalgic, and kind caption in Ukrainian.
    Use this information:
    - Photo description: {description}
    - Photo tags: {tags}
    - Time context: {date_info}
    
    Make it sound personal and heartwarming. For example: "Пам'ятаєш цей день?.." or "Поглянь, який чудовий момент!".
    Write only the caption itself, without any extra text.
    """
    
    # Для генерації тексту нам вже не потрібне зображення
    payload = {
        "model": "gemma3:4b", # Можна використати меншу модель для тексту, наприклад gemma:2b
        "prompt": prompt_text,
        "stream": False
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        
        response_data = response.json()
        return response_data.get("response", "Чудовий спогад!").strip()

    except requests.exceptions.RequestException as e:
        print(f"❌ Помилка при генерації підпису: {e}")
        return "Просто гарний день!"

# --- Основна логіка скрипта ---
if __name__ == "__main__":
    # 1. Знаходимо всі файли в папці test_images
    all_images = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if not all_images:
        print(f"Не знайдено зображень у папці {IMAGE_FOLDER}. Додай туди фото.")
    else:
        # 2. Вибираємо одне випадкове фото для аналізу
        random_image_name = random.choice(all_images)
        image_path = os.path.join(IMAGE_FOLDER, random_image_name)
        
        # 3. Аналізуємо його
        analysis = analyze_image(image_path)
        
        if analysis:
            print("\n--- Результати аналізу ---")
            print(json.dumps(analysis, indent=2, ensure_ascii=False))
            print("--------------------------\n")

            # 4. Перевіряємо, чи це хороший кандидат для спогаду
            if analysis.get("is_memory_candidate"):
                # Отримуємо дату створення файлу (в реальному додатку це буде дата з EXIF)
                file_stat = os.stat(image_path)
                creation_date = datetime.fromtimestamp(file_stat.st_mtime)
                date_info = f"зроблене {creation_date.strftime('%d %B, %Y року')}" # наприклад "зроблене 15 травня, 2024 року"
                
                # 5. Генеруємо фінальний підпис
                final_caption = generate_caption(analysis, date_info)
                
                print("\n🎉🎉🎉 ВАШ СЬОГОДНІШНІЙ СПОГАД! 🎉🎉🎉")
                print(f"Фото: {random_image_name}")
                print(f"Підпис: {final_caption}")
                print("🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")
            else:
                print(f"😕 Фото '{random_image_name}' не схоже на хороший спогад. Можливо, це скріншот або документ.")