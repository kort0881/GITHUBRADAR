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
MAX_AGE_DAYS = 3  # ⚡ Максимальный возраст — 3 дня

API_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ============ ПОИСКОВЫЕ ЗАПРОСЫ ============

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
    {"name": "🔧 Sing-box", "query": "sing-box+config"},
    {"name": "🔧 Xray Reality", "query": "xray+reality"},
]

CODE_SEARCHES = [
    {"name": "📄 VLESS Configs", "query": "vless://+extension:txt"},
    {"name": "📄 Hysteria2 Configs", "query": "hysteria2://+extension:txt"},
    {"name": "📄 Trojan Configs", "query": "trojan://+extension:txt"},
    {"name": "📄 Reality Configs", "query": "reality+pbk+extension:txt"},
]

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

def get_age_days(date_string):
    """Вычислить возраст в днях"""
    try:
        if not date_string:
            return 9999
        
        # Парсим дату
        if date_string.endswith('Z'):
            dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(date_string)
        
        now = datetime.now(timezone.utc)
        age = now - dt
        return age.days
    except:
        return 9999

def get_freshness_emoji(days):
    """Эмодзи в зависимости от свежести"""
    if days == 0:
        return "🔥 Сегодня"
    elif days == 1:
        return "✅ Вчера"
    elif days <= 3:
        return f"✅ {days} дн. назад"
    else:
        return f"⚠️ {days} дн. назад"

def is_fresh(date_string, max_days=MAX_AGE_DAYS):
    """Проверка: обновлялось ли за последние N дней"""
    return get_age_days(date_string) <= max_days

def load_state():
    """Загрузка состояния"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            
            if isinstance(data, list):
                return {"posted": data, "aggregator_commits": {}}
            
            if isinstance(data, dict):
                return {
                    "posted": data.get("posted", []),
                    "aggregator_commits": data.get("aggregator_commits", {})
                }
        except:
            pass
    
    return {"posted": [], "aggregator_commits": {}}

def save_state(state):
    """Сохранение состояния"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_repo_last_commit(owner, repo):
    """Получить последний коммит"""
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
    except:
        pass
    return None

def search_repos_fresh(query):
    """Поиск репозиториев с фильтром по дате"""
    # Добавляем pushed:> для фильтрации на уровне API
    date_filter = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime('%Y-%m-%d')
    full_query = f"{query}+pushed:>{date_filter}"
    
    url = f"https://api.github.com/search/repositories?q={full_query}&sort=updated&order=desc&per_page=10"
    
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json().get('items', [])
    except:
        pass
    return []

def search_code(query):
    """Поиск по коду"""
    url = f"https://api.github.com/search/code?q={query}&per_page=10"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json().get('items', [])
    except:
        pass
    return []

def get_repo_info(owner, repo):
    """Получить инфо о репозитории (для проверки свежести)"""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None

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
    except:
        return None

async def main():
    print("=" * 50)
    print("🕵️ SCOUT RADAR v3.1 — Fresh Only (≤3 дней)")
    print("=" * 50)
    
    state = load_state()
    posted_ids = state["posted"]
    aggregator_commits = state["aggregator_commits"]
    
    print(f"\n📊 История: {len(posted_ids)} постов")
    print(f"⏰ Фильтр: только обновления за {MAX_AGE_DAYS} дня\n")
    
    # ============ 1. АГРЕГАТОРЫ ============
    print("=" * 50)
    print("📦 ЧАСТЬ 1: Агрегаторы конфигов")
    print("=" * 50)
    
    for agg in KNOWN_AGGREGATORS:
        key = f"{agg['owner']}/{agg['repo']}"
        print(f"\n🔍 {agg['name']}")
        
        commit = get_repo_last_commit(agg['owner'], agg['repo'])
        
        if not commit:
            print(f"   ❌ Нет данных")
            continue
        
        age_days = get_age_days(commit['date'])
        freshness = get_freshness_emoji(age_days)
        
        # Проверяем свежесть
        if age_days > MAX_AGE_DAYS:
            print(f"   ⏭ Пропуск: {freshness} (>{MAX_AGE_DAYS} дней)")
            continue
        
        last_known = aggregator_commits.get(key)
        
        if last_known != commit['sha']:
            print(f"   🆕 Новый коммит: {commit['sha']} | {freshness}")
            
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
            print(f"   ⏸ Без изменений | {freshness}")
        
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
            repo_full_name = repo.get('full_name', '')
            
            if repo_id and repo_id not in posted_ids and repo_id not in unique_repos:
                # Получаем полную инфу для проверки свежести
                if '/' in repo_full_name:
                    owner, name = repo_full_name.split('/', 1)
                    full_info = get_repo_info(owner, name)
                    if full_info:
                        unique_repos[repo_id] = full_info
                        await asyncio.sleep(0.5)
        
        print(f"   Найдено уникальных: {len(unique_repos)}")
        
        for repo_id, repo in list(unique_repos.items())[:3]:
            name = repo.get('full_name', '')
            desc = repo.get('description', '') or ''
            url = repo.get('html_url', '')
            pushed_at = repo.get('pushed_at', '')
            
            age_days = get_age_days(pushed_at)
            freshness = get_freshness_emoji(age_days)
            
            # ⚡ ФИЛЬТР СВЕЖЕСТИ
            if age_days > MAX_AGE_DAYS:
                print(f"   ⏭ {name}: {freshness} (слишком старый)")
                posted_ids.append(repo_id)  # Чтобы не проверять повторно
                continue
            
            print(f"   📦 {name} | {freshness}")
            
            analysis = await analyze_with_gpt(name, desc, "", search['name'])
            
            if analysis:
                try:
                    msg = (
                        f"📄 <b>{search['name']}</b>\n\n"
                        f"📦 <code>{name}</code>\n"
                        f"⏰ {freshness}\n"
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
        
        await asyncio.sleep(2)
    
    # ============ 3. ПОИСК РЕПОЗИТОРИЕВ ============
    print("\n" + "=" * 50)
    print("🔧 ЧАСТЬ 3: Инструменты и белые списки")
    print("=" * 50)
    
    for search in REPO_SEARCHES:
        print(f"\n🔍 {search['name']}")
        
        # ⚡ Используем поиск с фильтром по дате
        items = search_repos_fresh(search['query'])
        
        if not items:
            print(f"   Ничего свежего не найдено")
            continue
        
        print(f"   Найдено свежих: {len(items)}")
        
        for item in items[:3]:
            repo_id = str(item.get('id', ''))
            
            if repo_id in posted_ids:
                continue
            
            name = item.get('full_name', '')
            desc = item.get('description', '') or ''
            url = item.get('html_url', '')
            stars = item.get('stargazers_count', 0)
            topics = ", ".join(item.get('topics', []))
            pushed_at = item.get('pushed_at', '')
            
            age_days = get_age_days(pushed_at)
            freshness = get_freshness_emoji(age_days)
            
            # ⚡ ДВОЙНАЯ ПРОВЕРКА СВЕЖЕСТИ
            if age_days > MAX_AGE_DAYS:
                print(f"   ⏭ {name}: {freshness}")
                continue
            
            print(f"   📦 {name} | ⭐{stars} | {freshness}")
            
            analysis = await analyze_with_gpt(name, desc, topics, search['name'])
            
            if analysis:
                try:
                    msg = (
                        f"🛠 <b>{search['name']}</b>\n\n"
                        f"📦 <code>{name}</code>\n"
                        f"⭐ {stars} | ⏰ {freshness}\n"
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
