#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GITHUB RADAR v11.1 (Fixed Models & No-Fallback JSON)

Secrets:
  CHANNEL_ID
  CONFIG_CHANNEL_ID
  GROQ_API_KEY
  TELEGRAM_BOT_TOKEN
  GITHUB_TOKEN (необязательно)
"""

import asyncio
import hashlib
import html
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

try:
    from groq import Groq
except ImportError:
    Groq = None

# =============================== КОНФИГУРАЦИЯ ===============================

STATE_FILE = os.getenv("STATE_FILE", "radar_state.json")
MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "15"))
MESSAGE_DELAY = float(os.getenv("MESSAGE_DELAY", "2.0"))
GROQ_DELAY = float(os.getenv("GROQ_DELAY", "1.5"))

CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
CONFIG_CHANNEL_ID = os.getenv("CONFIG_CHANNEL_ID", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    API_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

# Надежные production-модели Groq (быстрые, без 400 json_validate_failed)
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

CORE_PROJECTS = [
    {"owner": "bol-van", "repo": "zapret", "name": "Zapret", "icon": "🛡️"},
    {"owner": "bol-van", "repo": "zapret2", "name": "Zapret 2", "icon": "⚡"},
    {"owner": "ValdikSS", "repo": "GoodbyeDPI", "name": "GoodbyeDPI", "icon": "🚪"},
    {"owner": "hufrea", "repo": "byedpi", "name": "ByeDPI", "icon": "🛰️"},
    {"owner": "xvzc", "repo": "SpoofDPI", "name": "SpoofDPI", "icon": "👻"},
    {"owner": "amnezia-vpn", "repo": "amnezia-client", "name": "Amnezia VPN", "icon": "🔒"},
    {"owner": "amnezia-vpn", "repo": "amneziawg-linux-kernel-module", "name": "AmneziaWG Kernel", "icon": "🐧"},
    {"owner": "XTLS", "repo": "Xray-core", "name": "Xray-core", "icon": "💎"},
    {"owner": "SagerNet", "repo": "sing-box", "name": "Sing-Box", "icon": "📦"},
    {"owner": "apernet", "repo": "hysteria", "name": "Hysteria", "icon": "🚀"},
    {"owner": "Gozargah", "repo": "Marzban", "name": "Marzban", "icon": "👑"},
    {"owner": "MHSanaei", "repo": "3x-ui", "name": "3X-UI", "icon": "🎛️"},
    {"owner": "hiddify", "repo": "hiddify-next", "name": "Hiddify Next", "icon": "🌐"},
    {"owner": "MatsuriDayo", "repo": "nekoray", "name": "Nekoray", "icon": "🐱"},
    {"owner": "2dust", "repo": "v2rayN", "name": "V2RayN", "icon": "💻"},
    {"owner": "2dust", "repo": "v2rayNG", "name": "V2RayNG", "icon": "📱"},
    {"owner": "MetaCubeX", "repo": "mihomo", "name": "Mihomo (Clash.Meta)", "icon": "🔮"},
]

SEARCH_QUERIES = [
    "zapret OR goodbyedpi OR byedpi OR spoofdpi",
    "dpi-bypass OR bypass-dpi OR nodpi OR tspu",
    "xray-core OR vless-reality OR reality-vpn",
    "sing-box OR singbox OR hysteria2",
    "amneziawg OR awg-client OR amnezia-vpn",
    "censorship-circumvention OR anti-censorship OR traffic-obfuscation",
    "packet-fragmentation OR tls-fingerprint-bypass OR fake-tls",
]

BLACKLIST_WORDS = {
    "yemen", "iranian-protests", "flashcard", "quiz", "recipe", "shopping",
    "trading", "crypto", "nft", "crawler-bot", "course", "homework", "browser",
    "evidence", "ooni-data", "measurement", "survey",
}

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("radar")


# =============================== УТИЛИТЫ ===============================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def parse_iso(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None

def format_freshness(dt_str: Optional[str]) -> str:
    dt = parse_iso(dt_str)
    if not dt:
        return "недавно"
    hours = max(0.0, (now_utc() - dt).total_seconds() / 3600)
    if hours < 1:
        return "🔥 Только что"
    if hours < 6:
        return f"🔥 {int(hours)}ч назад"
    if hours < 24:
        return "✅ Сегодня"
    if hours < 48:
        return "📅 Вчера"
    days = int(hours // 24)
    return f"📅 {days} дн. назад"

def target_id(val: str) -> Any:
    val = val.strip()
    return int(val) if re.fullmatch(r"-?\d+", val) else val

def is_meaningful_release(tag: str, body: str, last_tag: Optional[str]) -> bool:
    if last_tag and tag == last_tag:
        return False
    body_low = body.lower()
    if any(w in body_low for w in ["breaking change", "feature", "добавлено", "bypass", "fix", "support", "protocol"]):
        return True
    return len(body.strip()) > 30

def clean_markdown_body(body: str, limit: int = 400) -> str:
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    body = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", body)
    body = re.sub(r"https?://\S+", "", body)
    body = re.sub(r"([#*`_~])", "", body)
    lines = [l.strip() for l in body.splitlines() if l.strip() and not l.strip().startswith(("Full Changelog", "Compare"))]
    cleaned = "\n".join(lines[:8])
    if len(cleaned) > limit:
        return cleaned[:limit].rsplit(" ", 1)[0] + "..."
    return cleaned or "Список изменений доступен на странице релиза."


# =============================== СОСТОЯНИЕ ===============================

def load_state() -> Dict[str, Any]:
    default = {
        "posted_releases": {},
        "posted_repos": {},
        "repos_seen": {},
        "last_run": None,
    }
    if not os.path.exists(STATE_FILE):
        return default
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in default.items():
                data.setdefault(k, v)
            return data
    except Exception as e:
        logger.warning(f"Ошибка загрузки {STATE_FILE}: {e}")
        return default

def save_state(state: Dict[str, Any]) -> None:
    state["last_run"] = now_utc().isoformat()
    for k in ["posted_releases", "posted_repos", "repos_seen"]:
        if len(state[k]) > 4000:
            state[k] = dict(list(state[k].items())[-3000:])
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не удалось сохранить состояние: {e}")


# =============================== GITHUB КЛИЕНТ ===============================

class GitHubClient:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=API_HEADERS)
        return self

    async def __aexit__(self, *_):
        if self.session:
            await self.session.close()

    async def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        full_url = url if url.startswith("http") else f"https://api.github.com{url}"
        try:
            async with self.session.get(full_url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.json()
                logger.debug(f"GitHub GET {r.status}: {full_url}")
        except Exception as e:
            logger.debug(f"GitHub request error {full_url}: {e}")
        return None

    async def get_text(self, url: str) -> str:
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status == 200:
                    return await r.text(errors="ignore")
        except Exception:
            pass
        return ""

    async def fetch_latest_release(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        releases = await self.get_json(f"/repos/{owner}/{repo}/releases", {"per_page": 1})
        if releases and isinstance(releases, list):
            return releases[0]
        return None

    async def fetch_readme(self, owner: str, repo: str, default_branch: str = "main") -> str:
        data = await self.get_json(f"/repos/{owner}/{repo}/readme")
        if data and data.get("download_url"):
            return await self.get_text(data["download_url"])
        for b in (default_branch, "main", "master"):
            text = await self.get_text(f"https://raw.githubusercontent.com/{owner}/{repo}/{b}/README.md")
            if text:
                return text
        return ""


# =============================== ИИ КУРАТОР (GROQ) ===============================

class GroqCurator:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY) if Groq and GROQ_API_KEY else None

    async def evaluate_project(self, full_name: str, desc: str, readme: str) -> Optional[str]:
        if not self.client:
            return None  # При отсутствии ИИ ничего сомнительного не пропускаем

        prompt = f"""Ты строгий технический куратор русскоязычного канала о свободе интернета, VPN и обходе блокировок (DPI, ТСПУ, Xray, Sing-Box, Hysteria, Zapret).

