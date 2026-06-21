from flask import Flask, request, render_template_string, send_file, jsonify, session
import os
import time
import zipfile
from io import BytesIO
import google.generativeai as genai
from PIL import Image
import tempfile
import shutil
import uuid

app = Flask(__name__)
app.secret_key = "optimized_frame_sorter_v2"

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "sorted_output"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ================== HTML ==================
HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Frame Sorter • v2</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        body { font-family: 'Inter', system_ui, sans-serif; }
        .dropzone { transition: all 0.3s ease; }
        .dropzone.dragover { background-color: #1e2937; border-color: #6366f1; }
    </style>
</head>
<body class="bg-zinc-950 text-zinc-200">
    <div class="max-w-5xl mx-auto px-6 py-10">
        <div class="flex items-center justify-between mb-8">
            <div class="flex items-center gap-x-3">
                <div class="w-11 h-11 bg-blue-600 rounded-2xl flex items-center justify-center">
                    <i class="fa-solid fa-film text-white text-3xl"></i>
                </div>
                <div>
                    <h1 class="text-4xl font-semibold tracking-tighter">AI Frame Sorter <span class="text-blue-400 text-2xl">v2</span></h1>
                    <p class="text-zinc-400 text-sm">Стабильная версия • Gemini 2.0 Flash</p>
                </div>
            </div>
        </div>

        <!-- Три ячейки -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
            
            <!-- API Key -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6">
                <div class="flex items-center gap-x-3 mb-4">
                    <div class="w-9 h-9 bg-emerald-600/20 text-emerald-400 rounded-2xl flex items-center justify-center">
                        <i class="fa-solid fa-key text-xl"></i>
                    </div>
                    <div class="font-semibold text-lg">Gemini API ключ</div>
                </div>
                <input type="password" id="api_key" class="w-full bg-zinc-950 border border-zinc-700 focus:border-emerald-500 rounded-2xl px-4 py-3.5 text-sm font-mono" placeholder="AIzaSy...">
                <div class="mt-3 text-xs text-emerald-400">
                    <a href="https://aistudio.google.com/app/apikey" target="_blank" class="underline">Получить ключ</a>
                </div>
            </div>

            <!-- Промпт -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6">
                <div class="flex items-center gap-x-3 mb-4">
                    <div class="w-9 h-9 bg-blue-600/20 text-blue-400 rounded-2xl flex items-center justify-center">
                        <i class="fa-solid fa-align-left text-xl"></i>
                    </div>
                    <div class="font-semibold text-lg">Промпт сцены</div>
                </div>
                <textarea id="prompt" rows="5" class="w-full bg-zinc-950 border border-zinc-700 focus:border-blue-500 rounded-2xl p-4 text-sm resize-y" placeholder="Опиши сцену подробно..."></textarea>
            </div>

            <!-- Загрузка кадров -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 flex flex-col">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-x-3">
                        <div class="w-9 h-9 bg-violet-600/20 text-violet-400 rounded-2xl flex items-center justify-center">
                            <i class="fa-solid fa-images text-xl"></i>
                        </div>
                        <div class="font-semibold text-lg">Кадры</div>
                    </div>
                    <div id="image-count" class="px-3 py-1 bg-zinc-800 text-xs font-medium rounded-2xl">0 / 300</div>
                </div>

                <div id="dropzone" class="dropzone flex-1 border-2 border-dashed border-zinc-700 hover:border-violet-600 rounded-3xl p-6 flex flex-col items-center justify-center cursor-pointer text-center">
                    <i class="fa-solid fa-cloud-upload-alt text-4xl text-zinc-600 mb-3"></i>
                    <div class="font-medium text-sm">Перетащи изображения</div>
                    <input type="file" id="file-input" multiple accept="image/*" class="hidden">
                </div>
                <div id="preview-container" class="mt-3 grid grid-cols-5 gap-1.5 hidden"></div>
            </div>
        </div>

        <!-- Кнопка -->
        <div class="flex flex-col md:flex-row items-center gap-4 justify-between bg-zinc-900 border border-zinc-800 rounded-3xl p-6">
            <div>
                <div class="text-sm text-zinc-400 mb-1">Ожидаемое количество кадров</div>
                <input type="number" id="expected_frames" value="287" class="bg-zinc-950 border border-zinc-700 rounded-2xl px-5 py-2.5 text-lg font-medium w-28">
            </div>
            
            <button id="analyze-btn" class="flex items-center justify-center gap-x-3 bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 transition-all text-white font-semibold py-4 px-10 rounded-2xl disabled:opacity-50 text-lg" disabled>
                <i class="fa-solid fa-magic mr-2"></i>
                <span>Анализировать и отсортировать</span>
            </button>
        </div>

        <!-- Прогресс -->
        <div id="progress-section" class="hidden mt-8">
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-8">
                <div class="flex justify-between mb-4">
                    <div class="font-semibold text-xl">Анализ и сортировка</div>
                    <div id="progress-percentage" class="text-4xl font-semibold text-blue-400">0%</div>
                </div>
                <div class="w-full bg-zinc-800 rounded-full h-3 mb-4">
                    <div id="progress-bar" class="h-3 bg-gradient-to-r from-blue-500 to-violet-600 rounded-full transition-all" style="width:0%"></div>
                </div>
                <div id="progress-status" class="text-sm text-zinc-400">Подготовка...</div>
            </div>
        </div>

        <!-- Результаты -->
        <div id="results-section" class="hidden mt-8">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-2xl font-semibold">Результаты</h2>
                <button onclick="downloadSorted()" class="flex items-center gap-x-2 bg-emerald-600 hover:bg-emerald-700 px-6 py-3 rounded-2xl font-medium">
                    <i class="fa-solid fa-download"></i>
                    <span>Скачать отсортированные кадры</span>
                </button>
            </div>
            
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6">
                <div id="results-table" class="text-sm"></div>
            </div>
        </div>
    </div>

    <script>
        let uploadedFiles = [];
        let sortedData = null;

        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('file-input');
        const previewContainer = document.getElementById('preview-container');
        const imageCount = document.getElementById('image-count');
        const analyzeBtn = document.getElementById('analyze-btn');

        dropzone.addEventListener('click', () => fileInput.click());
        dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
        dropzone.addEventListener('drop', e => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });
        fileInput.addEventListener('change', e => handleFiles(e.target.files));

        function handleFiles(files) {
            const valid = Array.from(files).filter(f => f.type.startsWith('image/'));
            uploadedFiles = [...uploadedFiles, ...valid].slice(0, 300);
            updatePreview();
            updateCount();
            analyzeBtn.disabled = uploadedFiles.length === 0;
        }

        function updateCount() {
            imageCount.innerHTML = `${uploadedFiles.length} / 300`;
        }

        function updatePreview() {
            previewContainer.innerHTML = '';
            previewContainer.classList.remove('hidden');
            uploadedFiles.slice(0, 10).forEach((file, index) => {
                const reader = new FileReader();
                reader.onload = e => {
                    const div = document.createElement('div');
                    div.className = 'relative group';
                    div.innerHTML = `
                        <img src="${e.target.result}" class="w-full aspect-square object-cover rounded-xl border border-zinc-700">
                        <button onclick="removeFile(${index}, event)" class="absolute -top-1 -right-1 bg-red-600 w-4 h-4 flex items-center justify-center rounded-full text-xs">
                            <i class="fa-solid fa-times"></i>
                        </button>
                    `;
                    previewContainer.appendChild(div);
                };
                reader.readAsDataURL(file);
            });
        }

        function removeFile(index, e) {
            e.stopImmediatePropagation();
            uploadedFiles.splice(index, 1);
            updatePreview();
            updateCount();
            analyzeBtn.disabled = uploadedFiles.length === 0;
        }

        analyzeBtn.addEventListener('click', async () => {
            const prompt = document.getElementById('prompt').value.trim();
            const apiKey = document.getElementById('api_key').value.trim();

            if (!prompt || !apiKey || uploadedFiles.length === 0) {
                alert("Заполните все поля");
                return;
            }

            document.getElementById('progress-section').classList.remove('hidden');
            document.getElementById('results-section').classList.add('hidden');
            analyzeBtn.disabled = true;

            const formData = new FormData();
            formData.append('api_key', apiKey);
            formData.append('prompt', prompt);
            uploadedFiles.forEach(f => formData.append('images', f, f.name));

            try {
                const res = await fetch('/analyze', { method: 'POST', body: formData });
                const data = await res.json();

                if (data.success) {
                    sortedData = data;
                    document.getElementById('progress-section').classList.add('hidden');
                    showResults(data);
                } else {
                    alert("Ошибка: " + data.error);
                    analyzeBtn.disabled = false;
                }
            } catch (err) {
                alert("Ошибка соединения: " + err.message);
                analyzeBtn.disabled = false;
            }
        });

        function showResults(data) {
            document.getElementById('results-section').classList.remove('hidden');
            const container = document.getElementById('results-table');
            container.innerHTML = '';

            let html = `<div class="grid grid-cols-1 gap-2">`;
            data.results.forEach(item => {
                html += `
                    <div class="flex justify-between items-center bg-zinc-950 p-3 rounded-xl">
                        <div class="font-mono text-blue-400">${item.new_index}</div>
                        <div class="text-xs text-zinc-400 flex-1 px-4">${item.original_name}</div>
                        <div class="text-xs">${item.description}</div>
                    </div>`;
            });
            html += `</div>`;
            container.innerHTML = html;
        }

        function downloadSorted() {
            if (!sortedData) return;
            window.location.href = '/download';
        }
    </script>
