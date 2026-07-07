#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import asyncio
import requests
import html
import re
import logging
import time
import urllib.parse
import hashlib
from datetime import datetime, timedelta, timezone
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError
from groq import Groq
import aiohttp

# ===================== НАСТРОЙКИ =====================
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
CONFIG_CHANNEL_ID = os.getenv("CONFIG_CHANNEL_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

STATE_FILE = "scout_history.json"
CONFIG_SOURCES_FILE = "config_sources.json"

MAX_AGE_DAYS = 3
MAX_CONFIG_AGE_DAYS = 60
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

# ===================== БАЗОВЫЕ СПИСКИ =====================
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
    {"name": "AntiZapret", "title": "🛡 AntiZapret", "query": "antizapret OR anti-zapret", "priority": 10},
    {"name": "AmneziaWG", "title": "🛡 AmneziaWG", "query": "amneziawg OR amnezia-vpn", "priority": 10},
    {"name": "Xray Reality", "title": "⚡ Xray Reality", "query": "xray-reality OR vless-reality", "priority": 9},
    {"name": "Sing-Box", "title": "📦 Sing-Box", "query": "sing-box OR singbox", "priority": 9},
    {"name": "Hysteria2", "title": "🚀 Hysteria 2", "query": "hysteria2 OR hysteria-2", "priority": 9},
    {"name": "Marzban Panel", "title": "🎛 Marzban", "query": "marzban-panel OR marzban-node", "priority": 8},
    {"name": "3x-UI Panel", "title": "🎛 3x-UI", "query": "3x-ui OR x-ui", "priority": 8},
    {"name": "Hiddify", "title": "🎛 Hiddify", "query": "hiddify-next OR hiddify-manager", "priority": 8},
    {"name": "Geosite Russia", "title": "🗺 Geosite Russia", "query": "geosite-russia OR geoip-russia", "priority": 7},
    {"name": "Blocked Domains RU", "title": "📋 Списки доменов", "query": "russia-domains OR ru-blocked-domains", "priority": 7},
    {"name": "Clash Meta Russia", "title": "⚔️ Clash Meta", "query": "clash-meta-russia OR mihomo", "priority": 7},
    {"name": "Outline VPN", "title": "📡 Outline", "query": "outline-russia OR outline-config", "priority": 6},
    {"name": "WireGuard RU", "title": "🔒 WireGuard", "query": "wireguard-russia OR wg-config-russia", "priority": 6},
    {"name": "Shadowsocks RU", "title": "🔐 Shadowsocks", "query": "shadowsocks-russia OR ss-config", "priority": 6},
    {"name": "Proxy Configs", "title": "📡 Прокси конфиги", "query": "proxy-config-russia OR free-proxy-russia", "priority": 6},
    {"name": "Subconverter", "title": "🔧 Subconverter", "query": "subconverter OR subscription-converter", "priority": 5},
    {"name": "Censorship Tracker", "title": "📢 CensorTracker", "query": "censortracker OR rkn-block", "priority": 8},
]

FRESH_SEARCHES.sort(key=lambda x: x.get('priority', 5), reverse=True)

CONFIG_SEARCH_QUERIES = [
    "vless reality subscription",
    "vless reality v2ray",
    "hysteria2 reality config",
    "clash reality subscription",
    "xray reality vless config",
    "sing-box reality config",
    "subscription link vless",
    "v2ray subscription free",
    "proxy config russia vless",
    "amneziawg config",
]

CONFIG_URL_PATTERNS = [
    r"https://raw\.githubusercontent\.com[^\s\"']+",
    r"https://github\.com[^\s\"']+/raw[^\s\"']*",
    r"https?://[^\s\"']*(?:sub|subscription|clash\.ya?ml|config|proxy)[^\s\"']*",
    r"https://gist\.githubusercontent\.com[^\s\"']+",
    r"https?://pastebin\.com/[^\s\"']+",
    r"https?://[^\s\"']*(?:vless|vmess|hysteria2|reality)[^\s\"']*",
]

# ===================== НОВЫЕ ФУНКЦИИ ДЛЯ ДЕДУПЛИКАЦИИ =====================

