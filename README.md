Вот профессиональный README с анимацией и детальным описанием для твоего скрипта **Scout Radar**.

***

# 📡 SCOUT RADAR v8.0

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub API](https://img.shields.io/badge/GitHub-API-black)](https://docs.github.com/en/rest)
[![Groq AI](https://img.shields.io/badge/Groq-AI-orange)](https://groq.com/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue)](https://core.telegram.org/bots)

**Автоматизированный радар для мониторинга инструментов обхода блокировок (DPI, VPN, Censorship).**
Скрипт отслеживает обновления ключевых репозиториев, ищет новые инструменты на GitHub, фильтрует их через AI и публикует в Telegram.

---

## 📟 Демонстрация работы

```
🕵️  SCOUT RADAR v8.0 (with releases tracking)
============================================================

🚀 Checking releases of tracked projects...
   🆕 Release: 🛡 Amnezia Client v4.1.0
   🆕 Release: ⚡ Xray-core v1.8.9

🔄 Checking commits of tracked projects...
   🆕 Commit: 🛠 Zapret (original) [f4a2b1]

📡 Checking config aggregators...
   🆕 📡 NoMoreWalls [a1b2c3]

🔍 Searching for new repositories...

🔍 Zapret Tools...
   🔍 Found candidate: bol-van/zapret-discord
   🤖 AI Analyzing batch (5 items)...
   ✅ Approved: bol-van/zapret-discord
   📝 Generating description...
   📤 Sending to Telegram...

🏁 Completed! Published: 5 posts
```

---

## ⚡ Основные возможности

### 1. 🎯 Трекинг ключевых проектов
Мониторинг **30+** важнейших репозиториев (Zapret, Amnezia, Xray, Sing-Box, GoodbyeDPI).
- **Релизы**: Мгновенное уведомление о выходе новых версий (Tags).
- **Коммиты**: Отслеживание изменений в коде для dev-веток.

### 2. 📡 Агрегаторы конфигов
Следит за популярными репозиториями-сборниками (SubCrawler, V2RayAggregator), чтобы вы получали свежие конфиги первыми.

### 3. 🔍 Глобальный поиск (Global Search)
Ежедневный скан GitHub по ключевым словам:
- `dpi-bypass`, `zapret`, `roskomnadzor`, `antizapret`
- `vless-reality`, `hysteria2`, `marzban`
- `russia-vpn`, `shadowsocks`

### 4. 🧠 AI-Фильтрация (Groq Llama 3)
- **Анализ релевантности**: AI читает описание репозитория и решает, полезный это инструмент или "мусор" (учебный проект, форк-спам).
- **Генерация описаний**: AI переводит и сокращает описание проекта на русский язык для поста.

### 5. 🛡 Умная защита
- **Rate Limit Check**: Следит за лимитами GitHub API.
- **Hieroglyph Filter**: Блокирует китайский спам и нерелевантный контент.
- **Fork Detector**: Игнорирует пустые форки без звезд.

---

## 🛠 Установка

### Требования
- Python 3.10+
- Аккаунт GitHub (для токена)
- Аккаунт Groq (для AI)

### 1. Клонирование
```bash
git clone https://github.com/yourusername/scout-radar.git
cd scout-radar
```

### 2. Виртуальное окружение
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```
*Зависимости: `aiogram`, `requests`, `groq`*

### 3. Настройка (.env)
Создайте файл `.env` или экспортируйте переменные:

```bash
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
CHANNEL_ID=@your_channel_id

# AI (Groq Cloud)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxx

# GitHub (Settings -> Developer settings -> Personal access tokens)
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4. Запуск
```bash
python scout_radar.py
```

---

## ⚙️ Конфигурация скрипта

Внутри `scout_radar.py` можно настроить списки отслеживания:

### `TRACKED_PROJECTS`
Список "элитных" репозиториев. Скрипт проверяет их на наличие новых **Релизов** и **Коммитов**.
```python
TRACKED_PROJECTS = [
    {"owner": "bol-van", "repo": "zapret", "name": "🛠 Zapret", "priority": "high"},
    {"owner": "XTLS", "repo": "Xray-core", "name": "⚡ Xray", "priority": "high"},
    # ... добавьте свои
]
```

### `FRESH_SEARCHES`
Поисковые запросы для обнаружения новых инструментов.
```python
FRESH_SEARCHES = [
    {"name": "DPI Bypass", "query": "dpi-bypass OR nodpi", "priority": 10},
    {"name": "Marzban", "query": "marzban-panel", "priority": 8},
]
```

---

## 💾 Хранение состояния

Скрипт создает файл `scout_history.json`.
**Не удаляйте его**, если не хотите получить дубликаты постов.

В файле хранится:
- `posted`: список ID репозиториев, которые уже были опубликованы.
- `commits`: последние SHA коммитов для отслеживаемых проектов.
- `releases`: последние теги релизов.

---

## 🤖 Как работает AI-анализ

Скрипт использует модель `llama-3.1-8b-instant` через Groq API.

1. **Batch Analysis**: Репозитории собираются в пачки по 5 штук.
2. **Prompt**:
   > "Отфильтруй репозитории для канала про обход блокировок... Темы: VPN, Zapret... Ответь GOOD или SKIP"
3. **Summarization**: Если репозиторий одобрен, AI генерирует краткое описание на русском языке (до 80 символов).

---

## 🐳 Docker Deployment

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY scout_radar.py .

CMD ["python", "scout_radar.py"]
```

**Запуск:**
```bash
docker build -t scout-radar .
docker run -d \
  -v $(pwd)/scout_history.json:/app/scout_history.json \
  --env-file .env \
  scout-radar
```

---

## 📊 Примеры постов в Telegram

### 1. Новый релиз
> 🚀 **Новый релиз: 🛡 Amnezia Client**
>
> 📦 `amnezia-vpn/amnezia-client`
> 🏷 Версия: **v4.6.0**
> ⏰ 🔥 Только что
>
> 📝 Added support for AmneziaWG on iOS...
>
> 🔗 [Скачать релиз](https://github.com...)

### 2. Новый инструмент (через поиск)
> **🛠 Zapret инструменты**
>
> 📦 `user/zapret-discord-fix`
> ⭐️ 45 | ⏰ 🔥 Сегодня
> 💡 Скрипт для автоматической настройки Zapret под Дискорд.
>
> 🔗 [Открыть на GitHub](https://github.com...)

---

## 📜 Лицензия

MIT License. Используйте свободно, создавайте свои агрегаторы Privacy-инструментов.

<div align="center">
    <strong>🛡 Keep the Internet Free 🛡</strong>
</div>
