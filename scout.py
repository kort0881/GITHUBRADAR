import os
import json
import asyncio
import time
import requests
from datetime import datetime, timedelta, timezone
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

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ============ ТРИ ТИПА ПОИСКА ============

# 1. ПОИСК ПО РЕПОЗИТОРИЯМ
REPO_SEARCHES = [
    {"name": "🇷🇺 AntiZapret", "query": "antizapret"},
    {"name": "🇷🇺 Antifilter", "query": "antifilter"},
    {"name": "🇷🇺 Geosite Russia", "query": "geosite-russia"},
    {"name": "🇷🇺 Russia Whitelist", "query": "russia+whitelist+domains"},
    {"name": "🔧 Zapret DPI", "query": "zapret"},
    {"name": "🔧 ByeDPI", "query": "byedpi"},
    {"name": "🔧 GoodbyeDPI", "query": "goodbyedpi"},
    {"name": "🔧 Marzban", "query": "marzban"},
    {"name": "🔧 3X-UI", "query": "3x-ui"},
    {"name": "🔧 Hiddify", "query": "hiddify-next"},
]

# 2. ПОИСК ПО КОДУ
CODE_SEARCHES = [
    {"name": "📄 VLESS Configs", "query": "vless://+extension:txt"},
    {"name": "📄 Hysteria2 Configs", "query": "hysteria2://+extension:txt"},
    {"name": "📄 Trojan Configs", "query": "trojan://+extension:txt"},
    {"name": "📄 Reality Configs", "query": "reality+pbk+extension:txt"},
]

# 3. ИЗВЕСТНЫЕ АГРЕГАТОРЫ
KNOWN_AGGREGATORS = [
    {"owner": "yebekhe", "repo": "TelegramV2rayCollector", "name": "🔥 Yebekhe Collector"},
    {"owner": "mahdibland", "repo": "V2RayAggregator", "name": "🔥 MahdiBland Aggregator"},
    {"owner": "barry-far", "repo": "V2ray-Configs", "name": "🔥 Barry-Far Configs"},
    {"owner": "Epodonios", "repo": "v2ray-configs", "name": "🔥 Epodonios Configs"},
    {"owner": "freefq", "repo": "free", "name": "🔥 FreeFQ"},
    {"owner": "Pawdroid", "repo": "Free-servers", "name": "🔥 Pawdroid Free"},
    {"owner": "mfuu", "repo": "v2ray", "name": "🔥 MFUU V2ray"},
    {"owner": "ermaozi", "repo": "get_subscribe", "name": "🔥 Ermaozi Subscribe"},
    {"owner": "aiboboxx", "repo": "v2rayfree", "name": "🔥 V2RayFree"},
    {"owner": "peasoft", "repo": "NoMoreWalls", "name": "🔥 NoMoreWalls"},
]

# ============ FUNCTIONS ============

def load_state():
    """Загрузка состояния с миграцией старого формата"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                
            # Миграция: если это старый формат (список)
            if isinstance(data, list):
                print("   ⚠️ Миграция старого формата...")
                return {
                    "posted": data,
                    "aggregator_commits": {}
                }
            
            # Новый формат (словарь)
            if isinstance(data, dict):
                return {
                    "posted": data.get("posted", []),
                    "aggregator_commits": data.get("aggregator_commits", {})
                }
        except Exception as e:
            print(f"   ⚠️ Ошибка загрузки: {e}")
    
    # По умолчанию
    return {
        "posted": [],
        "aggregator_commits": {}
    }

def save_state(state):
    """Сохранение состояния"""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"   ⚠️ Ошибка сохранения: {e}")

def get_repo_last_commit(owner, repo):
    """Получить время последнего коммита"""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code == 200:
            commits = resp.json()
            if commits:
                return {
                    "date": commits[0]['commit']['committer']['date'],
                    "sha": commits[0]['sha'][:7],
                    "message": commits[0]['commit']['message'].split('\n')[0][:50],
                    "url": commits[0]['html_url']
                }
    except Exception as e:
        print(f"      Error: {e}")
    return None

def search_code(query):
    """Поиск по содержимому файлов"""
    url = f"https://api.github.com/search/code?q={query}&per_page=10"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json().get('items', [])
        elif resp.status_code == 403:
            print(f"      ⚠️ Rate limit на code search")
    except Exception as e:
        print(f"      Error: {e}")
    return []

def search_repos(query):
    """Поиск репозиториев"""
    url = f"https://api.github.com/search/repositories?q={query}&sort=updated&order=desc&per_page=5"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json().get('items', [])
    except Exception as e:
        print(f"      Error: {e}")
    return []

async def analyze_with_gpt(title, desc, topics, context):
    """GPT анализ"""
    prompt = f"""Ты эксперт по обходу цензуры.
    
Контекст: {context}

Репозиторий:
- Название: {title}
- Описание: {desc}
- Теги: {topics}

Это полезно для обхода блокировок? (Конфиги VPN, белые списки, DPI bypass)

