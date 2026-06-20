from flask import Flask, request, render_template_string, send_file, jsonify, session
import os
import time
import zipfile
from pathlib import Path
from io import BytesIO
import google.generativeai as genai
from PIL import Image
import tempfile
import shutil
import uuid

app = Flask(__name__)
app.secret_key = "super_secret_key_12345"  # для сессий

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "sorted_output"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ================== HTML (оставляю тот же красивый интерфейс) ==================
HTML = """ ... (оставь тот же HTML, который у тебя сейчас) ... """

# ================== РОУТЫ ==================

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/analyze', methods=['POST'])
def analyze():
    api_key = request.form.get('api_key', '').strip()
    prompt = request.form.get('prompt', '')
    expected_frames = int(request.form.get('expected_frames', 0))

    if not api_key or not prompt:
        return jsonify({"success": False, "error": "API ключ или промпт не указан"})

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        return jsonify({"success": False, "error": f"Ошибка API ключа: {str(e)}"})

    # Сохраняем файлы
    temp_dir = tempfile.mkdtemp(dir=UPLOAD_FOLDER)
    image_paths = []
    for file in request.files.getlist('images'):
        if file.filename:
            path = os.path.join(temp_dir, file.filename)
            file.save(path)
            image_paths.append(path)

    if not image_paths:
        return jsonify({"success": False, "error": "Изображения не загружены"})

    try:
        # Анализ
        descriptions = []
        for i, path in enumerate(image_paths):
            desc = get_image_description(path, model)
            descriptions.append({
                "path": path,
                "original_name": os.path.basename(path),
                "description": desc
            })
            time.sleep(1.1)

        # Сортировка
        order = get_sorted_order([d["description"] for d in descriptions], prompt, model)

        # Формируем результаты
        results = []
        for new_idx, old_idx in enumerate(order):
            item = descriptions[old_idx]
            results.append({
                "new_index": f"{new_idx+1:04d}",
                "original_name": item["original_name"],
                "description": item["description"][:120],
                "status": "matched"
            })

        # Сохраняем отсортированные файлы
        session_id = str(uuid.uuid4())
        output_dir = os.path.join(OUTPUT_FOLDER, session_id)
        os.makedirs(output_dir, exist_ok=True)

        for new_idx, old_idx in enumerate(order):
            item = descriptions[old_idx]
            new_name = f"{new_idx+1:04d}_{item['original_name']}"
            shutil.copy(item["path"], os.path.join(output_dir, new_name))

        # Сохраняем путь в сессию
        session['download_path'] = output_dir
        session['total'] = len(results)

        return jsonify({
            "success": True,
            "total": len(results),
            "sorted_count": len(results),
            "missing": [],
            "unmatched": [],
            "prompt_preview": prompt[:80],
            "results": results[:20]
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def get_image_description(image_path, model):
    try:
        img = Image.open(image_path)
        response = model.generate_content([
            "Опиши максимально точно и кратко, что происходит на картинке.",
            img
        ])
        return response.text.strip()
    except:
        return "Описание недоступно"


def get_sorted_order(descriptions, prompt, model):
    text = "\n".join([f"{i+1}. {d}" for i, d in enumerate(descriptions)])
    full_prompt = f"""Расставь номера кадров в хронологическом порядке по промпту:\n{prompt}\n\n{text}\n\nОтветь только номерами через запятую."""
    try:
        resp = model.generate_content(full_prompt)
        order = [int(x.strip())-1 for x in resp.text.split(",") if x.strip().isdigit()]
        return order if len(order) == len(descriptions) else list(range(len(descriptions)))
    except:
        return list(range(len(descriptions)))


@app.route('/download')
def download():
    download_path = session.get('download_path')
    if not download_path or not os.path.exists(download_path):
        return "Файлы не найдены. Попробуйте проанализировать заново.", 400

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in os.listdir(download_path):
            zipf.write(os.path.join(download_path, file), file)

    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name='sorted_frames.zip')


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
