import os
import json
import asyncio
import requests
from datetime import datetime, timedelta, timezone
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from groq import Groq

# ============ CONFIG ============

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TARGET_CHANNEL_ID = os.getenv("CHANNEL_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

STATE_FILE = "scout_history.json"

MAX_AGE_DAYS = 3
MAX_POSTS_PER_RUN = 15
GROQ_DELAY = 2

API_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
groq_client = Groq(api_key=GROQ_API_KEY)

# ============ АГРЕГАТОРЫ ============

KNOWN_AGGREGATORS = [
    {"owner": "mahdibland", "repo": "V2RayAggregator", "name": "🔥 V2RayAggregator"},
    {"owner": "Epodonios", "repo": "v2ray-configs", "name": "🔥 Epodonios"},
    {"owner": "Pawdroid", "repo": "Free-servers", "name": "🔥 Pawdroid"},
    {"owner": "peasoft", "repo": "NoMoreWalls", "name": "🔥 NoMoreWalls"},
    {"owner": "ermaozi", "repo": "get_subscribe", "name": "🔥 Ermaozi"},
    {"owner": "aiboboxx", "repo": "v2rayfree", "name": "🔥 V2RayFree"},
    {"owner": "mfuu", "repo": "v2ray", "name": "🔥 MFUU"},
    {"owner": "Leon406", "repo": "SubCrawler", "name": "🔥 SubCrawler"},
]

# ============ ПОИСК (УЛУЧШЕННЫЙ) ============

FRESH_SEARCHES = [
    # Блокировки и белые списки РФ
    {"name": "🇷🇺 AntiZapret", "query": "antizapret OR anti-zapret"},
    {"name": "🇷🇺 Antifilter", "query": "antifilter russia"},
    {"name": "🇷🇺 Geosite Russia", "query": "geosite russia OR geoip russia"},
    {"name": "🇷🇺 Белые списки", "query": "russia whitelist OR russian whitelist"},
    {"name": "🇷🇺 Rule-set RU", "query": "ruleset russia OR russia routing"},
    {"name": "🇷🇺 РКН обход", "query": "rkn bypass OR roskomnadzor"},
    {"name": "🇷🇺 Список блокировок", "query": "russia blocklist OR russian censorship"},

    # DPI обход (актуально для РФ)
    {"name": "🔧 Zapret", "query": "zapret dpi"},
    {"name": "🔧 ByeDPI", "query": "byedpi"},
    {"name": "🔧 GoodbyeDPI", "query": "goodbyedpi russia OR goodbyedpi"},
    {"name": "🔧 DPI Tunnel", "query": "dpi tunnel russia"},
    {"name": "🔧 SpoofDPI", "query": "spoofdpi"},

    # Протоколы VLESS/Reality
    {"name": "📦 VLESS Reality", "query": "vless reality config"},
    {"name": "📦 VLESS Russia", "query": "vless russia OR vless russian"},
    {"name": "📦 Xray Reality", "query": "xray reality setup"},

    # Hysteria и новые протоколы
    {"name": "📦 Hysteria2", "query": "hysteria2 config OR hysteria2 server"},
    {"name": "📦 Tuic", "query": "tuic protocol OR tuic v5"},
    {"name": "📦 Shadowsocks 2022", "query": "shadowsocks-2022 OR ss2022"},

    # Конфиги и клиенты
    {"name": "📦 Sing-box", "query": "sing-box config russia OR singbox"},
    {"name": "📦 Xray Config", "query": "xray config subscription"},
    {"name": "📦 V2Ray Europe", "query": "v2ray europe servers"},
    {"name": "📦 Clash Meta", "query": "clash meta russia OR clash-meta"},

    # Панели управления
    {"name": "🛠 Marzban", "query": "marzban panel OR marzban xray"},
    {"name": "🛠 3X-UI", "query": "3x-ui OR x-ui panel"},
    {"name": "🛠 Hiddify", "query": "hiddify manager OR hiddify panel"},
    {"name": "🛠 V2Board", "query": "v2board"},

    # Telegram боты и инструменты
    {"name": "🤖 VPN Боты", "query": "telegram vpn bot russia"},
    {"name": "🤖 Proxy Checker", "query": "proxy checker vless OR vmess checker"},
    {"name": "🤖 Config Parser", "query": "vpn config parser telegram"},

    # WireGuard (популярен в Европе)
    {"name": "🔐 WireGuard", "query": "wireguard setup russia OR wg-easy"},
    {"name": "🔐 Amnezia", "query": "amnezia vpn OR amneziawg"},

    # Europeanские сервера и роутинг
    {"name": "🇪🇺 EU Servers", "query": "vpn europe servers OR eu proxy"},
    {"name": "🇪🇺 Netherlands VPN", "query": "netherlands vpn OR amsterdam servers"},
]

# ============ HELPERS ============

def safe_desc(desc, max_len=100):
    """Безопасное получение описания"""
    if desc is None:
        return "Нет описания"
    return str(desc)[:max_len]

def get_age_days(date_string):
    try:
        if not date_string:
            return 9999
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return (datetime.now(timezone.utc) - dt).days
    except:
        return 9999

def get_age_hours(date_string):
    try:
        if not date_string:
            return 9999
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600
    except:
        return 9999

def get_freshness(date_string):
    hours = get_age_hours(date_string)
    if hours < 1:
        return "🔥 Только что"
    elif hours < 6:
        return f"🔥 {int(hours)}ч назад"
    elif hours < 24:
        return "🔥 Сегодня"
    elif hours < 48:
        return "✅ Вчера"
    elif hours < 72:
        return "✅ 2д назад"
    else:
        return f"📅 {int(hours/24)}д назад"

def is_fresh(date_string):
    return get_age_days(date_string) <= MAX_AGE_DAYS

def quick_filter(name, desc):
    """Фильтр с исключением Китая и нерелевантных репо"""
    text = f"{name} {desc or ''}".lower()

    # Исключаем Китай и Азию (кроме России)
    china_keywords = [
        'china', 'chinese', '中国', 'cn-', 'gfw',
        'great firewall', 'beijing', 'shanghai',
        'iran', 'iranian', 'turkey', 'vietnam',
        'indonesia', 'malaysia', 'singapore'
    ]

    # Исключаем мусор
    trash_keywords = [
        'homework', 'assignment', 'tutorial', 'example', 
        'template', 'learning', 'practice', 'study', 
        'course', 'lesson', 'test', 'demo', 'sample',
        'fork of', 'archived', 'deprecated', 'old',
        'experiment', 'playground'
    ]

    # Проверяем исключения
    if any(keyword in text for keyword in china_keywords):
        # Исключение: если явно упоминается Россия, пропускаем
        if not any(ru in text for ru in ['russia', 'russian', 'рф', 'ркн', 'antizapret']):
            return False

    if any(keyword in text for keyword in trash_keywords):
        return False

    return True

def is_relevant_region(name, desc):
    """Проверка релевантности для России/Европы"""
    text = f"{name} {desc or ''}".lower()

    # Приоритетные ключевые слова
    priority_keywords = [
        # Россия
        'russia', 'russian', 'rkn', 'roskomnadzor', 'антизапрет',
        'antizapret', 'antifilter', 'zapret', 'рф', 'ркн',

        # Европа
        'europe', 'european', 'eu', 'netherlands', 'amsterdam',
        'germany', 'france', 'uk', 'london', 'poland',

        # Универсальные (но актуальные)
        'vless', 'reality', 'hysteria', 'xray', 'sing-box',
        'dpi', 'bypass', 'whitelist', 'routing', 'amnezia'
    ]

    return any(keyword in text for keyword in priority_keywords)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {"posted": data, "commits": {}}
            return {
                "posted": data.get("posted", []),
                "commits": data.get("commits", data.get("aggregator_commits", {}))
            }
        except:
            pass
    return {"posted": [], "commits": {}}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_last_commit(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code == 200 and resp.json():
            c = resp.json()[0]
            return {
                "sha": c['sha'][:7],
                "date": c['commit']['committer']['date'],
                "msg": c['commit']['message'].split('\n')[0][:50],
                "url": c['html_url']
            }
    except:
        pass
    return None

def search_fresh_repos(query):
    date_filter = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime('%Y-%m-%d')
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={query}+pushed:>{date_filter}"
        f"&sort=updated&order=desc&per_page=10"
    )
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            items = resp.json().get('items', [])
            return [i for i in items if is_fresh(i.get('pushed_at'))]
    except:
        pass
    return []

async def analyze_batch(repos, context):
    """Пакетный анализ с фокусом на Россию/Европу"""
    if not repos:
        return {}

    lines = []
    for i, r in enumerate(repos, 1):
        name = r.get('full_name', 'unknown')
        desc = safe_desc(r.get('description'), 100)
        fresh = get_freshness(r.get('pushed_at'))
        lines.append(f"{i}. {name}\n   Описание: {desc}\n   Обновлён: {fresh}")

    text = "\n".join(lines)

    prompt = f"""Ты эксперт по обходу блокировок в России и Европе.

Контекст: {context}

НУЖНЫ ТОЛЬКО:
✅ Рабочие конфиги VPN для РФ/Европы (VLESS, Reality, Hysteria, WireGuard)
✅ Белые списки доменов для России (AntiZapret, Antifilter)
✅ Инструменты обхода DPI (Zapret, GoodbyeDPI, ByeDPI)
✅ Панели управления VPN (Marzban, 3X-UI, Hiddify)
✅ Telegram боты для VPN/прокси
✅ Routing rules для России/Европы
✅ Европейские VPN сервера

НЕ НУЖНЫ:
❌ Китайские инструменты (GFW, China-specific)
❌ Форки без изменений
❌ Учебные проекты (tutorial, example, homework)
❌ Устаревшие репозитории
❌ Азиатские сервисы (кроме универсальных)

Репозитории:
{text}

Ответь ТОЛЬКО цифрами и GOOD/SKIP:
1: GOOD или SKIP
2: GOOD или SKIP
..."""

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0
        )
        answer = resp.choices[0].message.content

        results = {}
        for line in answer.split('\n'):
            if ':' in line:
                try:
                    num = int(line.split(':')[0].strip())
                    results[num] = 'GOOD' in line.upper()
                except:
                    pass
        return results
    except Exception as e:
        print(f"   ⚠️ Groq error: {e}")
        return {}

