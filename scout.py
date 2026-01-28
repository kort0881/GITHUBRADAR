import os
import json
import asyncio
import requests
import html
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

# ============ АГРЕГАТОРЫ (База) ============
KNOWN_AGGREGATORS = [
    {"owner": "mahdibland", "repo": "V2RayAggregator", "name": "V2RayAggregator"},
    {"owner": "Epodonios", "repo": "v2ray-configs", "name": "Epodonios"},
    {"owner": "Pawdroid", "repo": "Free-servers", "name": "Pawdroid"},
    {"owner": "peasoft", "repo": "NoMoreWalls", "name": "NoMoreWalls"},
    {"owner": "ermaozi", "repo": "get_subscribe", "name": "Ermaozi"},
    {"owner": "aiboboxx", "repo": "v2rayfree", "name": "V2RayFree"},
    {"owner": "mfuu", "repo": "v2ray", "name": "MFUU"},
    {"owner": "Leon406", "repo": "SubCrawler", "name": "SubCrawler"},
]

# ============ МАКСИМАЛЬНЫЙ ОХВАТ (Триггеры) ============

FRESH_SEARCHES = [
    # 1. Цензура, РКН, Мониторинг (Новое)
    {"name": "Roskomsvoboda", "title": "📢 Роскомсвобода / RuBlacklist", "query": "roskomsvoboda OR rublacklist OR runet-censorship"},
    {"name": "Mintsifry", "title": "🏛 Минцифры & Госуслуги", "query": "mintsifry OR gosuslugi bypass OR russian trusted ca"},
    {"name": "RKN & TSPU", "title": "👁 РКН & ТСПУ", "query": "roskomnadzor OR rkn OR tspu-russia OR sorm-russia"},
    {"name": "Blocklist RU", "title": "⛔️ Реестры блокировок", "query": "russia blocklist OR reestr-zapret OR zapret-info"},

    # 2. Инструменты обхода (База)
    {"name": "AntiZapret", "title": "🛡 AntiZapret", "query": "antizapret OR anti-zapret"},
    {"name": "Antifilter", "title": "🛡 Antifilter", "query": "antifilter russia"},
    {"name": "Zapret", "title": "🛠 Zapret DPI", "query": "zapret dpi OR zapret-discord"},
    {"name": "ByeDPI", "title": "🛠 ByeDPI / GoodbyeDPI", "query": "byedpi OR goodbyedpi"},
    {"name": "SpoofDPI", "title": "🛠 SpoofDPI", "query": "spoofdpi OR dpi-tunnel"},

    # 3. Протоколы и Конфиги
    {"name": "VLESS RU", "title": "🔧 VLESS Russia", "query": "vless russia OR vless reality russia"},
    {"name": "Xray Reality", "title": "🔧 Xray Reality", "query": "xray reality setup OR xray-core russia"},
    {"name": "Hysteria2", "title": "🚀 Hysteria 2", "query": "hysteria2 config OR hysteria2-server"},
    {"name": "Amnezia", "title": "🛡 Amnezia VPN", "query": "amnezia vpn OR amneziawg OR amnezia-client"},
    {"name": "WireGuard RU", "title": "🔐 WireGuard Russia", "query": "wireguard russia OR wg-easy russia"},
    {"name": "Shadowsocks", "title": "🔐 Shadowsocks 2022", "query": "shadowsocks-2022 OR ss2022 russia"},
    {"name": "Tuic", "title": "🚀 Tuic v5", "query": "tuic protocol OR tuic-server"},

    # 4. Панели и Боты
    {"name": "Marzban", "title": "🎛 Marzban", "query": "marzban panel OR marzban-node"},
    {"name": "3X-UI", "title": "🎛 3X-UI / X-UI", "query": "3x-ui OR x-ui panel russia"},
    {"name": "VPN Bots", "title": "🤖 Telegram VPN Bot", "query": "telegram vpn bot russia OR proxy checker python"},

    # 5. Гео и Списки
    {"name": "Geosite RU", "title": "🗺 Geosite / GeoIP RU", "query": "geosite russia OR geoip russia OR ru-list"},
    {"name": "Whitelist", "title": "📋 Белые списки РФ", "query": "russia whitelist OR russian-whitelist OR domestic-whitelist"},
]

# ============ HELPERS ============

def safe_desc(desc, max_len=100):
    if desc is None:
        return ""
    return str(desc).strip()[:max_len] if desc else ""

def get_age_hours(date_string):
    try:
        if not date_string: return 9999
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except: return 9999

def get_freshness(date_string):
    hours = get_age_hours(date_string)
    if hours < 1: return "🔥 Только что"
    elif hours < 6: return f"🔥 {int(hours)}ч назад"
    elif hours < 24: return "🔥 Сегодня"
    elif hours < 48: return "✅ Вчера"
    else: return f"📅 {int(hours/24)}д назад"

def is_fresh(date_string):
    return get_age_hours(date_string) <= (MAX_AGE_DAYS * 24)