def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = urllib.parse.unquote(parsed.path)
        path = re.sub(r'/+', '/', path)
        if path.endswith('/') and len(path) > 1:
            path = path[:-1]
        if '/raw/main/' in path:
            path = path.replace('/raw/main/', '/raw/master/')
        canonical = urllib.parse.urlunparse((scheme, netloc, path, "", "", ""))
        return canonical
    except Exception:
        return url

def url_signature(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        path = parsed.path.lower()
        segments = [s for s in path.split('/') if s]
        sig_segments = segments[:3] if segments else []
        return f"{netloc}::{'/'.join(sig_segments)}"
    except:
        return url

def extract_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except:
        return ""

def classify_repo_family(repo_name: str, description: str = "") -> str:
    text = f"{repo_name} {description}".lower()
    families = {
        'zapret': ['zapret', 'goodbyedpi', 'byedpi', 'spoofdpi', 'antizapret'],
        'amnezia': ['amnezia', 'amneziawg'],
        'xray': ['xray', 'vless', 'reality', 'xtls'],
        'sing-box': ['sing-box', 'singbox', 'mihomo'],
        'hysteria': ['hysteria', 'hysteria2'],
        'mtproto': ['mtproto', 'telegram proxy'],
        'proxy-collector': ['subcrawler', 'aggregator', 'v2rayfree', 'free-servers'],
        'subscription-aggregator': ['subscription', 'clash subscription', 'subconverter'],
        'panel': ['marzban', '3x-ui', 'hiddify', 'nekoray', 'v2rayn', 'v2rayng'],
        'dpi-bypass': ['dpi-bypass', 'bypass-dpi', 'nodpi'],
        'rkn': ['rkn', 'roskomnadzor', 'sorm', 'tspu'],
    }
    for family, keywords in families.items():
        if any(kw in text for kw in keywords):
            return family
    return 'other'

def compute_content_hash(text: str, max_tokens=20) -> str:
    if not text:
        return hashlib.md5(b'').hexdigest()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    tokens = []
    for line in lines:
        cleaned = re.sub(r'#.*$', '', line)
        cleaned = re.sub(r'https?://\S+', '', cleaned)
        cleaned = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '', cleaned)
        cleaned = cleaned.strip()
        if len(cleaned) > 5:
            tokens.append(cleaned)
        if len(tokens) >= max_tokens:
            break
    content = ' '.join(tokens)
    return hashlib.md5(content.encode('utf-8', errors='ignore')).hexdigest()

def is_family_overheated(family: str, state: dict, window_hours=48, max_hits=3) -> bool:
    if family not in state.get('family_hits', {}):
        return False
    hits = state['family_hits'].get(family, [])
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    recent = [ts for ts in hits if datetime.fromisoformat(ts) > cutoff]
    return len(recent) >= max_hits

def update_family_hits(family: str, state: dict):
    if 'family_hits' not in state:
        state['family_hits'] = {}
    if family not in state['family_hits']:
        state['family_hits'][family] = []
    state['family_hits'][family].append(datetime.now(timezone.utc).isoformat())
    if len(state['family_hits'][family]) > 100:
        state['family_hits'][family] = state['family_hits'][family][-100:]

