#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Radar v10.

Используемые GitHub Actions secrets:
  CHANNEL_ID
  CONFIG_CHANNEL_ID
  GROQ_API_KEY
  TELEGRAM_BOT_TOKEN

Необязательно:
  GITHUB_TOKEN — обычно автоматически доступен в GitHub Actions.
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
import requests
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

try:
    from groq import Groq
except ImportError:
    Groq = None

STATE_FILE = os.getenv("STATE_FILE", "radar_state.json")
MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "20"))
SEARCH_DAYS = int(os.getenv("SEARCH_DAYS", "7"))
MAX_REPO_AGE_DAYS = int(os.getenv("MAX_REPO_AGE_DAYS", "45"))
COOLDOWN_DAYS = int(os.getenv("COOLDOWN_DAYS", "30"))
MIN_MOMENTUM_SCORE = int(os.getenv("MIN_MOMENTUM_SCORE", "30"))
MIN_NOVELTY_SCORE = int(os.getenv("MIN_NOVELTY_SCORE", "35"))
MESSAGE_DELAY = float(os.getenv("MESSAGE_DELAY", "2"))
GROQ_DELAY = float(os.getenv("GROQ_DELAY", "1.5"))

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    API_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

GROQ_MODELS = [
    x.strip()
    for x in os.getenv(
        "GROQ_MODELS",
        "openai/gpt-oss-120b,openai/gpt-oss-20b",
    ).split(",")
    if x.strip()
]

SEARCH_QUERIES = [
    "in:name,description censorship resistance",
    "in:name,description traffic obfuscation",
    "in:name,description DPI evasion",
    "in:name,description network fingerprint",
    "in:name,description encrypted proxy",
    "in:name,description tunnel transport",
    "in:name,description traffic shaping",
    "in:name,description QUIC proxy",
    "in:name,description eBPF network",
    "in:name,description TUN userspace",
    "in:name,description fake TLS",
    "in:name,description packet fragmentation",
    "in:name,description censorship measurement",
    "in:name,description self healing tunnel",
    "in:name,description adaptive routing",
    "in:name,description privacy network",
]

VPN_TERMS = {
    "vpn", "proxy", "censorship", "dpi", "obfuscation", "tunnel", "transport",
    "vless", "vmess", "xray", "v2ray", "reality", "hysteria", "wireguard",
    "shadowsocks", "sing-box", "singbox", "clash", "zapret", "goodbyedpi",
    "bypass", "anti-censorship", "anticensorship", "network fingerprint",
    "traffic shaping", "packet fragmentation", "tls fingerprint", "quic",
    "http/3", "webtransport", "tun", "ebpf", "nftables", "nfqueue",
}

LOW_VALUE_TERMS = {
    "template", "boilerplate", "starter", "course", "tutorial", "example",
    "demo", "calculator", "portfolio", "recipe", "game", "weather", "shop",
    "ecommerce", "crypto", "nft", "blockchain", "finance", "trading",
    "language learning", "flashcard", "resume", "cv", "pomodoro",
}

COPY_TERMS = {"mirror", "repack", "repackage", "clone", "unofficial", "build-only"}

FAMILIES = {
    "zapret": {"zapret", "goodbyedpi", "byedpi", "spoofdpi", "antizapret"},
    "xray": {"xray", "vless", "vmess", "reality", "xtls", "v2ray"},
    "singbox": {"sing-box", "singbox", "mihomo", "clash-meta", "clash"},
    "hysteria": {"hysteria", "hysteria2"},
    "wireguard": {"wireguard", "amneziawg", "amnezia-wg"},
    "panels": {"marzban", "3x-ui", "x-ui", "hiddify", "nekoray", "v2rayn", "v2rayng"},
    "aggregator": {"subcrawler", "nomorewalls", "v2ray-config", "free-servers", "aggregator"},
}

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("github-radar")


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now().isoformat()


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except (TypeError, ValueError):
        return None


def age_days(value: Optional[str]) -> float:
    dt = parse_dt(value)
    return 9999 if not dt else max(0, (now() - dt).total_seconds() / 86400)


