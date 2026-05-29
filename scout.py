#!/usr/bin/env python3
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
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError
from groq import Groq
import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('scout_radar.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TARGET_CHANNEL_ID = os.getenv("CHANNEL_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

STATE_FILE = "scout_history.json"
CONFIG_SOURCES_FILE = "config_sources.json"

MAX_AGE_DAYS = 3
MAX_POSTS_PER_RUN = 100      # увеличено, чтобы хватало на поиск нового
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

# ------------------------------------------------------------
# Списки отслеживаемых проектов (из вашего исходного кода)
# ------------------------------------------------------------
TRACKED_PROJECTS = [
    {"owner": "bol-van", "repo": "zapret", "name": "🛠 Zapret (original)", "priority": "high"},
    {"owner": "bol-van", "repo": "zapret2", "name": "🛠 Zapret 2", "priority": "high"},
    {"owner": "ValdikSS", "repo": "GoodbyeDPI", "name": "🛠 GoodbyeDPI", "priority": "high"},
    {"owner": "hufrea", "repo": "byedpi", "name": "🛠 ByeDPI", "priority": "high"},
    {"owner": "xvzc", "repo": "SpoofDPI", "name": "🛠 SpoofDPI", "priority": "high"},

    {"owner": "amnezia-vpn", "repo": "amnezia-client", "name": "🛡 Amnezia Client", "priority": "high"},
    {"owner": "amnezia-vpn", "repo": "amneziawg-linux-kernel-module", "name": "🛡 AmneziaWG Kernel", "priority": "medium"},
    {"owner": "XTLS", "repo": "Xray-core", "name": "⚡ Xray-core", "priority": "high"},
    {"owner": "SagerNet", "repo": "sing-box", "name": "📦 Sing-Box", "priority": "high"},
    {"owner": "apernet", "repo": "hysteria", "name": "🚀 Hysteria", "priority": "high"},
    {"owner": "Jigsaw-Code", "repo": "outline-server", "name": "📡 Outline Server", "priority": "medium"},
    {"owner": "Jigsaw-Code", "repo": "outline-client", "name": "📡 Outline Client", "priority": "medium"},

    {"owner": "Gozargah", "repo": "Marzban", "name": "🎛 Marzban", "priority": "high"},
    {"owner": "MHSanaei", "repo": "3x-ui", "name": "🎛 3X-UI", "priority": "high"},
    {"owner": "hiddify", "repo": "hiddify-next", "name": "🎛 Hiddify Next", "priority": "high"},
    {"owner": "hiddify", "repo": "Hiddify-Manager", "name": "🎛 Hiddify Manager", "priority": "medium"},

    {"owner": "MatsuriDayo", "repo": "nekoray", "name": "🐱 Nekoray", "priority": "high"},
    {"owner": "2dust", "repo": "v2rayN", "name": "💻 V2RayN", "priority": "high"},
    {"owner": "2dust", "repo": "v2rayNG", "name": "📱 V2RayNG", "priority": "high"},
    {"owner": "metacubex", "repo": "ClashMeta", "name": "⚔️ Clash Meta", "priority": "medium"},
    {"owner": "metacubex", "repo": "mihomo", "name": "⚔️ Mihomo", "priority": "medium"},

    {"owner": "AntiZapret", "repo": "antizapret", "name": "🛡 AntiZapret", "priority": "high"},
    {"owner": "AntiZapret", "repo": "antizapret-pac-generator-light", "name": "🛡 AntiZapret PAC", "priority": "medium"},
    {"owner": "zapret-info", "repo": "z-i", "name": "📋 Zapret-Info", "priority": "medium"},
    {"owner": "C24Be", "repo": "AS_REG", "name": "📋 AS Registry RU", "priority": "medium"},

    {"owner": "roskomsvoboda", "repo": "censortracker", "name": "📢 CensorTracker", "priority": "high"},
    {"owner": "roskomsvoboda", "repo": "moscow_covid_queues", "name": "📢 RKS Tools", "priority": "low"},
]

CONFIG_AGGREGATORS = [
    {"owner": "Leon406", "repo": "SubCrawler", "name": "📡 SubCrawler"},
    {"owner": "peasoft", "repo": "NoMoreWalls", "name": "📡 NoMoreWalls"},
    {"owner": "barry-far", "repo": "V2ray-Configs", "name": "📡 V2ray-Configs"},
    {"owner": "mahdibland", "repo": "V2RayAggregator", "name": "📡 V2RayAggregator"},
    {"owner": "Pawdroid", "repo": "Free-servers", "name": "📡 Free-servers"},
    {"owner": "aiboboxx", "repo": "v2rayfree", "name": "📡 V2RayFree"},
]

FRESH_SEARCHES = [
    {"name": "Zapret Tools", "title": "🛠 Zapret инструменты", "query": "zapret OR zapret-discord OR zapret-youtube", "priority": 10},
    {"name": "DPI Bypass", "title": "🛠 DPI Bypass", "query": "dpi-bypass OR bypass-dpi OR nodpi", "priority": 10},
    {"name": "RKN Block", "title": "👁 РКН блокировки", "query": "roskomnadzor OR rkn-block OR rkn-bypass", "priority": 10},
    {"name": "TSPU", "title": "👁 ТСПУ", "query": "tspu OR sorm OR russia-censorship", "priority": 9},
    {"name": "AntiZapret", "title": "🛡 AntiZapret", "query": "antizapret OR anti-zapret", "priority": 10},

    {"name": "Russia VPN Tools", "title": "🔧 VPN инструменты для РФ",
     "query": "vpn russia bypass OR vpn russia censorship OR russia vpn tool", "priority": 8},
    {"name": "RU VPN Configs", "title": "🔧 Конфиги VPN для РФ",
     "query": "russia vless OR russia reality OR russia hysteria", "priority": 9},

    {"name": "VLESS Reality", "title": "🔧 VLESS Reality", "query": "vless-reality OR reality-config", "priority": 8},
    {"name": "Hysteria2", "title": "🚀 Hysteria 2", "query": "hysteria2 OR hysteria-2", "priority": 8},
    {"name": "XRay Config", "title": "⚡ XRay конфиги", "query": "xray-config OR xray-russia", "priority": 7},
    {"name": "Amnezia", "title": "🛡 Amnezia", "query": "amnezia-vpn OR amneziawg", "priority": 9},
    {"name": "Marzban", "title": "🎛 Marzban", "query": "marzban-panel OR marzban-node", "priority": 8},
    {"name": "Geosite RU", "title": "🗺 Geosite Russia", "query": "geosite-russia OR geoip-russia", "priority": 7},
    {"name": "Domain List RU", "title": "📋 Списки доменов", "query": "russia-domains OR ru-blocked-domains", "priority": 7},
    {"name": "Proxy Configs", "title": "📡 Прокси конфиги", "query": "proxy-config-russia OR free-proxy-russia", "priority": 6},
    {"name": "Sing-Box RU", "title": "📦 Sing-Box", "query": "sing-box-russia OR singbox-config", "priority": 7},
    {"name": "Clash Rules", "title": "⚔️ Clash правила", "query": "clash-rules-russia OR clash-meta-russia", "priority": 6},
    {"name": "Shadowsocks", "title": "🔐 Shadowsocks", "query": "shadowsocks-russia OR ss-config", "priority": 6},
    {"name": "WireGuard RU", "title": "🔒 WireGuard", "query": "wireguard-russia OR wg-config-russia", "priority": 6},
    {"name": "Outline", "title": "📡 Outline", "query": "outline-russia OR outline-config", "priority": 6},
    {"name": "Censorship", "title": "🌐 Антицензура", "query": "anti-censorship russia OR internet-freedom russia", "priority": 7},

    {"name": "Reality Extra", "title": "🔧 Reality доп. запросы",
     "query": "reality vless OR xray reality OR sing-box reality", "priority": 7},
    {"name": "Hysteria2 Extra", "title": "🚀 Hysteria2 доп. запросы",
     "query": "hysteria2 reality OR hysteria2 config", "priority": 7},
    {"name": "Subconverter", "title": "🔧 Subconverter/Subscriptions",
     "query": "subconverter OR clash subscription OR subscription converter", "priority": 6},
]

FRESH_SEARCHES.sort(key=lambda x: x.get('priority', 5), reverse=True)

CONFIG_SEARCH_QUERIES = [
    "v2ray configs free",
    "vless reality subscription",
    "vless reality v2ray",
    "v2ray subscription link",
    "free vless configs",
    "vpn configs russia vless",
    "hysteria2 reality config",
    "clash reality subscription",
    "subconverter subscription",
    "xray reality vless config",
]

CONFIG_URL_PATTERNS = [
    r"https://raw\.githubusercontent\.com[^\s\"']+",
    r"https://github\.com[^\s\"']+/raw[^\s\"']*",
    r"https?://[^\s\"']*(?:sub|subscription|clash\.ya?ml|config|proxy)[^\s\"']*",
    r"https://gist\.githubusercontent\.com[^\s\"']+",
    r"https?://pastebin\.com/[^\s\"']+",
    r"https?://[^\s\"']*(?:vless|vmess|hysteria2|reality)[^\s\"']*",
]

# ------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (без изменений)
# ------------------------------------------------------------
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

def check_rate_limit():
    try:
        resp = requests.get("https://api.github.com/rate_limit", headers=API_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            remaining = data['rate']['remaining']
            limit = data['rate']['limit']
            logger.info(f"📊 GitHub API: {remaining}/{limit} calls remaining")
            if remaining < MIN_API_CALLS_REMAINING:
                logger.warning(f"⚠️ API limit low ({remaining} left)")
                if remaining < 10:
                    return False
            return True
    except Exception as e:
        logger.warning(f"⚠️ Could not check rate limit: {e}")
    return True

def has_non_latin(text):
    if not text:
        return False
    patterns = [
        r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]',
        r'[\u0600-\u06ff\u0750-\u077f\uFB50-\uFDFF\uFE70-\uFEFF]',
        r'[\u0e00-\u0e7f\u1780-\u17ff]',
    ]
    return any(re.search(p, text) for p in patterns)

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
    if hours < 1:
        return "🔥 Только что"
    elif hours < 6:
        return f"🔥 {int(hours)}ч назад"
    elif hours < 24:
        return "🔥 Сегодня"
    elif hours < 48:
        return "✅ Вчера"
    elif hours < 72:
        return "📅 2 дня назад"
    else:
        return f"📅 {int(hours/24)}д назад"

def is_fresh(date_string):
    return get_age_hours(date_string) <= (MAX_AGE_DAYS * 24)

def safe_desc(desc, max_len=120):
    if desc is None:
        return ""
    desc = str(desc).strip()
    desc = re.sub(r'[🔥⚡️✨🎉]{3,}', '', desc)
    return desc[:max_len] if desc else ""

def quick_filter(name, desc, stars=0):
    text = f"{name} {desc or ''}".lower()
    full_text = f"{name} {desc or ''}"
    if has_non_latin(full_text):
        return False
    if stars < MIN_STARS:
        return False
    irrelevant_categories = [
        'vocabulary', 'trainer', 'learning', 'educational', 'course',
        'tutorial', 'lesson', 'homework', 'student', 'university',
        'language-learning', 'flashcard', 'quiz',
        'market', 'steel', 'trading', 'business', 'finance',
        'ecommerce', 'shop', 'store', 'retail', 'analytics',
        'example-', 'demo-', 'template', 'boilerplate', 'starter',
        'practice', 'exercise', 'sample',
        'recipe', 'cooking', 'food', 'restaurant', 'travel',
        'portfolio', 'resume', 'cv',
        'game', 'minigame',
    ]
    if any(cat in text for cat in irrelevant_categories):
        logger.debug(f"   ❌ Filtered by category: {name}")
        return False
    if 'russia' in text or 'russian' in text:
        vpn_context_required = [
            'vpn', 'proxy', 'bypass', 'dpi', 'censorship',
            'block', 'unblock', 'freedom', 'gfw',
            'zapret', 'rkn', 'sorm', 'tspu',
            'vless', 'vmess', 'xray', 'v2ray', 'reality',
            'shadowsocks', 'trojan', 'hysteria', 'wireguard',
            'amnezia', 'outline', 'clash', 'sing-box',
        ]
        if not any(ctx in text for ctx in vpn_context_required):
            logger.debug(f"   ❌ 'russia' without VPN context: {name}")
            return False
    whitelist = [
        'zapret', 'zapret2', 'antizapret', 'dpi-bypass', 'bypass-dpi', 'nodpi',
        'goodbyedpi', 'byedpi', 'spoofdpi', 'amnezia', 'amneziawg',
        'xray-core', 'xray', 'vless-reality', 'reality', 'vless',
        'hysteria2', 'hysteria', 'trojan', 'shadowsocks', 'wireguard',
        'clash-meta', 'sing-box', 'singbox', 'marzban', '3x-ui',
        'hiddify', 'nekoray', 'v2rayn', 'v2rayng',
        'roskomnadzor', 'rkn', 'tspu', 'sorm',
        'geosite', 'geoip', 'blocked-domains', 'block-list',
        'censorship', 'freedom', 'unblock', 'gfw'
    ]
    blacklist = [
        'china', 'chinese', 'cn-', 'iran', 'persian', 'vietnam',
        'vocabulary', 'trainer', 'flashcard', 'quiz', 'market',
        'steel', 'trading', 'business', 'finance', 'ecommerce',
        'shop', 'store', 'retail', 'analytics', 'recipe', 'cooking',
        'food', 'restaurant', 'travel', 'portfolio', 'resume', 'cv',
        'game', 'minigame', 'weather', 'calculator', 'notebook',
        'crypto', 'nft', 'blockchain', 'defi', 'sms', 'caller',
        'video', 'stream', 'youtube-dl', 'pomodoro', 'meditation',
        'workout', 'fitness', 'mental-health'
    ]
    if any(k in text for k in blacklist):
        logger.debug(f"   ❌ Blacklisted: {name}")
        return False
    if any(w in text for w in whitelist):
        return True
    return False

def is_likely_fork_spam(item):
    if not item.get('fork'):
        return False
    if item.get('stargazers_count', 0) == 0 and item.get('forks_count', 0) == 0:
        return True
    return False

async def get_default_branch(session, owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('default_branch', 'main')
    except Exception as e:
        logger.debug(f"Error getting default branch for {owner}/{repo}: {e}")
    return 'main'

async def fetch_repo_text_async(owner, repo):
    try:
        async with aiohttp.ClientSession(headers=API_HEADERS) as session:
            branch = await get_default_branch(session, owner, repo)
            urls = [
                f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md",
                f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md",
                f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md",
            ]
            for url in urls:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            logger.debug(f"   ✅ README loaded from {url}")
                            return text
                except asyncio.TimeoutError:
                    logger.debug(f"   ⏱ Timeout loading {url}")
                    continue
                except Exception as e:
                    logger.debug(f"   ⚠️ Error loading {url}: {e}")
                    continue
    except Exception as e:
        logger.debug(f"Error fetching README for {owner}/{repo}: {e}")
    return ""

def get_recent_releases(owner, repo, limit=5):
    url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page={limit}"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code == 200:
            releases = []
            for r in resp.json():
                if is_fresh(r.get('published_at', r.get('created_at'))):
                    releases.append({
                        "tag": r.get('tag_name', ''),
                        "name": r.get('name', r.get('tag_name', '')),
                        "date": r.get('published_at', r.get('created_at')),
                        "url": r.get('html_url', ''),
                        "body": (r.get('body', '') or '')[:300],
                        "prerelease": r.get('prerelease', False)
                    })
            return releases
    except Exception as e:
        logger.debug(f"Error getting releases for {owner}/{repo}: {e}")
    return []

def get_last_commit(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=10)
        if resp.status_code == 200 and resp.json():
            c = resp.json()[0]
            msg = c['commit']['message'].split('\n')[0][:60]
            if has_non_latin(msg):
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

def search_fresh_repos(query, per_page=40):
    date_filter = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime('%Y-%m-%d')
    results = []
    seen_ids = set()
    strategies = [
        f"{query}+pushed:>{date_filter}+language:python+NOT+fork:true",
        f"{query}+created:>{date_filter}+language:python+NOT+fork:true",
    ]
    for strategy in strategies:
        url = f"https://api.github.com/search/repositories?q={strategy}&sort=updated&order=desc&per_page={per_page}"
        try:
            resp = requests.get(url, headers=API_HEADERS, timeout=15)
            if resp.status_code == 200:
                for item in resp.json().get('items', []):
                    if item['id'] not in seen_ids:
                        seen_ids.add(item['id'])
                        if is_fresh(item.get('pushed_at')) or is_fresh(item.get('updated_at')):
                            results.append(item)
            elif resp.status_code == 403:
                logger.warning("⚠️ GitHub API rate limit!")
                break
        except Exception as e:
            logger.warning(f"⚠️ Search error: {e}")
    return results

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                data['posted'] = data.get('posted', [])[-3000:]
                if 'dynamic_tracked' not in data:
                    data['dynamic_tracked'] = {}
                if 'releases_meta' not in data:
                    data['releases_meta'] = {}
                if 'config_urls' not in data:
                    data['config_urls'] = {}
                logger.info(
                    f"📂 Loaded: {len(data.get('posted', []))} posted, "
                    f"{len(data.get('releases', {}))} releases, "
                    f"{len(data.get('dynamic_tracked', {}))} dynamic tracked"
                )
                return data
        except Exception as e:
            logger.warning(f"Could not load state: {e}")
    return {
        "posted": [],
        "commits": {},
        "releases": {},
        "repo_cache": {},
        "last_run": None,
        "dynamic_tracked": {},
        "releases_meta": {},
        "config_urls": {},
    }

def save_state(state):
    state['last_run'] = datetime.now(timezone.utc).isoformat()
    state['posted'] = state.get('posted', [])[-3000:]
    try:
        with open(STATE_FILE, "w", encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.info(
            f"💾 State saved "
            f"(posted={len(state.get('posted', []))}, "
            f"commits={len(state.get('commits', {}))}, "
            f"releases={len(state.get('releases', {}))}, "
            f"dynamic_tracked={len(state.get('dynamic_tracked', {}))})"
        )
    except Exception as e:
        logger.error(f"❌ Could not save state: {e}")

def load_config_sources():
    if os.path.exists(CONFIG_SOURCES_FILE):
        try:
            with open(CONFIG_SOURCES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load config_sources: {e}")
    return []

def save_config_sources(sources):
    try:
        with open(CONFIG_SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(sources, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Config sources saved: {len(sources)} urls")
    except Exception as e:
        logger.error(f"❌ Could not save config_sources: {e}")

# ------------------------------------------------------------
# НОВЫЙ AI с поддержкой категорий и исправленным парсингом
# ------------------------------------------------------------
async def analyze_relevance(repos):
    if not repos:
        return {}
    text = "\n".join([
        f"{i+1}. {r['full_name']} | ⭐{r['stargazers_count']} | {safe_desc(r['description'], 80)}"
        for i, r in enumerate(repos)
    ])
    prompt = f"""Оцени репозитории для канала про обход блокировок в РФ.

Категории важности:
- HIGH: новый инструмент/протокол/метод обхода (Zapret2, Hysteria2, Reality, AmneziaWG)
- MEDIUM: обновлённые списки (whitelist, geoip, домены), генераторы конфигов, панели управления
- LOW: учебные проекты, форки без изменений, не связанные с VPN/цензурой

❌ Нерелевантные темы (сразу LOW или SKIP):
- Обучение языку, бизнес/рынок, игры, утилиты без тематики обхода блокировок
- Любые проекты с "russia" БЕЗ VPN/DPI/цензуры-контекста

Репозитории:
{text}

Ответь строго в формате:
1: HIGH/MEDIUM/LOW/SKIP
2: HIGH/MEDIUM/LOW/SKIP
...
"""
    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3
        )
        res = {}
        content = resp.choices[0].message.content
        logger.debug(f"🤖 AI raw response: {content}")
        for line in content.split('\n'):
            if ':' in line:
                try:
                    idx, verdict = line.split(':', 1)
                    idx = int(idx.strip().replace('.', ''))
                    verdict = verdict.strip().upper()
                    # Нормализация
                    if verdict in ('GOOD', '1', 'HIGH', 'MEDIUM'):
                        category = 'HIGH' if verdict in ('HIGH', 'GOOD', '1') else 'MEDIUM'
                        res[idx] = {'publish': True, 'category': category}
                    elif verdict in ('SKIP', '2', 'LOW'):
                        res[idx] = {'publish': False, 'category': 'LOW'}
                    else:
                        res[idx] = {'publish': False, 'category': 'LOW'}
                except:
                    pass
        # Если ответ не распарсился, публикуем всё как MEDIUM (безопасно)
        if not res:
            logger.warning("⚠️ AI response parsing failed, fallback to publish all as MEDIUM")
            return {i: {'publish': True, 'category': 'MEDIUM'} for i in range(1, len(repos) + 1)}
        return res
    except Exception as e:
        logger.warning(f"⚠️ AI error: {e}, fallback to publish all as MEDIUM")
        return {i: {'publish': True, 'category': 'MEDIUM'} for i in range(1, len(repos) + 1)}

async def generate_desc(name, desc):
    if desc and len(desc) > 25 and not has_non_latin(desc):
        return desc
    prompt = f"""Репозиторий: {name}
Описание: {desc or 'нет'}

Напиши краткое описание (1 предложение, до 80 символов) на русском.
Контекст: VPN, обход блокировок.

Описание:"""
    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.3
        )
        generated = resp.choices[0].message.content.strip()
        if generated and not has_non_latin(generated):
            return generated
    except Exception as e:
        logger.debug(f"Error generating description: {e}")
    return "Инструмент для обхода блокировок"

async def check_repo_relevance(owner: str, repo: str, repo_cache: dict) -> bool:
    cache_key = f"relevance:{owner}/{repo}"
    if cache_key in repo_cache:
        return repo_cache[cache_key]
    text = await fetch_repo_text_async(owner, repo)
    if not text:
        repo_cache[cache_key] = False
        return False
    low = text.lower()
    required_terms = [
        'vpn', 'proxy', 'bypass', 'censorship', 'dpi',
        'vless', 'vmess', 'xray', 'v2ray', 'shadowsocks',
        'trojan', 'hysteria', 'wireguard', 'clash', 'sing-box',
        'zapret', 'rkn', 'roskomnadzor', 'sorm', 'tspu',
    ]
    if not any(term in low for term in required_terms):
        logger.debug(f"   ❌ No VPN/DPI terms in README: {owner}/{repo}")
        repo_cache[cache_key] = False
        return False
    bad_signs = [
        'vocabulary trainer', 'language learning', 'flashcard',
        'steel market', 'commodity market', 'stock market',
        'cooking recipe', 'restaurant', 'shopping cart', 'ecommerce',
    ]
    if any(sign in low for sign in bad_signs):
        logger.debug(f"   ❌ Irrelevant content in README: {owner}/{repo}")
        repo_cache[cache_key] = False
        return False
    repo_cache[cache_key] = True
    return True

async def send_message_safe(chat_id, text):
    if has_non_latin(text):
        logger.warning("⚠️ Blocked message with hieroglyphs!")
        return False
    for attempt in range(3):
        try:
            await bot.send_message(chat_id, text, disable_web_page_preview=True)
            return True
        except TelegramRetryAfter as e:
            logger.warning(f"⚠️ Flood control: waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            logger.error("❌ Bot blocked by user/chat")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Send attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2 ** attempt)
    return False

def build_release_post(project_name, release, owner, repo):
    tag = release['tag']
    body = release['body']
    if body:
        body = re.sub(r'#{1,6}\s*', '', body)
        body = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', body)
        body = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', body)
        body = body[:200] + ('...' if len(body) > 200 else '')
    text = (
        f"🚀 <b>Новый релиз: {html.escape(project_name)}</b>\n\n"
        f"📦 <code>{owner}/{repo}</code>\n"
        f"🏷 Версия: <b>{html.escape(tag)}</b>\n"
        f"⏰ {get_freshness(release['date'])}\n"
    )
    if body:
        text += f"\n📝 {html.escape(body)}\n"
    text += f"\n🔗 <a href='{release['url']}'>Скачать релиз</a>"
    return text

def build_commit_post(project_name, commit, owner, repo):
    return (
        f"🔄 <b>{html.escape(project_name)}</b>\n\n"
        f"📦 <code>{owner}/{repo}</code>\n"
        f"⏰ {get_freshness(commit['date'])}\n"
        f"📝 <code>{html.escape(commit['msg'])}</code>\n\n"
        f"🔗 <a href='{commit['url']}'>Посмотреть коммит</a>"
    )

def build_repo_post(title, repo_full_name, stars, freshness, description, url):
    return (
        f"<b>{title}</b>\n\n"
        f"📦 <code>{html.escape(repo_full_name)}</code>\n"
        f"⭐️ {stars} | ⏰ {freshness}\n"
        f"💡 {html.escape(description)}\n\n"
        f"🔗 <a href='{url}'>Открыть на GitHub</a>"
    )

def extract_config_urls(text: str):
    urls = set()
    if not text:
        return []
    for pattern in CONFIG_URL_PATTERNS:
        for m in re.findall(pattern, text):
            urls.add(m.strip())
    candidates = []
    for u in urls:
        low = u.lower()
        if any(proto in low for proto in ["vless", "vmess", "hysteria", "hysteria2", "trojan", "shadow", "sub", "clash"]):
            candidates.append(u)
    return candidates

def filter_url_for_russia_and_vless(url: str) -> bool:
    low = url.lower()
    if not any(p in low for p in ["vless", "reality", "vmess", "xray", "v2ray", "clash", "sub", "subscription"]):
        return False
    bad_markers = ["iran", "/ir-", "iran-"]
    if any(b in low for b in bad_markers):
        return False
    if re.search(r'Sub\d+\.txt$', url):
        return False
    return True

# ------------------------------------------------------------
# НОВАЯ ФУНКЦИЯ: отслеживание новых конфигов в агрегаторах
# ------------------------------------------------------------
async def discover_new_config_urls(state):
    new_global = []
    config_urls_state = state.get('config_urls', {})
    for agg in CONFIG_AGGREGATORS:
        key = f"{agg['owner']}/{agg['repo']}"
        old_urls = set(config_urls_state.get(key, []))
        text = await fetch_repo_text_async(agg['owner'], agg['repo'])
        if not text:
            continue
        new_urls = set(extract_config_urls(text))
        added = new_urls - old_urls
        if added:
            logger.info(f"🆕 Новые конфиги в {agg['name']}: {added}")
            for url in added:
                if filter_url_for_russia_and_vless(url):
                    new_global.append(url)
            config_urls_state[key] = list(new_urls)
    if new_global:
        existing = set(load_config_sources())
        save_config_sources(list(existing | set(new_global)))
    state['config_urls'] = config_urls_state
    return new_global

# ------------------------------------------------------------
# ФИЛЬТРАЦИЯ КОММИТОВ И РЕЛИЗОВ
# ------------------------------------------------------------
def is_commit_worth_posting(commit_msg: str) -> bool:
    msg_lower = commit_msg.lower()
    trivial = ['typo', 'readme', 'update readme', 'fix readme', 'docs', 'chore', 'bump version', 'merge', 'ci']
    if any(word in msg_lower for word in trivial):
        return False
    interesting = [
        'new', 'feature', 'add', 'bypass', 'whitelist', 'blacklist', 'geoip',
        'vless', 'reality', 'hysteria', 'trojan', 'config', 'subscription',
        'fix block', 'unblock', 'rkn', 'dpi', 'zapret', 'release', 'version'
    ]
    return any(word in msg_lower for word in interesting)

def is_release_worth_posting(release_tag: str, release_body: str, last_major_minor: tuple) -> bool:
    try:
        tag_clean = release_tag.lstrip('v')
        parts = tag_clean.split('.')
        if len(parts) >= 2:
            current = (parts[0], parts[1])
            if current != last_major_minor:
                return True
    except:
        pass
    body_lower = release_body.lower()
    keywords = ['new feature', 'add', 'bypass', 'experimental', 'breaking change', 'critical', 'security']
    return any(kw in body_lower for kw in keywords)

# ------------------------------------------------------------
# ОСНОВНАЯ ФУНКЦИЯ
# ------------------------------------------------------------
async def main():
    logger.info("=" * 60)
    logger.info("🕵️  SCOUT RADAR v9.0 (intelligent filtering)")
    logger.info("=" * 60)

    if not validate_env():
        return
    if not check_rate_limit():
        logger.error("❌ Insufficient API calls. Exiting.")
        return

    state = load_state()
    posted = set(state.get("posted", []))
    commits = state.get("commits", {})
    releases = state.get("releases", {})
    repo_cache = state.get("repo_cache", {})
    dynamic_tracked = state.get("dynamic_tracked", {})
    releases_meta = state.get("releases_meta", {})
    count = 0

    all_tracked_projects = list(TRACKED_PROJECTS)
    for full_name, meta in dynamic_tracked.items():
        try:
            owner, repo = full_name.split("/")
        except ValueError:
            continue
        all_tracked_projects.append({
            "owner": owner,
            "repo": repo,
            "name": f"🆕 {full_name}",
            "priority": meta.get("priority", "medium"),
        })

    logger.info(f"📡 Tracked projects: static={len(TRACKED_PROJECTS)}, dynamic={len(dynamic_tracked)}")

    # 1. Релизы с фильтрацией
    logger.info("\n🚀 Checking releases...")
    for project in all_tracked_projects:
        if count >= MAX_POSTS_PER_RUN:
            break
        owner = project['owner']
        repo = project['repo']
        name = project['name']
        key = f"{owner}/{repo}"
        fresh_releases = get_recent_releases(owner, repo)
        if not fresh_releases:
            continue
        last = releases_meta.get(key, ('0','0'))
        for rel in fresh_releases:
            if count >= MAX_POSTS_PER_RUN:
                break
            release_key = f"{key}:{rel['tag']}"
            if release_key in releases:
                continue
            if is_release_worth_posting(rel['tag'], rel['body'], last):
                logger.info(f"   🆕 Release: {name} {rel['tag']}")
                success = await send_message_safe(
                    TARGET_CHANNEL_ID,
                    build_release_post(name, rel, owner, repo)
                )
                if success:
                    releases[release_key] = rel['date']
                    try:
                        parts = rel['tag'].lstrip('v').split('.')
                        if len(parts) >= 2:
                            releases_meta[key] = (parts[0], parts[1])
                    except:
                        pass
                    count += 1
                    await asyncio.sleep(MESSAGE_DELAY)
            else:
                logger.debug(f"   ⏭ Skipped trivial release: {rel['tag']}")

    # 2. Коммиты (только значимые)
    logger.info("\n🔄 Checking commits...")
    for project in all_tracked_projects:
        if count >= MAX_POSTS_PER_RUN:
            break
        if project.get('priority') == 'low' and count > MAX_POSTS_PER_RUN // 2:
            continue
        owner = project['owner']
        repo = project['repo']
        name = project['name']
        key = f"{owner}/{repo}"
        commit = get_last_commit(owner, repo)
        if not commit or not is_fresh(commit['date']):
            continue
        if commits.get(key) == commit['sha']:
            continue
        if not is_commit_worth_posting(commit['msg']):
            logger.debug(f"   ⏭ Trivial commit: {commit['msg']}")
            commits[key] = commit['sha']
            continue
        logger.info(f"   🆕 Commit: {name}")
        success = await send_message_safe(
            TARGET_CHANNEL_ID,
            build_commit_post(name, commit, owner, repo)
        )
        if success:
            commits[key] = commit['sha']
            count += 1
            await asyncio.sleep(MESSAGE_DELAY)

    # 3. Новые конфиги в агрегаторах
    logger.info("\n📡 Checking config aggregators for new URLs...")
    new_urls = await discover_new_config_urls(state)
    for url in new_urls:
        if count >= MAX_POSTS_PER_RUN:
            break
        await send_message_safe(
            TARGET_CHANNEL_ID,
            f"📡 <b>Новый источник подписки</b>\n\n<code>{html.escape(url)}</code>"
        )
        count += 1
        await asyncio.sleep(MESSAGE_DELAY)

    # 4. Поиск новых репозиториев с AI-категоризацией
    logger.info("\n🔍 Searching for new repositories...")
    for s in FRESH_SEARCHES:
        if count >= MAX_POSTS_PER_RUN:
            break
        if not check_rate_limit():
            break
        logger.info(f"\n🔍 {s['name']}...")
        items = search_fresh_repos(s['query'])
        if not items:
            continue
        candidates = []
        for i in items:
            repo_id = str(i['id'])
            if repo_id in posted:
                continue
            if not quick_filter(i.get('full_name'), i.get('description'), i.get('stargazers_count', 0)):
                continue
            if is_likely_fork_spam(i):
                continue
            # Пропускаем пустые репозитории без README
            if i.get('stargazers_count', 0) == 0 and not i.get('description'):
                owner, repo = i['full_name'].split('/')
                readme = await fetch_repo_text_async(owner, repo)
                if not readme or len(readme) < 100:
                    logger.debug(f"   ⏭ Empty/trivial repo: {i['full_name']}")
                    continue
            candidates.append(i)
        if not candidates:
            continue
        batch_size = 10
        for batch_start in range(0, len(candidates), batch_size):
            if count >= MAX_POSTS_PER_RUN:
                break
            batch = candidates[batch_start:batch_start + batch_size]
            decisions = await analyze_relevance(batch)
            for local_idx, item in enumerate(batch, start=1):
                if count >= MAX_POSTS_PER_RUN:
                    break
                dec = decisions.get(local_idx, {'publish': False, 'category': 'LOW'})
                if not dec['publish']:
                    logger.debug(f"   ⏭ AI skipped ({dec['category']}): {item['full_name']}")
                    continue
                owner, repo = item['full_name'].split('/')
                is_relevant = await check_repo_relevance(owner, repo, repo_cache)
                if not is_relevant:
                    logger.info(f"   ⏭ Skipped (irrelevant README): {item['full_name']}")
                    continue
                final_desc = await generate_desc(item['full_name'], item['description'])
                cat_emoji = "🔥" if dec['category'] == 'HIGH' else "📌"
                title = f"{cat_emoji} {s.get('title', s['name'])}"
                success = await send_message_safe(
                    TARGET_CHANNEL_ID,
                    build_repo_post(
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
                    dynamic_tracked[item['full_name']] = {
                        "first_seen": datetime.now(timezone.utc).isoformat(),
                        "priority": "medium",
                        "ai_category": dec['category']
                    }
                    logger.info(f"   ✅ {item['full_name']} (category {dec['category']}) added")
                    count += 1
                    await asyncio.sleep(MESSAGE_DELAY)
            await asyncio.sleep(GROQ_DELAY)

    # Финальное сохранение
    save_state({
        "posted": list(posted),
        "commits": commits,
        "releases": releases,
        "repo_cache": repo_cache,
        "dynamic_tracked": dynamic_tracked,
        "releases_meta": releases_meta,
        "config_urls": state.get('config_urls', {})
    })

    logger.info(f"\n{'=' * 60}")
    logger.info(f"🏁 Completed! Published: {count} posts")
    logger.info(f"{'=' * 60}")

    await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n⏸ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