async def main():
    print("=" * 50)
    print("🕵️ SCOUT RADAR v4.0 — RU/EU Focus")
    print("=" * 50)

    state = load_state()
    posted = state["posted"]
    commits = state["commits"]
    posts_sent = 0
    groq_calls = 0

    print(f"\n📊 История: {len(posted)} постов")
    print(f"⏰ Ищем: ≤{MAX_AGE_DAYS} дней")
    print(f"🎯 Фокус: Россия + Европа")
    print(f"📬 Лимит: {MAX_POSTS_PER_RUN}\n")

    # ============ 1. АГРЕГАТОРЫ ============
    print("=" * 50)
    print("📦 ЧАСТЬ 1: Агрегаторы")
    print("=" * 50)

    for agg in KNOWN_AGGREGATORS:
        if posts_sent >= MAX_POSTS_PER_RUN:
            break

        key = f"{agg['owner']}/{agg['repo']}"
        commit = get_last_commit(agg['owner'], agg['repo'])

        if not commit:
            print(f"\n❌ {agg['name']}: недоступен")
            continue

        freshness = get_freshness(commit['date'])

        if not is_fresh(commit['date']):
            print(f"\n⏭ {agg['name']}: {freshness}")
            continue

        if commits.get(key) == commit['sha']:
            print(f"\n⏸ {agg['name']}: {freshness} (видели)")
            continue

        print(f"\n🆕 {agg['name']}")
        print(f"   {freshness} | {commit['sha']}")

        try:
            msg = (
                f"🔄 <b>{agg['name']}</b>\n\n"
                f"⏰ {freshness}\n"
                f"📝 <code>{commit['msg']}</code>\n\n"
                f"🔗 <a href='https://github.com/{key}'>Репозиторий</a>"
            )
            await bot.send_message(TARGET_CHANNEL_ID, msg, disable_web_page_preview=True)
            commits[key] = commit['sha']
            posts_sent += 1
            print(f"   ✅ [{posts_sent}/{MAX_POSTS_PER_RUN}]")
        except Exception as e:
            print(f"   ❌ TG: {e}")

        await asyncio.sleep(1)

    # ============ 2. ПОИСК ============
    print("\n" + "=" * 50)
    print(f"🔍 ЧАСТЬ 2: Свежие репо (RU/EU)")
    print("=" * 50)

    for search in FRESH_SEARCHES:
        if posts_sent >= MAX_POSTS_PER_RUN:
            print(f"\n⚠️ Лимит!")
            break

        print(f"\n🔍 {search['name']}")

        items = search_fresh_repos(search['query'])

        if not items:
            print(f"   Нет свежих")
            continue

        new_items = [i for i in items if str(i['id']) not in posted]

        if not new_items:
            print(f"   Всё видели")
            continue

        # Применяем двойную фильтрацию
        filtered = [i for i in new_items if quick_filter(i.get('name', ''), i.get('description'))]

        if not filtered:
            print(f"   Отфильтровано (мусор/Китай)")
            continue

        filtered.sort(key=lambda x: get_age_hours(x.get('pushed_at', '')))

        batch = filtered[:3]
        print(f"   Найдено {len(filtered)}, анализ {len(batch)}...")

        results = await analyze_batch(batch, search['name'])
        groq_calls += 1

        await asyncio.sleep(GROQ_DELAY)

        for idx, item in enumerate(batch, 1):
            if posts_sent >= MAX_POSTS_PER_RUN:
                break

            repo_id = str(item['id'])
            name = item.get('full_name', 'unknown')
            freshness = get_freshness(item.get('pushed_at'))
            stars = item.get('stargazers_count', 0)

            if not results.get(idx, False):
                print(f"   ⏩ {name}: skip")
                posted.append(repo_id)
                continue

            # Финальная проверка региона
            if not is_relevant_region(name, item.get('description')):
                print(f"   🌏 {name}: не РФ/ЕС")
                posted.append(repo_id)
                continue

            print(f"   ✅ {name} | {freshness}")

            try:
                desc = safe_desc(item.get('description'), 200)
                msg = (
                    f"🆕 <b>{search['name']}</b>\n\n"
                    f"📦 <code>{name}</code>\n"
                    f"⏰ {freshness} | ⭐ {stars}\n"
                    f"💡 {desc}\n\n"
                    f"🔗 <a href='{item.get('html_url', '')}'>GitHub</a>"
                )
                await bot.send_message(TARGET_CHANNEL_ID, msg, disable_web_page_preview=True)
                posted.append(repo_id)
                posts_sent += 1
                print(f"      📬 [{posts_sent}/{MAX_POSTS_PER_RUN}]")
            except Exception as e:
                print(f"      ❌ TG: {e}")

            await asyncio.sleep(1)

        await asyncio.sleep(1)

    # ============ СОХРАНЕНИЕ ============
    save_state({
        "posted": posted[-500:],
        "commits": commits
    })

    await bot.session.close()

    print("\n" + "=" * 50)
    print(f"✅ Готово! Постов: {posts_sent} | Groq: {groq_calls}")
    print(f"🎯 Фокус: Россия + Европа (Китай исключён)")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())