def normalize(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-zа-я0-9+#/.-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe(value: Any, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def sha(value: str) -> str:
    return hashlib.sha256(normalize(value).encode("utf-8", errors="ignore")).hexdigest()


def family(repo: Dict[str, Any]) -> str:
    text = normalize(f"{repo.get('name', '')} {repo.get('description', '')}")
    for name, terms in FAMILIES.items():
        if any(term in text for term in terms):
            return name
    return "other"


def vpn_context(repo: Dict[str, Any], readme: str) -> bool:
    text = normalize(f"{repo.get('name', '')} {repo.get('description', '')} {readme[:5000]}")
    return any(term in text for term in VPN_TERMS)


def low_value(repo: Dict[str, Any], readme: str) -> bool:
    text = normalize(f"{repo.get('name', '')} {repo.get('description', '')} {readme[:3000]}")
    return any(term in text for term in LOW_VALUE_TERMS)


def copy_project(repo: Dict[str, Any], readme: str) -> bool:
    name = normalize(repo.get("name", ""))
    return bool(
        repo.get("fork")
        or any(term in name for term in COPY_TERMS)
        or (len(readme.strip()) < 100 and repo.get("stargazers_count", 0) == 0)
    )


def load_state() -> Dict[str, Any]:
    default = {"posted": {}, "repos": {}, "concepts": {}, "query_index": 0}
    if not os.path.exists(STATE_FILE):
        return default
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        for key, value in default.items():
            state.setdefault(key, value)
        return state
    except Exception as exc:
        log.warning("State load error: %s", exc)
        return default


def save_state(state: Dict[str, Any]) -> None:
    state["last_run"] = iso_now()
    for key, limit in (("posted", 5000), ("repos", 5000), ("concepts", 5000)):
        state[key] = dict(list(state.get(key, {}).items())[-limit:])
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def target_id(value: str) -> Any:
    value = value.strip()
    return int(value) if re.fullmatch(r"-?\d+", value) else value


class GitHub:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.sync = requests.Session()
        self.sync.headers.update(API_HEADERS)

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=API_HEADERS)
        return self

    async def __aexit__(self, *_):
        if self.session:
            await self.session.close()
        self.sync.close()

    async def json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        assert self.session
        url = path if path.startswith("http") else GITHUB_API + path
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    return await r.json()
                log.debug("GitHub %s for %s", r.status, url)
        except Exception as exc:
            log.debug("GitHub error: %s", exc)
        return None

    async def text(self, url: str) -> str:
        assert self.session
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.text(errors="ignore")
        except Exception:
            pass
        return ""

    async def search(self, query: str) -> List[Dict[str, Any]]:
        cutoff = (now() - timedelta(days=SEARCH_DAYS)).strftime("%Y-%m-%d")
        data = await self.json("/search/repositories", {
            "q": f"{query} created:>={cutoff} fork:false",
            "sort": "stars",
            "order": "desc",
            "per_page": 50,
        })
        return data.get("items", []) if data else []

    async def repo(self, full_name: str) -> Dict[str, Any]:
        return await self.json(f"/repos/{full_name}") or {}

    async def inspect(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        full_name = repo["full_name"]
        info = await self.repo(full_name)
        branch = info.get("default_branch", "main")
        readme_data, tree_data, commit_data, contributors = await asyncio.gather(
            self.json(f"/repos/{full_name}/readme"),
            self.json(f"/repos/{full_name}/git/trees/{branch}", {"recursive": "1"}),
            self.json(f"/repos/{full_name}/commits", {"per_page": 10}),
            self.json(f"/repos/{full_name}/contributors", {"per_page": 1, "anon": "true"}),
        )

        readme = ""
        if readme_data and readme_data.get("download_url"):
            readme = await self.text(readme_data["download_url"])
        if not readme:
            for b in (branch, "main", "master"):
                readme = await self.text(f"https://raw.githubusercontent.com/{full_name}/{b}/README.md")
                if readme:
                    break

        files = [x.get("path", "") for x in (tree_data or {}).get("tree", []) if x.get("type") == "blob"][:300]
        commits = [safe(x.get("commit", {}).get("message", ""), 180) for x in (commit_data or [])]
        return {
            "readme": readme,
            "files": files,
            "commits": commits,
            "contributors": len(contributors or []),
            "has_release": bool(await self.json(f"/repos/{full_name}/releases", {"per_page": 1})),
            "has_demo": bool(re.search(r"demo|screenshot|video|try it|usage", readme, re.I)),
            "has_tests": any("test" in x.lower() for x in files),
            "has_docker": any(x.lower() in {"dockerfile", "docker-compose.yml", "compose.yml"} for x in files),
        }


def score(repo: Dict[str, Any], meta: Dict[str, Any], state: Dict[str, Any]) -> Tuple[int, List[str], str]:
    points = 0
    reasons: List[str] = []
    full_name = repo["full_name"]
    previous = state.get("repos", {}).get(full_name, {})
    stars = int(repo.get("stargazers_count", 0) or 0)
    forks = int(repo.get("forks_count", 0) or 0)
    old_stars = int(previous.get("stars", stars) or 0)
    old_forks = int(previous.get("forks", forks) or 0)
    star_delta = stars - old_stars
    fork_delta = forks - old_forks
    created = age_days(repo.get("created_at"))

    if created <= 3:
        points += 25; reasons.append("создан менее 3 дней назад")
    elif created <= 14:
        points += 15; reasons.append("молодой проект")
    elif created <= MAX_REPO_AGE_DAYS:
        points += 5; reasons.append("относительно новый проект")
    if age_days(repo.get("pushed_at")) <= 1:
        points += 5; reasons.append("активная разработка")
    if 2 <= stars <= 1000:
        points += 5; reasons.append("ранняя стадия интереса")
    if star_delta >= 10:
        points += 20; reasons.append(f"рост +{star_delta} звёзд")
    elif star_delta >= 3:
        points += 8; reasons.append(f"рост +{star_delta} звёзд")
    if fork_delta >= 3:
        points += 15; reasons.append(f"рост +{fork_delta} форков")
    elif fork_delta >= 1:
        points += 5; reasons.append("появился новый fork")
    if meta["contributors"] >= 2:
        points += 8; reasons.append("несколько contributors")
    if meta["has_demo"]:
        points += 8; reasons.append("есть demo или пример")
    if meta["has_release"]:
        points += 5; reasons.append("есть релиз")
    if meta["has_tests"]:
        points += 4; reasons.append("есть тесты")
    if meta["has_docker"]:
        points += 3; reasons.append("есть Docker-запуск")
    if repo.get("fork"):
        points -= 35; reasons.append("fork")
    if copy_project(repo, meta["readme"]):
        points -= 20; reasons.append("похож на копию или wrapper")
    if low_value(repo, meta["readme"]):
        points -= 30; reasons.append("низкая тематическая ценность")
    if not vpn_context(repo, meta["readme"]):
        points -= 40; reasons.append("нет VPN/DPI/network-контекста")

    concept = sha(" ".join([
        repo.get("name", ""), repo.get("description", "") or "",
        meta["readme"][:7000], " ".join(meta["files"][:80]), " ".join(meta["commits"]),
    ]))
    if concept in state.get("concepts", {}) and state["concepts"][concept] != full_name:
        points -= 30; reasons.append("похожая идея уже была")
    return points, reasons, concept


class AI:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY")) if Groq and os.getenv("GROQ_API_KEY") else None

    async def analyze(self, repo: Dict[str, Any], meta: Dict[str, Any], points: int, reasons: List[str]) -> Dict[str, Any]:
        fallback = {
            "verdict": "NEW_PROJECT",
            "novelty_score": points,
            "idea": safe(repo.get("description") or "Новый технический проект", 300),
            "what_is_new": "; ".join(reasons[:3]),
            "evidence": reasons[:4],
            "similar_projects": [],
        }
        if not self.client:
            return fallback
        prompt = f"""Ты редактор GitHub Radar для VPN, proxy, DPI и сетевой безопасности.
Определи самостоятельную новую идею. Обычный релиз, косметический fork, wrapper,
зеркало и конфиг-сборник должны быть SKIP. Если нет конкретного технического отличия,
выбери SKIP. Верни только JSON.

{{
  "verdict": "BREAKTHROUGH|NEW_PROJECT|USEFUL_FORK|UPDATE|SKIP",
  "novelty_score": 0,
  "idea": "одно предложение",
  "what_is_new": "конкретное техническое отличие",
  "evidence": ["факт 1", "факт 2"],
  "similar_projects": ["owner/repo"],
  "confidence": 0
}}

name: {repo.get('full_name')}
description: {safe(repo.get('description'), 600)}
created_at: {repo.get('created_at')}
stars: {repo.get('stargazers_count', 0)}
forks: {repo.get('forks_count', 0)}
language: {repo.get('language')}
heuristic_score: {points}
heuristic_reasons: {json.dumps(reasons, ensure_ascii=False)}
contributors: {meta['contributors']}
files: {json.dumps(meta['files'][:80], ensure_ascii=False)}
commits: {json.dumps(meta['commits'][:10], ensure_ascii=False)}
README:
{meta['readme'][:9000]}
"""
        for model in GROQ_MODELS:
            try:
                result = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=500,
                    response_format={"type": "json_object"},
                )
                data = json.loads(result.choices[0].message.content)
                if isinstance(data, dict) and data.get("verdict"):
                    return data
            except Exception as exc:
                log.warning("Groq error (%s): %s", model, exc)
            await asyncio.sleep(GROQ_DELAY)
        return fallback