def score_candidate(candidate: dict, state: dict) -> dict:
    score = 0
    breakdown = {}
    item_type = candidate.get('type', 'repo')
    if item_type == 'repo':
        full_name = candidate.get('full_name', '')
        if '/' not in full_name:
            return {'score': -999, 'breakdown': {'invalid': '-999'}, 'should_publish': False}
        owner, repo = full_name.split('/', 1)
        description = candidate.get('description', '')
        stars = candidate.get('stargazers_count', 0)
        pushed_at = candidate.get('pushed_at', '')
        family = classify_repo_family(repo, description)
        # Плюсы
        if owner and owner not in state.get('seen_repo_owners', {}):
            score += 5
            breakdown['new_owner'] = '+5'
        # Минусы
        if owner in state.get('owner_last_seen', {}):
            last_seen = state['owner_last_seen'][owner]
            hours_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(last_seen)).total_seconds() / 3600
            if hours_ago < 48:
                score -= 3
                breakdown['recent_owner'] = '-3'
        if is_family_overheated(family, state, window_hours=48, max_hits=3):
            score -= 5
            breakdown['overheated_family'] = '-5'
        if stars == 0 and not description:
            score -= 3
            breakdown['empty_repo'] = '-3'
        if candidate.get('fork', False) and candidate.get('forks_count', 0) == 0 and stars == 0:
            score -= 4
            breakdown['dead_fork'] = '-4'
        name_low = repo.lower()
        if any(word in name_low for word in ['wrapper', 'launcher', 'repack', 'clone', 'mirror']):
            score -= 3
            breakdown['wrapper_mirror'] = '-3'
        if 'vpn' in name_low or 'proxy' in name_low:
            if not any(p in description.lower() for p in ['vless', 'reality', 'hysteria', 'xray', 'sing-box']):
                score -= 2
                breakdown['generic_vpn'] = '-2'
        if str(candidate.get('id', '')) in state.get('posted', []):
            score = -100
            breakdown['already_posted'] = '-100'
        if owner in state.get('recent_publication_owners', {}):
            last_pub = state['recent_publication_owners'][owner]
            if (datetime.now(timezone.utc) - datetime.fromisoformat(last_pub)).total_seconds() < 86400:
                score -= 2
                breakdown['owner_published_recently'] = '-2'
        if pushed_at:
            hours = get_age_hours(pushed_at)
            if hours < 6:
                score += 3
                breakdown['very_fresh'] = '+3'
            elif hours < 24:
                score += 1
                breakdown['fresh'] = '+1'
    else:  # config_url
        url = candidate.get('url', '')
        domain = extract_domain(url)
        if domain and domain not in state.get('seen_source_domains', {}):
            score += 5
            breakdown['new_domain'] = '+5'
        if any(p in url.lower() for p in ['vless', 'reality', 'hysteria', 'sing-box']):
            score += 3
            breakdown['specific_protocol'] = '+3'
        if domain in state.get('domain_last_seen', {}):
            last_seen = state['domain_last_seen'][domain]
            hours_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(last_seen)).total_seconds() / 3600
            if hours_ago < 48:
                score -= 3
                breakdown['recent_domain'] = '-3'
        if any(agg in url.lower() for agg in ['subcrawler', 'nomorewalls', 'v2rayaggregator']):
            score -= 2
            breakdown['common_aggregator'] = '-2'
        content_hash = candidate.get('content_hash')
        if content_hash and content_hash in state.get('seen_content_hashes', {}):
            score = -100
            breakdown['duplicate_content'] = '-100'
    return {
        'score': score,
        'breakdown': breakdown,
        'should_publish': score >= 0
    }

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

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
    if CONFIG_CHANNEL_ID:
        logger.info(f"✅ Second channel enabled: {CONFIG_CHANNEL_ID}")
    else:
        logger.info("ℹ️ Second channel not set (CONFIG_CHANNEL_ID)")
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

def is_fresh(date_string, max_days=MAX_AGE_DAYS):
    return get_age_hours(date_string) <= (max_days * 24)

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
        'game', 'minigame', 'weather', 'calculator', 'notebook',
        'crypto', 'nft', 'blockchain', 'defi', 'sms', 'caller',
        'video', 'stream', 'youtube-dl', 'pomodoro', 'meditation',
        'workout', 'fitness', 'mental-health'
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
    wrapper_keywords = ['fork', 'clone', 'mirror', 'wrapper', 'launcher', 'repack']
    if any(kw in text for kw in wrapper_keywords) and stars < 5:
        logger.debug(f"   ⏭ Skipped likely wrapper: {name}")
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

async def fetch_repo_text_async(owner, repo, file_path=None):
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
                            logger.debug(f"   ✅ README loaded from {url}")
                            return text
                except asyncio.TimeoutError:
                    logger.debug(f"   ⏱ Timeout loading {url}")
                    continue
                except Exception as e:
                    logger.debug(f"   ⚠️ Error loading {url}: {e}")
                    continue
    except Exception as e:
        logger.debug(f"Error fetching file for {owner}/{repo}: {e}")
    return ""

