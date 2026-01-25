import os
import json
import asyncio
import hashlib
import time
import requests
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from openai import OpenAI

# ============ CONFIG ============

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TARGET_CHANNEL_ID = os.getenv("CHANNEL_ID")
# Автоматический токен от GitHub Actions
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") 

STATE_FILE = "scout_history.json"

# Заголовки для авторизации в API
API_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# Что ищем (API запросы)
SEARCH_QUERIES = [
    # 1. DPI и цензура
    {"name": "DPI Bypass", "query": "topic:dpi topic:circumvention"},
    # 2. Новые протоколы
    {"name": "Next-Gen VPN", "query": "vless reality hysteria2 sing-box"},
    # 3. Списки маршрутизации
    {"name": "Routing Lists", "query": "antizapret russia whitelist geoip"},
    # 4. Туннели
    {"name": "Tunneling", "query": "tunnel obfuscation vpn"},
]

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ============ LOGIC ============

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: return json.load(f)
        except: pass
    return []

def save_state(posted_ids):
    with open(STATE_FILE, "w") as f:
        json.dump(posted_ids[-400:], f)

async def analyze_repo(item):
    """GPT оценивает репозиторий из API"""
    
    # Собираем инфо из JSON
    title = item.get('name', '')
    desc = item.get('description', 'No description')
    url = item.get('html_url', '')
    lang = item.get('language', 'Unknown')
    stars = item.get('stargazers_count', 0)
    
    prompt = f"""Ты эксперт по обходу интернет-цензуры.
Я ищу ТОЛЬКО новые технические инструменты (VPN, DPI bypass).
Перед тобой данные о репозитории GitHub.

Твоя задача:
1. Понять, что это.
2. Если это мусор, просто список прокси, старый форк или не имеет отношения к обходу блокировок — ответь SKIP.
3. Если это реальный инструмент — напиши отчет.

Входные данные:
Name: {title}
Desc: {desc}
Lang: {lang}
Stars: {stars}

Формат ответа:
📦 [Название]
⭐ Звезд: {stars} | Язык: {lang}
💡 Суть: [Что делает и зачем нужно]"""

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = resp.choices[0].message.content.strip()
        
        if "SKIP" in answer or len(answer) < 20: return None
        return answer + f"\n\n🔗 <a href='{url}'>Открыть на GitHub</a>"
    except: return None

async def main():
    print("🕵️‍♂️ Scout Radar starting (API Mode)...")
    posted_ids = load_state()
    
    for category in SEARCH_QUERIES:
        print(f"📡 API Search: {category['name']}")
        
        # Формируем URL для поиска: сортировка по обновлению, порядок убывающий
        url = f"https://api.github.com/search/repositories?q={category['query']}&sort=updated&order=desc&per_page=5"
        
        try:
            response = requests.get(url, headers=API_HEADERS, timeout=10)
            
            if response.status_code != 200:
                print(f"   ⚠️ API Error: {response.status_code} - {response.text}")
                continue
                
            data = response.json()
            items = data.get('items', [])
            
            if not items:
                print("   ⚠️ Ничего не найдено.")
                continue

            # Берем топ-3 самых свежих
            for item in items[:3]:
                # Уникальный ID = ID репозитория в базе GitHub
                repo_id = str(item.get('id'))
                
                if repo_id in posted_ids: 
                    # print(f"   Skip seen: {item['name']}")
                    continue
                
                print(f"   🔍 Analyzing: {item['name']}")
                report = await analyze_repo(item)
                
                if report:
                    print("   🚨 HIT! Sending...")
                    try:
                        await bot.send_message(
                            TARGET_CHANNEL_ID, 
                            text=f"🛡 <b>GITHUB RADAR: {category['name']}</b>\n\n{report}",
                            disable_web_page_preview=True
                        )
                        posted_ids.append(repo_id)
                        await asyncio.sleep(3)
                    except Exception as e:
                        print(f"Telegram Error: {e}")
                else:
                    print("   ⏩ Skip (GPT rejected)")
                    posted_ids.append(repo_id)
                
        except Exception as e:
            print(f"Request Error: {e}")
            time.sleep(5) # Пауза при ошибке

    save_state(posted_ids)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
