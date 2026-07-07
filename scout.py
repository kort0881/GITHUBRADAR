#!/usr/bin/env python3
import os
import json
import asyncio
import requests
import html
import re
import logging
import time
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
CONFIG_CHANNEL_ID = os.getenv("CONFIG_CHANNEL_ID")   # РІвЂ С’ Р Р…Р С•Р Р†РЎвЂ№Р в„– Р С”Р В°Р Р…Р В°Р В» Р Т‘Р В»РЎРЏ Р С—Р С•Р Т‘Р С—Р С‘РЎРѓР С•Р С”
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

STATE_FILE = "scout_history.json"
CONFIG_SOURCES_FILE = "config_sources.json"

MAX_AGE_DAYS = 3                # Р Т‘Р В»РЎРЏ Р С—Р С•Р С‘РЎРѓР С”Р В° Р Р…Р С•Р Р†РЎвЂ№РЎвЂ¦ Р С‘Р Р…РЎРѓРЎвЂљРЎР‚РЎС“Р СР ВµР Р…РЎвЂљР С•Р Р†
MAX_CONFIG_AGE_DAYS = 60        # Р Т‘Р В»РЎРЏ Р С—Р С•Р С‘РЎРѓР С”Р В° Р С—Р С•Р Т‘Р С—Р С‘РЎРѓР Р…РЎвЂ№РЎвЂ¦ РЎРѓРЎРѓРЎвЂ№Р В»Р С•Р С” (2 Р СР ВµРЎРѓРЎРЏРЎвЂ Р В°)
MAX_POSTS_PER_RUN = 150
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
# Р РЋР С—Р С‘РЎРѓР С”Р С‘ Р С•РЎвЂљРЎРѓР В»Р ВµР В¶Р С‘Р Р†Р В°Р ВµР СРЎвЂ№РЎвЂ¦ Р С—РЎР‚Р С•Р ВµР С”РЎвЂљР С•Р Р† (Р С‘Р В· Р Р†Р В°РЎв‚¬Р ВµР С–Р С• Р С‘РЎРѓРЎвЂ¦Р С•Р Т‘Р Р…Р С•Р С–Р С• Р С”Р С•Р Т‘Р В°)
# ------------------------------------------------------------
TRACKED_PROJECTS = [
    {"owner": "bol-van", "repo": "zapret", "name": "СЂСџвЂє  Zapret (original)", "priority": "high"},
    {"owner": "bol-van", "repo": "zapret2", "name": "СЂСџвЂє  Zapret 2", "priority": "high"},
    {"owner": "ValdikSS", "repo": "GoodbyeDPI", "name": "СЂСџвЂє  GoodbyeDPI", "priority": "high"},
    {"owner": "hufrea", "repo": "byedpi", "name": "СЂСџвЂє  ByeDPI", "priority": "high"},
    {"owner": "xvzc", "repo": "SpoofDPI", "name": "СЂСџвЂє  SpoofDPI", "priority": "high"},

    {"owner": "amnezia-vpn", "repo": "amnezia-client", "name": "СЂСџвЂєРЋ Amnezia Client", "priority": "high"},
    {"owner": "amnezia-vpn", "repo": "amneziawg-linux-kernel-module", "name": "СЂСџвЂєРЋ AmneziaWG Kernel", "priority": "medium"},
    {"owner": "XTLS", "repo": "Xray-core", "name": "РІС™РЋ Xray-core", "priority": "high"},
    {"owner": "SagerNet", "repo": "sing-box", "name": "СЂСџвЂњВ¦ Sing-Box", "priority": "high"},
    {"owner": "apernet", "repo": "hysteria", "name": "СЂСџС™Р‚ Hysteria", "priority": "high"},
    {"owner": "Jigsaw-Code", "repo": "outline-server", "name": "СЂСџвЂњРЋ Outline Server", "priority": "medium"},
    {"owner": "Jigsaw-Code", "repo": "outline-client", "name": "СЂСџвЂњРЋ Outline Client", "priority": "medium"},

    {"owner": "Gozargah", "repo": "Marzban", "name": "СЂСџР‹вЂє Marzban", "priority": "high"},
    {"owner": "MHSanaei", "repo": "3x-ui", "name": "СЂСџР‹вЂє 3X-UI", "priority": "high"},
    {"owner": "hiddify", "repo": "hiddify-next", "name": "СЂСџР‹вЂє Hiddify Next", "priority": "high"},
    {"owner": "hiddify", "repo": "Hiddify-Manager", "name": "СЂСџР‹вЂє Hiddify Manager", "priority": "medium"},

    {"owner": "MatsuriDayo", "repo": "nekoray", "name": "СЂСџС’В± Nekoray", "priority": "high"},
    {"owner": "2dust", "repo": "v2rayN", "name": "СЂСџвЂ™В» V2RayN", "priority": "high"},
    {"owner": "2dust", "repo": "v2rayNG", "name": "СЂСџвЂњВ± V2RayNG", "priority": "high"},
    {"owner": "metacubex", "repo": "ClashMeta", "name": "РІС™вЂќРїС‘РЏ Clash Meta", "priority": "medium"},
    {"owner": "metacubex", "repo": "mihomo", "name": "РІС™вЂќРїС‘РЏ Mihomo", "priority": "medium"},

    {"owner": "AntiZapret", "repo": "antizapret", "name": "СЂСџвЂєРЋ AntiZapret", "priority": "high"},
    {"owner": "AntiZapret", "repo": "antizapret-pac-generator-light", "name": "СЂСџвЂєРЋ AntiZapret PAC", "priority": "medium"},
    {"owner": "zapret-info", "repo": "z-i", "name": "СЂСџвЂњвЂ№ Zapret-Info", "priority": "medium"},
    {"owner": "C24Be", "repo": "AS_REG", "name": "СЂСџвЂњвЂ№ AS Registry RU", "priority": "medium"},

    {"owner": "roskomsvoboda", "repo": "censortracker", "name": "СЂСџвЂњСћ CensorTracker", "priority": "high"},
    {"owner": "roskomsvoboda", "repo": "moscow_covid_queues", "name": "СЂСџвЂњСћ RKS Tools", "priority": "low"},
]

