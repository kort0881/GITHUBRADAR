import os
import json
import asyncio
import hashlib
import time

import feedparser
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from openai import OpenAI

# ============ CONFIG ============

# Ключи берем из Secrets
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TARGET_CHANNEL_ID = os.getenv("CHANNEL_ID") # Твой закрытый канал

STATE_FILE = "scout_history.json"

# ============ ЧТО ИЩЕМ (УМНЫЕ ЗАПРОСЫ) ============
GITHUB_SEARCHES = [
    # 1. Обход блокировок (Самое важное)
    {"name": "DPI Bypass & Anti-Censorship", "url": "https://github.com/search?o=desc&q=topic:dpi+topic:circumvention+sort:updated&type=Repositories.atom"},
    
    # 2. Новые протоколы (VLESS, Reality, Hysteria)
    {"name": "Next-Gen VPN Protocols", "url": "https://github.com/search?o=desc&q=vless+reality+hysteria2+sing-box+sort:updated&type=Repositories.atom"},
    
    # 3. Списки (Whitelists/Blacklists для РФ/Китая)
    {"name": "Routing Lists (Russia/China)", "url": "https://github.com/search?o=desc&q=antizapret+russia+whitelist+geoip+sort:updated&type=Repositories.atom"},
    
    # 4. Туннелирование
    {"name": "Tunneling Tools", "url": "https://github.com/search?o=desc&q=tunnel+obfuscation+sort:updated&type=Repositories.atom"},
]

# ============ INIT ============

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
        json.dump(posted_ids[-300:], f) # Храним последние 300

async def analyze_repo(entry):
    """GPT оценивает полезность находки"""
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
            feed = feedparser.parse(source['url'])
            # Берем 3 самых свежих репозитория из поиска
            for entry in feed.entries[:3]:
                uid = hashlib.md5(entry.link.encode()).hexdigest()
                
                if uid in posted_ids: continue
                
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
                        # Пауза чтобы не спамить
                        await asyncio.sleep(3)
                    except Exception as e:
                        print(f"Telegram Error: {e}")
                else:
                    posted_ids.append(uid) # Помечаем мусор как просмотренное
                
        except Exception as e:
            print(f"Feed Error: {e}")

    save_state(posted_ids)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