async def get_repo_files(owner, repo):
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

def search_fresh_repos(query, per_page=40, max_age_days=MAX_AGE_DAYS, sort_by='updated'):
    date_filter = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime('%Y-%m-%d')
    results = []
    seen_ids = set()
    strategy = f"{query}+pushed:>{date_filter}+NOT+fork:true"
    url = f"https://api.github.com/search/repositories?q={strategy}&sort={sort_by}&order=desc&per_page={per_page}"
    try:
        resp = requests.get(url, headers=API_HEADERS, timeout=15)
        if resp.status_code == 200:
            for item in resp.json().get('items', []):
                if item['id'] not in seen_ids:
                    seen_ids.add(item['id'])
                    if is_fresh(item.get('pushed_at'), max_age_days):
                        results.append(item)
        elif resp.status_code == 403:
            logger.warning("⚠️ GitHub Search rate limit! Waiting 60s...")
            time.sleep(60)
            resp = requests.get(url, headers=API_HEADERS, timeout=15)
            if resp.status_code == 200:
                for item in resp.json().get('items', []):
                    if item['id'] not in seen_ids:
                        seen_ids.add(item['id'])
                        if is_fresh(item.get('pushed_at'), max_age_days):
                            results.append(item)
    except Exception as e:
        logger.warning(f"⚠️ Search error: {e}")
    return results

# ===================== РАБОТА СО STATE =====================

def migrate_state(state: dict) -> dict:
    new_fields = {
        'seen_url_signatures': {},
        'seen_content_hashes': {},
        'seen_repo_families': {},
        'family_hits': {},
        'rejected_urls': [],
        'rejected_repos': [],
        'recent_publication_families': {},
        'owner_last_seen': {},
        'domain_last_seen': {},
        'family_last_seen': {},
        'query_rotation_state': {},
        'recent_publication_owners': {},
        'seen_repo_owners': {},
        'seen_source_domains': {},
    }
    for field, default in new_fields.items():
        if field not in state:
            state[field] = default
    return state

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
                data = migrate_state(data)
                logger.info(
                    f"📂 Loaded: {len(data.get('posted', []))} posted, "
                    f"{len(data.get('releases', {}))} releases, "
                    f"{len(data.get('dynamic_tracked', {}))} dynamic tracked"
                )
                return data
        except Exception as e:
            logger.warning(f"Could not load state: {e}")
    default = {
        "posted": [],
        "commits": {},
        "releases": {},
        "repo_cache": {},
        "last_run": None,
        "dynamic_tracked": {},
        "releases_meta": {},
        "config_urls": {},
    }
    return migrate_state(default)

def save_state(state):
    state['last_run'] = datetime.now(timezone.utc).isoformat()
    state['posted'] = state.get('posted', [])[-3000:]
    for key in ['rejected_urls', 'rejected_repos']:
        if key in state:
            state[key] = state[key][-1000:]
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

# ===================== AI И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

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

# ===================== ПОСТРОЕНИЕ СООБЩЕНИЙ =====================

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

# ===================== КОНФИГИ И ПОДПИСКИ =====================

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

async def fetch_content_from_url(url: str, timeout=10) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception as e:
        logger.debug(f"Could not fetch {url}: {e}")
    return ""

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

