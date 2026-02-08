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
    level=logging.DEBUG,  # ← ИЗМЕНЕНО: DEBUG для диагностики
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

MAX_AGE_DAYS = 3
MAX_POSTS_PER_RUN = 100
GROQ_DELAY = 2
MESSAGE_DELAY = 3
MIN_STARS = 0
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
    try:
        resp = requests.get("https://api.github.com/rate_limit", headers=API_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            remaining = data['rate']['remaining']
            limit = data['rate']['limit']
            reset_time = datetime.fromtimestamp(data['rate']['reset'], timezone.utc)
            
            logger.info(f"📊 GitHub API: {remaining}/{limit} calls remaining")
            
            if remaining < MIN_API_CALLS_REMAINING:
                logger.warning(f"⚠️ API limit low ({remaining} left). Reset at {reset_time.strftime('%H:%M:%S UTC')}")
                
                if remaining < 10:
                    logger.error(f"⏸ Critical: Only {remaining} calls left. Stopping.")
                    return False
            
            return True
    except Exception as e:
        logger.warning(f"⚠️ Could not check rate limit: {e}")
        return True

# ============ HELPERS ============

def has_non_latin(text):
    if not text: 
        return False
    
    patterns = [
        r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]',
        r'[\u0600-\u06ff\u0750-\u077f\uFB50-\uFDFF\uFE70-\uFEFF]',
        r'[\u0e00-\u0e7f\u1780-\u17ff]',
    ]
    
    return any(re.search(p, text) for p in patterns)

def is_repo_empty(owner, repo, cache):
    """✅ ИСПРАВЛЕНО: Уменьшен TTL кэша до 6 часов"""
    key = f"{owner}/{repo}"
    
    if key in cache:
        try:
            cached_time = datetime.fromisoformat(cache[key]['checked_at'])
            # ✅ ИЗМЕНЕНО: 6 часов вместо 24
            if (datetime.now(timezone.utc) - cached_time).total_seconds() < 21600:
                logger.debug(f"   📦 Cache hit for {key}: empty={cache[key]['is_empty']}")
                return cache[key]['is_empty']
        except:
            pass
    
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        
        if resp.status_code != 200:
            logger.debug(f"   ⚠️ Repo check failed for {key}: status {resp.status_code}")
            result = True
        else:
            data = resp.json()
            size = data.get('size', 0)
            issues = data.get('open_issues_count', 0)
            stars = data.get('stargazers_count', 0)
            
            result = size < 5 or (issues == 0 and stars == 0 and size < 50)
            logger.debug(f"   📦 Repo {key}: size={size}, stars={stars}, issues={issues}, empty={result}")
        
        cache[key] = {
            'is_empty': result,
            'checked_at': datetime.now(timezone.utc).isoformat()
        }
        
        return result
    except Exception as e:
        logger.debug(f"Error checking {key}: {e}")
        return False  # ✅ ИЗМЕНЕНО: При ошибке НЕ считаем пустым

def is_likely_fork_spam(item):
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
    if desc is None:
        return ""
    
    desc = str(desc).strip()
    desc = re.sub(r'[🔥⚡️✨🎉]{3,}', '', desc)
    
    return desc[:max_len] if desc else ""

def get_age_hours(date_string):
    try:
        if not date_string: 
            return 9999
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
    """✅ ИСПРАВЛЕНО: Добавлено логирование"""
    hours = get_age_hours(date_string)
    max_hours = MAX_AGE_DAYS * 24
    is_ok = hours <= max_hours
    if not is_ok:
        logger.debug(f"   ⏰ Not fresh: {hours:.1f}h > {max_hours}h limit")
    return is_ok

