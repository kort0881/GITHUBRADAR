import os
import json
import asyncio
import requests
import html
import re
import logging
from datetime import datetime, timedelta, timezone
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from groq import Groq

# ============ LOGGING ============

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('scout_radar.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============ CONFIG ============

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TARGET_CHANNEL_ID = os.getenv("CHANNEL_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

STATE_FILE = "scout_history.json"

MAX_AGE_DAYS = 4
MAX_POSTS_PER_RUN = 100
GROQ_DELAY = 2
MESSAGE_DELAY = 3
MIN_STARS = 1
MIN_API_CALLS_REMAINING = 50

API_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
groq_client = Groq(api_key=GROQ_API_KEY)

# ============ АГРЕГАТОРЫ ============
KNOWN_AGGREGATORS = [
    {"owner": "Leon406", "repo": "SubCrawler", "name": "SubCrawler"},
    {"owner": "peasoft", "repo": "NoMoreWalls", "name": "NoMoreWalls"},
    {"owner": "barry-far", "repo": "V2ray-Configs", "name": "V2ray-Configs"},
]

# ============ ПОИСКОВЫЕ ЗАПРОСЫ ============
FRESH_SEARCHES = [
    {"name": "Roskomsvoboda", "title": "📢 Роскомсвобода / RuBlacklist", "query": "roskomsvoboda OR rublacklist OR runet-censorship", "priority": 10},
    {"name": "RKN & TSPU", "title": "👁 РКН & ТСПУ", "query": "roskomnadzor OR rkn OR tspu OR sorm", "priority": 10},
    {"name": "Blocklist RU", "title": "⛔️ Реестры блокировок", "query": "russia blocklist OR reestr-zapret OR zapret-info", "priority": 9},
    {"name": "AntiZapret", "title": "🛡 AntiZapret", "query": "antizapret OR anti-zapret", "priority": 10},
    {"name": "Zapret", "title": "🛠 Zapret DPI", "query": "zapret dpi OR zapret-discord OR zapret-winws", "priority": 9},
    {"name": "ByeDPI", "title": "🛠 ByeDPI / GoodbyeDPI", "query": "byedpi OR goodbyedpi", "priority": 9},
    {"name": "SpoofDPI", "title": "🛠 SpoofDPI", "query": "spoofdpi OR dpi-tunnel", "priority": 8},
    {"name": "VLESS RU", "title": "🔧 VLESS Russia", "query": "vless russia OR vless reality", "priority": 8},
    {"name": "Hysteria2", "title": "🚀 Hysteria 2", "query": "hysteria2 config OR hysteria2-server", "priority": 8},
    {"name": "Amnezia", "title": "🛡 Amnezia VPN", "query": "amnezia vpn OR amneziawg", "priority": 9},
    {"name": "Shadowsocks", "title": "🔐 Shadowsocks 2022", "query": "shadowsocks-2022 OR ss2022", "priority": 7},
    {"name": "Marzban", "title": "🎛 Marzban", "query": "marzban panel OR marzban-node", "priority": 8},
    {"name": "3X-UI", "title": "🎛 3X-UI / X-UI", "query": "3x-ui OR x-ui panel", "priority": 7},
    {"name": "Geosite RU", "title": "🗺 Geosite / GeoIP RU", "query": "geosite russia OR geoip russia", "priority": 7},
    {"name": "Whitelist RU", "title": "✅ Белые списки РФ", "query": "russia whitelist OR russian-whitelist OR domestic-whitelist OR gosuslugi-whitelist", "priority": 10},
    {"name": "NoDPI", "title": "🛠 NoDPI", "query": "nodpi python OR dpi-bypass-python", "priority": 8},
    {"name": "Cloak", "title": "🎭 Cloak", "query": "cloak censorship OR cbeuw-cloak", "priority": 8},
    {"name": "TrustTunnel", "title": "🔒 TrustTunnel", "query": "trusttunnel OR adguard-vpn-protocol", "priority": 8},
    {"name": "Trojan-Go", "title": "🐴 Trojan-Go", "query": "trojan-go russia OR trojan-gfw", "priority": 7},
    {"name": "Outline VPN", "title": "📡 Outline VPN", "query": "outline vpn OR outline-server russia", "priority": 8},
    {"name": "Hiddify", "title": "🎛 Hiddify Manager", "query": "hiddify manager OR hiddify-next", "priority": 8},
    {"name": "V2Board", "title": "🎛 V2Board", "query": "v2board russia OR v2ray-panel", "priority": 7},
    {"name": "Domain Lists", "title": "📋 Списки доменов РФ", "query": "russia domain-list OR ru-domain-routing", "priority": 8},
    {"name": "IP Lists RU", "title": "🌐 IP списки РФ", "query": "russia ip-list OR russian-networks OR ru-cidr", "priority": 7},
    {"name": "Routing Rules", "title": "🧶 Правила маршрутизации", "query": "russia routing-rules OR split-routing russia", "priority": 8},
    {"name": "Nekoray", "title": "🐱 Nekoray / V2RayN", "query": "nekoray OR v2rayn russia", "priority": 7},
    {"name": "Clash Meta", "title": "⚔️ Clash Meta", "query": "clash-meta russia OR clash-verge", "priority": 7},
    {"name": "Sing-Box", "title": "📦 Sing-Box", "query": "sing-box russia OR sing-box-subscribe", "priority": 8},
    {"name": "BypassHub", "title": "🔗 BypassHub", "query": "bypasshub OR censorship-abstraction", "priority": 7},
    {"name": "SNI Proxy", "title": "🎏 SNI Proxy", "query": "sni-proxy russia OR sni-routing", "priority": 7},
    {"name": "XTLS Reality", "title": "🌜 XTLS Reality", "query": "xtls-reality OR reality-protocol", "priority": 8},
    {"name": "Obfuscation", "title": "🌥 Обфускация трафика", "query": "traffic-obfuscation russia OR vpn-obfuscation", "priority": 7},
    {"name": "CDN Fronting", "title": "☁️ CDN Fronting", "query": "cdn-fronting russia OR domain-fronting cloudflare", "priority": 7},
    {"name": "DNS-over-HTTPS", "title": "🔐 DNS-over-HTTPS", "query": "doh russia OR dns-over-https bypass", "priority": 7},
    {"name": "DNS-over-TLS", "title": "🔐 DNS-over-TLS", "query": "dot russia OR dns-over-tls", "priority": 7},
    {"name": "Encrypted SNI", "title": "🔒 Encrypted SNI", "query": "esni russia OR encrypted-client-hello", "priority": 7},
    {"name": "Config Generators", "title": "⚙️ Генераторы конфигов", "query": "v2ray-config-generator russia OR subscription-converter", "priority": 7},
    {"name": "Auto Subscribe", "title": "📡 Автоподписки", "query": "v2ray-subscription OR proxy-subscription russia", "priority": 6},
    {"name": "Speed Test", "title": "⚡️ Тестирование VPN", "query": "vpn-speed-test russia OR proxy-checker", "priority": 6},
]

FRESH_SEARCHES.sort(key=lambda x: x.get('priority', 5), reverse=True)

# ============ VALIDATION ============

def validate_env():
    """✅ Проверка обязательных переменных окружения"""
    required = {
        "GROQ_API_KEY": GROQ_API_KEY,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "CHANNEL_ID": TARGET_CHANNEL_ID,
        "GITHUB_TOKEN": GITHUB_TOKEN
    }
    
    missing = [k for k, v in required.items() if not v]
    
    if missing:
        logger.error(f"❌ Missing environment variables: {', '.join(missing)}")
        return False
    
    logger.info("✅ All environment variables validated")
    return True

# ============ GITHUB API RATE LIMIT ============

def check_rate_limit():
    """✅ Проверка оставшихся запросов к GitHub API"""
    try:
        resp = requests.get("https://api.github.com/rate_limit", headers=API_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            remaining = data['rate']['remaining']
            limit = data['rate']['limit']
            reset_time = datetime.fromtimestamp(data['rate']['reset'], timezone.utc)
            
            logger.info(f"📊 GitHub API: {remaining}/{limit} calls remaining")
            
            if remaining < MIN_API_CALLS_REMAINING:
                wait_seconds = (reset_time - datetime.now(timezone.utc)).total_seconds()
                logger.warning(f"⚠️ API limit low ({remaining} left). Reset at {reset_time.strftime('%H:%M:%S UTC')}")
                
                if remaining < 10:
                    logger.error(f"⏸ Critical: Only {remaining} calls left. Stopping to avoid rate limit.")
                    return False
            
            return True
    except Exception as e:
        logger.warning(f"⚠️ Could not check rate limit: {e}. Continuing anyway...")
        return True

# ============ HELPERS ============

def has_non_latin(text):
    """✅ Проверка на иероглифы (Китай, Иран, Африка, Азия)"""
    if not text: 
        return False
    
    patterns = [
        r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]',  # CJK (исправлено)
        r'[\u0600-\u06ff\u0750-\u077f\uFB50-\uFDFF\uFE70-\uFEFF]',  # Арабские/Персидские
        r'[\u0e00-\u0e7f\u1780-\u17ff]',  # Тайский/Кхмерский
    ]
    
    return any(re.search(p, text) for p in patterns)

def is_repo_empty(owner, repo, cache):
    """✅ Проверка на пустой репозиторий (с кэшированием)"""
    key = f"{owner}/{repo}"
    
    if key in cache:
        cached_time = datetime.fromisoformat(cache[key]['checked_at'])
        if (datetime.now(timezone.utc) - cached_time).total_seconds() < 86400:
            return cache[key]['is_empty']
    
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        
        if resp.status_code != 200:
            result = True
        else:
            data = resp.json()
            result = (
                data.get('size', 0) < 5 or
                (data.get('open_issues_count', 0) == 0 and data.get('stargazers_count', 0) == 0)
            )
        
        cache[key] = {
            'is_empty': result,
            'checked_at': datetime.now(timezone.utc).isoformat()
        }
        
        return result
    except Exception as e:
        logger.debug(f"Error checking {key}: {e}")
        return True

def is_likely_fork_spam(item):
    """✅ Определение спам-форков"""
    if not item.get('fork'):
        return False
    
    if item.get('stargazers_count', 0) == 0 and item.get('forks_count', 0) == 0:
        return True
    
    created = item.get('created_at')
    pushed = item.get('pushed_at')
    if created and pushed:
        try:
            created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            pushed_dt = datetime.fromisoformat(pushed.replace('Z', '+00:00'))
            if abs((pushed_dt - created_dt).total_seconds()) < 60:
                return True
        except:
            pass
    
    return False

def safe_desc(desc, max_len=120):
    """✅ Безопасное описание с очисткой"""
    if desc is None:
        return ""
    
    desc = str(desc).strip()
    desc = re.sub(r'[🔥⚡️✨🎉]{3,}', '', desc)
    
    return desc[:max_len] if desc else ""

def get_age_hours(date_string):
    try:
        if not date_string: return 9999
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except: 
        return 9999

def get_freshness(date_string):
    hours = get_age_hours(date_string)
    if hours < 1: return "🔥 Только что"
    elif hours < 6: return f"🔥 {int(hours)}ч назад"
    elif hours < 24: return "🔥 Сегодня"
    elif hours < 48: return "✅ Вчера"
    else: return f"📅 {int(hours/24)}д назад"

def is_fresh(date_string):
    return get_age_hours(date_string) <= (MAX_AGE_DAYS * 24)

def quick_filter(name, desc, stars=0):
    """✅ Быстрый фильтр (без API запросов)"""
    text = f"{name} {desc or ''}".lower()
    full_text = f"{name} {desc or ''}"

    # 1. Иероглифы - ЖЁСТКИЙ БЛОК
    if has_non_latin(full_text):
        return False

    # 2. Минимум звёзд
    if stars < MIN_STARS:
        return False

    # 3. Белый список (приоритет)
    whitelist = [
        'russia', 'russian', 'ru-block', 'roskomnadzor', 'rkn', 'antizapret',
        'zapret', 'mintsifry', 'tspu', 'sorm', 'роскомнадзор', 'рф',
        'amnezia', 'hysteria', 'reality', 'marzban', 'xray-core'
    ]
    if any(w in text for w in whitelist):
        return True

    # 4. Черный список
    blacklist = [
        'china', 'chinese', 'cn-', 'gfw', 'iran', 'persian', 'vietnam',
        'homework', 'tutorial', 'example-', 'template', 'deprecated',
        'test-repo', 'demo-', 'practice', 'learning'
    ]
    if any(k in text for k in blacklist):
        return False

    # 5. Проверка на "шум" в названии
    noise_patterns = [
        r'\d{4,}',
        r'[A-Z]{8,}',
        r'[-_]{3,}',
    ]
    if any(re.search(p, name) for p in noise_patterns):
        return False

    return True

def build_post(title, repo_full_name, stars, freshness, description, url):
    """✅ Формат поста"""
    return (
        f"<b>{title}</b>\n\n"
        f"📦 <code>{html.escape(repo_full_name)}</code>\n"
        f"⭐️ {stars} | ⏰ {freshness}\n"
        f"💡 {html.escape(description)}\n\n"
        f"🔗 <a href='{url}'>Открыть на GitHub</a>"
    )

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load state: {e}")
    return {"posted": [], "commits": {}, "repo_cache": {}, "last_run": None}

def save_state(state):
    state['last_run'] = datetime.now(timezone.utc).isoformat()
    try:
        with open(STATE_FILE, "w", encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 State saved ({len(state['posted'])} posted repos)")
    except Exception as e:
        logger.error(f"❌ Could not save state: {e}")

def get_last_commit(owner, repo):
    """✅ Получение последнего коммита с ПРОВЕРКОЙ НА ИЕРОГЛИФЫ"""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code == 200 and resp.json():
            c = resp.json()[0]
            msg = c['commit']['message'].split('\n')[0][:60]
            
            # ✅ БЛОКИРОВКА ИЕРОГЛИФОВ В КОММИТАХ
            if has_non_latin(msg):
                logger.debug(f"   ⏭ SKIP commit (hieroglyphs): {owner}/{repo}")
                return None
            
            return {
                "sha": c['sha'][:7],
                "date": c['commit']['committer']['date'],
                "msg": msg,
                "url": c['html_url']
            }
    except Exception as e:
        logger.debug(f"Error getting commit for {owner}/{repo}: {e}")
    return None

def search_fresh_repos(query, per_page=30):
    """✅ Поиск свежих репозиториев"""
    date_filter = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime('%Y-%m-%d')
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={query}+pushed:>{date_filter}"
        f"&sort=updated&order=desc&per_page={per_page}"
    )
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            return [i for i in resp.json().get('items', []) if is_fresh(i.get('pushed_at'))]
        elif resp.status_code == 403:
            logger.warning("⚠️ GitHub API rate limit hit!")
            return []
        else:
            logger.warning(f"⚠️ Search failed with status {resp.status_code}")
            return []
    except Exception as e:
        logger.warning(f"⚠️ Search error: {e}")
    return []

async def analyze_relevance(repos):
    """✅ AI анализ релевантности"""
    if not repos: 
        return {}

    text = "\n".join([
        f"{i+1}. {r['full_name']} | ⭐{r['stargazers_count']} | {safe_desc(r['description'], 80)}" 
        for i, r in enumerate(repos)
    ])

    prompt = f"""Задача: Отфильтровать GitHub репозитории для канала про обход блокировок в РФ.

Целевая тема:
- VPN, прокси, DPI-обход (Zapret, ByeDPI, AntiZapret, Amnezia)
- Цензура в РФ (РКН, ТСПУ, Минцифры, Роскомнадзор)
- Полезные конфиги, списки IP/доменов для России и Европы
- Панели управления (Marzban, 3X-UI)

Список репозиториев:
{text}

Ответь для каждого: GOOD или SKIP

GOOD если:
✅ Реально полезный инструмент/конфиг для обхода блокировок
✅ Связан с РКН/ТСПУ/интернет-цензурой в РФ
✅ Актуальные списки/базы для РФ или Европы

SKIP если:
❌ Учебные примеры, домашка, устаревший проект
❌ Китайский/Иранский софт БЕЗ связи с РФ
❌ Пустой форк без изменений
❌ Мусор, спам, реклама

Формат ответа:
1: GOOD
2: SKIP
..."""

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1
        )
        
        res = {}
        for line in resp.choices[0].message.content.split('\n'):
            if ':' in line:
                try:
                    idx, verdict = line.split(':', 1)
                    res[int(idx.strip())] = 'GOOD' in verdict.upper()
                except: 
                    pass
        return res
    except Exception as e:
        logger.warning(f"⚠️ AI error: {e}")
        return {}

async def generate_desc(name, desc):
    """✅ Генерация описания через AI с ЗАЩИТОЙ ОТ ИЕРОГЛИФОВ"""
    if desc and len(desc) > 25 and not has_non_latin(desc): 
        return desc

    prompt = f"""Репозиторий: {name}
Текущее описание: {desc or 'отсутствует'}

Задача: Напиши краткое описание (1 предложение, до 100 символов) на русском языке.
Контекст: VPN, обход блокировок, интернет-цензура в России.
ВАЖНО: Только на русском или английском, БЕЗ иероглифов!

Описание:"""

    for attempt in range(2):
        try:
            resp = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.3
            )
            generated = resp.choices[0].message.content.strip()
            
            # ✅ ПРОВЕРКА РЕЗУЛЬТАТА НА ИЕРОГЛИФЫ
            if generated and not has_non_latin(generated):
                return generated
            else:
                logger.debug(f"AI generated text with hieroglyphs, retrying...")
                
        except Exception as e:
            logger.debug(f"AI description attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)
    
    return "Инструмент для обхода блокировок"

async def send_message_safe(chat_id, text):
    """✅ Безопасная отправка с ФИНАЛЬНОЙ ПРОВЕРКОЙ"""
    # ✅ ПОСЛЕДНЯЯ ЛИНИЯ ЗАЩИТЫ - НЕ ШЛЁМ ИЕРОГЛИФЫ
    if has_non_latin(text):
        logger.warning("⚠️ Blocked message with hieroglyphs from sending!")
        return False
    
    for attempt in range(3):
        try:
            await bot.send_message(chat_id, text, disable_web_page_preview=True)
            return True
        except Exception as e:
            logger.warning(f"⚠️ Send attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2 ** attempt)
    return False

async def main():
    logger.info("=" * 50)
    logger.info("🕵️  SCOUT RADAR v7.0 (3-day cycle)")
    logger.info("=" * 50)

    if not validate_env():
        return

    if not check_rate_limit():
        logger.error("❌ Insufficient API calls. Exiting.")
        return

    state = load_state()
    posted = state.get("posted", [])
    commits = state.get("commits", {})
    repo_cache = state.get("repo_cache", {})
    count = 0

    # 1. Проверка агрегаторов
    logger.info("\n📦 Checking aggregators...")
    for agg in KNOWN_AGGREGATORS:
        if count >= MAX_POSTS_PER_RUN: 
            break
        
        key = f"{agg['owner']}/{agg['repo']}"
        c = get_last_commit(agg['owner'], agg['repo'])
        
        if not c:
            continue
        
        if is_fresh(c['date']) and commits.get(key) != c['sha']:
            logger.info(f"   🆕 {agg['name']}")
            
            success = await send_message_safe(
                TARGET_CHANNEL_ID,
                f"🔄 <b>{agg['name']}</b>\n\n"
                f"⏰ {get_freshness(c['date'])}\n"
                f"📝 <code>{html.escape(c['msg'])}</code>\n\n"
                f"🔗 <a href='{c['url']}'>Посмотреть коммит</a>"
            )
            
            if success:
                commits[key] = c['sha']
                count += 1
                await asyncio.sleep(MESSAGE_DELAY)

    # 2. Поиск по запросам
    logger.info("\n🔍 Searching repositories...")
    for s in FRESH_SEARCHES:
        if count >= MAX_POSTS_PER_RUN: 
            break
        
        if not check_rate_limit():
            logger.warning("⚠️ API limit reached during search. Stopping.")
            break
        
        logger.info(f"\n🔍 {s['name']} (priority: {s.get('priority', 5)})...")
        items = search_fresh_repos(s['query'])

        if not items:
            logger.info("   ℹ️ No fresh repos found")
            continue

        candidates = []
        for i in items:
            if str(i['id']) in posted:
                continue
            
            if not quick_filter(i.get('full_name'), i.get('description'), i.get('stargazers_count', 0)):
                continue
            
            if is_likely_fork_spam(i):
                logger.debug(f"   ⏭ SKIP (fork spam): {i['full_name']}")
                continue
            
            owner, repo = i['full_name'].split('/')
            if is_repo_empty(owner, repo, repo_cache):
                logger.debug(f"   ⏭ SKIP (empty): {i['full_name']}")
                continue
            
            candidates.append(i)

        if not candidates:
            logger.info("   ℹ️ No candidates after filtering")
            continue

        batch_size = 4
        for batch_start in range(0, len(candidates), batch_size):
            if count >= MAX_POSTS_PER_RUN: 
                break
            
            batch = candidates[batch_start:batch_start + batch_size]
            decisions = await analyze_relevance(batch)

            for idx, item in enumerate(batch, 1):
                if count >= MAX_POSTS_PER_RUN: 
                    break
                
                if not decisions.get(idx, False):
                    logger.debug(f"   ⏭ AI SKIP: {item['full_name']}")
                    continue

                final_desc = await generate_desc(item['full_name'], item['description'])

                title = s.get('title', s['name'])
                success = await send_message_safe(
                    TARGET_CHANNEL_ID,
                    build_post(
                        title, 
                        item['full_name'], 
                        item['stargazers_count'],
                        get_freshness(item['pushed_at']), 
                        final_desc, 
                        item['html_url']
                    )
                )
                
                if success:
                    posted.append(str(item['id']))
                    count += 1
                    logger.info(f"   ✅ Posted: {item['full_name']} (⭐{item['stargazers_count']})")
                    await asyncio.sleep(MESSAGE_DELAY)
            
            await asyncio.sleep(GROQ_DELAY)

    save_state({"posted": posted[-2000:], "commits": commits, "repo_cache": repo_cache})
    
    logger.info(f"\n{'=' * 50}")
    logger.info(f"🏁 Completed! Published: {count}/{MAX_POSTS_PER_RUN}")
    logger.info(f"{'=' * 50}")
    
    await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n⏸ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)