async def discover_new_config_urls(state):
    new_global = []
    config_urls_state = state.get('config_urls', {})
    config_extensions = ('.txt', '.json', '.yaml', '.yml', '.conf', '.config', '.sub', '.list')

    for agg in CONFIG_AGGREGATORS:
        if not await is_repo_recently_updated(agg['owner'], agg['repo'], MAX_CONFIG_AGE_DAYS):
            logger.info(f"⏭ Skipping old aggregator: {agg['name']} (not updated in {MAX_CONFIG_AGE_DAYS} days)")
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
                    logger.debug(f"   📄 Read {fname} from {agg['name']}")
        raw_urls = set(extract_config_urls(all_text))
        canonical_to_raw = {}
        for url in raw_urls:
            canon = canonicalize_url(url)
            if canon:
                canonical_to_raw[canon] = url
        added = []
        for canon, raw in canonical_to_raw.items():
            content = await fetch_content_from_url(raw)
            if content:
                h = compute_content_hash(content)
                if h in state.get('seen_content_hashes', {}):
                    logger.debug(f"   ⏭ Duplicate content for {raw}")
                    continue
            sig = url_signature(raw)
            if sig in state.get('seen_url_signatures', {}):
                logger.debug(f"   ⏭ Duplicate URL signature for {raw}")
                continue
            if raw not in old_urls:
                added.append(raw)
                state.setdefault('seen_url_signatures', {})[sig] = True
                if content:
                    state.setdefault('seen_content_hashes', {})[h] = True

        if added:
            logger.info(f"🆕 Новые конфиги в {agg['name']}: {added}")
            for url in added:
                if filter_url_for_russia_and_vless(url):
                    candidate = {'type': 'config_url', 'url': url}
                    score_result = score_candidate(candidate, state)
                    if score_result['should_publish']:
                        new_global.append(url)
                        domain = extract_domain(url)
                        state['domain_last_seen'][domain] = datetime.now(timezone.utc).isoformat()
                        state.setdefault('seen_source_domains', {})[domain] = True
                    else:
                        logger.debug(f"   ⏭ Skipped {url} due to score {score_result['score']}")
            config_urls_state[key] = list(raw_urls)
    if new_global:
        existing = set(load_config_sources())
        save_config_sources(list(existing | set(new_global)))
    state['config_urls'] = config_urls_state
    return new_global

async def search_configs_github(state):
    new_urls = []
    config_urls_state = state.get('config_urls', {})
    for query in CONFIG_SEARCH_QUERIES:
        logger.info(f"🔍 GitHub search for configs: {query}")
        repos = search_fresh_repos(query, per_page=30, max_age_days=MAX_CONFIG_AGE_DAYS, sort_by='updated')
        await asyncio.sleep(3)
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
            raw_urls = set(extract_config_urls(all_text))
            canonical_to_raw = {}
            for url in raw_urls:
                canon = canonicalize_url(url)
                if canon:
                    canonical_to_raw[canon] = url
            added = []
            for canon, raw in canonical_to_raw.items():
                content = await fetch_content_from_url(raw)
                if content:
                    h = compute_content_hash(content)
                    if h in state.get('seen_content_hashes', {}):
                        continue
                sig = url_signature(raw)
                if sig in state.get('seen_url_signatures', {}):
                    continue
                if raw not in old_urls:
                    added.append(raw)
                    state.setdefault('seen_url_signatures', {})[sig] = True
                    if content:
                        state.setdefault('seen_content_hashes', {})[h] = True
            if added:
                logger.info(f"🆕 Новые конфиги из {key}: {added}")
                for url in added:
                    if filter_url_for_russia_and_vless(url):
                        candidate = {'type': 'config_url', 'url': url}
                        score_result = score_candidate(candidate, state)
                        if score_result['should_publish']:
                            new_urls.append(url)
                            domain = extract_domain(url)
                            state['domain_last_seen'][domain] = datetime.now(timezone.utc).isoformat()
                            state.setdefault('seen_source_domains', {})[domain] = True
                config_urls_state[key] = list(raw_urls)
    if new_urls:
        existing = set(load_config_sources())
        save_config_sources(list(existing | set(new_urls)))
    state['config_urls'] = config_urls_state
    return new_urls

# ===================== ФИЛЬТРАЦИЯ КОММИТОВ/РЕЛИЗОВ =====================

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

# ===================== ОСНОВНАЯ ФУНКЦИЯ MAIN =====================