</body>
</html>
"""

# ================== РОУТЫ ==================

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/analyze', methods=['POST'])
def analyze():
    api_key = request.form.get('api_key', '').strip()
    prompt = request.form.get('prompt', '')

    if not api_key or not prompt:
        return jsonify({"success": False, "error": "API ключ или промпт не указан"})

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')   # ← АКТУАЛЬНАЯ МОДЕЛЬ
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

    temp_dir = tempfile.mkdtemp(dir=UPLOAD_FOLDER)
    image_paths = []

    # === СИЛЬНОЕ СЖАТИЕ КАРТИНОК ===
    for file in request.files.getlist('images'):
        if file.filename:
            path = os.path.join(temp_dir, file.filename)
            file.save(path)

            try:
                img = Image.open(path)
                img.thumbnail((512, 512))
                img = img.convert("RGB")
                img.save(path, "JPEG", quality=65, optimize=True)
            except:
                pass

            image_paths.append(path)

    if not image_paths:
        return jsonify({"success": False, "error": "Изображения не загружены"})

    try:
        descriptions = []
        for i, path in enumerate(image_paths):
            desc = get_image_description(path, model)
            descriptions.append({
                "path": path,
                "original_name": os.path.basename(path),
                "description": desc
            })
            time.sleep(1.4)

        order = get_sorted_order([d["description"] for d in descriptions], prompt, model)

        results = []
        for new_idx, old_idx in enumerate(order):
            item = descriptions[old_idx]
            results.append({
                "new_index": f"{new_idx+1:04d}",
                "original_name": item["original_name"],
                "description": item["description"][:75],
                "status": "matched"
            })

        session_id = str(uuid.uuid4())
        output_dir = os.path.join(OUTPUT_FOLDER, session_id)
        os.makedirs(output_dir, exist_ok=True)

        for new_idx, old_idx in enumerate(order):
            item = descriptions[old_idx]
            new_name = f"{new_idx+1:04d}_{item['original_name']}"
            shutil.copy(item["path"], os.path.join(output_dir, new_name))

        session['download_path'] = output_dir

        return jsonify({
            "success": True,
            "total": len(results),
            "results": results[:25]
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def get_image_description(image_path, model):
    try:
        img = Image.open(image_path)
        response = model.generate_content([
            "Опиши максимально кратко, что происходит на картинке. Одно предложение.",
            img
        ])
        return response.text.strip()
    except Exception as e:
        return f"Ошибка: {str(e)}"


def get_sorted_order(descriptions, prompt, model):
    text = "\n".join([f"{i+1}. {d}" for i, d in enumerate(descriptions)])
    full_prompt = f"""Ты режиссёр раскадровки. Расставь номера кадров в правильном хронологическом порядке по промпту:\n{prompt}\n\n{text}\n\nОтветь только номерами через запятую."""
    try:
        resp = model.generate_content(full_prompt)
        order = [int(x.strip()) - 1 for x in resp.text.split(",") if x.strip().isdigit()]
        return order if len(order) == len(descriptions) else list(range(len(descriptions)))
    except:
        return list(range(len(descriptions)))


@app.route('/download')
def download():
    path = session.get('download_path')
    if not path or not os.path.exists(path):
        return "Файлы не найдены", 400

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in os.listdir(path):
            zipf.write(os.path.join(path, file), file)
    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name='sorted_frames.zip')


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