def make_post(repo: Dict[str, Any], meta: Dict[str, Any], ai: Dict[str, Any], points: int, reasons: List[str]) -> str:
    verdict = str(ai.get("verdict", "NEW_PROJECT")).upper()
    emoji = {"BREAKTHROUGH": "🚀", "NEW_PROJECT": "🆕", "USEFUL_FORK": "🛠", "MOMENTUM": "📈"}.get(verdict, "🔎")
    title = {"BREAKTHROUGH": "ВОЗМОЖНЫЙ ПРОРЫВ", "NEW_PROJECT": "НОВЫЙ ПРОЕКТ", "USEFUL_FORK": "ПОЛЕЗНЫЙ FORK", "MOMENTUM": "РАННИЙ РОСТ"}.get(verdict, verdict)
    evidence = ai.get("evidence") or reasons[:4]
    evidence_text = "\n".join(f"• {html.escape(safe(x, 220))}" for x in evidence[:4])
    similar = ", ".join(html.escape(str(x)) for x in (ai.get("similar_projects") or [])[:4]) or "не определены"
    return (
        f"{emoji} <b>{title}</b>\n\n"
        f"<b>{html.escape(repo['full_name'])}</b>\n"
        f"⭐ {repo.get('stargazers_count', 0)} | 🍴 {repo.get('forks_count', 0)}\n"
        f"Возраст: {age_days(repo.get('created_at')):.1f} дней\n"
        f"Язык: {html.escape(str(repo.get('language') or 'не указан'))}\n"
        f"Оценка: {points}\n\n"
        f"<b>Что делает:</b>\n{html.escape(safe(repo.get('description') or 'Без описания', 600))}\n\n"
        f"<b>Что нового:</b>\n{html.escape(safe(ai.get('what_is_new') or 'Не установлено', 800))}\n\n"
        f"<b>Доказательства:</b>\n{evidence_text}\n\n"
        f"<b>Похожие проекты:</b> {similar}\n\n"
        f"<a href=\"{html.escape(repo['html_url'])}\">Открыть на GitHub</a>"
    )


