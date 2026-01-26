import os
import json
import asyncio
import time
import requests
from datetime import datetime, timedelta
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

# 1. ПОИСК ПО РЕПОЗИТОРИЯМ (названия, описания)
REPO_SEARCHES = [
    # Белые списки
    {"name": "🇷🇺 AntiZapret", "query": "antizapret"},
    {"name": "🇷🇺 Antifilter", "query": "antifilter"},
    {"name": "🇷🇺 Geosite Russia", "query": "geosite-russia"},
    {"name": "🇷🇺 Russia Whitelist", "query": "russia+whitelist+domains"},
    
    # Инструменты
    {"name": "🔧 Zapret DPI", "query": "zapret"},
    {"name": "🔧 ByeDPI", "query": "byedpi"},
    {"name": "🔧 GoodbyeDPI", "query": "goodbyedpi"},
    {"name": "🔧 Marzban", "query": "marzban"},
    {"name": "🔧 3X-UI", "query": "3x-ui"},
    {"name": "🔧 Hiddify", "query": "hiddify-next"},
]

# 2. ПОИСК ПО КОДУ/ФАЙЛАМ (ищет ВНУТРИ файлов!)
CODE_SEARCHES = [
    # Это ищет файлы где есть строки с конфигами
    {"name": "📄 VLESS Configs", "query": "vless://+extension:txt", "type": "code"},
    {"name": "📄 Hysteria2 Configs", "query": "hysteria2://+extension:txt", "type": "code"},
    {"name": "📄 Trojan Configs", "query": "trojan://+extension:txt", "type": "code"},
    {"name": "📄 SS Configs", "query": "ss://+extension:txt", "type": "code"},
    {"name": "📄 VMess Configs", "query": "vmess://+extension:txt", "type": "code"},
    {"name": "📄 Reality Configs", "query": "reality+pbk+extension:txt", "type": "code"},
]

# 3. ИЗВЕСТНЫЕ АГРЕГАТОРЫ (проверяем напрямую их активность)
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
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"posted": [], "aggregator_commits": {}}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_repo_last_commit(owner, repo):
    """Получить время последнего коммита"""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code == 200:
            commits = resp.json()
            if commits:
                commit_date = commits[0]['commit']['committer']['date']
                commit_sha = commits[0]['sha'][:7]
                commit_msg = commits[0]['commit']['message'][:50]
                return {
                    "date": commit_date,
                    "sha": commit_sha,
                    "message": commit_msg,
                    "url": commits[0]['html_url']
                }
    except:
        pass
    return None

def search_code(query):
    """Поиск по содержимому файлов"""
    url = f"https://api.github.com/search/code?q={query}&per_page=10"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json().get('items', [])
    except:
        pass
    return []

def search_repos(query):
    """Поиск репозиториев"""
    url = f"https://api.github.com/search/repositories?q={query}&sort=updated&order=desc&per_page=5"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json().get('items', [])
    except:
        pass
    return []

async def analyze_with_gpt(title, desc, topics, context):
    """GPT анализ"""
    prompt = f"""Ты эксперт по обходу цензуры.
    
Контекст: {context}

Репозиторий:
- Название: {title}
- Описание: {desc}
- Теги: {topics}

Это полезно для обхода блокировок в России?
(Конфиги VPN, белые списки, DPI bypass, панели управления)

Если мусор — ответь SKIP.
Если полезно — кратко опиши (2-3 предложения)."""

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
    except:
        return None

async def main():
    print("=" * 50)
    print("🕵️ SCOUT RADAR v3.0 — Smart Search")
    print("=" * 50)
    
    state = load_state()
    posted_ids = state.get("posted", [])
    aggregator_commits = state.get("aggregator_commits", {})
    
    # ============ 1. ПРОВЕРКА ИЗВЕСТНЫХ АГРЕГАТОРОВ ============
    print("\n📦 ЧАСТЬ 1: Проверка агрегаторов конфигов\n")
    
    for agg in KNOWN_AGGREGATORS:
        key = f"{agg['owner']}/{agg['repo']}"
        print(f"   🔍 {agg['name']}...")
        
        commit = get_repo_last_commit(agg['owner'], agg['repo'])
        
        if not commit:
            print(f"      ❌ Не удалось получить данные")
            continue
        
        last_known = aggregator_commits.get(key)
        
        # Новый коммит?
        if last_known != commit['sha']:
            print(f"      🆕 Новый коммит: {commit['sha']}")
            print(f"      📝 {commit['message']}")
            
            # Проверяем насколько свежий
            commit_time = datetime.fromisoformat(commit['date'].replace('Z', '+00:00'))
            age = datetime.now(commit_time.tzinfo) - commit_time
            
            if age < timedelta(hours=24):
                freshness = "🔥 Свежий" if age < timedelta(hours=1) else "✅ Сегодня"
            else:
                freshness = f"📅 {age.days}д назад"
            
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
                await asyncio.sleep(1)
            except Exception as e:
                print(f"      TG Error: {e}")
        else:
            print(f"      ⏸ Без изменений")
        
        await asyncio.sleep(1)
    
    # ============ 2. ПОИСК ПО КОДУ (внутри файлов) ============
    print("\n📄 ЧАСТЬ 2: Поиск конфигов в файлах\n")
    
    for search in CODE_SEARCHES:
        print(f"   🔍 {search['name']}...")
        
        items = search_code(search['query'])
        unique_repos = {}
        
        for item in items:
            repo = item.get('repository', {})
            repo_id = str(repo.get('id', ''))
            
            if repo_id and repo_id not in posted_ids and repo_id not in unique_repos:
                unique_repos[repo_id] = repo
        
        print(f"      Найдено уникальных: {len(unique_repos)}")
        
        for repo_id, repo in list(unique_repos.items())[:2]:
            name = repo.get('full_name', '')
            desc = repo.get('description', '')
            url = repo.get('html_url', '')
            
            analysis = await analyze_with_gpt(
                name, desc, "", 
                f"Найден через поиск: {search['query']}"
            )
            
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
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"      TG Error: {e}")
        
        await asyncio.sleep(2)
    
    # ============ 3. ПОИСК ПО РЕПОЗИТОРИЯМ ============
    print("\n🔧 ЧАСТЬ 3: Поиск инструментов и белых списков\n")
    
    for search in REPO_SEARCHES:
        print(f"   🔍 {search['name']}...")
        
        items = search_repos(search['query'])
        
        for item in items[:2]:
            repo_id = str(item.get('id', ''))
            
            if repo_id in posted_ids:
                continue
            
            name = item.get('full_name', '')
            desc = item.get('description', '') or ''
            url = item.get('html_url', '')
            stars = item.get('stargazers_count', 0)
            topics = ", ".join(item.get('topics', []))
            
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
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"      TG Error: {e}")
        
        await asyncio.sleep(2)
    
    # ============ СОХРАНЕНИЕ ============
    state = {
        "posted": posted_ids[-500:],
        "aggregator_commits": aggregator_commits
    }
    save_state(state)
    
    await bot.session.close()
    print("\n✅ Готово!")

if __name__ == "__main__":
    asyncio.run(main())