Если мусор — ответь SKIP.
Если полезно — кратко (2-3 предложения)."""

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        answer = resp.choices[0].message.content.strip()
        if "SKIP" in answer.upper():
            return None
        return answer
    except Exception as e:
        print(f"      GPT Error: {e}")
        return None

async def main():
    print("=" * 50)
    print("🕵️ SCOUT RADAR v3.0 — Smart Search")
    print("=" * 50)
    
    # Загрузка состояния
    state = load_state()
    posted_ids = state["posted"]
    aggregator_commits = state["aggregator_commits"]
    
    print(f"\n📊 Загружено: {len(posted_ids)} постов, {len(aggregator_commits)} агрегаторов\n")
    
    # ============ 1. ПРОВЕРКА ИЗВЕСТНЫХ АГРЕГАТОРОВ ============
    print("=" * 50)
    print("📦 ЧАСТЬ 1: Проверка агрегаторов конфигов")
    print("=" * 50)
    
    for agg in KNOWN_AGGREGATORS:
        key = f"{agg['owner']}/{agg['repo']}"
        print(f"\n🔍 {agg['name']} ({key})")
        
        commit = get_repo_last_commit(agg['owner'], agg['repo'])
        
        if not commit:
            print(f"   ❌ Не удалось получить данные")
            continue
        
        last_known = aggregator_commits.get(key)
        
        if last_known != commit['sha']:
            print(f"   🆕 Новый коммит: {commit['sha']}")
            print(f"   📝 {commit['message']}")
            
            # Вычисляем возраст коммита
            try:
                commit_time = datetime.fromisoformat(commit['date'].replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                age = now - commit_time
                
                if age < timedelta(hours=1):
                    freshness = "🔥 < 1 часа назад"
                elif age < timedelta(hours=24):
                    freshness = f"✅ {int(age.total_seconds() // 3600)} ч. назад"
                else:
                    freshness = f"📅 {age.days} дн. назад"
            except:
                freshness = "📅 Недавно"
            
            try:
                msg = (
                    f"🔄 <b>{agg['name']}</b>\n\n"
                    f"📦 <code>{key}</code>\n"
                    f"⏰ {freshness}\n"
                    f"📝 <i>{commit['message']}</i>\n\n"
                    f"🔗 <a href='{commit['url']}'>Коммит</a> | "
                    f"<a href='https://github.com/{key}'>Репо</a>"
                )
                await bot.send_message(TARGET_CHANNEL_ID, msg, disable_web_page_preview=True)
                aggregator_commits[key] = commit['sha']
                print(f"   ✅ Отправлено!")
                await asyncio.sleep(2)
            except Exception as e:
                print(f"   TG Error: {e}")
        else:
            print(f"   ⏸ Без изменений (sha: {commit['sha']})")
        
        await asyncio.sleep(1)
    
    # ============ 2. ПОИСК ПО КОДУ ============
    print("\n" + "=" * 50)
    print("📄 ЧАСТЬ 2: Поиск конфигов в файлах")
    print("=" * 50)
    
    for search in CODE_SEARCHES:
        print(f"\n🔍 {search['name']}")
        
        items = search_code(search['query'])
        
        if not items:
            print(f"   Ничего не найдено")
            continue
            
        unique_repos = {}
        for item in items:
            repo = item.get('repository', {})
            repo_id = str(repo.get('id', ''))
            if repo_id and repo_id not in posted_ids and repo_id not in unique_repos:
                unique_repos[repo_id] = repo
        
        print(f"   Найдено уникальных: {len(unique_repos)}")
        
        for repo_id, repo in list(unique_repos.items())[:2]:
            name = repo.get('full_name', '')
            desc = repo.get('description', '') or ''
            url = repo.get('html_url', '')
            
            print(f"   📦 {name}")
            
            analysis = await analyze_with_gpt(name, desc, "", search['name'])
            
            if analysis:
                try:
                    msg = (
                        f"📄 <b>{search['name']}</b>\n\n"
                        f"📦 <code>{name}</code>\n"
                        f"💡 {analysis}\n\n"
                        f"🔗 <a href='{url}'>Открыть</a>"
                    )
                    await bot.send_message(TARGET_CHANNEL_ID, msg, disable_web_page_preview=True)
                    posted_ids.append(repo_id)
                    print(f"      ✅ Отправлено!")
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"      TG Error: {e}")
            else:
                print(f"      ⏩ GPT отклонил")
                posted_ids.append(repo_id)
        
        await asyncio.sleep(3)
    
    # ============ 3. ПОИСК ПО РЕПОЗИТОРИЯМ ============
    print("\n" + "=" * 50)
    print("🔧 ЧАСТЬ 3: Поиск инструментов и белых списков")
    print("=" * 50)
    
    for search in REPO_SEARCHES:
        print(f"\n🔍 {search['name']}")
        
        items = search_repos(search['query'])
        
        if not items:
            print(f"   Ничего не найдено")
            continue
        
        for item in items[:2]:
            repo_id = str(item.get('id', ''))
            
            if repo_id in posted_ids:
                continue
            
            name = item.get('full_name', '')
            desc = item.get('description', '') or ''
            url = item.get('html_url', '')
            stars = item.get('stargazers_count', 0)
            topics = ", ".join(item.get('topics', []))
            
            print(f"   📦 {name} (⭐{stars})")
            
            analysis = await analyze_with_gpt(name, desc, topics, search['name'])
            
            if analysis:
                try:
                    msg = (
                        f"🛠 <b>{search['name']}</b>\n\n"
                        f"📦 <code>{name}</code>\n"
                        f"⭐ {stars}\n"
                        f"💡 {analysis}\n\n"
                        f"🔗 <a href='{url}'>GitHub</a>"
                    )
                    await bot.send_message(TARGET_CHANNEL_ID, msg, disable_web_page_preview=True)
                    posted_ids.append(repo_id)
                    print(f"      ✅ Отправлено!")
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"      TG Error: {e}")
            else:
                print(f"      ⏩ GPT отклонил")
                posted_ids.append(repo_id)
        
        await asyncio.sleep(2)
    
    # ============ СОХРАНЕНИЕ ============
    state = {
        "posted": posted_ids[-500:],
        "aggregator_commits": aggregator_commits
    }
    save_state(state)
    
    await bot.session.close()
    print("\n" + "=" * 50)
    print("✅ Готово!")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