Проверь репозиторий:
Имя: {full_name}
Описание: {desc}
README:
{readme[:3500]}

ТРЕБОВАНИЯ:
1. Если это статистика, отчеты об интернет-блокировках в других странах (например Йемен, Иран), общие браузеры, списки серверов/конфигов без софта, не относящиеся к сетевому обходу темы или пустые форки — ОТВЕТЬ ТОЛЬКО СЛОВОМ: SKIP
2. Если это РЕАЛЬНО полезный инструмент, VPN/DPI-клиент, скрипт обхода или интересная утилита:
   Напиши 2-3 коротких предложения на русском языке:
   - Что делает проект
   - Чем полезен для обхода блокировок или настройки сети.

Ответ (SKIP или краткий текст на русском):"""

        for model in GROQ_MODELS:
            try:
                resp = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=250,
                )
                text = resp.choices[0].message.content.strip()
                if not text or text.upper() == "SKIP" or text.startswith("SKIP"):
                    return None
                return text
            except Exception as e:
                logger.warning(f"Groq ({model}) failed: {e}")
            await asyncio.sleep(GROQ_DELAY)
        
        # Если все попытки упали с ошибкой — отклоняем, чтобы не публиковать мусор
        return None


# =============================== ПОСТИНГ ===============================

def post_release(icon: str, name: str, owner_repo: str, tag: str, date_str: str, body: str, url: str) -> str:
    freshness = format_freshness(date_str)
    cleaned_body = clean_markdown_body(body)
    return (
        f"🚀 <b>Новый релиз:</b> {icon} <b>{html.escape(name)}</b>\n"
        f"📦 <code>{html.escape(owner_repo)}</code>\n"
        f"🏷 <b>Версия:</b> <code>{html.escape(tag)}</code>\n"
        f"⏰ {freshness}\n\n"
        f"📝 <b>Изменения:</b>\n"
        f"<blockquote>{html.escape(cleaned_body)}</blockquote>\n\n"
        f"🔗 <a href=\"{html.escape(url)}\">Скачать релиз на GitHub</a>"
    )

def post_new_idea(owner_repo: str, stars: int, forks: int, lang: str, created_at: str, summary: str, url: str, is_breakthrough: bool = False) -> str:
    freshness = format_freshness(created_at)
    badge = "🚀 <b>ПРОРЫВ / ТРЕНД</b>" if is_breakthrough else "💡 <b>НАХОДКА РАДАРА</b>"
    return (
        f"{badge}: <code>{html.escape(owner_repo)}</code>\n"
        f"⭐ {stars}  |  🍴 {forks}  |  💻 {html.escape(lang or 'Code')}\n"
        f"⏰ Создан: {freshness}\n\n"
        f"📝 <b>В чём суть и новизна:</b>\n"
        f"{html.escape(summary)}\n\n"
        f"🔗 <a href=\"{html.escape(url)}\">Открыть репозиторий</a>"
    )

async def send_tg(bot: Bot, target: Any, text: str) -> bool:
    if not target:
        return False
    for attempt in range(3):
        try:
            await bot.send_message(target, text, disable_web_page_preview=True)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            logger.error(f"Бот заблокирован в канале {target}")
            return False
        except Exception as e:
            logger.warning(f"Ошибка отправки TG: {e}")
            await asyncio.sleep(2)
    return False


# =============================== MAIN ===============================

async def main() -> None:
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        raise SystemExit("Ошибка: Задайте TELEGRAM_BOT_TOKEN и CHANNEL_ID в Secrets!")

    state = load_state()
    bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    curator = GroqCurator()
    main_channel = target_id(CHANNEL_ID)

    published = 0

    async with GitHubClient() as gh:
        # 1. ПРОВЕРКА РЕЛИЗОВ ФЛАГМАНОВ
        logger.info("Проверка ключевых проектов на новые релизы...")
        for p in CORE_PROJECTS:
            if published >= MAX_POSTS_PER_RUN:
                break
            owner, repo, name, icon = p["owner"], p["repo"], p["name"], p["icon"]
            key = f"{owner}/{repo}"
            
            rel = await gh.fetch_latest_release(owner, repo)
            if not rel:
                continue
            
            tag = rel.get("tag_name", "")
            published_at = rel.get("published_at") or rel.get("created_at")
            last_tag = state["posted_releases"].get(key)
            
            if last_tag != tag:
                dt = parse_iso(published_at)
                # Публикуем, если релиз вышел в последние 3 дня
                if dt and (now_utc() - dt).total_seconds() < 3 * 86400:
                    body = rel.get("body") or ""
                    if is_meaningful_release(tag, body, last_tag):
                        text = post_release(icon, name, key, tag, published_at, body, rel.get("html_url", ""))
                        if await send_tg(bot, main_channel, text):
                            state["posted_releases"][key] = tag
                            published += 1
                            logger.info(f"Опубликован релиз: {key} {tag}")
                            await asyncio.sleep(MESSAGE_DELAY)
                else:
                    state["posted_releases"][key] = tag

        # 2. ПОИСК НОВЫХ ИДЕЙ И ПРОРЫВОВ
        logger.info("Поиск свежих репозиториев...")
        date_cutoff = (now_utc() - timedelta(days=7)).strftime("%Y-%m-%d")
        found_candidates: Dict[str, Dict[str, Any]] = {}

        for q in SEARCH_QUERIES:
            query = f"{q} pushed:>={date_cutoff} fork:false"
            data = await gh.get_json("/search/repositories", {"q": query, "sort": "stars", "order": "desc", "per_page": 20})
            if data and "items" in data:
                for item in data["items"]:
                    fn = item["full_name"]
                    if fn not in state["posted_repos"]:
                        found_candidates[fn] = item
            await asyncio.sleep(1)

        logger.info(f"Найдено {len(found_candidates)} потенциальных проектов.")

        for fn, item in found_candidates.items():
            if published >= MAX_POSTS_PER_RUN:
                break

            owner = item["owner"]["login"]
            repo_name = item["name"]
            desc = item.get("description") or ""
            stars = item.get("stargazers_count", 0)
            forks = item.get("forks_count", 0)
            created_at = item.get("created_at")
            lang = item.get("language") or ""
            url = item.get("html_url")

            # Фильтр ключевых стоп-слов
            text_for_check = f"{repo_name} {desc}".lower()
            if any(w in text_for_check for w in BLACKLIST_WORDS):
                state["posted_repos"][fn] = "skipped_blacklist"
                continue

            # Отсекаем мёртвые репозитории
            if stars == 0 and len(desc) < 20:
                continue

            readme = await gh.fetch_readme(owner, repo_name, item.get("default_branch", "main"))
            if len(readme.strip()) < 100 and stars < 5:
                continue

            # ИИ-фильтр (Groq)
            summary = await curator.evaluate_project(fn, desc, readme)
            if not summary:
                state["posted_repos"][fn] = "skipped_ai"
                logger.info(f"ИИ отклонил: {fn}")
                continue

            # Проверяем, прорыв ли это (создан недавно + набрал звезды)
            created_dt = parse_iso(created_at)
            is_breakthrough = False
            if created_dt and (now_utc() - created_dt).total_seconds() < 7 * 86400 and stars >= 10:
                is_breakthrough = True

            text = post_new_idea(fn, stars, forks, lang, created_at, summary, url, is_breakthrough)
            if await send_tg(bot, main_channel, text):
                state["posted_repos"][fn] = now_utc().isoformat()
                published += 1
                logger.info(f"Опубликована новинка: {fn}")
                await asyncio.sleep(MESSAGE_DELAY)

    save_state(state)
    await bot.session.close()
    logger.info(f"Завершено. Всего опубликовано: {published}")


if __name__ == "__main__":
    asyncio.run(main())