def quick_filter(name, desc, stars=0):
    """✅ ИСПРАВЛЕНО: Добавлено логирование причин отклонения"""
    text = f"{name} {desc or ''}".lower()
    full_text = f"{name} {desc or ''}"

    if has_non_latin(full_text):
        logger.debug(f"   ❌ FILTER: hieroglyphs in {name}")
        return False

    if stars < MIN_STARS:
        logger.debug(f"   ❌ FILTER: stars={stars} < {MIN_STARS} for {name}")
        return False

    whitelist = [
        'russia', 'russian', 'ru-block', 'roskomnadzor', 'rkn', 'antizapret',
        'zapret', 'mintsifry', 'tspu', 'sorm', 'роскомнадзор', 'рф',
        'amnezia', 'hysteria', 'reality', 'marzban', 'xray-core',
        'v2ray', 'vless', 'trojan', 'shadowsocks', 'clash', 'sing-box',
        'bypass', 'proxy', 'vpn', 'dpi', 'gfw'  # ✅ ДОБАВЛЕНО: больше ключевых слов
    ]
    if any(w in text for w in whitelist):
        logger.debug(f"   ✅ FILTER: whitelist match for {name}")
        return True

    blacklist = [
        'china', 'chinese', 'cn-', 'iran', 'persian', 'vietnam',
        'homework', 'tutorial', 'example-', 'template', 'deprecated',
        'test-repo', 'demo-', 'practice', 'learning'
    ]
    for kw in blacklist:
        if kw in text:
            logger.debug(f"   ❌ FILTER: blacklist '{kw}' in {name}")
            return False

    noise_patterns = [
        r'\d{4,}',
        r'[A-Z]{8,}',
        r'[-_]{3,}',
    ]
    for p in noise_patterns:
        if re.search(p, name):
            logger.debug(f"   ❌ FILTER: noise pattern in {name}")
            return False

    # ✅ ИЗМЕНЕНО: По умолчанию ПРОПУСКАЕМ, а не блокируем
    logger.debug(f"   ⚠️ FILTER: no match, allowing {name}")
    return True

def build_post(title, repo_full_name, stars, freshness, description, url):
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
                data = json.load(f)
                logger.info(f"📂 Loaded state: {len(data.get('posted', []))} posted, {len(data.get('commits', {}))} commits tracked")
                return data
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
    """✅ ИСПРАВЛЕНО: Проверка нескольких коммитов"""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=5"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code == 200 and resp.json():
            for c in resp.json():
                msg = c['commit']['message'].split('\n')[0][:60]
                
                if has_non_latin(msg):
                    logger.debug(f"   ⏭ SKIP commit (hieroglyphs): {owner}/{repo}")
                    continue
                
                commit_date = c['commit']['committer']['date']
                
                # ✅ ДОБАВЛЕНО: Проверка свежести коммита
                if not is_fresh(commit_date):
                    logger.debug(f"   ⏭ SKIP commit (old): {owner}/{repo} - {commit_date}")
                    continue
                
                return {
                    "sha": c['sha'][:7],
                    "date": commit_date,
                    "msg": msg,
                    "url": c['html_url']
                }
            
            logger.debug(f"   ⚠️ No valid fresh commits for {owner}/{repo}")
    except Exception as e:
        logger.debug(f"Error getting commit for {owner}/{repo}: {e}")
    return None

def get_recent_commits(owner, repo, since_sha=None):
    """✅ НОВАЯ ФУНКЦИЯ: Получение всех новых коммитов после определённого SHA"""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=20"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        
        commits = []
        for c in resp.json():
            sha = c['sha'][:7]
            
            if since_sha and sha == since_sha:
                break
            
            msg = c['commit']['message'].split('\n')[0][:60]
            
            if has_non_latin(msg):
                continue
            
            commit_date = c['commit']['committer']['date']
            if not is_fresh(commit_date):
                break
            
            commits.append({
                "sha": sha,
                "date": commit_date,
                "msg": msg,
                "url": c['html_url']
            })
        
        return commits
    except Exception as e:
        logger.debug(f"Error getting commits for {owner}/{repo}: {e}")
    return []

def search_fresh_repos(query, per_page=50):  # ✅ ИЗМЕНЕНО: 50 вместо 30
    """✅ ИСПРАВЛЕНО: Улучшенный поиск с несколькими стратегиями"""
    results = []
    
    # Стратегия 1: pushed:>date
    date_filter = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime('%Y-%m-%d')
    
    strategies = [
        f"{query}+pushed:>{date_filter}",
        f"{query}+created:>{date_filter}",  # ✅ ДОБАВЛЕНО: новые репо
    ]
    
    seen_ids = set()
    
    for strategy in strategies:
        url = (
            f"https://api.github.com/search/repositories"
            f"?q={strategy}"
            f"&sort=updated&order=desc&per_page={per_page}"
        )
        
        try:
            resp = requests.get(url, headers=API_HEADERS, timeout=15)
            
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                logger.debug(f"   🔍 Strategy '{strategy[:50]}...': found {len(items)} repos")
                
                for item in items:
                    if item['id'] not in seen_ids:
                        seen_ids.add(item['id'])
                        
                        # ✅ ИСПРАВЛЕНО: Проверяем И pushed_at И updated_at
                        pushed_at = item.get('pushed_at')
                        updated_at = item.get('updated_at')
                        
                        if is_fresh(pushed_at) or is_fresh(updated_at):
                            results.append(item)
                        else:
                            logger.debug(f"   ⏰ Skip {item['full_name']}: pushed={pushed_at}, updated={updated_at}")
                            
            elif resp.status_code == 403:
                logger.warning("⚠️ GitHub API rate limit hit!")
                break
            else:
                logger.warning(f"⚠️ Search failed with status {resp.status_code}")
                
        except Exception as e:
            logger.warning(f"⚠️ Search error: {e}")
    
    logger.info(f"   📊 Total unique fresh repos found: {len(results)}")
    return results