async def send(bot: Bot, target: Any, text: str) -> bool:
    for attempt in range(3):
        try:
            await bot.send_message(target, text, disable_web_page_preview=True)
            return True
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            log.error("Нет доступа к Telegram-каналу %s", target)
            return False
        except Exception as exc:
            log.warning("Telegram attempt %s: %s", attempt + 1, exc)
            await asyncio.sleep(2)
    return False


async def main() -> None:
    required = ["CHANNEL_ID", "CONFIG_CHANNEL_ID", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit("Не заданы secrets: " + ", ".join(missing))

    state = load_state()
    bot = Bot(
        token=os.environ["TELEGRAM_BOT_TOKEN"],
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    analyzer = AI()
    channel = target_id(os.environ["CHANNEL_ID"])
    config_channel = target_id(os.environ["CONFIG_CHANNEL_ID"])
    candidates: Dict[str, Dict[str, Any]] = {}
    start = int(state.get("query_index", 0))
    queries = SEARCH_QUERIES[start:] + SEARCH_QUERIES[:start]

    async with GitHub() as github:
        for query in queries:
            log.info("Search: %s", query)
            for repo in await github.search(query):
                if repo.get("full_name"):
                    candidates[repo["full_name"]] = repo
            await asyncio.sleep(1)

        state["query_index"] = (start + 3) % len(SEARCH_QUERIES)
        ranked = []
        for full_name, repo in candidates.items():
            old = state.get("posted", {}).get(full_name)
            if old and age_days(old.get("at")) < COOLDOWN_DAYS:
                continue
            meta = await github.inspect(repo)
            points, reasons, concept = score(repo, meta, state)
            if points < MIN_MOMENTUM_SCORE:
                continue
            ranked.append((points, repo, meta, reasons, concept))
            state.setdefault("repos", {})[full_name] = {
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "at": iso_now(),
            }

        ranked.sort(key=lambda row: row[0], reverse=True)
        published = 0
        family_count: Dict[str, int] = {}

        for points, repo, meta, reasons, concept in ranked:
            if published >= MAX_POSTS_PER_RUN:
                break
            fam = family(repo)
            if family_count.get(fam, 0) >= 2:
                continue
            ai = await analyzer.analyze(repo, meta, points, reasons)
            verdict = str(ai.get("verdict", "SKIP")).upper()
            ai_score = int(ai.get("novelty_score", points) or points)
            if verdict in {"SKIP", "UPDATE"} or ai_score < MIN_MOMENTUM_SCORE:
                continue
            if concept in state.get("concepts", {}) and state["concepts"][concept] != repo["full_name"]:
                continue

            text = make_post(repo, meta, ai, ai_score, reasons)
            if await send(bot, channel, text):
                state.setdefault("posted", {})[repo["full_name"]] = {
                    "at": iso_now(), "verdict": verdict, "score": ai_score, "concept": concept,
                }
                state.setdefault("concepts", {})[concept] = repo["full_name"]
                family_count[fam] = family_count.get(fam, 0) + 1
                published += 1
                log.info("Published %s: %s", repo["full_name"], verdict)
                await asyncio.sleep(MESSAGE_DELAY)

    save_state(state)
    await bot.session.close()
    log.info("Finished. Published: %s", published)


if __name__ == "__main__":
    asyncio.run(main())