async def main():
    logger.info("=" * 60)
    logger.info("🕵️  SCOUT RADAR v9.2 (fixed rate limits + advanced dedup)")
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

    # ---- РЕЛИЗЫ ----
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

    # ---- КОММИТЫ ----
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

    # ---- КОНФИГИ ИЗ АГРЕГАТОРОВ ----
    logger.info("\n📡 Checking config aggregators for new URLs (age ≤ 60 days)...")
    new_urls_agg = await discover_new_config_urls(state)
    if new_urls_agg:
        message_template = "📡 <b>Новый источник подписки (агрегатор)</b>\n\n<code>{}</code>"
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

    # ---- КОНФИГИ ИЗ ПОИСКА ----
    logger.info("\n🔍 Searching GitHub for config repositories (updated within 60 days)...")
    new_urls_search = await search_configs_github(state)
    if new_urls_search:
        message_template = "📡 <b>Новый источник подписки (найден через поиск)</b>\n\n<code>{}</code>"
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

    # ---- ПОИСК НОВЫХ РЕПОЗИТОРИЕВ ----
    logger.info("\n🔍 Searching for new repositories (latest 3 days)...")
    for s in FRESH_SEARCHES:
        if count >= MAX_POSTS_PER_RUN:
            break
        if not check_rate_limit():
            break
        logger.info(f"\n🔍 {s['name']}...")
        items = search_fresh_repos(s['query'], max_age_days=MAX_AGE_DAYS)
        await asyncio.sleep(3)
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

                # ---- НОВАЯ ЛОГИКА СКОРИНГА И ДЕДУПА ----
                family = classify_repo_family(repo, item.get('description', ''))
                if is_family_overheated(family, state, window_hours=48, max_hits=3):
                    logger.info(f"   ⏭ Skipped due to overheated family {family}: {item['full_name']}")
                    continue
                cand = {
                    'type': 'repo',
                    'full_name': item['full_name'],
                    'description': item.get('description', ''),
                    'stargazers_count': item.get('stargazers_count', 0),
                    'pushed_at': item.get('pushed_at', ''),
                    'id': item['id'],
                    'fork': item.get('fork', False),
                    'forks_count': item.get('forks_count', 0)
                }
                score_result = score_candidate(cand, state)
                if not score_result['should_publish']:
                    logger.info(f"   ⏭ Skipped by scoring ({score_result['score']}): {item['full_name']} - {score_result['breakdown']}")
                    state.setdefault('rejected_repos', []).append(item['full_name'])
                    continue

                # ---- ПУБЛИКАЦИЯ ----
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
                    # обновляем state
                    owner_name = item['full_name'].split('/')[0]
                    state['owner_last_seen'][owner_name] = datetime.now(timezone.utc).isoformat()
                    state['family_last_seen'][family] = datetime.now(timezone.utc).isoformat()
                    update_family_hits(family, state)
                    state.setdefault('seen_repo_families', {})[family] = True
                    state.setdefault('recent_publication_owners', {})[owner_name] = datetime.now(timezone.utc).isoformat()
                    state.setdefault('seen_repo_owners', {})[owner_name] = True
                    logger.info(f"   ✅ {item['full_name']} (category {dec['category']}, score {score_result['score']}) added")
                    count += 1
                    await asyncio.sleep(MESSAGE_DELAY)
            await asyncio.sleep(GROQ_DELAY)

    # ---- СОХРАНЕНИЕ ----
    save_state({
        "posted": list(posted),
        "commits": commits,
        "releases": releases,
        "repo_cache": repo_cache,
        "dynamic_tracked": dynamic_tracked,
        "releases_meta": releases_meta,
        "config_urls": state.get('config_urls', {}),
        "seen_url_signatures": state.get('seen_url_signatures', {}),
        "seen_content_hashes": state.get('seen_content_hashes', {}),
        "seen_repo_families": state.get('seen_repo_families', {}),
        "family_hits": state.get('family_hits', {}),
        "rejected_urls": state.get('rejected_urls', []),
        "rejected_repos": state.get('rejected_repos', []),
        "recent_publication_families": state.get('recent_publication_families', {}),
        "owner_last_seen": state.get('owner_last_seen', {}),
        "domain_last_seen": state.get('domain_last_seen', {}),
        "family_last_seen": state.get('family_last_seen', {}),
        "query_rotation_state": state.get('query_rotation_state', {}),
        "recent_publication_owners": state.get('recent_publication_owners', {}),
        "seen_repo_owners": state.get('seen_repo_owners', {}),
        "seen_source_domains": state.get('seen_source_domains', {}),
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