def check_repo_activity(owner, repo):
    """✅ НОВАЯ ФУНКЦИЯ: Проверка реальной активности репозитория"""
    url = f"https://api.github.com/repos/{owner}/{repo}/events?per_page=10"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code == 200:
            events = resp.json()
            for event in events:
                event_date = event.get('created_at')
                if event_date and is_fresh(event_date):
                    event_type = event.get('type', 'Unknown')
                    logger.debug(f"   ✅ Fresh activity: {event_type} at {event_date}")
                    return True
            logger.debug(f"   ⚠️ No fresh events for {owner}/{repo}")
        return False
    except Exception as e:
        logger.debug(f"Error checking activity for {owner}/{repo}: {e}")
        return False

async def analyze_relevance(repos):
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
- Панели управления (Marzban, 3X-UI, Hiddify)
- Протоколы: VLESS, Hysteria, Trojan, Shadowsocks, WireGuard
- Клиенты: Nekoray, Clash, Sing-Box, V2RayN

Список репозиториев:
{text}

Ответь для каждого: GOOD или SKIP

GOOD если:
✅ Реально полезный инструмент/конфиг для обхода блокировок
✅ Связан с интернет-цензурой (не только РФ, но и полезный для РФ)
✅ Актуальные списки/базы/конфиги
✅ Форк с реальными улучшениями

SKIP если:
❌ Учебные примеры, домашка, явно устаревший проект
❌ Пустой форк без изменений
❌ Мусор, спам, реклама
❌ Не связан с VPN/прокси/цензурой вообще