def quick_filter(name, desc):
    """Фильтр с исключением Китая, но ЖЕСТКИМ пропуском тем РФ"""
    text = f"{name} {desc or ''}".lower()

    # 1. Сначала ищем явные маркеры РФ (Белый список)
    # Если они есть - пропускаем СРАЗУ, игнорируя фильтры Китая/мусора
    ru_whitelist = [
        'russia', 'russian', 'ru-block', 'roskomnadzor', 'rkn', 'mintsifry', 
        'gosuslugi', 'antizapret', 'antifilter', 'zapret', 'рф', 'ркн', 
        'роскомнадзор', 'минцифры', 'роскомсвобода', 'tspu', 'sorm'
    ]
    if any(w in text for w in ru_whitelist):
        return True

    # 2. Если маркеров РФ нет, включаем фильтры
    china_keywords = ['china', 'chinese', '中国', 'cn-', 'gfw', 'iran', 'vietnam']
    trash_keywords = ['homework', 'tutorial', 'example', 'template', 'study', 'deprecated']

    if any(k in text for k in china_keywords): return False
    if any(k in text for k in trash_keywords): return False

    return True

def build_post(title, repo_full_name, stars, freshness, description, url):
    """Строгий формат поста"""
    return (
        f"<b>{title}</b>\n\n"
        f"📦 <code>{html.escape(repo_full_name)}</code>\n"
        f"⭐️ {stars} | ⏰ {freshness}\n"
        f"💡 {html.escape(description)}\n\n"
        f"🔗 <a href='{url}'>GitHub</a>"
    )

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except: pass
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
    except: pass
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
            return [i for i in resp.json().get('items', []) if is_fresh(i.get('pushed_at'))]
    except: pass
    return []

async def analyze_relevance(repos):
    """AI проверяет релевантность (True/False)"""
    if not repos: return {}

    text = "\n".join([f"{i+1}. {r['full_name']} | {safe_desc(r['description'], 100)}" for i, r in enumerate(repos)])

    prompt = f"""Задача: Отфильтровать репозитории.
Тема: Обход блокировок (VPN, DPI, AntiZapret), интернет-цензура в РФ (РКН, ТСПУ, Минцифры).

Список:
{text}

Ответь: N - GOOD или SKIP.
GOOD если:
- Связано с VPN, прокси, обходом блокировок
- Связано с Роскомнадзором, реестрами, ТСПУ, Минцифры
- Полезные конфиги или списки IP

SKIP если:
- Мусор, домашнее задание, пустой форк
- Китайский/Иранский специфицичный софт (если нет связи с РФ)

Формат:
1: GOOD
2: SKIP"""

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0
        )
        res = {}
        for line in resp.choices[0].message.content.split('\n'):
            if ':' in line:
                try:
                    idx, verdict = line.split(':', 1)
                    res[int(idx.strip())] = 'GOOD' in verdict.upper()
                except: pass
        return res
    except: return {}

async def generate_desc(name, desc):
    """Генерация описания если пустое"""
    if desc and len(desc) > 20: return desc

    prompt = f"""Репозиторий: {name}
Описание: {desc}
Напиши 1 предложение на русском: что это и зачем нужно (в контексте VPN/обхода блокировок/РФ)."""

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )
        return resp.choices[0].message.content.strip()
    except: return desc or "Репозиторий по теме обхода блокировок"

async def main():
    print("="*40 + "\n🕵️ SCOUT RADAR v5.0 (MAX COVERAGE)\n" + "="*40)

    state = load_state()
    posted = state.get("posted", [])
    commits = state.get("commits", {})
    count = 0

    # 1. Агрегаторы
    for agg in KNOWN_AGGREGATORS:
        if count >= MAX_POSTS_PER_RUN: break
        key = f"{agg['owner']}/{agg['repo']}"
        c = get_last_commit(agg['owner'], agg['repo'])
        if c and is_fresh(c['date']) and commits.get(key) != c['sha']:
            print(f"🆕 AGG: {agg['name']}")
            await bot.send_message(TARGET_CHANNEL_ID, 
                f"🔄 <b>{agg['name']}</b>\n\n⏰ {get_freshness(c['date'])}\n📝 <code>{c['msg']}</code>\n\n🔗 <a href='{c['url']}'>GitHub</a>",
                disable_web_page_preview=True
            )
            commits[key] = c['sha']
            count += 1
            await asyncio.sleep(1)

    # 2. Поиск
    for s in FRESH_SEARCHES:
        if count >= MAX_POSTS_PER_RUN: break
        print(f"🔍 {s['name']}...")
        items = search_fresh_repos(s['query'])

        # Фильтр дублей и мусора
        candidates = []
        for i in items:
            if str(i['id']) in posted: continue
            if not quick_filter(i.get('full_name'), i.get('description')): continue
            candidates.append(i)

        if not candidates: continue

        # AI проверка
        batch = candidates[:3]
        decisions = await analyze_relevance(batch)

        for idx, item in enumerate(batch, 1):
            if count >= MAX_POSTS_PER_RUN: break
            if not decisions.get(idx, False): continue

            # Генерация описания
            final_desc = await generate_desc(item['full_name'], item['description'])

            # Отправка
            title = s.get('title', s['name'])
            await bot.send_message(TARGET_CHANNEL_ID,
                build_post(title, item['full_name'], item['stargazers_count'], 
                          get_freshness(item['pushed_at']), final_desc, item['html_url']),
                disable_web_page_preview=True
            )
            posted.append(str(item['id']))
            count += 1
            print(f"   ✅ Posted: {item['full_name']}")
            await asyncio.sleep(1)

    save_state({"posted": posted[-500:], "commits": commits})
    print(f"\n🏁 Done. Sent: {count}")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