CONFIG_AGGREGATORS = [
    {"owner": "Leon406", "repo": "SubCrawler", "name": "СЂСџвЂњРЋ SubCrawler"},
    {"owner": "peasoft", "repo": "NoMoreWalls", "name": "СЂСџвЂњРЋ NoMoreWalls"},
    {"owner": "barry-far", "repo": "V2ray-Configs", "name": "СЂСџвЂњРЋ V2ray-Configs"},
    {"owner": "mahdibland", "repo": "V2RayAggregator", "name": "СЂСџвЂњРЋ V2RayAggregator"},
    {"owner": "Pawdroid", "repo": "Free-servers", "name": "СЂСџвЂњРЋ Free-servers"},
    {"owner": "aiboboxx", "repo": "v2rayfree", "name": "СЂСџвЂњРЋ V2RayFree"},
]

FRESH_SEARCHES = [
    {"name": "Zapret Tools", "title": "СЂСџвЂє  Zapret Р С‘Р Р…РЎРѓРЎвЂљРЎР‚РЎС“Р СР ВµР Р…РЎвЂљРЎвЂ№", "query": "zapret OR zapret-discord OR zapret-youtube", "priority": 10},
    {"name": "DPI Bypass", "title": "СЂСџвЂє  DPI Bypass", "query": "dpi-bypass OR bypass-dpi OR nodpi", "priority": 10},
    {"name": "RKN Block", "title": "СЂСџвЂРѓ Р  Р С™Р Сњ Р В±Р В»Р С•Р С”Р С‘РЎР‚Р С•Р Р†Р С”Р С‘", "query": "roskomnadzor OR rkn-block OR rkn-bypass", "priority": 10},
    {"name": "TSPU", "title": "СЂСџвЂРѓ Р СћР РЋР СџР Р€", "query": "tspu OR sorm OR russia-censorship", "priority": 9},
    {"name": "AntiZapret", "title": "СЂСџвЂєРЋ AntiZapret", "query": "antizapret OR anti-zapret", "priority": 10},

    {"name": "Russia VPN Tools", "title": "СЂСџвЂќВ§ VPN Р С‘Р Р…РЎРѓРЎвЂљРЎР‚РЎС“Р СР ВµР Р…РЎвЂљРЎвЂ№ Р Т‘Р В»РЎРЏ Р  Р В¤",
     "query": "vpn russia bypass OR vpn russia censorship OR russia vpn tool", "priority": 8},
    {"name": "RU VPN Configs", "title": "СЂСџвЂќВ§ Р С™Р С•Р Р…РЎвЂћР С‘Р С–Р С‘ VPN Р Т‘Р В»РЎРЏ Р  Р В¤",
     "query": "russia vless OR russia reality OR russia hysteria", "priority": 9},

    {"name": "VLESS Reality", "title": "СЂСџвЂќВ§ VLESS Reality", "query": "vless-reality OR reality-config", "priority": 8},
    {"name": "Hysteria2", "title": "СЂСџС™Р‚ Hysteria 2", "query": "hysteria2 OR hysteria-2", "priority": 8},
    {"name": "XRay Config", "title": "РІС™РЋ XRay Р С”Р С•Р Р…РЎвЂћР С‘Р С–Р С‘", "query": "xray-config OR xray-russia", "priority": 7},
    {"name": "Amnezia", "title": "СЂСџвЂєРЋ Amnezia", "query": "amnezia-vpn OR amneziawg", "priority": 9},
    {"name": "Marzban", "title": "СЂСџР‹вЂє Marzban", "query": "marzban-panel OR marzban-node", "priority": 8},
    {"name": "Geosite RU", "title": "СЂСџвЂ”С” Geosite Russia", "query": "geosite-russia OR geoip-russia", "priority": 7},
    {"name": "Domain List RU", "title": "СЂСџвЂњвЂ№ Р РЋР С—Р С‘РЎРѓР С”Р С‘ Р Т‘Р С•Р СР ВµР Р…Р С•Р Р†", "query": "russia-domains OR ru-blocked-domains", "priority": 7},
    {"name": "Proxy Configs", "title": "СЂСџвЂњРЋ Р СџРЎР‚Р С•Р С”РЎРѓР С‘ Р С”Р С•Р Р…РЎвЂћР С‘Р С–Р С‘", "query": "proxy-config-russia OR free-proxy-russia", "priority": 6},
    {"name": "Sing-Box RU", "title": "СЂСџвЂњВ¦ Sing-Box", "query": "sing-box-russia OR singbox-config", "priority": 7},
    {"name": "Clash Rules", "title": "РІС™вЂќРїС‘РЏ Clash Р С—РЎР‚Р В°Р Р†Р С‘Р В»Р В°", "query": "clash-rules-russia OR clash-meta-russia", "priority": 6},
    {"name": "Shadowsocks", "title": "СЂСџвЂќС’ Shadowsocks", "query": "shadowsocks-russia OR ss-config", "priority": 6},
    {"name": "WireGuard RU", "title": "СЂСџвЂќвЂ™ WireGuard", "query": "wireguard-russia OR wg-config-russia", "priority": 6},
    {"name": "Outline", "title": "СЂСџвЂњРЋ Outline", "query": "outline-russia OR outline-config", "priority": 6},
    {"name": "Censorship", "title": "СЂСџРЉС’ Р С’Р Р…РЎвЂљР С‘РЎвЂ Р ВµР Р…Р В·РЎС“РЎР‚Р В°", "query": "anti-censorship russia OR internet-freedom russia", "priority": 7},

    {"name": "Reality Extra", "title": "СЂСџвЂќВ§ Reality Р Т‘Р С•Р С—. Р В·Р В°Р С—РЎР‚Р С•РЎРѓРЎвЂ№",
     "query": "reality vless OR xray reality OR sing-box reality", "priority": 7},
    {"name": "Hysteria2 Extra", "title": "СЂСџС™Р‚ Hysteria2 Р Т‘Р С•Р С—. Р В·Р В°Р С—РЎР‚Р С•РЎРѓРЎвЂ№",
     "query": "hysteria2 reality OR hysteria2 config", "priority": 7},
    {"name": "Subconverter", "title": "СЂСџвЂќВ§ Subconverter/Subscriptions",
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
# Р вЂ™Р РЋР СџР С›Р СљР С›Р вЂњР С’Р СћР вЂўР вЂєР В¬Р СњР В«Р вЂў Р В¤Р Р€Р СњР С™Р В¦Р ВР В
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
        logger.error(f"РІСњРЉ Missing environment variables: {', '.join(missing)}")
        return False
    if CONFIG_CHANNEL_ID:
        logger.info(f"РІСљвЂ¦ Second channel enabled: {CONFIG_CHANNEL_ID}")
    else:
        logger.info("РІвЂћв„–РїС‘РЏ Second channel not set (CONFIG_CHANNEL_ID) РІР‚вЂњ config URLs will go only to main channel")
    logger.info("РІСљвЂ¦ All environment variables validated")
    return True

def check_rate_limit():
    try:
        resp = requests.get("https://api.github.com/rate_limit", headers=API_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            remaining = data['rate']['remaining']
            limit = data['rate']['limit']
            logger.info(f"СЂСџвЂњР‰ GitHub API: {remaining}/{limit} calls remaining")
            if remaining < MIN_API_CALLS_REMAINING:
                logger.warning(f"РІС™ РїС‘РЏ API limit low ({remaining} left)")
                if remaining < 10:
                    return False
            return True
    except Exception as e:
        logger.warning(f"РІС™ РїС‘РЏ Could not check rate limit: {e}")
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
        return "СЂСџвЂќТђ Р СћР С•Р В»РЎРЉР С”Р С• РЎвЂЎРЎвЂљР С•"
    elif hours < 6:
        return f"СЂСџвЂќТђ {int(hours)}РЎвЂЎ Р Р…Р В°Р В·Р В°Р Т‘"
    elif hours < 24:
        return "СЂСџвЂќТђ Р РЋР ВµР С–Р С•Р Т‘Р Р…РЎРЏ"
    elif hours < 48:
        return "РІСљвЂ¦ Р вЂ™РЎвЂЎР ВµРЎР‚Р В°"
    elif hours < 72:
        return "СЂСџвЂњвЂ¦ 2 Р Т‘Р Р…РЎРЏ Р Р…Р В°Р В·Р В°Р Т‘"
    else:
        return f"СЂСџвЂњвЂ¦ {int(hours/24)}Р Т‘ Р Р…Р В°Р В·Р В°Р Т‘"

def is_fresh(date_string, max_days=MAX_AGE_DAYS):
    return get_age_hours(date_string) <= (max_days * 24)

def safe_desc(desc, max_len=120):
    if desc is None:
        return ""
    desc = str(desc).strip()
    desc = re.sub(r'[СЂСџвЂќТђРІС™РЋРїС‘РЏРІСљРЃСЂСџР‹вЂ°]{3,}', '', desc)
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
        logger.debug(f"   РІСњРЉ Filtered by category: {name}")
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
            logger.debug(f"   РІСњРЉ 'russia' without VPN context: {name}")
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
        logger.debug(f"   РІСњРЉ Blacklisted: {name}")
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

async def fetch_repo_text_async(owner, repo, file_path=None):
    """Р вЂўРЎРѓР В»Р С‘ file_path Р В·Р В°Р Т‘Р В°Р Р…, РЎРѓР С”Р В°РЎвЂЎР С‘Р Р†Р В°Р ВµРЎвЂљ Р С”Р С•Р Р…Р С”РЎР‚Р ВµРЎвЂљР Р…РЎвЂ№Р в„– РЎвЂћР В°Р в„–Р В»; Р С‘Р Р…Р В°РЎвЂЎР Вµ Р С—РЎвЂ№РЎвЂљР В°Р ВµРЎвЂљРЎРѓРЎРЏ РЎРѓР С”Р В°РЎвЂЎР В°РЎвЂљРЎРЉ README."""
    try:
        async with aiohttp.ClientSession(headers=API_HEADERS) as session:
            if file_path:
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{file_path}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        return await resp.text()
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/{file_path}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        return await resp.text()
                return ""
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
                            logger.debug(f"   РІСљвЂ¦ README loaded from {url}")
                            return text
                except asyncio.TimeoutError:
                    logger.debug(f"   РІРЏВ± Timeout loading {url}")
                    continue
                except Exception as e:
                    logger.debug(f"   РІС™ РїС‘РЏ Error loading {url}: {e}")
                    continue
    except Exception as e:
        logger.debug(f"Error fetching file for {owner}/{repo}: {e}")
    return ""

async def get_repo_files(owner, repo):
    """Р вЂ™Р С•Р В·Р Р†РЎР‚Р В°РЎвЂ°Р В°Р ВµРЎвЂљ РЎРѓР С—Р С‘РЎРѓР С•Р С” Р С‘Р СРЎвЂР Р… РЎвЂћР В°Р в„–Р В»Р С•Р Р† Р Р† Р С”Р С•РЎР‚Р Р…Р Вµ РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘РЎРЏ."""
    files = []
    try:
        async with aiohttp.ClientSession(headers=API_HEADERS) as session:
            branch = await get_default_branch(session, owner, repo)
            url = f"https://api.github.com/repos/{owner}/{repo}/contents?ref={branch}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data:
                        if item['type'] == 'file':
                            files.append(item['name'])
                else:
                    logger.debug(f"   Could not get file list for {owner}/{repo}: status {resp.status}")
    except Exception as e:
        logger.debug(f"Error getting file list: {e}")
    return files

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

# ============================================================
# Р ВР РЋР СџР  Р С’Р вЂ™Р вЂєР вЂўР СњР СњР С’Р Р‡ Р В¤Р Р€Р СњР С™Р В¦Р ВР Р‡ Р СџР С›Р ВР РЋР С™Р С’ (Р С•Р Т‘Р Р…Р В° РЎРѓРЎвЂљРЎР‚Р В°РЎвЂљР ВµР С–Р С‘РЎРЏ + Р С•Р В±РЎР‚Р В°Р В±Р С•РЎвЂљР С”Р В° 403)
# ============================================================
def search_fresh_repos(query, per_page=40, max_age_days=MAX_AGE_DAYS):
    date_filter = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime('%Y-%m-%d')
    results = []
    seen_ids = set()
    # Р ВРЎРѓР С—Р С•Р В»РЎРЉР В·РЎС“Р ВµР С РЎвЂљР С•Р В»РЎРЉР С”Р С• Р С•Р Т‘Р Р…РЎС“ РЎРѓРЎвЂљРЎР‚Р В°РЎвЂљР ВµР С–Р С‘РЎР‹ (pushed) РІР‚вЂњ РЎРЊРЎвЂљР С• Р Р†Р Т‘Р Р†Р С•Р Вµ РЎРѓР С•Р С”РЎР‚Р В°РЎвЂ°Р В°Р ВµРЎвЂљ РЎвЂЎР С‘РЎРѓР В»Р С• Р В·Р В°Р С—РЎР‚Р С•РЎРѓР С•Р Р†
    strategy = f"{query}+pushed:>{date_filter}+language:python+NOT+fork:true"
    url = f"https://api.github.com/search/repositories?q={strategy}&sort=updated&order=desc&per_page={per_page}"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            for item in resp.json().get('items', []):
                if item['id'] not in seen_ids:
                    seen_ids.add(item['id'])
                    if is_fresh(item.get('pushed_at'), max_age_days):
                        results.append(item)
        elif resp.status_code == 403:
            logger.warning("РІС™ РїС‘РЏ GitHub Search rate limit! Waiting 60s...")
            time.sleep(60)
            # Р СџР С•Р Р†РЎвЂљР С•РЎР‚РЎРЏР ВµР С Р В·Р В°Р С—РЎР‚Р С•РЎРѓ Р С•Р Т‘Р С‘Р Р… РЎР‚Р В°Р В·
            resp = requests.get(url, headers=API_HEADERS, timeout=15)
            if resp.status_code == 200:
                for item in resp.json().get('items', []):
                    if item['id'] not in seen_ids:
                        seen_ids.add(item['id'])
                        if is_fresh(item.get('pushed_at'), max_age_days):
                            results.append(item)
    except Exception as e:
        logger.warning(f"РІС™ РїС‘РЏ Search error: {e}")
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
                    f"СЂСџвЂњвЂљ Loaded: {len(data.get('posted', []))} posted, "
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
            f"СЂСџвЂ™С• State saved "
            f"(posted={len(state.get('posted', []))}, "
            f"commits={len(state.get('commits', {}))}, "
            f"releases={len(state.get('releases', {}))}, "
            f"dynamic_tracked={len(state.get('dynamic_tracked', {}))})"
        )
    except Exception as e:
        logger.error(f"РІСњРЉ Could not save state: {e}")

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
        logger.info(f"СЂСџвЂ™С• Config sources saved: {len(sources)} urls")
    except Exception as e:
        logger.error(f"РІСњРЉ Could not save config_sources: {e}")

# ------------------------------------------------------------
# AI-Р В°Р Р…Р В°Р В»Р С‘Р В· Р С‘ Р С–Р ВµР Р…Р ВµРЎР‚Р В°РЎвЂ Р С‘РЎРЏ
# ------------------------------------------------------------
async def analyze_relevance(repos):
    if not repos:
        return {}
    text = "\n".join([
        f"{i+1}. {r['full_name']} | РІВ­С’{r['stargazers_count']} | {safe_desc(r['description'], 80)}"
        for i, r in enumerate(repos)
    ])
    prompt = f"""Р С›РЎвЂ Р ВµР Р…Р С‘ РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р С‘ Р Т‘Р В»РЎРЏ Р С”Р В°Р Р…Р В°Р В»Р В° Р С—РЎР‚Р С• Р С•Р В±РЎвЂ¦Р С•Р Т‘ Р В±Р В»Р С•Р С”Р С‘РЎР‚Р С•Р Р†Р С•Р С” Р Р† Р  Р В¤.

Р С™Р В°РЎвЂљР ВµР С–Р С•РЎР‚Р С‘Р С‘ Р Р†Р В°Р В¶Р Р…Р С•РЎРѓРЎвЂљР С‘:
- HIGH: Р Р…Р С•Р Р†РЎвЂ№Р в„– Р С‘Р Р…РЎРѓРЎвЂљРЎР‚РЎС“Р СР ВµР Р…РЎвЂљ/Р С—РЎР‚Р С•РЎвЂљР С•Р С”Р С•Р В»/Р СР ВµРЎвЂљР С•Р Т‘ Р С•Р В±РЎвЂ¦Р С•Р Т‘Р В° (Zapret2, Hysteria2, Reality, AmneziaWG)
- MEDIUM: Р С•Р В±Р Р…Р С•Р Р†Р В»РЎвЂР Р…Р Р…РЎвЂ№Р Вµ РЎРѓР С—Р С‘РЎРѓР С”Р С‘ (whitelist, geoip, Р Т‘Р С•Р СР ВµР Р…РЎвЂ№), Р С–Р ВµР Р…Р ВµРЎР‚Р В°РЎвЂљР С•РЎР‚РЎвЂ№ Р С”Р С•Р Р…РЎвЂћР С‘Р С–Р С•Р Р†, Р С—Р В°Р Р…Р ВµР В»Р С‘ РЎС“Р С—РЎР‚Р В°Р Р†Р В»Р ВµР Р…Р С‘РЎРЏ
- LOW: РЎС“РЎвЂЎР ВµР В±Р Р…РЎвЂ№Р Вµ Р С—РЎР‚Р С•Р ВµР С”РЎвЂљРЎвЂ№, РЎвЂћР С•РЎР‚Р С”Р С‘ Р В±Р ВµР В· Р С‘Р В·Р СР ВµР Р…Р ВµР Р…Р С‘Р в„–, Р Р…Р Вµ РЎРѓР Р†РЎРЏР В·Р В°Р Р…Р Р…РЎвЂ№Р Вµ РЎРѓ VPN/РЎвЂ Р ВµР Р…Р В·РЎС“РЎР‚Р С•Р в„–

РІСњРЉ Р СњР ВµРЎР‚Р ВµР В»Р ВµР Р†Р В°Р Р…РЎвЂљР Р…РЎвЂ№Р Вµ РЎвЂљР ВµР СРЎвЂ№ (РЎРѓРЎР‚Р В°Р В·РЎС“ LOW Р С‘Р В»Р С‘ SKIP):
- Р С›Р В±РЎС“РЎвЂЎР ВµР Р…Р С‘Р Вµ РЎРЏР В·РЎвЂ№Р С”РЎС“, Р В±Р С‘Р В·Р Р…Р ВµРЎРѓ/РЎР‚РЎвЂ№Р Р…Р С•Р С”, Р С‘Р С–РЎР‚РЎвЂ№, РЎС“РЎвЂљР С‘Р В»Р С‘РЎвЂљРЎвЂ№ Р В±Р ВµР В· РЎвЂљР ВµР СР В°РЎвЂљР С‘Р С”Р С‘ Р С•Р В±РЎвЂ¦Р С•Р Т‘Р В° Р В±Р В»Р С•Р С”Р С‘РЎР‚Р С•Р Р†Р С•Р С”
- Р вЂєРЎР‹Р В±РЎвЂ№Р Вµ Р С—РЎР‚Р С•Р ВµР С”РЎвЂљРЎвЂ№ РЎРѓ "russia" Р вЂР вЂўР вЂ” VPN/DPI/РЎвЂ Р ВµР Р…Р В·РЎС“РЎР‚РЎвЂ№-Р С”Р С•Р Р…РЎвЂљР ВµР С”РЎРѓРЎвЂљР В°

Р  Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р С‘:
{text}

Р С›РЎвЂљР Р†Р ВµРЎвЂљРЎРЉ РЎРѓРЎвЂљРЎР‚Р С•Р С–Р С• Р Р† РЎвЂћР С•РЎР‚Р СР В°РЎвЂљР Вµ:
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
        logger.debug(f"СЂСџВ¤вЂ“ AI raw response: {content}")
        for line in content.split('\n'):
            if ':' in line:
                try:
                    idx, verdict = line.split(':', 1)
                    idx = int(idx.strip().replace('.', ''))
                    verdict = verdict.strip().upper()
                    if verdict in ('GOOD', '1', 'HIGH', 'MEDIUM'):
                        category = 'HIGH' if verdict in ('HIGH', 'GOOD', '1') else 'MEDIUM'
                        res[idx] = {'publish': True, 'category': category}
                    elif verdict in ('SKIP', '2', 'LOW'):
                        res[idx] = {'publish': False, 'category': 'LOW'}
                    else:
                        res[idx] = {'publish': False, 'category': 'LOW'}
                except:
                    pass
        if not res:
            logger.warning("РІС™ РїС‘РЏ AI response parsing failed, fallback to publish all as MEDIUM")
            return {i: {'publish': True, 'category': 'MEDIUM'} for i in range(1, len(repos) + 1)}
        return res
    except Exception as e:
        logger.warning(f"РІС™ РїС‘РЏ AI error: {e}, fallback to publish all as MEDIUM")
        return {i: {'publish': True, 'category': 'MEDIUM'} for i in range(1, len(repos) + 1)}

async def generate_desc(name, desc):
    if desc and len(desc) > 25 and not has_non_latin(desc):
        return desc
    prompt = f"""Р  Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р в„–: {name}
Р С›Р С—Р С‘РЎРѓР В°Р Р…Р С‘Р Вµ: {desc or 'Р Р…Р ВµРЎвЂљ'}

Р СњР В°Р С—Р С‘РЎв‚¬Р С‘ Р С”РЎР‚Р В°РЎвЂљР С”Р С•Р Вµ Р С•Р С—Р С‘РЎРѓР В°Р Р…Р С‘Р Вµ (1 Р С—РЎР‚Р ВµР Т‘Р В»Р С•Р В¶Р ВµР Р…Р С‘Р Вµ, Р Т‘Р С• 80 РЎРѓР С‘Р СР Р†Р С•Р В»Р С•Р Р†) Р Р…Р В° РЎР‚РЎС“РЎРѓРЎРѓР С”Р С•Р С.
Р С™Р С•Р Р…РЎвЂљР ВµР С”РЎРѓРЎвЂљ: VPN, Р С•Р В±РЎвЂ¦Р С•Р Т‘ Р В±Р В»Р С•Р С”Р С‘РЎР‚Р С•Р Р†Р С•Р С”.

Р С›Р С—Р С‘РЎРѓР В°Р Р…Р С‘Р Вµ:"""
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
    return "Р ВР Р…РЎРѓРЎвЂљРЎР‚РЎС“Р СР ВµР Р…РЎвЂљ Р Т‘Р В»РЎРЏ Р С•Р В±РЎвЂ¦Р С•Р Т‘Р В° Р В±Р В»Р С•Р С”Р С‘РЎР‚Р С•Р Р†Р С•Р С”"

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
        logger.debug(f"   РІСњРЉ No VPN/DPI terms in README: {owner}/{repo}")
        repo_cache[cache_key] = False
        return False
    bad_signs = [
        'vocabulary trainer', 'language learning', 'flashcard',
        'steel market', 'commodity market', 'stock market',
        'cooking recipe', 'restaurant', 'shopping cart', 'ecommerce',
    ]
    if any(sign in low for sign in bad_signs):
        logger.debug(f"   РІСњРЉ Irrelevant content in README: {owner}/{repo}")
        repo_cache[cache_key] = False
        return False
    repo_cache[cache_key] = True
    return True

async def send_message_safe(chat_id, text):
    if has_non_latin(text):
        logger.warning("РІС™ РїС‘РЏ Blocked message with hieroglyphs!")
        return False
    for attempt in range(3):
        try:
            await bot.send_message(chat_id, text, disable_web_page_preview=True)
            return True
        except TelegramRetryAfter as e:
            logger.warning(f"РІС™ РїС‘РЏ Flood control: waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            logger.error("РІСњРЉ Bot blocked by user/chat")
            return False
        except Exception as e:
            logger.warning(f"РІС™ РїС‘РЏ Send attempt {attempt+1} failed: {e}")
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
        f"СЂСџС™Р‚ <b>Р СњР С•Р Р†РЎвЂ№Р в„– РЎР‚Р ВµР В»Р С‘Р В·: {html.escape(project_name)}</b>\n\n"
        f"СЂСџвЂњВ¦ <code>{owner}/{repo}</code>\n"
        f"СЂСџРЏВ· Р вЂ™Р ВµРЎР‚РЎРѓР С‘РЎРЏ: <b>{html.escape(tag)}</b>\n"
        f"РІРЏВ° {get_freshness(release['date'])}\n"
    )
    if body:
        text += f"\nСЂСџвЂњСњ {html.escape(body)}\n"
    text += f"\nСЂСџвЂќвЂ” <a href='{release['url']}'>Р РЋР С”Р В°РЎвЂЎР В°РЎвЂљРЎРЉ РЎР‚Р ВµР В»Р С‘Р В·</a>"
    return text

def build_commit_post(project_name, commit, owner, repo):
    return (
        f"СЂСџвЂќвЂћ <b>{html.escape(project_name)}</b>\n\n"
        f"СЂСџвЂњВ¦ <code>{owner}/{repo}</code>\n"
        f"РІРЏВ° {get_freshness(commit['date'])}\n"
        f"СЂСџвЂњСњ <code>{html.escape(commit['msg'])}</code>\n\n"
        f"СЂСџвЂќвЂ” <a href='{commit['url']}'>Р СџР С•РЎРѓР СР С•РЎвЂљРЎР‚Р ВµРЎвЂљРЎРЉ Р С”Р С•Р СР СР С‘РЎвЂљ</a>"
    )

def build_repo_post(title, repo_full_name, stars, freshness, description, url):
    return (
        f"<b>{title}</b>\n\n"
        f"СЂСџвЂњВ¦ <code>{html.escape(repo_full_name)}</code>\n"
        f"РІВ­С’РїС‘РЏ {stars} | РІРЏВ° {freshness}\n"
        f"СЂСџвЂ™РЋ {html.escape(description)}\n\n"
        f"СЂСџвЂќвЂ” <a href='{url}'>Р С›РЎвЂљР С”РЎР‚РЎвЂ№РЎвЂљРЎРЉ Р Р…Р В° GitHub</a>"
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
    return True

# ------------------------------------------------------------
# Р СњР С›Р вЂ™Р С’Р Р‡ Р В¤Р Р€Р СњР С™Р В¦Р ВР Р‡: Р С•РЎвЂљРЎРѓР В»Р ВµР В¶Р С‘Р Р†Р В°Р Р…Р С‘Р Вµ Р Р…Р С•Р Р†РЎвЂ№РЎвЂ¦ Р С”Р С•Р Р…РЎвЂћР С‘Р С–Р С•Р Р† Р Р† Р В°Р С–РЎР‚Р ВµР С–Р В°РЎвЂљР С•РЎР‚Р В°РЎвЂ¦ (РЎРѓ Р С—РЎР‚Р С•Р Р†Р ВµРЎР‚Р С”Р С•Р в„– Р Р†Р С•Р В·РЎР‚Р В°РЎРѓРЎвЂљР В°)
# ------------------------------------------------------------
async def discover_new_config_urls(state):
    new_global = []
    config_urls_state = state.get('config_urls', {})
    config_extensions = ('.txt', '.json', '.yaml', '.yml', '.conf', '.config', '.sub', '.list')

    for agg in CONFIG_AGGREGATORS:
        # Р СџРЎР‚Р С•Р Р†Р ВµРЎР‚РЎРЏР ВµР С, Р С•Р В±Р Р…Р С•Р Р†Р В»РЎРЏР В»РЎРѓРЎРЏ Р В»Р С‘ РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р в„– Р В·Р В° Р С—Р С•РЎРѓР В»Р ВµР Т‘Р Р…Р С‘Р Вµ 2 Р СР ВµРЎРѓРЎРЏРЎвЂ Р В°
        if not await is_repo_recently_updated(agg['owner'], agg['repo'], MAX_CONFIG_AGE_DAYS):
            logger.info(f"РІРЏВ­ Skipping old aggregator: {agg['name']} (not updated in {MAX_CONFIG_AGE_DAYS} days)")
            continue

        key = f"{agg['owner']}/{agg['repo']}"
        old_urls = set(config_urls_state.get(key, []))
        files = await get_repo_files(agg['owner'], agg['repo'])
        all_text = ""
        readme = await fetch_repo_text_async(agg['owner'], agg['repo'])
        if readme:
            all_text += "\n" + readme
        for fname in files:
            if fname.lower().endswith(config_extensions):
                content = await fetch_repo_text_async(agg['owner'], agg['repo'], file_path=fname)
                if content:
                    all_text += "\n" + content
                    logger.debug(f"   СЂСџвЂњвЂћ Read {fname} from {agg['name']}")
        new_urls = set(extract_config_urls(all_text))
        added = new_urls - old_urls
        if added:
            logger.info(f"СЂСџвЂ вЂў Р СњР С•Р Р†РЎвЂ№Р Вµ Р С”Р С•Р Р…РЎвЂћР С‘Р С–Р С‘ Р Р† {agg['name']}: {added}")
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
# Р ВР РЋР СџР  Р С’Р вЂ™Р вЂєР вЂўР СњР СњР С’Р Р‡ Р В¤Р Р€Р СњР С™Р В¦Р ВР Р‡: Р С—Р С•Р С‘РЎРѓР С” Р С”Р С•Р Р…РЎвЂћР С‘Р С–Р С•Р Р† РЎРѓ Р В·Р В°Р Т‘Р ВµРЎР‚Р В¶Р С”Р С•Р в„–
# ------------------------------------------------------------
async def search_configs_github(state):
    """Р ВРЎвЂ°Р ВµРЎвЂљ Р Р…Р С•Р Р†РЎвЂ№Р Вµ РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р С‘ Р С—Р С• Р В·Р В°Р С—РЎР‚Р С•РЎРѓР В°Р С Р С‘Р В· CONFIG_SEARCH_QUERIES Р С‘ Р С‘Р В·Р Р†Р В»Р ВµР С”Р В°Р ВµРЎвЂљ РЎРѓРЎРѓРЎвЂ№Р В»Р С”Р С‘.
       Р Р€РЎвЂЎР С‘РЎвЂљРЎвЂ№Р Р†Р В°РЎР‹РЎвЂљРЎРѓРЎРЏ РЎвЂљР С•Р В»РЎРЉР С”Р С• РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р С‘, Р С•Р В±Р Р…Р С•Р Р†Р В»РЎвЂР Р…Р Р…РЎвЂ№Р Вµ Р В·Р В° Р С—Р С•РЎРѓР В»Р ВµР Т‘Р Р…Р С‘Р Вµ MAX_CONFIG_AGE_DAYS Р Т‘Р Р…Р ВµР в„–.
    """
    new_urls = []
    config_urls_state = state.get('config_urls', {})
    for query in CONFIG_SEARCH_QUERIES:
        logger.info(f"СЂСџвЂќРЊ GitHub search for configs: {query}")
        repos = search_fresh_repos(query, per_page=30, max_age_days=MAX_CONFIG_AGE_DAYS)
        await asyncio.sleep(3)   # <-- Р вЂ”Р С’Р вЂќР вЂўР  Р вЂ“Р С™Р С’ Р вЂќР вЂєР Р‡ Р вЂ”Р С’Р В©Р ВР СћР В« Р С›Р Сћ Р вЂєР ВР СљР ВР СћР С’
        if not repos:
            continue
        for repo in repos:
            owner = repo['owner']['login']
            repo_name = repo['name']
            key = f"{owner}/{repo_name}"
            old_urls = set(config_urls_state.get(key, []))
            files = await get_repo_files(owner, repo_name)
            all_text = ""
            readme = await fetch_repo_text_async(owner, repo_name)
            if readme:
                all_text += "\n" + readme
            config_extensions = ('.txt', '.json', '.yaml', '.yml', '.conf', '.config', '.sub', '.list')
            for fname in files:
                if fname.lower().endswith(config_extensions):
                    content = await fetch_repo_text_async(owner, repo_name, file_path=fname)
                    if content:
                        all_text += "\n" + content
            urls = set(extract_config_urls(all_text))
            added = urls - old_urls
            if added:
                logger.info(f"СЂСџвЂ вЂў Р СњР С•Р Р†РЎвЂ№Р Вµ Р С”Р С•Р Р…РЎвЂћР С‘Р С–Р С‘ Р С‘Р В· {key}: {added}")
                for url in added:
                    if filter_url_for_russia_and_vless(url):
                        new_urls.append(url)
                config_urls_state[key] = list(urls)
    if new_urls:
        existing = set(load_config_sources())
        save_config_sources(list(existing | set(new_urls)))
    state['config_urls'] = config_urls_state
    return new_urls

# ------------------------------------------------------------
# Р вЂќР С›Р СџР С›Р вЂєР СњР ВР СћР вЂўР вЂєР В¬Р СњР С’Р Р‡ Р В¤Р Р€Р СњР С™Р В¦Р ВР Р‡: Р С—РЎР‚Р С•Р Р†Р ВµРЎР‚Р С”Р В° РЎРѓР Р†Р ВµР В¶Р ВµРЎРѓРЎвЂљР С‘ РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘РЎРЏ
# ------------------------------------------------------------
async def is_repo_recently_updated(owner, repo, max_age_days=MAX_CONFIG_AGE_DAYS):
    try:
        async with aiohttp.ClientSession(headers=API_HEADERS) as session:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pushed_at = data.get('pushed_at')
                    if pushed_at:
                        return is_fresh(pushed_at, max_age_days)
                else:
                    logger.debug(f"   Could not get repo info for {owner}/{repo}: status {resp.status}")
    except Exception as e:
        logger.debug(f"Error checking repo freshness: {e}")
    return False

# ------------------------------------------------------------
# Р В¤Р ВР вЂєР В¬Р СћР  Р С’Р В¦Р ВР Р‡ Р С™Р С›Р СљР СљР ВР СћР С›Р вЂ™ Р В Р  Р вЂўР вЂєР ВР вЂ”Р С›Р вЂ™
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
# Р С›Р РЋР СњР С›Р вЂ™Р СњР С’Р Р‡ Р В¤Р Р€Р СњР С™Р В¦Р ВР Р‡
# ------------------------------------------------------------
async def main():
    logger.info("=" * 60)
    logger.info("СЂСџвЂўВµРїС‘РЏ  SCOUT RADAR v9.2 (fixed rate limits)")
    logger.info("=" * 60)

    if not validate_env():
        return
    if not check_rate_limit():
        logger.error("РІСњРЉ Insufficient API calls. Exiting.")
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
            "name": f"СЂСџвЂ вЂў {full_name}",
            "priority": meta.get("priority", "medium"),
        })

    logger.info(f"СЂСџвЂњРЋ Tracked projects: static={len(TRACKED_PROJECTS)}, dynamic={len(dynamic_tracked)}")

    # 1. Р  Р ВµР В»Р С‘Р В·РЎвЂ№
    logger.info("\nСЂСџС™Р‚ Checking releases...")
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
                logger.info(f"   СЂСџвЂ вЂў Release: {name} {rel['tag']}")
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
                logger.debug(f"   РІРЏВ­ Skipped trivial release: {rel['tag']}")

    # 2. Р С™Р С•Р СР СР С‘РЎвЂљРЎвЂ№
    logger.info("\nСЂСџвЂќвЂћ Checking commits...")
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
            logger.debug(f"   РІРЏВ­ Trivial commit: {commit['msg']}")
            commits[key] = commit['sha']
            continue
        logger.info(f"   СЂСџвЂ вЂў Commit: {name}")
        success = await send_message_safe(
            TARGET_CHANNEL_ID,
            build_commit_post(name, commit, owner, repo)
        )
        if success:
            commits[key] = commit['sha']
            count += 1
            await asyncio.sleep(MESSAGE_DELAY)

    # 3. Р СњР С•Р Р†РЎвЂ№Р Вµ Р С”Р С•Р Р…РЎвЂћР С‘Р С–Р С‘ Р Р† Р В°Р С–РЎР‚Р ВµР С–Р В°РЎвЂљР С•РЎР‚Р В°РЎвЂ¦ (РЎРѓ Р С—РЎР‚Р С•Р Р†Р ВµРЎР‚Р С”Р С•Р в„– Р Р†Р С•Р В·РЎР‚Р В°РЎРѓРЎвЂљР В°)
    logger.info("\nСЂСџвЂњРЋ Checking config aggregators for new URLs (age РІвЂ°В¤ 60 days)...")
    new_urls_agg = await discover_new_config_urls(state)
    if new_urls_agg:
        message_template = "СЂСџвЂњРЋ <b>Р СњР С•Р Р†РЎвЂ№Р в„– Р С‘РЎРѓРЎвЂљР С•РЎвЂЎР Р…Р С‘Р С” Р С—Р С•Р Т‘Р С—Р С‘РЎРѓР С”Р С‘ (Р В°Р С–РЎР‚Р ВµР С–Р В°РЎвЂљР С•РЎР‚)</b>\n\n<code>{}</code>"
        for url in new_urls_agg:
            if count >= MAX_POSTS_PER_RUN:
                break
            text = message_template.format(html.escape(url))
            success_main = await send_message_safe(TARGET_CHANNEL_ID, text)
            if CONFIG_CHANNEL_ID:
                await send_message_safe(CONFIG_CHANNEL_ID, text)
            if success_main:
                count += 1
            await asyncio.sleep(MESSAGE_DELAY)

    # 4. Р СџР С•Р С‘РЎРѓР С” Р С”Р С•Р Р…РЎвЂћР С‘Р С–Р С•Р Р† РЎвЂЎР ВµРЎР‚Р ВµР В· GitHub Search (РЎРѓ Р Р†Р С•Р В·РЎР‚Р В°РЎРѓРЎвЂљР С•Р С 60 Р Т‘Р Р…Р ВµР в„–)
    logger.info("\nСЂСџвЂќРЊ Searching GitHub for config repositories (updated within 60 days)...")
    new_urls_search = await search_configs_github(state)
    if new_urls_search:
        message_template = "СЂСџвЂњРЋ <b>Р СњР С•Р Р†РЎвЂ№Р в„– Р С‘РЎРѓРЎвЂљР С•РЎвЂЎР Р…Р С‘Р С” Р С—Р С•Р Т‘Р С—Р С‘РЎРѓР С”Р С‘ (Р Р…Р В°Р в„–Р Т‘Р ВµР Р… РЎвЂЎР ВµРЎР‚Р ВµР В· Р С—Р С•Р С‘РЎРѓР С”)</b>\n\n<code>{}</code>"
        for url in new_urls_search:
            if count >= MAX_POSTS_PER_RUN:
                break
            text = message_template.format(html.escape(url))
            success_main = await send_message_safe(TARGET_CHANNEL_ID, text)
            if CONFIG_CHANNEL_ID:
                await send_message_safe(CONFIG_CHANNEL_ID, text)
            if success_main:
                count += 1
            await asyncio.sleep(MESSAGE_DELAY)

    # 5. Р СџР С•Р С‘РЎРѓР С” Р Р…Р С•Р Р†РЎвЂ№РЎвЂ¦ РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р ВµР Р† (Р С‘Р Р…РЎРѓРЎвЂљРЎР‚РЎС“Р СР ВµР Р…РЎвЂљРЎвЂ№, РЎвЂљР С•Р В»РЎРЉР С”Р С• РЎРѓР Р†Р ВµР В¶Р С‘Р Вµ 3 Р Т‘Р Р…РЎРЏ) - Р РЋ Р вЂ”Р С’Р вЂќР вЂўР  Р вЂ“Р С™Р С›Р в„ў
    logger.info("\nСЂСџвЂќРЊ Searching for new repositories (latest 3 days)...")
    for s in FRESH_SEARCHES:
        if count >= MAX_POSTS_PER_RUN:
            break
        if not check_rate_limit():
            break
        logger.info(f"\nСЂСџвЂќРЊ {s['name']}...")
        items = search_fresh_repos(s['query'], max_age_days=MAX_AGE_DAYS)
        await asyncio.sleep(3)   # <-- Р вЂ”Р С’Р вЂќР вЂўР  Р вЂ“Р С™Р С’ Р вЂќР вЂєР Р‡ Р вЂ”Р С’Р В©Р ВР СћР В« Р С›Р Сћ Р вЂєР ВР СљР ВР СћР С’
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
            if i.get('stargazers_count', 0) == 0 and not i.get('description'):
                owner, repo = i['full_name'].split('/')
                readme = await fetch_repo_text_async(owner, repo)
                if not readme or len(readme) < 100:
                    logger.debug(f"   РІРЏВ­ Empty/trivial repo: {i['full_name']}")
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
                    logger.debug(f"   РІРЏВ­ AI skipped ({dec['category']}): {item['full_name']}")
                    continue
                owner, repo = item['full_name'].split('/')
                is_relevant = await check_repo_relevance(owner, repo, repo_cache)
                if not is_relevant:
                    logger.info(f"   РІРЏВ­ Skipped (irrelevant README): {item['full_name']}")
                    continue
                final_desc = await generate_desc(item['full_name'], item['description'])
                cat_emoji = "СЂСџвЂќТђ" if dec['category'] == 'HIGH' else "СЂСџвЂњРЉ"
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
                    logger.info(f"   РІСљвЂ¦ {item['full_name']} (category {dec['category']}) added")
                    count += 1
                    await asyncio.sleep(MESSAGE_DELAY)
            await asyncio.sleep(GROQ_DELAY)

    # Р В¤Р С‘Р Р…Р В°Р В»РЎРЉР Р…Р С•Р Вµ РЎРѓР С•РЎвЂ¦РЎР‚Р В°Р Р…Р ВµР Р…Р С‘Р Вµ
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
    logger.info(f"СЂСџРЏРѓ Completed! Published: {count} posts")
    logger.info(f"{'=' * 60}")

    await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nРІРЏС‘ Interrupted by user")
    except Exception as e:
        logger.error(f"РІСњРЉ Fatal error: {e}", exc_info=True)
