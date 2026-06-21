from flask import Flask, request, render_template_string, send_file, jsonify
import os
import time
import zipfile
from pathlib import Path
from io import BytesIO
try:
    from google import genai as google_genai
    USE_NEW_SDK = True
except ImportError:
    import google.generativeai as genai
    USE_NEW_SDK = False

from PIL import Image
import tempfile
import shutil

app = Flask(__name__)

# ================== НАСТРОЙКИ ==================
# API ключ теперь вводится в интерфейсе (не нужно редактировать код)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "sorted_output"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ================== HTML ШАБЛОН ==================
HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Frame Sorter • 250+ кадров</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&amp;family=Space+Grotesk:wght@500;600&amp;display=swap');
        
        body {
            font-family: 'Inter', system_ui, sans-serif;
        }
        
        .title-font {
            font-family: 'Space Grotesk', 'Inter', sans-serif;
            font-weight: 600;
        }

        .dropzone {
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .dropzone.dragover {
            background-color: #f0f9ff;
            border-color: #3b82f6;
        }

        .image-preview {
            max-height: 120px;
            object-fit: cover;
        }

        .progress-bar {
            transition: width 0.4s ease;
        }

        .frame-card {
            transition: all 0.2s ease;
        }

        .result-table {
            font-size: 0.875rem;
        }
    </style>
</head>
<body class="bg-zinc-950 text-zinc-200">
    <div class="max-w-5xl mx-auto px-6 py-10">
        <!-- Header -->
        <div class="flex items-center justify-between mb-10">
            <div>
                <div class="flex items-center gap-x-3">
                    <div class="w-11 h-11 bg-blue-600 rounded-2xl flex items-center justify-center">
                        <i class="fa-solid fa-film text-white text-3xl"></i>
                    </div>
                    <div>
                        <h1 class="title-font text-4xl font-semibold tracking-tighter">AI Frame Sorter</h1>
                        <p class="text-zinc-400 text-sm">Умная расстановка кадров по промпту</p>
                    </div>
                </div>
            </div>
            <div class="text-right">
                <div class="text-xs text-zinc-500">Gemini 1.5 Flash</div>
                <div class="text-emerald-400 text-sm font-medium">250–300 кадров • бесплатно</div>
            </div>
        </div>

        <!-- Три красивые ячейки -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
            
            <!-- Ячейка 1: API Key -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6">
                <div class="flex items-center gap-x-3 mb-4">
                    <div class="w-9 h-9 bg-emerald-600/20 text-emerald-400 rounded-2xl flex items-center justify-center">
                        <i class="fa-solid fa-key text-xl"></i>
                    </div>
                    <div>
                        <div class="font-semibold text-lg">Gemini API ключ</div>
                        <div class="text-xs text-emerald-400">Бесплатно</div>
                    </div>
                </div>
                
                <input type="password" id="api_key" 
                       class="w-full bg-zinc-950 border border-zinc-700 focus:border-emerald-500 rounded-2xl px-4 py-3.5 text-sm font-mono"
                       placeholder="AIzaSy...">
                
                <div class="mt-3 text-[10px] text-emerald-400 flex items-center gap-x-1">
                    <i class="fa-solid fa-external-link-alt"></i>
                    <a href="https://aistudio.google.com/app/apikey" target="_blank" class="underline hover:text-emerald-300">Получить ключ</a>
                </div>
            </div>

            <!-- Ячейка 2: Промпт -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6">
                <div class="flex items-center gap-x-3 mb-4">
                    <div class="w-9 h-9 bg-blue-600/20 text-blue-400 rounded-2xl flex items-center justify-center">
                        <i class="fa-solid fa-align-left text-xl"></i>
                    </div>
                    <div class="font-semibold text-lg">Промпт сцены</div>
                </div>
                
                <textarea id="prompt" rows="5" 
                          class="w-full bg-zinc-950 border border-zinc-700 focus:border-blue-500 rounded-2xl p-4 text-sm resize-y"
                          placeholder="Опиши сцену подробно..."></textarea>
                
                <div class="mt-2 text-xs text-zinc-500">Можно указать несколько сцен</div>
            </div>

            <!-- Ячейка 3: Загрузка файлов -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 flex flex-col">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-x-3">
                        <div class="w-9 h-9 bg-violet-600/20 text-violet-400 rounded-2xl flex items-center justify-center">
                            <i class="fa-solid fa-images text-xl"></i>
                        </div>
                        <div class="font-semibold text-lg">Кадры</div>
                    </div>
                    <div id="image-count" 
                         class="px-3 py-1 bg-zinc-800 text-xs font-medium rounded-2xl flex items-center gap-x-1">
                        <span>0</span> / 300
                    </div>
                </div>

                <!-- Dropzone -->
                <div id="dropzone"
                     class="dropzone flex-1 border-2 border-dashed border-zinc-700 hover:border-violet-600 transition-colors rounded-3xl p-6 flex flex-col items-center justify-center cursor-pointer text-center">
                    <i class="fa-solid fa-cloud-upload-alt text-4xl text-zinc-600 mb-3"></i>
                    <div class="font-medium text-sm">Перетащи изображения</div>
                    <div class="text-xs text-zinc-400 mt-1">или нажми для выбора</div>
                    <input type="file" id="file-input" multiple accept="image/*" class="hidden">
                </div>

                <div id="preview-container" class="mt-3 grid grid-cols-5 gap-1.5 hidden"></div>
            </div>
            
        </div>

        <!-- Кнопка + Ожидаемое количество -->
        <div class="flex flex-col md:flex-row items-center gap-4 justify-between bg-zinc-900 border border-zinc-800 rounded-3xl p-6">
            <div class="flex items-center gap-x-4 w-full md:w-auto">
                <div>
                    <div class="text-sm text-zinc-400 mb-1">Ожидаемое количество кадров</div>
                    <input type="number" id="expected_frames" value="287" 
                           class="bg-zinc-950 border border-zinc-700 rounded-2xl px-5 py-2.5 text-lg font-medium w-28">
                </div>
            </div>
            
            <button id="analyze-btn"
                    class="flex-1 md:flex-none w-full md:w-auto flex items-center justify-center gap-x-3 bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 transition-all text-white font-semibold py-4 px-10 rounded-2xl disabled:opacity-50 text-lg shadow-xl"
                    disabled>
                <i class="fa-solid fa-magic mr-2"></i>
                <span>Анализировать и отсортировать</span>
            </button>
        </div>

        <!-- Красивый прогресс-бар -->
        <div id="progress-section" class="hidden mt-8">
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-8">
                <div class="flex items-center justify-between mb-6">
                    <div>
                        <div class="font-semibold text-xl">Анализ и сортировка</div>
                        <div id="progress-status" class="text-sm text-zinc-400 mt-1">Подготовка...</div>
                    </div>
                    <div id="progress-percentage" 
                         class="text-4xl font-semibold tabular-nums text-blue-400">0%</div>
                </div>
                
                <!-- Progress bar -->
                <div class="w-full bg-zinc-800 rounded-full h-3 mb-6 overflow-hidden">
                    <div id="progress-bar" 
                         class="progress-bar h-3 bg-gradient-to-r from-blue-500 via-violet-500 to-blue-600 rounded-full transition-all duration-300"
                         style="width: 0%"></div>
                </div>
                
                <div class="grid grid-cols-3 gap-4 text-xs">
                    <div class="flex items-center gap-x-2">
                        <div class="w-2.5 h-2.5 bg-emerald-400 rounded-full animate-pulse"></div>
                        <span id="step-1">Анализ изображений</span>
                    </div>
                    <div class="flex items-center gap-x-2">
                        <div class="w-2.5 h-2.5 bg-zinc-600 rounded-full" id="step-dot-2"></div>
                        <span id="step-2" class="text-zinc-400">Сортировка по промпту</span>
                    </div>
                    <div class="flex items-center gap-x-2">
                        <div class="w-2.5 h-2.5 bg-zinc-600 rounded-full" id="step-dot-3"></div>
                        <span id="step-3" class="text-zinc-400">Финализация</span>
                    </div>
                </div>
                
                <div class="mt-5 text-xs text-zinc-500 flex justify-between">
                    <div id="progress-detail">Обработано: <span id="processed-count">0</span> / <span id="total-count">0</span></div>
                    <div>Примерно 10–18 минут</div>
                </div>
            </div>
        </div>

        <!-- Results Section -->
        <div id="results-section" class="hidden mt-8">
            <div class="flex items-center justify-between mb-4">
                <div>
                    <h2 class="text-2xl font-semibold">Результаты</h2>
                    <p id="result-subtitle" class="text-zinc-400"></p>
                </div>
                <button onclick="downloadSorted()"
                        class="flex items-center gap-x-2 bg-emerald-600 hover:bg-emerald-700 px-6 py-3 rounded-2xl font-medium">
                    <i class="fa-solid fa-download"></i>
                    <span>Скачать отсортированные кадры</span>
                </button>
            </div>

            <!-- Stats -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <div class="bg-zinc-900 border border-zinc-800 p-4 rounded-3xl">
                    <div class="text-xs text-zinc-400">Проанализировано</div>
                    <div id="stat-total" class="text-3xl font-semibold mt-1">—</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 p-4 rounded-3xl">
                    <div class="text-xs text-zinc-400">Правильно расставлено</div>
                    <div id="stat-sorted" class="text-3xl font-semibold mt-1 text-emerald-400">—</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 p-4 rounded-3xl">
                    <div class="text-xs text-zinc-400">Пропущенные кадры</div>
                    <div id="stat-missing" class="text-3xl font-semibold mt-1 text-amber-400">—</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 p-4 rounded-3xl">
                    <div class="text-xs text-zinc-400">Не соответствуют</div>
                    <div id="stat-unmatched" class="text-3xl font-semibold mt-1 text-red-400">—</div>
                </div>
            </div>

            <!-- Table of results -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl overflow-hidden">
                <div class="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
                    <div class="font-semibold">Отсортированный порядок</div>
                    <div class="text-xs px-3 py-1 bg-zinc-800 rounded-full">Первые 20 кадров</div>
                </div>
                
                <div class="overflow-auto max-h-[420px]">
                    <table class="w-full result-table">
                        <thead class="bg-zinc-950 sticky top-0">
                            <tr class="border-b border-zinc-800">
                                <th class="text-left px-6 py-3 w-16 font-medium text-zinc-400">Новый №</th>
                                <th class="text-left px-6 py-3 font-medium text-zinc-400">Оригинальное имя</th>
                                <th class="text-left px-6 py-3 font-medium text-zinc-400">Описание</th>
                                <th class="text-left px-6 py-3 w-24 font-medium text-zinc-400">Статус</th>
                            </tr>
                        </thead>
                        <tbody id="results-table" class="divide-y divide-zinc-800 text-sm"></tbody>
                    </table>
                </div>
            </div>
            
            <div class="mt-3 text-xs text-zinc-500 px-1">
                Примечание: кадры с низким соответствием промпту выделены красным
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

        // Drag & drop
        dropzone.addEventListener('click', () => fileInput.click());
        
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        
        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });
        
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });
        
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });

        function handleFiles(files) {
            const validFiles = Array.from(files).filter(f => f.type.startsWith('image/'));
            
            if (validFiles.length === 0) return;
            
            uploadedFiles = [...uploadedFiles, ...validFiles].slice(0, 300);
            updatePreview();
            updateCount();
            analyzeBtn.disabled = uploadedFiles.length === 0;
        }

        function updateCount() {
            imageCount.innerHTML = `<span>${uploadedFiles.length}</span> / 300`;
        }

        function updatePreview() {
            previewContainer.innerHTML = '';
            previewContainer.classList.remove('hidden');
            
            uploadedFiles.slice(0, 10).forEach((file, index) => {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const div = document.createElement('div');
                    div.className = 'relative group';
                    div.innerHTML = `
                        <img src="${e.target.result}" class="w-full aspect-square object-cover rounded-xl border border-zinc-700">
                        <div class="absolute bottom-0.5 right-0.5 bg-black/80 text-[9px] px-1 rounded font-mono">${index + 1}</div>
                        <button onclick="removeFile(${index}, event)" 
                                class="absolute -top-1 -right-1 bg-red-600 hover:bg-red-700 w-4 h-4 flex items-center justify-center rounded-full text-[9px] opacity-90 group-hover:opacity-100">
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

        // Main analysis function
        analyzeBtn.addEventListener('click', async () => {
            const prompt = document.getElementById('prompt').value.trim();
            const expected = parseInt(document.getElementById('expected_frames').value) || 0;
            
            if (!prompt) {
                alert("Пожалуйста, введи промпт");
                return;
            }
            
            if (uploadedFiles.length === 0) {
                alert("Загрузи изображения");
                return;
            }

            const apiKey = document.getElementById('api_key').value.trim();
            if (!apiKey) {
                alert("Пожалуйста, вставь свой Gemini API ключ");
                return;
            }

            // Показываем красивый прогресс-бар
            document.getElementById('progress-section').classList.remove('hidden');
            document.getElementById('results-section').classList.add('hidden');
            analyzeBtn.disabled = true;
            analyzeBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-2"></i> Анализирую...`;

            const formData = new FormData();
            formData.append('api_key', apiKey);
            formData.append('prompt', prompt);
            formData.append('expected_frames', expected);
            
            uploadedFiles.forEach((file) => {
                formData.append('images', file, file.name);
            });

            // Симуляция прогресса (реальный прогресс будет приходить позже)
            simulateProgress(uploadedFiles.length);

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                // Завершаем прогресс
                finishProgress();
                
                if (data.success) {
                    sortedData = data;
                    setTimeout(() => {
                        document.getElementById('progress-section').classList.add('hidden');
                        showResults(data);
                    }, 800);
                } else {
                    document.getElementById('progress-section').classList.add('hidden');
                    alert("Ошибка: " + (data.error || "Неизвестная ошибка"));
                    analyzeBtn.disabled = false;
                    analyzeBtn.innerHTML = `<i class="fa-solid fa-magic"></i> <span>Анализировать и отсортировать</span>`;
                }
            } catch (err) {
                document.getElementById('progress-section').classList.add('hidden');
                alert("Ошибка соединения: " + err.message);
                analyzeBtn.disabled = false;
                analyzeBtn.innerHTML = `<i class="fa-solid fa-magic"></i> <span>Анализировать и отсортировать</span>`;
            }
        });

        // Красивый прогресс-бар
        let progressInterval = null;

        function simulateProgress(totalImages) {
            const progressBar = document.getElementById('progress-bar');
            const percentEl = document.getElementById('progress-percentage');
            const statusEl = document.getElementById('progress-status');
            const processedEl = document.getElementById('processed-count');
            const totalEl = document.getElementById('total-count');
            
            totalEl.textContent = totalImages;
            processedEl.textContent = '0';
            
            let progress = 0;
            let processed = 0;
            const step = 100 / (totalImages * 1.8);
            
            progressInterval = setInterval(() => {
                progress += step;
                processed = Math.min(Math.floor((progress / 100) * totalImages), totalImages);
                
                if (progress > 100) progress = 100;
                
                progressBar.style.width = `${progress}%`;
                percentEl.textContent = `${Math.floor(progress)}%`;
                processedEl.textContent = processed;
                
                // Статусы
                if (progress < 35) {
                    statusEl.textContent = "Анализирую изображения с помощью Gemini...";
                    document.getElementById('step-1').classList.add('text-emerald-400');
                } else if (progress < 70) {
                    statusEl.textContent = "Сопоставляю кадры с промптом...";
                    document.getElementById('step-dot-2').classList.add('bg-emerald-400');
                    document.getElementById('step-2').classList.remove('text-zinc-400');
                    document.getElementById('step-2').classList.add('text-emerald-400');
                } else {
                    statusEl.textContent = "Расставляю кадры в правильном порядке...";
                    document.getElementById('step-dot-3').classList.add('bg-emerald-400');
                    document.getElementById('step-3').classList.remove('text-zinc-400');
                    document.getElementById('step-3').classList.add('text-emerald-400');
                }
            }, 650);
        }

        function finishProgress() {
            if (progressInterval) clearInterval(progressInterval);
            
            const progressBar = document.getElementById('progress-bar');
            const percentEl = document.getElementById('progress-percentage');
            const statusEl = document.getElementById('progress-status');
            
            progressBar.style.width = '100%';
            percentEl.textContent = '100%';
            statusEl.textContent = "Готово! Формирую результаты...";
        }

        function showResults(data) {
            document.getElementById('results-section').classList.remove('hidden');
            
            document.getElementById('stat-total').innerText = data.total;
            document.getElementById('stat-sorted').innerText = data.sorted_count;
            document.getElementById('stat-missing').innerText = data.missing.length;
            document.getElementById('stat-unmatched').innerText = data.unmatched.length;
            
            document.getElementById('result-subtitle').innerHTML = 
                `Проанализировано <strong>${data.total}</strong> кадров • Промпт: ${data.prompt_preview}`;

            const tbody = document.getElementById('results-table');
            tbody.innerHTML = '';

            // Show first 20 results
            const toShow = data.results.slice(0, 20);
            
            toShow.forEach(item => {
                const row = document.createElement('tr');
                row.className = 'hover:bg-zinc-950';
                
                const statusColor = item.status === 'matched' ? 'emerald' : 
                                   item.status === 'unmatched' ? 'red' : 'amber';
                
                row.innerHTML = `
                    <td class="px-6 py-3 font-mono text-blue-400 font-medium">${item.new_index}</td>
                    <td class="px-6 py-3 font-mono text-xs text-zinc-400">${item.original_name}</td>
                    <td class="px-6 py-3 text-xs text-zinc-300">${item.description}</td>
                    <td class="px-6 py-3">
                        <span class="inline-block px-3 py-px text-xs font-medium rounded-full 
                                     ${item.status === 'matched' ? 'bg-emerald-900 text-emerald-400' : 
                                       item.status === 'unmatched' ? 'bg-red-900 text-red-400' : 'bg-amber-900 text-amber-400'}">
                            ${item.status === 'matched' ? 'Подходит' : 
                              item.status === 'unmatched' ? 'Не подходит' : 'Пропущен'}
                        </span>
                    </td>
                `;
                tbody.appendChild(row);
            });
            
            if (data.results.length > 20) {
                const moreRow = document.createElement('tr');
                moreRow.innerHTML = `
                    <td colspan="4" class="px-6 py-4 text-center text-xs text-zinc-500">
                        ... и ещё ${data.results.length - 20} кадров (полный список в скачанном архиве)
                    </td>
                `;
                tbody.appendChild(moreRow);
            }
        }

        function downloadSorted() {
            if (!sortedData) return;
            
            // Create a download link to the backend
            window.location.href = '/download';
        }

        // Keyboard support
        document.addEventListener('keydown', function(e) {
            if (e.key === "Enter" && document.activeElement.id === "prompt") {
                e.preventDefault();
                if (!analyzeBtn.disabled) analyzeBtn.click();
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/analyze', methods=['POST'])
def analyze():
    api_key = request.form.get('api_key', '').strip()
    prompt = request.form.get('prompt', '')
    expected_frames = int(request.form.get('expected_frames', 0))
    
    if not api_key:
        return jsonify({"success": False, "error": "API ключ не указан"})
    
    if not prompt:
        return jsonify({"success": False, "error": "Промпт не указан"})
    
    # Настраиваем Gemini с ключом пользователя
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        return jsonify({"success": False, "error": f"Ошибка API ключа: {str(e)}"})

    # Сохраняем загруженные файлы
    temp_dir = tempfile.mkdtemp()
    image_paths = []
    
    for file in request.files.getlist('images'):
        if file.filename:
            path = os.path.join(temp_dir, file.filename)
            file.save(path)
            image_paths.append(path)
    
    if not image_paths:
        return jsonify({"success": False, "error": "Изображения не загружены"})

    try:
        # 1. Получаем описания всех изображений
        descriptions = []
        for i, path in enumerate(image_paths):
            desc = get_image_description(path, model)
            descriptions.append({
                "path": path,
                "original_name": os.path.basename(path),
                "description": desc
            })
            time.sleep(1.1)  # защита от rate limit

        # 2. Просим Gemini отсортировать
        order = get_sorted_order([d["description"] for d in descriptions], prompt, model)
        
        # 3. Формируем результаты
        results = []
        unmatched = []
        matched_count = 0
        
        for new_idx, old_idx in enumerate(order):
            item = descriptions[old_idx]
            status = "matched"
            
            # Простая проверка соответствия
            if "не подходит" in item["description"].lower() or len(item["description"]) < 15:
                status = "unmatched"
                unmatched.append(new_idx + 1)
            else:
                matched_count += 1
            
            results.append({
                "new_index": f"{new_idx+1:04d}",
                "original_name": item["original_name"],
                "description": item["description"][:120] + "..." if len(item["description"]) > 120 else item["description"],
                "status": status
            })
        
        # 4. Определяем пропущенные кадры
        missing = []
        if expected_frames > 0:
            for i in range(1, expected_frames + 1):
                if i not in [int(r["new_index"]) for r in results]:
                    missing.append(i)
        
        # 5. Сохраняем данные для скачивания
        global sorted_results, sorted_images
        sorted_results = results
        sorted_images = descriptions
        
        return jsonify({
            "success": True,
            "total": len(results),
            "sorted_count": matched_count,
            "missing": missing,
            "unmatched": unmatched,
            "prompt_preview": prompt[:80] + "..." if len(prompt) > 80 else prompt,
            "results": results
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

def get_image_description(image_path, model):
    try:
        img = Image.open(image_path)
        response = model.generate_content([
            "Опиши максимально точно и кратко, что происходит на картинке. "
            "Главные действия, позы, персонажи, окружение. 1-2 предложения.",
            img
        ])
        return response.text.strip()
    except Exception as e:
        return f"Ошибка анализа: {str(e)}"

def get_sorted_order(descriptions, prompt, model):
    text = "\n".join([f"{i+1}. {desc}" for i, desc in enumerate(descriptions)])
    
    full_prompt = f"""Ты — профессиональный режиссёр раскадровки видео.

Промпт сцены:
{prompt}

Описания всех кадров (в случайном порядке):
{text}

Задача: расположи номера кадров в правильном хронологическом порядке, 
максимально соответствующем промпту.

Если какой-то кадр совсем не соответствует промпту — всё равно включи его в конец списка.

Ответь ТОЛЬКО номерами через запятую. Пример: 7,2,15,3,28,9,41,12"""
    
    try:
        response = model.generate_content(full_prompt)
        order_str = response.text.strip()
        order = [int(x.strip()) - 1 for x in order_str.split(",") if x.strip().isdigit()]
        
        # Проверка
        if len(order) == len(descriptions):
            return order
        else:
            return list(range(len(descriptions)))
    except:
        return list(range(len(descriptions)))

@app.route('/download')
def download():
    global sorted_results, sorted_images
    
    if not sorted_results or not sorted_images:
        return "Нет данных для скачивания", 400
    
    # Создаём zip
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in sorted_results:
            # Находим оригинальный файл
            original = next((d for d in sorted_images if d["original_name"] == item["original_name"]), None)
            if original:
                new_name = f"{item['new_index']}_{item['original_name']}"
                zipf.write(original["path"], new_name)
    
    zip_buffer.seek(0)
    
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='sorted_frames.zip'
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