Формат ответа (СТРОГО):
1: GOOD
2: SKIP
..."""

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1
        )
        
        response_text = resp.choices[0].message.content
        logger.debug(f"   🤖 AI response:\n{response_text}")
        
        res = {}
        for line in response_text.split('\n'):
            if ':' in line:
                try:
                    idx, verdict = line.split(':', 1)
                    idx = int(idx.strip().replace('.', ''))
                    is_good = 'GOOD' in verdict.upper()
                    res[idx] = is_good
                    logger.debug(f"   🤖 Repo #{idx}: {'GOOD' if is_good else 'SKIP'}")
                except: 
                    pass
        return res
    except Exception as e:
        logger.warning(f"⚠️ AI error: {e}")
        # ✅ ИЗМЕНЕНО: При ошибке AI - пропускаем всё (а не блокируем)
        return {i: True for i in range(1, len(repos) + 1)}

async def generate_desc(name, desc):
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
            
            if generated and not has_non_latin(generated):
                return generated
                
        except Exception as e:
            logger.debug(f"AI description attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)
    
    return "Инструмент для обхода блокировок"

async def send_message_safe(chat_id, text):
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
    logger.info("=" * 60)
    logger.info("🕵️  SCOUT RADAR v7.1 (improved detection)")
    logger.info("=" * 60)

    if not validate_env():
        return

    if not check_rate_limit():
        logger.error("❌ Insufficient API calls. Exiting.")
        return

    state = load_state()
    posted = set(state.get("posted", []))  # ✅ ИЗМЕНЕНО: set для O(1) lookup
    commits = state.get("commits", {})
    repo_cache = state.get("repo_cache", {})
    count = 0
    
    # ✅ ДОБАВЛЕНО: Статистика для отладки
    stats = {
        "total_found": 0,
        "skipped_posted": 0,
        "skipped_filter": 0,
        "skipped_fork": 0,
        "skipped_empty": 0,
        "skipped_ai": 0,
        "posted": 0
    }

    # 1. Проверка агрегаторов (улучшенная)
    logger.info("\n📦 Checking aggregators...")
    for agg in KNOWN_AGGREGATORS:
        if count >= MAX_POSTS_PER_RUN: 
            break
        
        key = f"{agg['owner']}/{agg['repo']}"
        last_known_sha = commits.get(key)
        
        # ✅ ИСПРАВЛЕНО: Получаем ВСЕ новые коммиты
        new_commits = get_recent_commits(agg['owner'], agg['repo'], last_known_sha)
        
        if not new_commits:
            logger.info(f"   ℹ️ {agg['name']}: no new commits")
            continue
        
        logger.info(f"   🆕 {agg['name']}: {len(new_commits)} new commit(s)")
        
        # Постим только последний (чтобы не спамить)
        c = new_commits[0]
        
        success = await send_message_safe(
            TARGET_CHANNEL_ID,
            f"🔄 <b>{agg['name']}</b>\n\n"
            f"⏰ {get_freshness(c['date'])}\n"
            f"📝 <code>{html.escape(c['msg'])}</code>\n"
            f"📊 +{len(new_commits)} коммит(ов)\n\n"
            f"🔗 <a href='{c['url']}'>Посмотреть коммит</a>"
        )
        
        if success:
            commits[key] = c['sha']
            count += 1
            stats["posted"] += 1
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
        
        stats["total_found"] += len(items)

        if not items:
            continue

        candidates = []
        for i in items:
            repo_id = str(i['id'])
            full_name = i.get('full_name', 'unknown')
            
            if repo_id in posted:
                logger.debug(f"   ⏭ Already posted: {full_name}")
                stats["skipped_posted"] += 1
                continue
            
            if not quick_filter(i.get('full_name'), i.get('description'), i.get('stargazers_count', 0)):
                stats["skipped_filter"] += 1
                continue
            
            if is_likely_fork_spam(i):
                logger.debug(f"   ⏭ Fork spam: {full_name}")
                stats["skipped_fork"] += 1
                continue
            
            owner, repo = full_name.split('/')
            if is_repo_empty(owner, repo, repo_cache):
                stats["skipped_empty"] += 1
                continue
            
            candidates.append(i)

        logger.info(f"   📊 Candidates after filtering: {len(candidates)}")

        if not candidates:
            continue

        batch_size = 5  # ✅ ИЗМЕНЕНО: 5 вместо 4
        for batch_start in range(0, len(candidates), batch_size):
            if count >= MAX_POSTS_PER_RUN: 
                break
            
            batch = candidates[batch_start:batch_start + batch_size]
            
            logger.info(f"   🤖 Analyzing batch of {len(batch)} repos...")
            decisions = await analyze_relevance(batch)

            for idx, item in enumerate(batch, 1):
                if count >= MAX_POSTS_PER_RUN: 
                    break
                
                if not decisions.get(idx, False):
                    logger.debug(f"   ⏭ AI rejected: {item['full_name']}")
                    stats["skipped_ai"] += 1
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
                    posted.add(str(item['id']))
                    count += 1
                    stats["posted"] += 1
                    logger.info(f"   ✅ Posted: {item['full_name']} (⭐{item['stargazers_count']})")
                    await asyncio.sleep(MESSAGE_DELAY)
            
            await asyncio.sleep(GROQ_DELAY)

    # ✅ ДОБАВЛЕНО: Детальная статистика
    logger.info(f"\n{'=' * 60}")
    logger.info("📊 STATISTICS:")
    logger.info(f"   Total found: {stats['total_found']}")
    logger.info(f"   Skipped (already posted): {stats['skipped_posted']}")
    logger.info(f"   Skipped (filter): {stats['skipped_filter']}")
    logger.info(f"   Skipped (fork spam): {stats['skipped_fork']}")
    logger.info(f"   Skipped (empty): {stats['skipped_empty']}")
    logger.info(f"   Skipped (AI): {stats['skipped_ai']}")
    logger.info(f"   ✅ Posted: {stats['posted']}")
    logger.info(f"{'=' * 60}")

    save_state({
        "posted": list(posted)[-3000:],  # ✅ ИЗМЕНЕНО: 3000 вместо 2000
        "commits": commits, 
        "repo_cache": repo_cache
    })
    
    logger.info(f"🏁 Completed! Published: {count}/{MAX_POSTS_PER_RUN}")
    
    await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n⏸ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)

