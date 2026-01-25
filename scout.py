import os
import json
import asyncio
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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") 

STATE_FILE = "scout_history.json"

API_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# ============ ТОЧНЫЕ ЗАПРОСЫ (Hardcore Mode) ============
SEARCH_QUERIES = [
    # 1. Современные протоколы (VLESS, Reality, Hysteria, Tuic)
    # Ищем упоминание конкретных технологий маскировки
    {"name": "Xray & Sing-box Configs", "query": "vless reality hysteria2 tuic juicity sing-box config"},
    
    # 2. Списки маршрутизации (Белые списки, GeoSite, Rule-sets)
    # Это нужно для настройки Split Tunneling (Ютуб через VPN, Госуслуги напрямую)
    {"name": "Routing & Whitelists", "query": "antizapret geosite-russia whitelist rule-set moschina"},
    
    # 3. Обход DPI (Deep Packet Inspection)
    # Инструменты, которые дурят оборудование провайдера (Zapret, GoodbyeDPI)
    {"name": "DPI Bypass Tools", "query": "dpi-bypass zapret goodbyedpi kyber spoofing"},
    
    # 4. Клиенты и Панели (Настройка своих серверов)
    # Панели управления (3x-ui, Marzban) и клиенты (NekoBox, Hiddify)
    {"name": "Server & Clients", "query": "marzban 3x-ui nekobox hiddify amnezia setup"},
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
    """
    GPT фильтрует находки.
    Критерий: Это должно быть полезно для настройки ОБХОДА БЛОКИРОВОК.
    """
    
    title = item.get('name', '')
    desc = item.get('description', 'No description')
    url = item.get('html_url', '')
    lang = item.get('language', 'Unknown')
    topics = ", ".join(item.get('topics', []))
    
    prompt = f"""Ты инженер по обходу интернет-цензуры.
Я ищу СТРОГО технические вещи:
1. Конфигурации для VLESS / Reality / Hysteria.
2. Списки маршрутизации (Rule-sets, Geosite) для раздельного туннелирования.
3. Скрипты для обхода DPI (Zapret, Spoofing).
4. Инструкции по настройке клиентов (Sing-box, NekoBox).

Перед тобой репозиторий с GitHub.
Если это просто "очередной VPN на OpenVPN" или мусор — ответь SKIP.
Если это ПОЛЕЗНЫЙ инструмент, конфиг или список — напиши отчет.

Входные данные:
Название: {title}
Описание: {desc}
Теги: {topics}
Язык: {lang}

Формат отчета:
📦 [Название]
🛠 Тип: [Например: Конфиг VLESS / Список доменов / Утилита DPI]
💡 Суть: [Чем именно это полезно для обхода]"""

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
    print("🕵️‍♂️ Scout Radar (VLESS/DPI Edition) starting...")
    posted_ids = load_state()
    
    for category in SEARCH_QUERIES:
        print(f"📡 API Search: {category['name']}")
        
        # Сортировка по обновлению (самое свежее)
        url = f"https://api.github.com/search/repositories?q={category['query']}&sort=updated&order=desc&per_page=5"
        
        try:
            response = requests.get(url, headers=API_HEADERS, timeout=10)
            
            if response.status_code != 200:
                print(f"   ⚠️ API Error: {response.status_code}")
                continue
                
            items = response.json().get('items', [])
            
            if not items: continue

            for item in items[:3]:
                repo_id = str(item.get('id'))
                
                if repo_id in posted_ids: continue
                
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
            time.sleep(5)

    save_state(posted_ids)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
