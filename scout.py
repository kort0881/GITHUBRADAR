import os
import json
import asyncio
import hashlib
import time

import requests  # <--- Добавили requests для обхода защиты
import feedparser
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from openai import OpenAI

# ============ CONFIG ============

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TARGET_CHANNEL_ID = os.getenv("CHANNEL_ID")

STATE_FILE = "scout_history.json"

# Заголовки, чтобы GitHub не блокировал нас
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/atom+xml,application/xml,text/xml"
}

GITHUB_SEARCHES = [
    {"name": "DPI Bypass", "url": "https://github.com/search?o=desc&q=topic:dpi+topic:circumvention+sort:updated&type=Repositories.atom"},
    {"name": "Next-Gen VPN", "url": "https://github.com/search?o=desc&q=vless+reality+hysteria2+sing-box+sort:updated&type=Repositories.atom"},
    {"name": "Routing Lists", "url": "https://github.com/search?o=desc&q=antizapret+russia+whitelist+geoip+sort:updated&type=Repositories.atom"},
    {"name": "Tunneling", "url": "https://github.com/search?o=desc&q=tunnel+obfuscation+sort:updated&type=Repositories.atom"},
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
        json.dump(posted_ids[-300:], f)

async def analyze_repo(entry):
    prompt = """Ты эксперт по обходу интернет-цензуры.
Я ищу ТОЛЬКО новые технические инструменты (VPN, DPI bypass, Routing lists).
Перед тобой репозиторий с GitHub.

Твоя задача:
1. Понять, что это.
2. Если это мусор, старый форк, домашка студента или просто список прокси — ответь SKIP.
3. Если это реальный инструмент, скрипт или полезный список доменов — напиши короткий отчет.

Формат:
📦 [Название]
🛠 Технологии: [Протоколы/Язык]
💡 Суть: [Что делает и зачем нужно в 2025 году]"""

    text = f"Title: {entry.title}\nDesc: {entry.get('summary', '')}\nLink: {entry.link}"

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}]
        )
        answer = resp.choices[0].message.content.strip()
        
        if "SKIP" in answer or len(answer) < 20: return None
        return answer + f"\n\n🔗 <a href='{entry.link}'>Открыть на GitHub</a>"
    except: return None

async def main():
    print("🕵️‍♂️ Scout Radar starting...")
    posted_ids = load_state()
    
    for source in GITHUB_SEARCHES:
        print(f"📡 Scanning: {source['name']}")
        try:
            # --- ИЗМЕНЕНИЕ: Скачиваем через Requests с заголовками ---
            response = requests.get(source['url'], headers=HEADERS, timeout=15)
            
            if response.status_code != 200:
                print(f"   ⚠️ Ошибка доступа к GitHub: {response.status_code}")
                continue
                
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                print("   ⚠️ Лента пустая (или GitHub изменил формат).")
                continue

            for entry in feed.entries[:3]:
                uid = hashlib.md5(entry.link.encode()).hexdigest()
                
                if uid in posted_ids: 
                    # print("   Уже видели") 
                    continue
                
                print(f"   🔍 Analyzing: {entry.title}")
                report = await analyze_repo(entry)
                
                if report:
                    print("   🚨 HIT! Sending to channel.")
                    try:
                        await bot.send_message(
                            TARGET_CHANNEL_ID, 
                            text=f"🛡 <b>GITHUB RADAR: {source['name']}</b>\n\n{report}",
                            disable_web_page_preview=True
                        )
                        posted_ids.append(uid)
                        await asyncio.sleep(3)
                    except Exception as e:
                        print(f"Telegram Error: {e}")
                else:
                    print("   ⏩ Skip (мусор)")
                    posted_ids.append(uid)
                
        except Exception as e:
            print(f"Feed Error: {e}")

    save_state(posted_ids)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
