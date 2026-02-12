import pandas as pd
import time
import random
import numpy as np
import re
import json
import uuid
import requests
from collections import defaultdict
import os
import shutil
import matplotlib.pyplot as plt
import networkx as nx
from html import unescape
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from config import CONFIG
from extensibility import HookBus
from environment import EnvironmentSystem
from llm_providers import call_llm
from experience_store import (
    append_agent_episode,
    load_agent_episodes,
    load_agent_habits,
    load_agent_intentions,
    load_agent_relationships,
    prune_and_decay_episodes,
    save_agent_habits,
    save_agent_intentions,
    save_agent_relationships,
)
from human_realism import (
    build_context_key,
    build_daily_intentions,
    compute_episode_salience,
    consolidate_day,
    infer_episode_tags,
    infer_interaction_signal,
    intention_text,
    relationship_update,
    relationship_weight,
    update_habits_from_episode,
    update_needs,
)
from memory_store import (
    append_agent_log,
    load_agent_actions,
    load_agent_locations,
    load_agent_location_action_bias,
    load_agent_memory,
    load_agent_schedule,
    load_recent_actions,
    load_recent_log_blocks,
    load_sim_state,
    reset_agent_memory,
    retrieve_relevant_memories,
    save_agent_actions,
    save_agent_location_action_bias,
    save_agent_locations,
    save_agent_memory,
    save_agent_schedule,
    save_sim_state,
    seed_vector_db_from_memory,
    vector_db_add_entry,
    VECTOR_DB_TOP_K,
    _format_memory_hint,
    _memory_action_bias,
)

# =========================================================
# Utils
# =========================================================
def _parse_step_minutes(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if not text:
        return None
    match = re.match(r"^(\d+)\s*(m|min|mins|minute|minutes|h|hour|hours)?$", text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if not unit or unit.startswith("m"):
        return amount
    if unit.startswith("h"):
        return amount * 60
    return amount

def _time_str_to_minutes(time_str):
    if not re.match(r"^\d{2}:\d{2}$", str(time_str)):
        return None
    hh, mm = time_str.split(":")
    return int(hh) * 60 + int(mm)

def _minutes_to_time_str(minutes):
    minutes = int(minutes) % (24 * 60)
    hh = minutes // 60
    mm = minutes % 60
    return f"{hh:02d}:{mm:02d}"

def _build_time_grid(step_minutes):
    step = max(1, int(step_minutes))
    return [_minutes_to_time_str(m) for m in range(0, 24 * 60, step)]

def _clear_dir(path):
    if not path or not os.path.exists(path):
        return
    for name in os.listdir(path):
        target = os.path.join(path, name)
        try:
            if os.path.islink(target) or os.path.isfile(target):
                os.remove(target)
            elif os.path.isdir(target):
                shutil.rmtree(target)
        except OSError:
            continue

def _strip_html(text):
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\\s+", " ", text)
    return text.strip()

def _extract_title(text):
    if not text:
        return ""
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
    if not match:
        return ""
    title = _strip_html(match.group(1))
    return re.sub(r"\\s+", " ", title).strip()

def _normalize_text(text):
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"\u00a0", " ", text)
    text = re.sub(r"\\s+", " ", text)
    return text.strip()

def _extract_ld_json_article_body(text):
    if not text:
        return ""
    scripts = re.findall(
        r'(?is)<script[^>]*type=["\']application/ld\\+json["\'][^>]*>(.*?)</script>',
        text,
    )
    for block in scripts:
        candidate = block.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            article_body = node.get("articleBody")
            if isinstance(article_body, str) and len(article_body.strip()) > 80:
                return _normalize_text(article_body)
    return ""

def _extract_article_like_block(text):
    if not text:
        return ""
    candidate_patterns = [
        r"(?is)<article[^>]*>(.*?)</article>",
        r"(?is)<main[^>]*>(.*?)</main>",
        r'(?is)<div[^>]+(?:id|class)=["\'][^"\']*(?:article|content|story|post|entry|news|正文)[^"\']*["\'][^>]*>(.*?)</div>',
    ]
    for pattern in candidate_patterns:
        blocks = re.findall(pattern, text)
        for block in blocks:
            paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", block)
            parts = [_normalize_text(_strip_html(p)) for p in paragraphs]
            parts = [p for p in parts if len(p) >= 25]
            joined = "\n".join(parts)
            if len(joined) >= 180:
                return joined
    return ""

def _extract_paragraph_fallback(text):
    if not text:
        return ""
    paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", text)
    cleaned = []
    blacklist = ("copyright", "subscribe", "登录", "注册", "隐私", "cookie", "版权所有")
    for p in paragraphs:
        line = _normalize_text(_strip_html(p))
        lower = line.lower()
        if len(line) < 25:
            continue
        if any(b in lower for b in blacklist):
            continue
        cleaned.append(line)
    if not cleaned:
        return ""
    return "\n".join(cleaned[:16])

def _extract_news_main_content(html_text):
    # Prefer structured article content, then paragraph extraction, and finally full-page text.
    for extractor in (_extract_ld_json_article_body, _extract_article_like_block, _extract_paragraph_fallback):
        content = extractor(html_text)
        if content and len(content) >= 120:
            return content
    return _strip_html(html_text)

def load_news_sources(path):
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    urls = re.findall(r"\\((https?://[^)\\s]+)\\)", text)
    urls.extend(re.findall(r"https?://[^\\s)]+", text))
    cleaned = []
    seen = set()
    for url in urls:
        url = url.strip().rstrip(").,;")
        if not url or url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned

def load_news_cache(path):
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        return []
    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        text = str(item.get("text", "")).strip()
        if not url or not text:
            continue
        cleaned.append({
            "url": url,
            "text": text,
            "title": str(item.get("title", "")).strip(),
            "fetched_at": str(item.get("fetched_at", "")).strip(),
        })
    return cleaned

def fetch_news_excerpt(
    url,
    timeout=8,
    max_chars=2000,
    user_agent="GAWorld/1.0",
    return_title=False,
):
    if not url:
        return ("", "") if return_title else ""
    try:
        headers = {"User-Agent": user_agent}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        if not resp.encoding:
            resp.encoding = resp.apparent_encoding
        raw_text = resp.text or ""
    except requests.RequestException:
        return ("", "") if return_title else ""
    if not raw_text:
        return ("", "") if return_title else ""
    content_type = (resp.headers.get("content-type") or "").lower()
    title = ""
    if "text/html" in content_type or "<html" in raw_text.lower():
        title = _extract_title(raw_text)
        cleaned = _extract_news_main_content(raw_text)
    else:
        cleaned = re.sub(r"\\s+", " ", raw_text).strip()
    if max_chars and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rsplit(" ", 1)[0].strip() if " " in cleaned else cleaned[:max_chars]
    if return_title:
        return cleaned, title
    return cleaned

def update_news_cache(path, sources, config=None):
    config = config or {}
    existing = load_news_cache(path)
    if not sources:
        return existing
    timeout = int(config.get("timeout", 8))
    max_chars = int(config.get("max_chars", 2000))
    user_agent = str(config.get("user_agent", "GAWorld/1.0"))
    items = []
    seen = set()
    for url in sources:
        url = str(url).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        excerpt, title = fetch_news_excerpt(
            url,
            timeout=timeout,
            max_chars=max_chars,
            user_agent=user_agent,
            return_title=True,
        )
        if not excerpt:
            continue
        items.append({
            "url": url,
            "title": title,
            "text": excerpt,
            "fetched_at": time.strftime("%Y-%m-%d"),
        })
    if not items:
        return existing
    cache_dir = os.path.dirname(path)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except OSError:
        return existing
    return items

def _extract_interest_keywords(agent, max_items=24):
    profile_fields = [
        "job",
        "personality",
        "daily_life",
        "values",
        "work_style",
        "living",
        "residence",
    ]
    seed_text = " ".join(str(agent.get(k, "")) for k in profile_fields)
    tokens = re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,8}", seed_text)
    stopwords = {
        "自己", "一些", "这种", "这个", "那个", "他们", "我们", "你们",
        "以及", "对于", "非常", "比较", "可以", "因为", "所以", "但是",
        "工作", "生活", "习惯", "日常", "态度", "价值观", "情绪", "性格",
        "城市", "社会", "公共", "事务", "时候", "进行", "觉得", "喜欢",
        "about", "into", "with", "from", "that", "this", "have", "their",
    }
    counts = defaultdict(int)
    for raw in tokens:
        token = raw.lower().strip()
        if len(token) < 2 or token in stopwords:
            continue
        counts[token] += 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], -len(x[0]), x[0]))
    return [k for k, _ in ranked[:max_items]]

def _score_news_relevance(url, title, excerpt, interests):
    if not interests:
        return 0.0, []
    domain = urlparse(url).netloc.lower() if url else ""
    haystack = " ".join(
        [
            str(url or "").lower(),
            str(domain or "").lower(),
            str(title or "").lower(),
            str(excerpt or "").lower(),
        ]
    )
    if not haystack.strip():
        return 0.0, []
    matched = []
    score = 0.0
    for kw in interests:
        if kw and kw in haystack:
            matched.append(kw)
            score += 1.0 + min(len(kw), 10) * 0.05
    return score, matched[:8]

def choose_news_for_agent(
    agent,
    news_cache,
    news_sources,
    use_cache_first=True,
    seen_urls=None,
):
    seen_urls = seen_urls or set()
    interests = _extract_interest_keywords(agent)

    def _pick_best_from_cache(items):
        ranked = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            if not url or url in seen_urls:
                continue
            title = str(item.get("title", "")).strip()
            text = str(item.get("text", "")).strip()
            score, matched = _score_news_relevance(url, title, text, interests)
            ranked.append((score + random.random() * 0.05, matched, item))
        if not ranked:
            return None
        ranked.sort(key=lambda x: x[0], reverse=True)
        top_n = ranked[: min(3, len(ranked))]
        chosen = random.choice(top_n)
        return chosen[2], chosen[0], chosen[1]

    if use_cache_first and news_cache:
        picked = _pick_best_from_cache(news_cache)
        if picked:
            item, score, matched = picked
            return (
                item.get("url", ""),
                item.get("text", ""),
                item.get("title", ""),
                score,
                matched,
            )

    candidate_sources = [u for u in news_sources if u and u not in seen_urls]
    if candidate_sources:
        source_ranked = []
        for source_url in candidate_sources:
            score, matched = _score_news_relevance(source_url, "", "", interests)
            source_ranked.append((score + random.random() * 0.05, matched, source_url))
        source_ranked.sort(key=lambda x: x[0], reverse=True)
        best_score, best_matched, best_url = source_ranked[0]
        return best_url, "", "", best_score, best_matched

    if news_cache:
        picked = _pick_best_from_cache(news_cache)
        if picked:
            item, score, matched = picked
            return (
                item.get("url", ""),
                item.get("text", ""),
                item.get("title", ""),
                score,
                matched,
            )
    return "", "", "", 0.0, []

def _domain_from_url(url):
    domain = urlparse(str(url or "")).netloc.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain

def _build_agent_preferred_sites(agent, news_sources=None, news_cache=None, max_sites=6):
    news_sources = news_sources or []
    news_cache = news_cache or []
    interests = _extract_interest_keywords(agent, max_items=18)
    fallback_domains = [
        "baidu.com",
        "bing.com",
        "google.com",
        "thepaper.cn",
        "news.qq.com",
        "weibo.com",
        "zhihu.com",
    ]
    domain_scores = defaultdict(float)
    for url in news_sources:
        domain = _domain_from_url(url)
        if domain:
            domain_scores[domain] += 0.6
            score, _ = _score_news_relevance(url, "", "", interests)
            domain_scores[domain] += score
    for item in news_cache:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        text = str(item.get("text", "")).strip()
        domain = _domain_from_url(url)
        if not domain:
            continue
        score, _ = _score_news_relevance(url, title, text, interests)
        domain_scores[domain] += 0.5 + score
    for domain in fallback_domains:
        domain_scores[domain] += 0.2
    ranked = sorted(domain_scores.items(), key=lambda x: (-x[1], x[0]))
    return [domain for domain, _ in ranked[:max(1, int(max_sites))]]

def _choose_info_target(
    agent,
    news_cache,
    news_sources,
    preferred_sites,
    seen_urls=None,
    used_queries=None,
    config=None,
):
    config = config or {}
    seen_urls = seen_urls or set()
    used_queries = used_queries or set()
    direct_visit_ratio = float(config.get("prefer_source_visit_ratio", 0.55))
    interests = _extract_interest_keywords(agent)

    preferred_cache = []
    for item in news_cache or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if not url or url in seen_urls:
            continue
        domain = _domain_from_url(url)
        if preferred_sites and domain not in preferred_sites:
            continue
        title = str(item.get("title", "")).strip()
        text = str(item.get("text", "")).strip()
        score, matched = _score_news_relevance(url, title, text, interests)
        preferred_cache.append((score + random.random() * 0.03, matched, url, title, text))
    preferred_cache.sort(key=lambda x: x[0], reverse=True)

    preferred_sources = []
    for url in news_sources or []:
        url = str(url).strip()
        if not url or url in seen_urls:
            continue
        domain = _domain_from_url(url)
        if preferred_sites and domain not in preferred_sites:
            continue
        score, matched = _score_news_relevance(url, "", "", interests)
        preferred_sources.append((score + random.random() * 0.03, matched, url))
    preferred_sources.sort(key=lambda x: x[0], reverse=True)

    if random.random() < direct_visit_ratio and preferred_cache:
        score, matched, url, title, text = preferred_cache[0]
        return {
            "mode": "direct_source",
            "query": "",
            "engine": "",
            "url": url,
            "title": title,
            "content": text,
            "score": score,
            "matched": matched,
        }
    if random.random() < direct_visit_ratio and preferred_sources:
        score, matched, url = preferred_sources[0]
        text = fetch_news_excerpt(
            url,
            timeout=int(config.get("content_timeout", config.get("timeout", 8))),
            max_chars=int(config.get("content_max_chars", 2000)),
            user_agent=str(config.get("user_agent", "GAWorld/1.0")),
        )
        if text:
            return {
                "mode": "direct_source",
                "query": "",
                "engine": "",
                "url": url,
                "title": "",
                "content": text,
                "score": score,
                "matched": matched,
            }

    query = _build_search_query(agent, used_queries=used_queries)
    if preferred_sites and random.random() < 0.85:
        query = f"{query} site:{random.choice(preferred_sites)}"
    engine, results = web_search(query, config=config)
    if not results:
        return None

    ranked = []
    timeout = int(config.get("content_timeout", config.get("timeout", 8)))
    max_chars = int(config.get("content_max_chars", 2000))
    user_agent = str(config.get("user_agent", "GAWorld/1.0"))
    for item in results:
        url = str(item.get("url", "")).strip()
        if not url or url in seen_urls:
            continue
        title = str(item.get("title", "")).strip()
        snippet = str(item.get("snippet", "")).strip()
        excerpt = fetch_news_excerpt(url, timeout=timeout, max_chars=max_chars, user_agent=user_agent)
        content = excerpt or snippet
        if not content:
            continue
        score, matched = _score_news_relevance(url, title, content, interests)
        if preferred_sites and _domain_from_url(url) in preferred_sites:
            score += 0.9
        ranked.append((score + random.random() * 0.03, matched, url, title, content))
    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    score, matched, url, title, content = ranked[0]
    return {
        "mode": "web_search",
        "query": query,
        "engine": engine,
        "url": url,
        "title": title,
        "content": content,
        "score": score,
        "matched": matched,
    }

def info_seek_and_store(
    agent,
    day=None,
    time_str=None,
    news_cache=None,
    news_sources=None,
    preferred_sites=None,
    seen_urls=None,
    used_queries=None,
    config=None,
):
    config = config or {}
    target = _choose_info_target(
        agent=agent,
        news_cache=news_cache or [],
        news_sources=news_sources or [],
        preferred_sites=preferred_sites or [],
        seen_urls=seen_urls or set(),
        used_queries=used_queries or set(),
        config=config,
    )
    if not target:
        return None, None, "", ""

    title = target.get("title", "")
    url = target.get("url", "")
    content = str(target.get("content", "")).strip()
    if not url or not content:
        return None, None, "", ""
    mode = target.get("mode", "direct_source")
    query = target.get("query", "")
    engine = target.get("engine", "")

    profile_text = "\\n".join([
        f"姓名：{agent.get('name', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    prompt = f"""
你是{agent['name']}。
角色资料：
{profile_text}

你本次的信息获取方式：{mode}
检索词：{query or "N/A"}
来源：{title or "N/A"} ({url})
内容摘要：
{content}

请用1-2句写出你为何会关注这条信息，以及你的看法。
"""
    thought = call_llm(prompt, task="info_seek_reaction", agent_id=agent["id"]).strip()
    if not thought:
        thought = "这条信息符合我近期关注，我会继续观察。"

    memory_excerpt_chars = int(config.get("memory_excerpt_chars", 700))
    memory_excerpt = content
    if memory_excerpt_chars > 0 and len(memory_excerpt) > memory_excerpt_chars:
        memory_excerpt = memory_excerpt[:memory_excerpt_chars].rsplit(" ", 1)[0].strip() if " " in memory_excerpt else memory_excerpt[:memory_excerpt_chars]
        memory_excerpt = f"{memory_excerpt}..."

    stamp = f"Day {day} {time_str}" if day and time_str else "InfoSeek"
    preferred_text = ", ".join(preferred_sites or []) if preferred_sites else "N/A"
    memory_entry = (
        f"[{stamp}] 信息获取：{mode}\n"
        f"偏好站点：{preferred_text}\n"
        f"检索词：{query or 'N/A'}\n"
        f"来源：{title or 'N/A'} ({url})\n"
        f"内容：{memory_excerpt}\n"
        f"想法：{thought}"
    )
    agent["memory"].append(memory_entry)
    save_agent_memory(agent)
    vector_db_add_entry(agent["id"], "info_seek", memory_entry, sim_day=day, sim_time=time_str or "info_seek")

    log = f"""
[InfoSeek {agent['name']} @ {time_str}]
Mode: {mode}
Query: {query or "N/A"}
Engine: {engine or "N/A"}
PreferredSites: {preferred_text}
Result: {title or "N/A"}
URL: {url}
MatchedInterests: {", ".join(target.get("matched", [])) if target.get("matched") else "N/A"}
RelevanceScore: {float(target.get("score", 0.0)):.2f}
"""
    return memory_entry, log, url, query

def _estimate_curiosity(agent):
    state = agent.get("state", {})
    platform_dependence = float(state.get("platform_dependence", 0.5))
    risk_preference = float(state.get("risk_preference", 0.5))
    text = " ".join(
        str(agent.get(k, ""))
        for k in ("personality", "daily_life", "values", "job")
    )
    boosts = {
        "好奇": 0.25,
        "探索": 0.20,
        "新鲜": 0.12,
        "学习": 0.10,
        "研究": 0.10,
        "科技": 0.08,
        "关注": 0.06,
        "trend": 0.06,
        "research": 0.10,
    }
    dampens = {
        "保守": 0.12,
        "封闭": 0.15,
        "排斥": 0.10,
        "抗拒": 0.10,
    }
    score = 0.20 + 0.45 * platform_dependence + 0.20 * risk_preference
    for key, value in boosts.items():
        if key in text.lower() or key in text:
            score += value
    for key, value in dampens.items():
        if key in text:
            score -= value
    return max(0.05, min(0.98, score))

def _build_search_query(agent, used_queries=None):
    used_queries = used_queries or set()
    interests = _extract_interest_keywords(agent, max_items=16)
    if not interests:
        interests = ["本地新闻", "行业动态", "公共政策"]
    name = agent.get("name", "该居民")
    job = str(agent.get("job", "")).strip()
    seeds = []
    for kw in interests[:8]:
        seeds.extend(
            [
                f"{kw} 最新消息",
                f"{kw} 今日新闻",
                f"{kw} 趋势",
            ]
        )
        if job:
            seeds.append(f"{job} {kw} 资讯")
    random.shuffle(seeds)
    for q in seeds:
        if q not in used_queries:
            return q
    return f"{name} 关注话题 今日新闻"

def _extract_google_results(html_text, max_results=5):
    results = []
    blocks = re.findall(r'(?is)<a[^>]+href="(/url\?q=[^"]+)"[^>]*>(.*?)</a>', html_text)
    for href, anchor in blocks:
        qs = parse_qs(urlparse(href).query)
        raw_url = (qs.get("q") or [""])[0]
        raw_url = unquote(raw_url).strip()
        if not raw_url.startswith("http"):
            continue
        title = _normalize_text(_strip_html(anchor))
        if len(title) < 6:
            continue
        results.append({"url": raw_url, "title": title, "snippet": ""})
        if len(results) >= max_results:
            break
    return results

def _extract_baidu_results(html_text, max_results=5):
    results = []
    blocks = re.findall(r'(?is)<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</h3>', html_text)
    for href, anchor in blocks:
        url = unquote(href).strip()
        if not url.startswith("http"):
            continue
        title = _normalize_text(_strip_html(anchor))
        if len(title) < 4:
            continue
        results.append({"url": url, "title": title, "snippet": ""})
        if len(results) >= max_results:
            break
    return results

def _extract_bing_results(html_text, max_results=5):
    results = []
    blocks = re.findall(r'(?is)<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>.*?</li>', html_text)
    for block in blocks:
        link = re.search(r'(?is)<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>', block)
        if not link:
            continue
        url = unquote(link.group(1)).strip()
        if not url.startswith("http"):
            continue
        title = _normalize_text(_strip_html(link.group(2)))
        snippet_match = re.search(r'(?is)<p[^>]*>(.*?)</p>', block)
        snippet = _normalize_text(_strip_html(snippet_match.group(1))) if snippet_match else ""
        if len(title) < 4:
            continue
        results.append({"url": url, "title": title, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results

def _extract_generic_results(html_text, max_results=5):
    results = []
    links = re.findall(r'(?is)<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', html_text)
    for href, anchor in links:
        title = _normalize_text(_strip_html(anchor))
        if len(title) < 10:
            continue
        results.append({"url": unquote(href).strip(), "title": title, "snippet": ""})
        if len(results) >= max_results:
            break
    return results

def web_search(query, config=None):
    config = config or {}
    engines = config.get("engines", ["google", "baidu", "bing"])
    timeout = int(config.get("timeout", 8))
    max_results = int(config.get("max_results", 4))
    user_agent = str(config.get("user_agent", "GAWorld/1.0"))
    search_urls = {
        "google": f"https://www.google.com/search?q={quote_plus(query)}&hl=zh-CN",
        "baidu": f"https://www.baidu.com/s?wd={quote_plus(query)}",
        "bing": f"https://www.bing.com/search?q={quote_plus(query)}",
    }
    extractors = {
        "google": _extract_google_results,
        "baidu": _extract_baidu_results,
        "bing": _extract_bing_results,
    }
    headers = {"User-Agent": user_agent}
    for engine in engines:
        search_url = search_urls.get(str(engine).lower())
        if not search_url:
            continue
        try:
            resp = requests.get(search_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            html_text = resp.text or ""
        except requests.RequestException:
            continue
        extractor = extractors.get(str(engine).lower(), _extract_generic_results)
        results = extractor(html_text, max_results=max_results)
        if not results:
            results = _extract_generic_results(html_text, max_results=max_results)
        if results:
            return engine, results
    return "", []

def search_web_and_store(agent, query, day=None, time_str=None, config=None, seen_urls=None):
    config = config or {}
    seen_urls = seen_urls or set()
    engine, results = web_search(query, config=config)
    if not results:
        return None, None, ""
    interests = _extract_interest_keywords(agent)
    timeout = int(config.get("content_timeout", config.get("timeout", 8)))
    max_chars = int(config.get("content_max_chars", 2000))
    user_agent = str(config.get("user_agent", "GAWorld/1.0"))

    ranked = []
    for item in results:
        url = str(item.get("url", "")).strip()
        if not url or url in seen_urls:
            continue
        title = str(item.get("title", "")).strip()
        snippet = str(item.get("snippet", "")).strip()
        excerpt = fetch_news_excerpt(
            url,
            timeout=timeout,
            max_chars=max_chars,
            user_agent=user_agent,
        )
        candidate_text = excerpt or snippet
        if not candidate_text:
            continue
        score, matched = _score_news_relevance(url, title, candidate_text, interests)
        ranked.append((score + random.random() * 0.03, matched, url, title, candidate_text))

    if not ranked:
        return None, None, ""

    ranked.sort(key=lambda x: x[0], reverse=True)
    score, matched, url, title, content = ranked[0]
    profile_text = "\\n".join([
        f"姓名：{agent.get('name', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    prompt = f"""
你是{agent['name']}。
角色资料：
{profile_text}

你主动搜索了：{query}
搜索结果标题：{title}
内容摘要：
{content}

请用1-2句写出你为何关注这个信息，以及你的看法。
"""
    thought = call_llm(prompt, task="web_search_reaction", agent_id=agent["id"]).strip()
    if not thought:
        thought = "这条信息与我关注的话题相关，我会继续跟进。"

    memory_excerpt_chars = int(config.get("memory_excerpt_chars", 700))
    memory_excerpt = content.strip()
    if memory_excerpt_chars > 0 and len(memory_excerpt) > memory_excerpt_chars:
        memory_excerpt = memory_excerpt[:memory_excerpt_chars].rsplit(" ", 1)[0].strip() if " " in memory_excerpt else memory_excerpt[:memory_excerpt_chars]
        memory_excerpt = f"{memory_excerpt}..."

    stamp = f"Day {day} {time_str}" if day and time_str else "WebSearch"
    memory_entry = (
        f"[{stamp}] 主动搜索：{query}\n"
        f"搜索引擎：{engine or 'unknown'}\n"
        f"结果：{title} ({url})\n"
        f"内容：{memory_excerpt}\n"
        f"想法：{thought}"
    )
    agent["memory"].append(memory_entry)
    save_agent_memory(agent)
    vector_db_add_entry(agent["id"], "web_search", memory_entry, sim_day=day, sim_time=time_str or "search")

    log = f"""
[WebSearch {agent['name']} @ {time_str}]
Query: {query}
Engine: {engine or "N/A"}
Result: {title}
URL: {url}
MatchedInterests: {", ".join(matched) if matched else "N/A"}
RelevanceScore: {score:.2f}
"""
    return memory_entry, log, url

def read_news_and_store(agent, source_url, day=None, time_str=None, config=None, excerpt=None, title=None):
    config = config or {}
    if not excerpt:
        excerpt = fetch_news_excerpt(
            source_url,
            timeout=int(config.get("timeout", 8)),
            max_chars=int(config.get("max_chars", 2000)),
            user_agent=str(config.get("user_agent", "GAWorld/1.0")),
        )
    if not excerpt:
        return None, None
    profile_text = "\\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    prompt = f"""
你是{agent['name']}。
角色资料：
{profile_text}

你刚阅读了一条新闻/社交媒体内容（节选）：
{excerpt}

请用1-2句写出你的反应，尽量体现角色身份与态度。
"""
    response = call_llm(prompt, task="news_reaction", agent_id=agent["id"]).strip()
    if not response:
        return None, None
    stamp = f"Day {day} {time_str}" if day and time_str else "NewsRead"
    title_text = f" 标题：{title}" if title else ""
    memory_excerpt_chars = int(config.get("memory_excerpt_chars", 600))
    memory_excerpt = excerpt.strip()
    if memory_excerpt_chars > 0 and len(memory_excerpt) > memory_excerpt_chars:
        memory_excerpt = memory_excerpt[:memory_excerpt_chars].rsplit(" ", 1)[0].strip() if " " in memory_excerpt else memory_excerpt[:memory_excerpt_chars]
        memory_excerpt = f"{memory_excerpt}..."
    memory_entry = (
        f"[{stamp}] 来源：{source_url}{title_text}\n"
        f"内容：{memory_excerpt}\n"
        f"想法：{response}"
    )
    agent["memory"].append(memory_entry)
    save_agent_memory(agent)
    vector_db_add_entry(agent["id"], "news", memory_entry, sim_day=day, sim_time=time_str or "news")
    log = f"""
[NewsRead {agent['name']} @ {time_str}]
Source: {source_url}
Title: {title or "N/A"}
Response: {response}
"""
    return memory_entry, log

def reset_simulation():
    memory_dir = CONFIG.get("memory_dir", "output/memory")
    log_dir = CONFIG.get("log_dir", "output/logs")
    _clear_dir(memory_dir)
    _clear_dir(log_dir)
    vector_db_path = CONFIG.get("vector_db_path")
    if vector_db_path and os.path.exists(vector_db_path):
        try:
            if os.path.isdir(vector_db_path):
                shutil.rmtree(vector_db_path)
            else:
                os.remove(vector_db_path)
        except OSError:
            pass
    for output_dir in ["output/state", "output/network"]:
        if output_dir not in (memory_dir, log_dir):
            _clear_dir(output_dir)
    save_sim_state({
        "last_day": 0,
        "memory_model_version": MEMORY_MODEL_VERSION,
    })

def visualize_social_network(
    agents,
    step=None,
    output_dir="output/network",
    node_color_attr=None
):
    """
    agents:
        - dict: {agent_id: agent_dict}
        - or list: [agent_dict, ...]
    agent_dict 中建议包含：
        - "id" 或 "name"
        - "friends" / "social_connections"
    """

    os.makedirs(output_dir, exist_ok=True)

    G = nx.Graph()

    # ---------- 统一 agent 访问方式 ----------
    if isinstance(agents, dict):
        agent_items = agents.items()
    else:  # list
        agent_items = [(a.get("id", str(i)), a) for i, a in enumerate(agents)]

    # ---------- 加节点 ----------
    for agent_id, agent in agent_items:
        value = agent.get(node_color_attr, 0.5) if node_color_attr else 0.5
        G.add_node(agent_id, value=value)

    # ---------- 加边 ----------
    for agent_id, agent in agent_items:
        friends = (
            agent.get("friends")
            or agent.get("social_connections")
            or []
        )
        for f in friends:
            if G.has_node(f):
                G.add_edge(agent_id, f)

    # ---------- 布局 ----------
    pos = nx.spring_layout(G, seed=42)

    node_values = [G.nodes[n]["value"] for n in G.nodes]

    plt.figure(figsize=(8, 8))
    nodes = nx.draw_networkx_nodes(
        G,
        pos,
        node_size=300,
        node_color=node_values,
        cmap=plt.cm.YlGn
    )
    nx.draw_networkx_edges(G, pos, alpha=0.4)
    nx.draw_networkx_labels(G, pos, font_size=8)

    if node_color_attr:
        plt.colorbar(nodes, label=node_color_attr)

    title = "Social Network"
    if step is not None:
        title += f" (Step {step})"
    plt.title(title)

    plt.axis("off")

    filename = "social_network.png" if step is None else f"social_network_{step:03d}.png"
    plt.savefig(os.path.join(output_dir, filename), dpi=200)
    plt.close()

def visualize_agent_state_changes(
    state_history,
    agent_names,
    output_dir="output/state",
    metrics=None,
):
    os.makedirs(output_dir, exist_ok=True)
    if not metrics:
        sample_history = next(iter(state_history.values()), {})
        metrics = list(sample_history.keys())

    if not metrics:
        return

    cols = 3 if len(metrics) > 4 else 2
    rows = int(np.ceil(len(metrics) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.2, rows * 3.2), sharex=True)
    axes = np.array(axes).reshape(-1)

    steps = None
    for i, metric in enumerate(metrics):
        ax = axes[i]
        for agent_id, history in state_history.items():
            series = history.get(metric, [])
            if steps is None:
                steps = list(range(len(series)))
            label = agent_names.get(agent_id, str(agent_id))
            ax.plot(steps, series, label=label, linewidth=1.6)
        ax.set_title(metric)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.2)

    for j in range(len(metrics), len(axes)):
        axes[j].axis("off")

    axes[0].legend(loc="upper right", fontsize=8)
    fig.suptitle("Agent State Changes Over Time")
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = os.path.join(output_dir, "agent_state_over_time.png")
    plt.savefig(out_path, dpi=200)
    plt.close()

def save_state_history(state_history, output_dir="output/state"):
    os.makedirs(output_dir, exist_ok=True)
    rows = []
    for agent_id, history in state_history.items():
        for metric, series in history.items():
            for step, value in enumerate(series):
                rows.append({
                    "agent_id": agent_id,
                    "step": step,
                    "metric": metric,
                    "value": float(value),
                })
    if not rows:
        return
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(output_dir, "agent_state_history.csv"), index=False)


# =========================================================
# 参数
# =========================================================
AGENT_IDS = CONFIG["agent_ids"]   # 可扩展为 100
SIM_DAYS = CONFIG["sim_days"]
SECONDS_PER_DAY = CONFIG["seconds_per_day"]

CSV_PATH = CONFIG["csv_path"]
MD_PATH = CONFIG["md_path"]
STATEFUL = CONFIG["stateful"]
MAP_PATH = CONFIG.get("map_path", "citymap.md")
PRINT_AGENT_PROFILE = CONFIG.get("print_agent_profile", False)
BACKGROUND = CONFIG.get("background", "")
MEMORY_MODEL_VERSION = int(CONFIG.get("memory_model_version", 1))
REQUIRE_CLEAN_RESET_ON_MEMORY_MODEL_CHANGE = bool(
    CONFIG.get("require_clean_reset_on_memory_model_change", False)
)
HUMAN_REALISM_CONFIG = CONFIG.get("human_realism", {})
HUMAN_REALISM_ENABLED = bool(HUMAN_REALISM_CONFIG.get("enabled", False))
TIME_STEP_MINUTES = _parse_step_minutes(CONFIG.get("time_step_minutes"))
ROUTINE_CHANGE_CONFIG = CONFIG.get("routine_change", {})
ROUTINE_CHANGE_ENABLED = bool(ROUTINE_CHANGE_CONFIG.get("enabled", True))
ROUTINE_CHANGE_BASE_CHANCE = float(ROUTINE_CHANGE_CONFIG.get("base_chance", 0.08))
ROUTINE_CHANGE_EVENT_BOOST = float(ROUTINE_CHANGE_CONFIG.get("event_boost", 0.08))
ROUTINE_CHANGE_POLICY_BOOST = float(ROUTINE_CHANGE_CONFIG.get("policy_boost", 0.05))
ROUTINE_CHANGE_MAX_CHANCE = float(ROUTINE_CHANGE_CONFIG.get("max_chance", 0.45))
NEWS_CONFIG = CONFIG.get("news", {})
NEWS_ENABLED = bool(NEWS_CONFIG.get("enabled", False))
NEWS_SOURCES_PATH = NEWS_CONFIG.get("sources_path", "news_source.md")
NEWS_DAILY_CHANCE = float(NEWS_CONFIG.get("daily_chance", 0.5))
NEWS_MAX_READS_PER_DAY = int(NEWS_CONFIG.get("max_reads_per_day", 1))
NEWS_CACHE_PATH = NEWS_CONFIG.get("cache_path", "news_cache.json")
NEWS_USE_CACHE_FIRST = bool(NEWS_CONFIG.get("use_cache_first", True))
INFO_SEEK_CONFIG = NEWS_CONFIG.get("info_seek", NEWS_CONFIG.get("curiosity_search", {}))
INFO_SEEK_ENABLED = bool(INFO_SEEK_CONFIG.get("enabled", True))
INFO_SEEK_BASE_CHANCE = float(INFO_SEEK_CONFIG.get("base_daily_chance", 0.55))
INFO_SEEK_MAX_PER_DAY = int(INFO_SEEK_CONFIG.get("max_seeks_per_day", INFO_SEEK_CONFIG.get("max_searches_per_day", 3)))
DAILY_PLANNING_CONFIG = CONFIG.get("daily_planning", {})
DAILY_PLAN_ANCHOR_MINUTES = max(1, int(DAILY_PLANNING_CONFIG.get("anchor_minutes", 30)))
DAILY_PLAN_RANDOM_DELAY_MAX_MINUTES = max(0, int(DAILY_PLANNING_CONFIG.get("random_delay_max_minutes", 10)))

# =========================================================
# 政策事件
# =========================================================
POLICY_EVENTS = CONFIG["policy_events"]

# =========================================================
# Profile 解析
# =========================================================
def load_profile_from_md(agent_id):
    with open(MD_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    pattern = rf"## Profile {agent_id:02d}｜.*?(?=\n## Profile |\Z)"
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError(f"Profile {agent_id} not found")
    return match.group(0)

def parse_profile(block):
    def _extract(pattern, default=""):
        match = re.search(pattern, block)
        return match.group(1) if match else default

    p = {}
    p["name"] = _extract(r"## Profile \d+｜(.+)")
    base = _extract(r"\*\*基础信息\*\*：(.+)")
    p["age"] = int(re.search(r"(\d+)岁", base).group(1))
    p["living"] = re.search(r"居住(?:于)?(.+?)[，。]", base).group(1)
    p["job"] = _extract(r"\*\*职业与工作节奏\*\*：(.+)")
    p["personality"] = _extract(r"\*\*性格与情绪特征\*\*：(.+)")
    p["daily_life"] = _extract(r"\*\*日常生活与生活习惯\*\*：(.+)")
    p["values"] = _extract(r"\*\*价值观与公共事务态度\*\*：(.+)")
    p["work_style"] = p["job"]
    return p

def build_agent(agent_id, df, city_map=None):
    row = df[df["id"] == agent_id].iloc[0]
    text = parse_profile(load_profile_from_md(agent_id))
    agent = {
        "id": agent_id,
        **text,
        "gender": row.get("gender", ""),
        "hukou": row.get("hukou", ""),
        "residence": row.get("residence", ""),
        "state": {
            "emotion": float(row["emotion"]),
            "stress": float(row["stress"]),
            "econ_security": float(row["econ_security"]),
            "city_identity": float(row["city_identity"]),
            "policy_sensitivity": float(row.get("policy_sensitivity", 0.5)),
            "platform_dependence": float(row.get("platform_dependence", 0.5)),
            "risk_preference": float(row.get("risk_preference", 0.5)),
            "voice_propensity": float(row.get("voice_propensity", 0.5)),
            "mobility_intent": float(row.get("mobility_intent", 0.5)),
        },
        "memory": [],
        "social_neighbors": []
    }
    if city_map is None:
        city_map = load_city_map(MAP_PATH)
    init_agent_locations(agent, city_map)
    return agent

def print_agent_profiles(agent_ids):
    print("\n================= Agent Profiles =================")
    for agent_id in agent_ids:
        try:
            block = load_profile_from_md(agent_id)
        except ValueError as exc:
            print(f"⚠️ {exc}")
            continue
        print(block.strip())
        print()

# =========================================================
# 社交网络构建（核心新增）
# =========================================================
def build_social_network(agents, avg_degree=6, p_cross=0.15):
    groups = defaultdict(list)

    for a in agents:
        age_group = a["age"] // 10 * 10
        job_key = a["job"][:6]
        groups[f"{job_key}_{age_group}"].append(a["id"])

    network = {a["id"]: set() for a in agents}
    all_ids = [a["id"] for a in agents]

    # 组内连接
    for members in groups.values():
        for a in members:
            others = [m for m in members if m != a]
            k = min(len(others), avg_degree)
            for b in random.sample(others, k=k) if others else []:
                network[a].add(b)
                network[b].add(a)

    # 跨组弱连接
    for a in all_ids:
        if random.random() < p_cross:
            b = random.choice(all_ids)
            if b != a:
                network[a].add(b)
                network[b].add(a)

    return {k: list(v) for k, v in network.items()}

# =========================================================
# Map & Location
# =========================================================
def load_city_map(map_path):
    if not os.path.exists(map_path):
        return {}
    hubs = {}
    current_hub = None
    with open(map_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            hub_match = re.match(r"-\s*Hub:\s*(.+)", line)
            if hub_match:
                current_hub = hub_match.group(1).strip()
                hubs.setdefault(current_hub, [])
                continue
            nearby_match = re.match(r"-\s*Nearby:\s*(.+)", line)
            if nearby_match and current_hub:
                hubs[current_hub].append(nearby_match.group(1).strip())
    return hubs

def load_city_map_text(map_path):
    if not os.path.exists(map_path):
        return ""
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""

def _all_locations(city_map):
    locs = []
    for hub, nearby in city_map.items():
        locs.append(hub)
        locs.extend(nearby)
    return list(dict.fromkeys(locs))

def _pick_first_available(candidates, location_set):
    for c in candidates:
        if c in location_set:
            return c
    return None

def _infer_workplace(agent, location_set):
    profile_blob = " ".join([
        agent.get("job", ""),
        agent.get("personality", ""),
        agent.get("daily_life", ""),
        agent.get("values", "")
    ])
    if any(k in profile_blob for k in ["学生", "硕士", "博士", "学校", "上课", "老师", "教师", "教育"]):
        return _pick_first_available(
            ["Riverside Middle School", "Riverside Primary School", "Little River Daycare"],
            location_set
        )
    if any(k in profile_blob for k in ["医院", "医生", "护士", "医疗", "诊所"]):
        return _pick_first_available(
            ["Riverside Community Hospital", "Northside Family Clinic"],
            location_set
        )
    if any(k in profile_blob for k in ["研发", "工程", "技术", "程序", "互联网", "算法", "产品", "数据"]):
        return _pick_first_available(
            ["Hangzhou Tech Labs", "RnD Center", "Admin Office"],
            location_set
        )
    if any(k in profile_blob for k in ["银行", "金融", "证券", "财务"]):
        return _pick_first_available(
            ["Riverside Bank Branch"],
            location_set
        )
    if any(k in profile_blob for k in ["物流", "仓储", "配送", "快递"]):
        return _pick_first_available(
            ["Riverside Logistics", "Warehouse A", "Warehouse B"],
            location_set
        )
    if any(k in profile_blob for k in ["设计", "工作室"]):
        return _pick_first_available(
            ["Willow Design Studio"],
            location_set
        )
    if any(k in profile_blob for k in ["警察", "公安", "消防"]):
        return _pick_first_available(
            ["Riverside Police Station", "Riverside Fire Station"],
            location_set
        )
    return _pick_first_available(
        ["C-01 (Village Center)", "Riverside Night Market", "Market St"],
        location_set
    )

def _infer_home(agent, location_set):
    candidates = ["Central Block", "North Block", "South Block"]
    home = _pick_first_available(candidates, location_set)
    if home:
        return home
    return random.choice(list(location_set)) if location_set else "Home"

def assign_agent_locations(agent, city_map):
    location_set = set(_all_locations(city_map))
    home = _infer_home(agent, location_set)
    workplace = _infer_workplace(agent, location_set) or home
    return {
        "home": home,
        "workplace": workplace,
        "current": home,
    }

def init_agent_locations(agent, city_map):
    cached_locations = load_agent_locations(agent["id"]) if STATEFUL else {}
    if cached_locations:
        agent["locations"] = cached_locations
        agent["locations"].setdefault("current", agent["locations"].get("home", "Home"))
        return agent["locations"]
    agent["locations"] = assign_agent_locations(agent, city_map)
    if STATEFUL:
        save_agent_locations(agent["id"], agent["locations"])
    return agent["locations"]

def resolve_location(agent, activity, time_str, city_map):
    location_set = set(_all_locations(city_map))
    home = agent["locations"].get("home", "Home")
    work = agent["locations"].get("workplace", home)
    current = agent["locations"].get("current", home)

    def pick_any(candidates):
        choice = _pick_first_available(candidates, location_set)
        return choice or home

    def _time_to_minutes(t):
        if not re.match(r"^\d{2}:\d{2}$", str(t)):
            return None
        hh, mm = t.split(":")
        return int(hh) * 60 + int(mm)

    def _profile_flags(a):
        profile_blob = " ".join([
            a.get("job", ""),
            a.get("personality", ""),
            a.get("daily_life", ""),
            a.get("values", ""),
            a.get("work_style", ""),
        ])
        is_student = any(k in profile_blob for k in ["学生", "硕士", "博士", "课题组", "上课", "学习"])
        is_retired = any(k in profile_blob for k in ["退休", "无业", "待业", "失业", "家庭主妇", "家庭主夫", "已退休"])
        late_schedule = any(k in profile_blob for k in ["夜间活跃", "晚睡", "作息偏晚"])
        overtime = "加班" in a.get("work_style", "")
        return is_student, is_retired, late_schedule, overtime

    def _public_pool():
        keywords = ["Park", "Cinema", "Market", "Library", "Community", "Center", "Riverwalk",
                    "Grove", "Playground", "Fitness", "Picnic", "Pocket", "Night Market"]
        pool = [loc for loc in location_set if any(k in loc for k in keywords)]
        if not pool:
            pool = [loc for loc in location_set if loc not in {home, work}]
        return pool

    def _time_bias():
        minutes = _time_to_minutes(time_str)
        is_student, is_retired, late_schedule, overtime = _profile_flags(agent)
        if minutes is None:
            return {"home": 0.4, "work": 0.3, "public": 0.3, "current": 0.2}
        if late_schedule:
            minutes = (minutes - 60) % (24 * 60)

        if minutes >= 22 * 60 or minutes < 6 * 60:
            base = {"home": 0.75, "work": 0.05, "public": 0.2, "current": 0.25}
        elif minutes < 9 * 60:
            base = {"home": 0.45, "work": 0.2, "public": 0.35, "current": 0.25}
        elif minutes < 17 * 60 + 30:
            if is_retired:
                base = {"home": 0.45, "work": 0.15, "public": 0.4, "current": 0.25}
            elif is_student:
                base = {"home": 0.2, "work": 0.55, "public": 0.25, "current": 0.2}
            else:
                base = {"home": 0.2, "work": 0.6, "public": 0.2, "current": 0.2}
        else:
            base = {"home": 0.55, "work": 0.1, "public": 0.35, "current": 0.25}
            if overtime:
                base["work"] += 0.1
                base["home"] -= 0.05
        s = agent.get("state", {})
        mobility = s.get("mobility_intent", 0.5)
        stress = s.get("stress", 0.5)
        if mobility > 0.65:
            base["public"] += 0.1
            base["home"] -= 0.05
        if mobility < 0.35:
            base["home"] += 0.1
            base["public"] -= 0.05
        if stress > 0.7:
            base["home"] += 0.08
            base["public"] -= 0.05
        return base

    def _weighted_pick(candidate_weights):
        if not candidate_weights:
            return home
        items = list(candidate_weights.items())
        locs, weights = zip(*items)
        return random.choices(locs, weights=weights, k=1)[0]

    def _add_weight(weights, loc, w):
        if not loc or w <= 0:
            return
        if loc not in location_set:
            return
        weights[loc] = weights.get(loc, 0) + w

    if any(k in activity for k in ["通勤"]):
        return pick_any(["Riverside Bus Station", "Riverside Ave", "Bridge Rd", "Market St"])

    activity_candidates = []
    if any(k in activity for k in ["工作", "上班", "加班"]):
        activity_candidates.append(work)
    if any(k in activity for k in ["学习", "上课", "实验"]):
        activity_candidates += ["Riverside Middle School", "Riverside Primary School", "Hangzhou Tech Labs"]
    if any(k in activity for k in ["看病", "医院", "诊所"]):
        activity_candidates += ["Riverside Community Hospital", "Northside Family Clinic", "Willow Pharmacy"]
    if any(k in activity for k in ["晨练", "散步", "运动", "健身", "锻炼"]):
        activity_candidates += ["Riverside Park", "Willow Grove Park", "Fitness Area", "Playground"]
    if any(k in activity for k in ["买菜", "购物", "市场"]):
        activity_candidates += ["Market St", "Riverside Supermart", "Riverside Night Market", "Corner Mart"]
    if any(k in activity for k in ["电影", "娱乐", "休闲"]):
        activity_candidates += ["Riverside Cinema", "Riverside Park"]

    weights = {}
    bias = _time_bias()
    _add_weight(weights, home, bias["home"])
    _add_weight(weights, work, bias["work"])
    _add_weight(weights, current, bias["current"])

    public_pool = _public_pool()
    if public_pool:
        for loc in random.sample(public_pool, k=min(2, len(public_pool))):
            _add_weight(weights, loc, bias["public"])

    for loc in activity_candidates:
        _add_weight(weights, loc, 1.2)

    if any(k in activity for k in ["午饭", "晚饭", "吃饭"]):
        if time_str <= "10:30":
            _add_weight(weights, home, 0.6)
        _add_weight(weights, "Market St", 0.8)
        _add_weight(weights, "Riverside Night Market", 0.8)
        _add_weight(weights, "Riverside Supermart", 0.6)

    if any(k in activity for k in ["吃早饭", "睡前", "午休", "休息", "个人时间"]):
        _add_weight(weights, home, 0.8)

    choice = _weighted_pick(weights)
    return choice or home

# =========================================================
# Schedule & Action
# =========================================================
def _extract_json_array_block(text):
    block_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    if block_match:
        return block_match.group(1)
    inline_match = re.search(r"\[.*\]", text, re.S)
    return inline_match.group(0) if inline_match else ""

def _parse_schedule(text):
    json_blob = _extract_json_array_block(text)
    if not json_blob:
        return []
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    schedule = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            time_str, activity = item
        elif isinstance(item, dict) and "time" in item and "activity" in item:
            time_str, activity = item["time"], item["activity"]
        else:
            continue
        time_str = str(time_str).strip()
        activity = str(activity).strip()
        if re.match(r"^\d{2}:\d{2}$", time_str) and activity:
            schedule.append((time_str, activity))
    if not schedule:
        return []
    seen = set()
    cleaned = []
    for time_str, activity in schedule:
        if time_str in seen:
            continue
        seen.add(time_str)
        cleaned.append((time_str, activity))
    return cleaned

def _heuristic_schedule(agent):
    profile_blob = " ".join([
        agent.get("job", ""),
        agent.get("personality", ""),
        agent.get("daily_life", ""),
        agent.get("values", "")
    ])

    is_student = any(k in profile_blob for k in ["学生", "硕士", "博士", "课题组"])
    is_retired = any(k in profile_blob for k in ["退休", "无业", "待业", "失业", "家庭主妇", "家庭主夫"])
    late_schedule = any(k in profile_blob for k in ["夜间活跃", "晚睡", "作息偏晚"])

    if is_retired:
        base = [
            ("07:30", "晨练"),
            ("08:30", "吃早饭"),
            ("10:00", "买菜"),
            ("11:30", "午饭"),
            ("13:00", "午休"),
            ("16:00", "散步"),
            ("18:00", "晚饭"),
            ("20:00", "个人时间"),
            ("22:30", "睡前"),
        ]
        return base

    if is_student:
        base = [
            ("09:30", "吃早饭"),
            ("10:00", "上午学习"),
            ("12:00", "午饭"),
            ("14:00", "下午学习"),
            ("18:00", "下课"),
            ("20:30", "个人时间"),
            ("00:30", "睡前"),
        ]
        return base

    if late_schedule:
        base = [
            ("09:30", "吃早饭"),
            ("10:30", "通勤"),
            ("11:00", "上午工作"),
            ("12:30", "午饭"),
            ("14:30", "下午工作"),
        ]
        base += [("19:30", "加班" if "加班" in agent["work_style"] else "下班")]
        base += [("22:00", "个人时间"), ("01:00", "睡前")]
        return base

    base = [
        ("08:00", "吃早饭"),
        ("09:00", "通勤"),
        ("10:00", "上午工作"),
        ("12:00", "午饭"),
        ("14:00", "下午工作"),
    ]
    base += [("18:30", "加班" if "加班" in agent["work_style"] else "下班")]
    base += [("21:00", "个人时间"), ("23:30", "睡前")]
    return base

def _schedule_profile_flags(agent):
    profile_blob = " ".join([
        agent.get("job", ""),
        agent.get("personality", ""),
        agent.get("daily_life", ""),
        agent.get("values", ""),
        agent.get("work_style", ""),
    ])
    is_student = any(k in profile_blob for k in ["学生", "硕士", "博士", "课题组", "上课", "学习"])
    is_retired = any(k in profile_blob for k in ["退休", "无业", "待业", "失业", "家庭主妇", "家庭主夫", "已退休"])
    late_schedule = any(k in profile_blob for k in ["夜间活跃", "晚睡", "作息偏晚"])
    overtime = "加班" in agent.get("work_style", "")
    return is_student, is_retired, late_schedule, overtime

def ensure_sleep_in_schedule(agent, schedule):
    if any(is_sleep_activity(activity) for _, activity in schedule):
        return schedule
    is_student, is_retired, late_schedule, _ = _schedule_profile_flags(agent)
    if is_retired:
        sleep_time = "22:30"
    elif is_student:
        sleep_time = "00:30"
    elif late_schedule:
        sleep_time = "01:00"
    else:
        sleep_time = "23:30"

    used_times = {t for t, _ in schedule}
    sleep_minutes = _time_str_to_minutes(sleep_time)
    if sleep_minutes is None:
        sleep_minutes = 23 * 60 + 30
    max_minutes = max((_time_str_to_minutes(t) for t in used_times if _time_str_to_minutes(t) is not None), default=None)
    if max_minutes is not None and max_minutes >= sleep_minutes:
        sleep_minutes = min(max_minutes + 60, 23 * 60 + 59)
    candidate = _minutes_to_time_str(sleep_minutes)
    if candidate in used_times:
        for _ in range(48):
            sleep_minutes = (sleep_minutes + 30) % (24 * 60)
            candidate = _minutes_to_time_str(sleep_minutes)
            if candidate not in used_times:
                break

    schedule = list(schedule) + [(candidate, "睡前")]
    schedule.sort(key=lambda x: _time_str_to_minutes(x[0]) or 0)
    return schedule

def _schedule_times(schedule):
    return [t for t, _ in schedule]

def _is_strictly_increasing_times(schedule):
    minutes = []
    for t, _ in schedule:
        m = _time_str_to_minutes(t)
        if m is None:
            return False
        minutes.append(m)
    return all(a < b for a, b in zip(minutes, minutes[1:]))

def _round_to_anchor(minutes, anchor_step=30):
    step = max(1, int(anchor_step))
    return int(round(minutes / step) * step)

def _align_daily_planning_start_time(schedule, anchor_step=30, max_delay=10, min_gap=20):
    if not schedule:
        return []
    minute_points = [_time_str_to_minutes(t) for t, _ in schedule]
    if any(m is None for m in minute_points):
        return list(schedule)

    start_idx = 0
    for idx, (_, activity) in enumerate(schedule):
        if not is_sleep_activity(activity):
            start_idx = idx
            break

    anchor = _round_to_anchor(minute_points[start_idx], anchor_step=anchor_step)
    target = min(23 * 60 + 59, anchor + random.randint(0, max(0, int(max_delay))))

    lower_bound = 0
    if start_idx > 0:
        lower_bound = minute_points[start_idx - 1] + max(1, int(min_gap))
    upper_bound = 23 * 60 + 59
    if start_idx + 1 < len(minute_points):
        upper_bound = minute_points[start_idx + 1] - max(1, int(min_gap))

    if upper_bound < lower_bound:
        return list(schedule)
    minute_points[start_idx] = max(lower_bound, min(target, upper_bound))
    return [(_minutes_to_time_str(m), act) for m, (_, act) in zip(minute_points, schedule)]

def _jitter_schedule_times(base_schedule, max_shift=45, min_gap=20):
    if not base_schedule:
        return []
    base_minutes = [_time_str_to_minutes(t) for t, _ in base_schedule]
    if any(m is None for m in base_minutes):
        return list(base_schedule)
    adjusted_minutes = []
    prev = None
    for m in base_minutes:
        shift = random.randint(-max_shift, max_shift)
        target = m + shift
        if prev is None:
            target = max(0, target)
        else:
            target = max(prev + min_gap, target)
        target = min(target, 23 * 60 + 59)
        adjusted_minutes.append(target)
        prev = target
    adjusted = [(_minutes_to_time_str(m), act) for m, (_, act) in zip(adjusted_minutes, base_schedule)]
    return adjusted

def normalize_schedule_to_base(base_schedule, candidate_schedule):
    if not base_schedule:
        return candidate_schedule
    if not candidate_schedule:
        return base_schedule
    base_times = [t for t, _ in base_schedule]
    candidate_by_time = {t: a for t, a in candidate_schedule}
    normalized = []
    for t, base_act in base_schedule:
        act = candidate_by_time.get(t, base_act)
        normalized.append((t, act))
    return normalized

def normalize_flexible_schedule(base_schedule, candidate_schedule):
    if not candidate_schedule or not base_schedule:
        return None
    if len(candidate_schedule) != len(base_schedule):
        return None
    sorted_candidate = sorted(candidate_schedule, key=lambda x: _time_str_to_minutes(x[0]) or 0)
    if not _is_strictly_increasing_times(sorted_candidate):
        return None
    return sorted_candidate

def generate_daily_routine(agent, base_schedule, day=None):
    if not base_schedule:
        return base_schedule
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    base_text = json.dumps(
        [{"time": t, "activity": a} for t, a in base_schedule],
        ensure_ascii=False,
        indent=2,
    )
    memory_hits = retrieve_relevant_memories(agent, "日程安排 今日计划", max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    intent_hint = intention_text(agent.get("intentions")) if HUMAN_REALISM_ENABLED else "无"
    prompt = f"""
你是城市生活模拟器的“今日日程”制定器。请基于角色资料与基础日程，生成今天的日程。
角色资料：
{profile_text}
基础日程（作为框架，可在时间点上做 0-60 分钟内的微调）：
{base_text}
可参考的近期记忆：{memory_hint}
今日行为意图：{intent_hint}
要求：
1) 输出 JSON 数组，每项为 ["HH:MM","活动"] 或 {{"time":"HH:MM","activity":"活动"}}。
2) 时间点需保持顺序，可在基础时间上做小幅调整（0-60 分钟），不要大幅偏离。
3) 必须包含“睡前/睡觉/睡眠”类活动，并给出具体时间。
4) 仅输出 JSON，不要其他文字。
"""
    response = call_llm(prompt, task="daily_routine", agent_id=agent["id"])
    schedule = _parse_schedule(response)
    normalized = normalize_flexible_schedule(base_schedule, schedule)
    if normalized:
        if _schedule_times(normalized) == _schedule_times(base_schedule):
            normalized = _jitter_schedule_times(base_schedule)
        normalized = ensure_sleep_in_schedule(agent, normalized)
        return _align_daily_planning_start_time(
            normalized,
            anchor_step=DAILY_PLAN_ANCHOR_MINUTES,
            max_delay=DAILY_PLAN_RANDOM_DELAY_MAX_MINUTES,
        )
    jittered = _jitter_schedule_times(base_schedule)
    jittered = ensure_sleep_in_schedule(agent, jittered)
    return _align_daily_planning_start_time(
        jittered,
        anchor_step=DAILY_PLAN_ANCHOR_MINUTES,
        max_delay=DAILY_PLAN_RANDOM_DELAY_MAX_MINUTES,
    )

def generate_schedule(agent):
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    memory_hits = retrieve_relevant_memories(agent, "日程安排", max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    prompt = f"""
你是城市生活模拟器的日程生成器。请基于角色资料生成一天日程安排。
角色资料：
{profile_text}
可参考的近期记忆：{memory_hint}
要求：
1) 输出 JSON 数组，每项为 ["HH:MM","活动"] 或 {{"time":"HH:MM","activity":"活动"}}。
2) 6-10 项，时间升序覆盖早中晚，活动为中文短语。
3) 必须包含“睡前/睡觉/睡眠”类活动，并给出具体时间。
4) 若角色为退休/无业/待业/失业/家庭主妇/家庭主夫/已退休，不出现“工作/通勤/上班/加班”等活动。
5) 若角色为学生，优先出现“上课/学习/实验”等活动；若作息偏晚，适度延后。
6) 仅输出 JSON，不要其他文字。
"""
    response = call_llm(prompt, task="schedule", agent_id=agent["id"])
    schedule = _parse_schedule(response)
    if schedule:
        return ensure_sleep_in_schedule(agent, schedule)
    return ensure_sleep_in_schedule(agent, _heuristic_schedule(agent))

def _extract_json_block(text):
    block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if block_match:
        return block_match.group(1)
    inline_match = re.search(r"\{.*\}", text, re.S)
    return inline_match.group(0) if inline_match else ""

def _parse_schedule_change(text):
    json_blob = _extract_json_block(text)
    if not json_blob:
        return {}
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    change = raw.get("change")
    if isinstance(change, str):
        change = change.strip().lower() in ("true", "yes", "y", "1", "是", "需要", "改变", "变更")
    change = bool(change)
    activity = str(raw.get("activity", "")).strip()
    reason = str(raw.get("reason", "")).strip()
    return {"change": change, "activity": activity, "reason": reason}

def _routine_change_probability(agent, env_events, policy_desc):
    if not ROUTINE_CHANGE_ENABLED:
        return 0.0
    prob = ROUTINE_CHANGE_BASE_CHANCE
    if env_events:
        prob += ROUTINE_CHANGE_EVENT_BOOST * len(env_events)
    if policy_desc:
        prob += ROUTINE_CHANGE_POLICY_BOOST
    s = agent.get("state", {})
    stress = float(s.get("stress", 0.5))
    emotion = float(s.get("emotion", 0.5))
    if stress > 0.6:
        prob += (stress - 0.6) * 0.3
    if emotion < 0.4:
        prob += (0.4 - emotion) * 0.25
    return float(max(0.0, min(prob, ROUTINE_CHANGE_MAX_CHANCE)))

def maybe_adjust_activity(agent, time_str, scheduled_activity, perception_text, plan_text,
                          env_context, env_events, policy_desc):
    prob = _routine_change_probability(agent, env_events, policy_desc)
    if prob <= 0 or random.random() > prob:
        return scheduled_activity, "", False

    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    state = agent.get("state", {})
    state_text = (
        f"emotion={state.get('emotion', 0.5):.2f}, "
        f"stress={state.get('stress', 0.5):.2f}, "
        f"econ_security={state.get('econ_security', 0.5):.2f}, "
        f"risk_preference={state.get('risk_preference', 0.5):.2f}"
    )
    prompt = f"""
你是城市生活模拟器的“临时改程”决策器。
当前时间：{time_str}
原计划活动：{scheduled_activity}
角色资料：
{profile_text}
当前状态数值：{state_text}
当前感知：{perception_text}
当前计划：{plan_text}
环境事件：{env_context if env_context else "无"}
政策事件：{policy_desc if policy_desc else "无"}

请判断是否需要因个人意愿或环境/事件影响而临时更改该时段活动。
要求：
1) 仅输出 JSON：{{"change": true/false, "activity": "活动", "reason": "原因"}}。
2) 若不改变，change=false，activity 可留空。
3) 若改变，activity 为中文短语（2-8字），能合理反映动机与情境。
4) 不要输出其他文字。
"""
    response = call_llm(prompt, task="routine_change", agent_id=agent["id"])
    parsed = _parse_schedule_change(response)
    if not parsed:
        return scheduled_activity, "", False
    if not parsed.get("change"):
        return scheduled_activity, parsed.get("reason", ""), False
    activity = parsed.get("activity", "").strip()
    if not activity or activity == scheduled_activity:
        return scheduled_activity, parsed.get("reason", ""), False
    return activity, parsed.get("reason", ""), True

def _parse_action_space(text, activities):
    json_blob = _extract_json_block(text)
    if not json_blob:
        return {}
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    action_space = {}
    for activity in activities:
        acts = raw.get(activity, [])
        if not isinstance(acts, list):
            continue
        cleaned = [str(a).strip() for a in acts if str(a).strip()]
        if cleaned:
            action_space[activity] = cleaned
    return action_space

def _parse_location_bias(text, activities):
    json_blob = _extract_json_block(text)
    if not json_blob:
        return {}
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    bias_map = {}
    for activity in activities:
        item = raw.get(activity, {})
        if not isinstance(item, dict):
            continue
        prefer = item.get("prefer", [])
        avoid = item.get("avoid", [])
        if not isinstance(prefer, list):
            prefer = []
        if not isinstance(avoid, list):
            avoid = []
        cleaned_prefer = [str(a).strip() for a in prefer if str(a).strip()]
        cleaned_avoid = [str(a).strip() for a in avoid if str(a).strip()]
        if cleaned_prefer or cleaned_avoid:
            bias_map[activity] = {
                "prefer": cleaned_prefer,
                "avoid": cleaned_avoid,
            }
    return bias_map

def _parse_policy_effect(text):
    json_blob = _extract_json_block(text)
    if not json_blob:
        return {}
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    allowed = {
        "emotion",
        "stress",
        "econ_security",
        "city_identity",
        "policy_sensitivity",
        "platform_dependence",
        "risk_preference",
        "voice_propensity",
        "mobility_intent",
    }
    effect = {}
    for k in allowed:
        if k in raw:
            try:
                effect[k] = float(raw[k])
            except (TypeError, ValueError):
                continue
    return effect

def _llm_generate_actions(agent, activities, seed_actions=None):
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    memory_context = " ".join(activities)
    memory_hits = retrieve_relevant_memories(agent, memory_context, max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    seed_text = ""
    if seed_actions:
        seed_text = f"\n已有动作参考（可改写、扩展、去重）：\n{json.dumps(seed_actions, ensure_ascii=False, indent=2)}"
    prompt = f"""
你是城市生活模拟器的动作生成器。请基于角色资料，为每个活动生成具体动作。
角色资料：
{profile_text}
活动列表：{", ".join(activities)}
可参考的近期记忆：{memory_hint}
要求：
1) 每个活动给出 5-10 个动作，中文短语。
2) 动作要符合角色职业、性格与生活习惯。
3) 仅输出 JSON 对象，键为活动名，值为动作列表，不要输出其他文字。
{seed_text}
"""
    response = call_llm(prompt, task="actions", agent_id=agent["id"])
    action_space = _parse_action_space(response, activities)
    missing = [a for a in activities if a not in action_space]
    if missing:
        retry_prompt = f"""
请只为以下活动补全动作，仍然严格输出 JSON。
角色资料：
{profile_text}
活动列表：{", ".join(missing)}
每个活动 5-10 个动作，中文短语。
"""
        retry_response = call_llm(retry_prompt, task="actions", agent_id=agent["id"])
        retry_actions = _parse_action_space(retry_response, missing)
        for activity, acts in retry_actions.items():
            action_space[activity] = acts
    return action_space

def _llm_generate_location_bias(agent, location, city_map_text, action_space):
    activities = list(action_space.keys())
    if not activities:
        return {}
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    actions_text = json.dumps(action_space, ensure_ascii=False, indent=2)
    prompt = f"""
你是城市生活模拟器的“地点动作偏好”生成器。请基于角色资料、地点与城市地图，
为每个活动在该地点给出“偏好动作/避免动作”。

角色资料：
{profile_text}

地点：{location}

城市地图（完整）：
{city_map_text}

活动与可选动作（仅可从下列动作中选择）：
{actions_text}

要求：
1) 仅输出 JSON 对象，键为活动名，值为对象：{{"prefer":[...], "avoid":[...]}}。
2) prefer/avoid 中的动作必须来自给定动作列表，使用完全一致的动作文本。
3) 每个活动 0-5 个 prefer，0-5 个 avoid，允许为空数组。
4) 不要输出其他文字。
"""
    response = call_llm(prompt, task="location_actions", agent_id=agent["id"])
    return _parse_location_bias(response, activities)

def get_location_action_bias(agent, location, city_map_text, action_space):
    if not city_map_text:
        return {}
    bias_cache = agent.setdefault("location_action_bias", {})
    cached = bias_cache.get(location)
    if isinstance(cached, dict):
        return cached
    bias = _llm_generate_location_bias(agent, location, city_map_text, action_space)
    bias_cache[location] = bias
    save_agent_location_action_bias(agent["id"], bias_cache)
    return bias

def generate_actions(agent, schedule):
    activities = sorted({activity for _, activity in schedule})
    return _llm_generate_actions(agent, activities)

def build_action_space_for_agent(agent, base_actions):
    activities = list(base_actions.keys())
    refined_actions = _llm_generate_actions(agent, activities, seed_actions=base_actions)
    action_space = {k: list(v) for k, v in base_actions.items()}
    for activity, acts in refined_actions.items():
        action_space.setdefault(activity, [])
        for act in acts:
            if act not in action_space[activity]:
                action_space[activity].append(act)
    return action_space

DEFAULT_ACTIONS = {
    "工作": "继续处理手头工作",
    "时间": "发呆",
}

SLEEP_KEYWORDS = ["睡前", "睡觉", "睡眠", "入睡", "就寝"]

def is_sleep_activity(activity):
    return any(k in activity for k in SLEEP_KEYWORDS)

def fallback_action(activity):
    for k, v in DEFAULT_ACTIONS.items():
        if k in activity:
            return v
    return "继续当前活动"

def ensure_action_space_for_activity(agent, action_space, activity):
    if activity in action_space:
        return False
    generated = _llm_generate_actions(agent, [activity])
    acts = generated.get(activity, [])
    if not acts:
        acts = [fallback_action(activity)]
    action_space[activity] = acts
    return True

def choose_action(agent, activity, action_space, context=None, location_bias=None, location=None, time_str=None):
    if is_sleep_activity(activity):
        return "睡觉"
    options = action_space.get(activity, [])

    if not options:
        return fallback_action(activity)

    weights = []
    s = agent["state"]
    recent_actions = []
    memory_hits = []
    if STATEFUL:
        recent_actions = load_recent_actions(agent["id"], max_items=6)
    if context or activity:
        query = context if context else activity
        memory_hits = retrieve_relevant_memories(agent, query, max_items=2)

    bias = (location_bias or {}).get(activity, {})
    prefer_set = set(bias.get("prefer", [])) if isinstance(bias, dict) else set()
    avoid_set = set(bias.get("avoid", [])) if isinstance(bias, dict) else set()
    habits = agent.get("habits", {}) if HUMAN_REALISM_ENABLED else {}
    behavior_cfg = HUMAN_REALISM_CONFIG.get("behavior", {}) if HUMAN_REALISM_ENABLED else {}
    inertia_weight = float(behavior_cfg.get("inertia_weight", 0.25))
    need_weights = behavior_cfg.get("need_weights", {}) if isinstance(behavior_cfg, dict) else {}
    energy_w = float(need_weights.get("energy", 0.45))
    hunger_w = float(need_weights.get("hunger", 0.30))
    social_w = float(need_weights.get("social_need", 0.25))
    context_key = build_context_key(time_str or "", location or "", activity)
    habit_entry = habits.get(context_key, {}) if isinstance(habits, dict) else {}
    preferred_habit_action = str(habit_entry.get("preferred_action", ""))
    habit_strength = float(habit_entry.get("strength", 0.0))
    energy = float(s.get("energy", 0.75))
    hunger = float(s.get("hunger", 0.25))
    social_need = float(s.get("social_need", 0.4))

    for act in options:
        w = 1.0

        # 压力高 → 更可能摸鱼 / 情绪化
        if s["stress"] > 0.7 and any(k in act for k in ["摸鱼", "拖延", "发呆", "胡思乱想"]):
            w += 1.5

        # 情绪低 → 回避型行为
        if s["emotion"] < 0.4 and any(k in act for k in ["刷手机", "放空", "无意识"]):
            w += 1.2

        # 经济安全感高 → 自我提升
        if s["econ_security"] > 0.6 and any(k in act for k in ["读书", "学习", "规划"]):
            w += 0.8

        # 睡前更容易反思
        if activity == "睡前" and "回顾" in act:
            w += 1.0

        # 历史行动偏好：更可能重复近期做过的行为
        if act in recent_actions:
            w += 0.4
        w += _memory_action_bias(act, memory_hits)

        # 地点偏好：同一地点的行为倾向
        if act in prefer_set:
            w += 1.0
        if act in avoid_set:
            w -= 0.6

        # 人类行为惯性与习惯
        if HUMAN_REALISM_ENABLED:
            if act == preferred_habit_action:
                w += habit_strength * 0.9
            if agent.get("last_activity") == activity:
                w += inertia_weight
            if agent.get("last_action") == act:
                w += inertia_weight * 0.6

            # 需求驱动
            if energy < 0.35 and any(k in act for k in ["休息", "放松", "回家", "睡", "午休"]):
                w += (0.35 - energy) * 2.2 * energy_w
            if hunger > 0.65 and any(k in act for k in ["吃", "买菜", "做饭", "餐", "饭"]):
                w += (hunger - 0.65) * 2.2 * hunger_w
            if social_need > 0.65 and any(k in act for k in ["聊天", "联系", "社交", "聚会", "拜访"]):
                w += (social_need - 0.65) * 2.2 * social_w
            if social_need < 0.25 and any(k in act for k in ["独处", "安静", "放空"]):
                w += (0.25 - social_need) * 1.8 * social_w

        weights.append(max(w, 0.01))  # 防止权重为 0

    return random.choices(options, weights=weights, k=1)[0]

# =========================================================
# Policy effect inference
# =========================================================
def infer_event_effect(agent, event_desc, event_type="event"):
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    prompt = f"""
你是城市生活模拟器的影响评估器。请基于事件描述与角色资料，推断该事件对角色状态的短期影响。
角色资料：
{profile_text}
事件类型：{event_type}
事件描述：{event_desc}
要求：
1) 仅输出 JSON 对象，键为 emotion、stress、econ_security、city_identity、policy_sensitivity、
   platform_dependence、risk_preference、voice_propensity、mobility_intent 的子集。
2) 值为 -0.2 到 0.2 的小幅浮点数，正值为提升，负值为下降。
3) 不要输出其他文字。
"""
    response = call_llm(prompt, task="event_effect", agent_id=agent["id"])
    effect = _parse_policy_effect(response)
    if not effect:
        return {}
    for k in effect:
        effect[k] = float(np.clip(effect[k], -0.2, 0.2))
    return effect

# =========================================================
# A. 认知模块（使用社交网络）
# =========================================================
def get_social_context(agent, agents_by_id):
    neighbors = agent["social_neighbors"]
    agent["_recent_social_partners"] = []
    if not neighbors:
        return "今天几乎没有与熟人互动。"
    k = min(3, len(neighbors))
    if HUMAN_REALISM_ENABLED:
        sampled = []
        pool = list(neighbors)
        for _ in range(k):
            weights = [max(0.01, relationship_weight(agent, n)) for n in pool]
            pick = random.choices(pool, weights=weights, k=1)[0]
            sampled.append(pick)
            pool = [n for n in pool if n != pick]
            if not pool:
                break
    else:
        sampled = random.sample(neighbors, k)
    agent["_recent_social_partners"] = sampled
    names = [agents_by_id[n]["name"] for n in sampled]
    return "、".join(names) + "等熟人的近况对你产生影响。"

def perception(agent, time_str, social_context, env_context, policy_event):
    prompt = f"""
你是{agent['name']}。
现在是 {time_str}。
你感知到的社交环境是：{social_context}
自然与社会环境：{env_context if env_context else "无特殊变化"}
政策环境：{policy_event if policy_event else "无特殊变化"}

请描述你此刻对环境、他人和制度的感知。（1-2句）
"""
    return call_llm(prompt, task="perception", agent_id=agent["id"])

def planning(agent, perception_text):
    memory_hits = retrieve_relevant_memories(agent, perception_text, max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    history_hint = "暂无历史"
    if STATEFUL:
        history_blocks = load_recent_log_blocks(agent["id"], max_blocks=2, max_chars=380)
        if history_blocks:
            history_hint = "\n---\n".join(history_blocks)
    intent_hint = intention_text(agent.get("intentions")) if HUMAN_REALISM_ENABLED else "无"
    prompt = f"""
你是{agent['name']}。
你的感知是：{perception_text}
你的近期经验：{memory_hint}
你今天的行为意图：{intent_hint}
你的近期历史片段：
{history_hint}

你此刻的短期计划是什么？（1-2句）
"""
    return call_llm(prompt, task="planning", agent_id=agent["id"])

def reflection(agent, outcome):
    memory_hits = retrieve_relevant_memories(agent, outcome, max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    prompt = f"""
你是{agent['name']}。
刚刚发生的事情是：{outcome}
你的相关记忆：{memory_hint}

你对此有何反思或情绪变化？（1-2句）
"""
    return call_llm(prompt, task="reflection", agent_id=agent["id"])

def _parse_interview(text, questions):
    json_blob = _extract_json_array_block(text)
    if not json_blob:
        return []
    try:
        raw = json.loads(json_blob)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    parsed = []
    for i, item in enumerate(raw):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            q, a = item
        elif isinstance(item, dict):
            q = item.get("question")
            a = item.get("answer")
        else:
            continue
        q = str(q).strip() if q else ""
        a = str(a).strip() if a else ""
        if not q:
            q = questions[i] if i < len(questions) else ""
        if q and a:
            parsed.append({"question": q, "answer": a})
    return parsed

def interview_agent(agent, questions, context=None, max_questions=6):
    if not questions:
        return []
    if isinstance(questions, str):
        questions = [q.strip() for q in questions.splitlines() if q.strip()]
    else:
        questions = [str(q).strip() for q in questions if str(q).strip()]
    if not questions:
        return []
    questions = questions[:max_questions]

    memory_hits = retrieve_relevant_memories(agent, "访谈", max_items=VECTOR_DB_TOP_K)
    memory_hint = _format_memory_hint(memory_hits)
    context_text = context if context else "无"
    question_text = "\n".join(f"- {q}" for q in questions)
    prompt = f"""
你是{agent['name']}。
这是一次访谈，回答要真实且基于角色经历。
背景：{context_text}
你的近期经验：{memory_hint}

请逐题回答以下问题，每题1-3句。
要求：
1) 输出 JSON 数组，每项为 {{"question":"...","answer":"..."}} 或 ["question","answer"]。
2) 仅输出 JSON，不要其他文字。
问题列表：
{question_text}
"""
    response = call_llm(prompt, task="interview", agent_id=agent["id"])
    parsed = _parse_interview(response, questions)
    if parsed:
        return parsed
    fallback = response.strip()
    if not fallback:
        return []
    return [{"question": q, "answer": fallback} for q in questions]

# =========================================================
# 社会影响（情绪扩散）
# =========================================================
def social_influence(agent, agents_by_id):
    neighbors = agent["social_neighbors"]
    if not neighbors:
        return
    if HUMAN_REALISM_ENABLED:
        weights = [max(0.01, relationship_weight(agent, n)) for n in neighbors]
        total = sum(weights)
        if total <= 0:
            avg_emotion = sum(agents_by_id[n]["state"]["emotion"] for n in neighbors) / len(neighbors)
        else:
            avg_emotion = sum(
                agents_by_id[n]["state"]["emotion"] * w for n, w in zip(neighbors, weights)
            ) / total
    else:
        avg_emotion = sum(agents_by_id[n]["state"]["emotion"] for n in neighbors) / len(neighbors)
    agent["state"]["emotion"] += 0.1 * (avg_emotion - agent["state"]["emotion"])

# =========================================================
# 状态更新
# =========================================================
def update_state(agent):
    s = agent["state"]
    s.setdefault("policy_sensitivity", 0.5)
    s.setdefault("platform_dependence", 0.5)
    s.setdefault("risk_preference", 0.5)
    s.setdefault("voice_propensity", 0.5)
    s.setdefault("mobility_intent", 0.5)
    if HUMAN_REALISM_ENABLED:
        s.setdefault("energy", 0.75)
        s.setdefault("hunger", 0.25)
        s.setdefault("social_need", 0.40)

    s["emotion"] += 0.05 * s["econ_security"] - 0.07 * s["stress"] + random.uniform(-0.02, 0.02)
    s["stress"] += 0.03 * (1 - s["econ_security"]) + random.uniform(-0.02, 0.03)
    s["econ_security"] += 0.02 * (1 - s["stress"]) - 0.015 * s["platform_dependence"] + random.uniform(-0.015, 0.02)
    s["city_identity"] += 0.03 * (s["emotion"] - 0.5) - 0.02 * s["mobility_intent"] + random.uniform(-0.01, 0.01)
    s["policy_sensitivity"] += 0.02 * (s["stress"] - 0.5) + random.uniform(-0.01, 0.01)
    s["platform_dependence"] += 0.02 * (1 - s["econ_security"]) + random.uniform(-0.01, 0.01)
    s["risk_preference"] += 0.02 * (s["emotion"] - s["stress"]) + random.uniform(-0.01, 0.01)
    s["voice_propensity"] += 0.02 * (s["city_identity"] - 0.5) + 0.01 * (s["emotion"] - 0.5) + random.uniform(-0.01, 0.01)
    s["mobility_intent"] += 0.03 * (s["stress"] - s["city_identity"]) + random.uniform(-0.01, 0.01)
    if HUMAN_REALISM_ENABLED:
        s["energy"] += random.uniform(-0.01, 0.01)
        s["hunger"] += random.uniform(-0.01, 0.01)
        s["social_need"] += random.uniform(-0.01, 0.01)

    for k in s:
        s[k] = float(np.clip(s[k], 0, 1))

# =========================================================
# B. 长期记忆
# =========================================================
def daily_summary(agent, logs, day=None):
    prompt = f"""
你是{agent['name']}。
这是你今天经历的关键片段：
{logs}

请总结今天最重要的一条经验或感受。
"""
    memory = call_llm(prompt, task="summary", agent_id=agent["id"])
    agent["memory"].append(memory)
    save_agent_memory(agent)
    vector_db_add_entry(agent["id"], "memory", memory, sim_day=day, sim_time="end_of_day")
    return memory

# =========================================================
# C. 主循环
# =========================================================
def validate_action_space(schedules, action_space):
    missing = set()
    if not schedules:
        return

    def iter_action_spaces():
        sample_key = next(iter(action_space.keys()))
        if isinstance(sample_key, int):
            return action_space.items()
        return ((agent_id, action_space) for agent_id in schedules.keys())

    for agent_id, space in iter_action_spaces():
        sch = schedules.get(agent_id, [])
        for _, activity in sch:
            if activity not in space:
                missing.add(activity)
    if missing:
        print("⚠️ 警告：以下活动没有定义动作空间：")
        for m in missing:
            print("  -", m)

def build_schedule_map(schedules):
    sorted_map = {}
    for agent_id, sch in schedules.items():
        sorted_map[agent_id] = sorted(sch, key=lambda x: x[0])
    return sorted_map

def get_activity_for_time(schedule, time_str):
    if not schedule:
        return "个人时间"
    current_minutes = _time_str_to_minutes(time_str)
    if current_minutes is None:
        return schedule[-1][1]
    last_activity = None
    for t, activity in schedule:
        t_minutes = _time_str_to_minutes(t)
        if t_minutes is None:
            continue
        if t_minutes <= current_minutes:
            last_activity = activity
        else:
            break
    return last_activity or "个人时间"

def apply_schedule_override(schedule, time_str, activity):
    if not schedule:
        return [(time_str, activity)]
    updated = [(t, a) for t, a in schedule if t != time_str]
    updated.append((time_str, activity))
    updated.sort(key=lambda x: _time_str_to_minutes(x[0]) or 0)
    return updated

def build_master_timeline(schedules, step_minutes=None):
    if step_minutes:
        times = set(_build_time_grid(step_minutes))
        for sch in schedules.values():
            times.update(t for t, _ in sch)
        return sorted(times)
    times = set()
    for sch in schedules.values():
        times.update(t for t, _ in sch)
    return sorted(times)

def _enforce_memory_model_compat(sim_state):
    if not REQUIRE_CLEAN_RESET_ON_MEMORY_MODEL_CHANGE:
        return
    current_version = sim_state.get("memory_model_version")
    if current_version != MEMORY_MODEL_VERSION:
        raise RuntimeError(
            "Memory model version changed. "
            "Please run `python generative_city_sim.py reset` once, "
            "then rerun simulation."
        )

def run_simulation():
    df = pd.read_csv(CSV_PATH)
    city_map = load_city_map(MAP_PATH)
    city_map_text = load_city_map_text(MAP_PATH)
    hook_bus = HookBus(CONFIG.get("extensions", {}))
    extension_state = {}
    agents = [build_agent(i, df, city_map=city_map) for i in AGENT_IDS]
    if PRINT_AGENT_PROFILE:
        print_agent_profiles([a["id"] for a in agents])
    start_day = 1
    if STATEFUL:
        sim_state = load_sim_state()
        _enforce_memory_model_compat(sim_state)
        # Resume day count for persistent simulations.
        last_day = sim_state.get("last_day", 0)
        if isinstance(last_day, int) and last_day >= 0:
            start_day = last_day + 1
    if STATEFUL:
        for agent in agents:
            agent["memory"] = load_agent_memory(agent["id"])
            seed_vector_db_from_memory(agent)
            if HUMAN_REALISM_ENABLED:
                agent["episodes"] = load_agent_episodes(agent["id"])
                agent["habits"] = load_agent_habits(agent["id"])
                agent["intentions"] = load_agent_intentions(agent["id"])
                agent["relationships"] = load_agent_relationships(agent["id"])
                state = agent.setdefault("state", {})
                state.setdefault("energy", 0.75)
                state.setdefault("hunger", 0.25)
                state.setdefault("social_need", 0.40)
                agent.setdefault("last_activity", "")
                agent.setdefault("last_action", "")
    else:
        for agent in agents:
            agent["memory"] = []
            reset_agent_memory(agent["id"])
            if HUMAN_REALISM_ENABLED:
                agent["episodes"] = []
                agent["habits"] = {}
                agent["intentions"] = {}
                agent["relationships"] = {}
                state = agent.setdefault("state", {})
                state.setdefault("energy", 0.75)
                state.setdefault("hunger", 0.25)
                state.setdefault("social_need", 0.40)
                agent.setdefault("last_activity", "")
                agent.setdefault("last_action", "")
    agents_by_id = {a["id"]: a for a in agents}
    agent_names = {a["id"]: a.get("name", str(a["id"])) for a in agents}
    state_metrics = list(agents[0]["state"].keys()) if agents else []
    state_history = {
        a["id"]: {
            metric: [] for metric in state_metrics
        }
        for a in agents
    }
    env_system = EnvironmentSystem(CONFIG.get("environment", {}), llm_fn=call_llm)
    background_text = str(BACKGROUND).strip()
    news_sources = load_news_sources(NEWS_SOURCES_PATH) if NEWS_ENABLED else []
    news_cache = []
    if NEWS_ENABLED:
        if news_sources:
            news_cache = update_news_cache(NEWS_CACHE_PATH, news_sources, NEWS_CONFIG)
        else:
            news_cache = load_news_cache(NEWS_CACHE_PATH)
    if NEWS_ENABLED and not news_sources:
        print(f"ℹ️ 未找到新闻源列表或列表为空：{NEWS_SOURCES_PATH}，将主要使用 Web 搜索。")
    if NEWS_ENABLED and not news_cache and NEWS_USE_CACHE_FIRST:
        print(f"ℹ️ 新闻缓存为空或未找到：{NEWS_CACHE_PATH}，将实时抓取网页。")

    # === 构建社交网络 ===
    social_net = build_social_network(agents)
    for a in agents:
        a["social_neighbors"] = social_net[a["id"]]
        if HUMAN_REALISM_ENABLED:
            rel = a.setdefault("relationships", {})
            for n in a["social_neighbors"]:
                key = str(n)
                rel.setdefault(
                    key,
                    {
                        "closeness": 0.5,
                        "trust": 0.5,
                        "last_interaction_day": 0,
                    },
                )

    for a in agents:
        if not a.get("locations"):
            init_agent_locations(a, city_map)
        a["location_action_bias"] = load_agent_location_action_bias(a["id"])
        locs = a.get("locations", {})
        init_loc_line = (
            f"[InitLocation] {a.get('name', a['id'])}: "
            f"home={locs.get('home', 'Home')} "
            f"work={locs.get('workplace', locs.get('home', 'Home'))} "
            f"current={locs.get('current', locs.get('home', 'Home'))}\n"
        )
        print(init_loc_line.strip())
        append_agent_log(a, init_loc_line)

    schedules = {}
    actions = {}
    for a in agents:
        agent_id = a["id"]
        cached_schedule = load_agent_schedule(agent_id)
        if cached_schedule:
            ensured = ensure_sleep_in_schedule(a, cached_schedule)
            schedules[agent_id] = ensured
            if ensured != cached_schedule and STATEFUL:
                save_agent_schedule(agent_id, ensured)
        else:
            # Generate schedule once per agent unless cache exists.
            schedules[agent_id] = generate_schedule(a)
            save_agent_schedule(agent_id, schedules[agent_id])

        cached_actions = load_agent_actions(agent_id)
        if cached_actions:
            actions[agent_id] = cached_actions
        else:
            # Action space is expensive; cache for reuse across runs.
            base_actions = generate_actions(a, schedules[agent_id])
            actions[agent_id] = build_action_space_for_agent(a, base_actions)
            save_agent_actions(agent_id, actions[agent_id])

    # Print each agent's base routine at the beginning of the simulation.
    for agent in agents:
        sch = schedules.get(agent["id"], [])
        lines = [f"{t} {act}" for t, act in sch] if sch else ["(no schedule)"]
        routine_text = "\n".join(lines)
        header = f"\n[BasicRoutine] {agent.get('name', agent['id'])}\n"
        print(header + routine_text)
        append_agent_log(agent, header + routine_text + "\n")

    base_schedule_map = build_schedule_map(schedules)
    validate_action_space(schedules, actions)
    hook_bus.emit(
        "on_simulation_start",
        config=CONFIG,
        agents=agents,
        agents_by_id=agents_by_id,
        city_map=city_map,
        city_map_text=city_map_text,
        schedules=schedules,
        actions=actions,
        extension_state=extension_state,
    )

    for day in range(start_day, start_day + SIM_DAYS):
        print(f"\n================= Day {day} =================")
        daily_logs = defaultdict(str)
        llm_budget_by_agent = {}
        daily_schedules = {}
        daily_routine_texts = {}
        daily_wake_times = {}
        daily_routine_logged = {}
        if HUMAN_REALISM_ENABLED:
            max_extra = int(
                HUMAN_REALISM_CONFIG.get("llm", {}).get("max_extra_calls_per_agent_day", 2)
            )
            for agent in agents:
                agent["current_day"] = day
                budget = {"remaining": max(0, max_extra)}
                llm_budget_by_agent[agent["id"]] = budget
                episodes = sorted(
                    agent.get("episodes", []),
                    key=lambda x: float(x.get("decayed_salience", x.get("salience", 0.0))),
                    reverse=True,
                )
                intentions = build_daily_intentions(
                    agent,
                    episodes,
                    HUMAN_REALISM_CONFIG,
                    budget,
                )
                intentions["day"] = day
                agent["intentions"] = intentions
                if STATEFUL:
                    save_agent_intentions(agent["id"], intentions)
        for agent in agents:
            agent_id = agent["id"]
            daily_schedule = generate_daily_routine(agent, base_schedule_map[agent_id], day=day)
            daily_schedules[agent_id] = daily_schedule
            # Ensure action space covers any new activities in today's routine.
            updated = False
            for _, activity in daily_schedule:
                updated = ensure_action_space_for_activity(agent, actions[agent_id], activity) or updated
            if updated and STATEFUL:
                save_agent_actions(agent_id, actions[agent_id])
            lines = [f"{t} {act}" for t, act in daily_schedule] if daily_schedule else ["(no schedule)"]
            routine_text = "\n".join(lines)
            daily_routine_texts[agent_id] = routine_text
            wake_time = None
            for t, act in daily_schedule:
                if not is_sleep_activity(act):
                    wake_time = t
                    break
            daily_wake_times[agent_id] = wake_time or (daily_schedule[0][0] if daily_schedule else None)
            daily_routine_logged[agent_id] = False

        schedule_map = build_schedule_map(daily_schedules)
        timeline = build_master_timeline(daily_schedules, TIME_STEP_MINUTES)
        sleep_step = SECONDS_PER_DAY / (SIM_DAYS * max(len(timeline), 1))
        info_schedule = {}
        daily_info_seen = defaultdict(set)
        daily_query_seen = defaultdict(set)
        preferred_sites_map = {}
        if NEWS_ENABLED and timeline:
            for agent in agents:
                agent_id = agent["id"]
                preferred_sites = _build_agent_preferred_sites(
                    agent,
                    news_sources=news_sources,
                    news_cache=news_cache,
                    max_sites=int(INFO_SEEK_CONFIG.get("preferred_sites_per_agent", 6)),
                )
                preferred_sites_map[agent_id] = preferred_sites
                agent["preferred_info_sites"] = preferred_sites
                curiosity = _estimate_curiosity(agent)
                if not INFO_SEEK_ENABLED:
                    continue
                daily_chance = min(0.98, INFO_SEEK_BASE_CHANCE * curiosity + 0.05)
                if random.random() > daily_chance:
                    continue
                max_seeks = max(1, int(round(INFO_SEEK_MAX_PER_DAY * curiosity)))
                seeks = min(max_seeks, len(timeline))
                info_schedule[agent_id] = set(random.sample(timeline, k=seeks))

        day_header = f"\n================= Day {day} =================\n"
        for agent in agents:
            daily_logs[agent["id"]] += day_header
            append_agent_log(agent, day_header)
        hook_bus.emit(
            "on_day_start",
            day=day,
            config=CONFIG,
            agents=agents,
            agents_by_id=agents_by_id,
            city_map=city_map,
            city_map_text=city_map_text,
            schedule_map=schedule_map,
            actions=actions,
            timeline=timeline,
            daily_logs=daily_logs,
            extension_state=extension_state,
        )

        for time_str in timeline:
            policy = next((p for p in POLICY_EVENTS if p["day"] == day and p["time"] == time_str), None)
            env_system.tick(day, time_str, agents)
            env_events = env_system.get_events()
            env_context = env_system.get_context_text()
            if background_text:
                env_context = f"背景：{background_text} 当前环境事件：{env_context}"
            hook_bus.emit(
                "on_time_tick",
                day=day,
                time_str=time_str,
                config=CONFIG,
                agents=agents,
                agents_by_id=agents_by_id,
                city_map=city_map,
                city_map_text=city_map_text,
                schedule_map=schedule_map,
                actions=actions,
                daily_logs=daily_logs,
                env_events=env_events,
                env_context=env_context,
                policy=policy,
                extension_state=extension_state,
            )

            for agent in agents:
                agent_id = agent["id"]
                if (
                    not daily_routine_logged.get(agent_id)
                    and daily_wake_times.get(agent_id) == time_str
                ):
                    header = (
                        f"\n[TodayRoutine Day {day}] "
                        f"{agent.get('name', agent_id)} @ {time_str}\n"
                    )
                    routine_text = daily_routine_texts.get(agent_id, "")
                    print(header + routine_text)
                    daily_logs[agent_id] += header + routine_text + "\n"
                    append_agent_log(agent, header + routine_text + "\n")
                    daily_routine_logged[agent_id] = True
                if time_str in info_schedule.get(agent_id, set()):
                    _, info_log, result_url, query = info_seek_and_store(
                        agent,
                        day=day,
                        time_str=time_str,
                        news_cache=news_cache,
                        news_sources=news_sources,
                        preferred_sites=preferred_sites_map.get(agent_id, []),
                        seen_urls=daily_info_seen[agent_id],
                        used_queries=daily_query_seen[agent_id],
                        config=INFO_SEEK_CONFIG,
                    )
                    if query:
                        daily_query_seen[agent_id].add(query)
                    if result_url:
                        daily_info_seen[agent_id].add(result_url)
                    if info_log:
                        print(info_log)
                        daily_logs[agent_id] += info_log
                        append_agent_log(agent, info_log)
                #act = random.choice(actions.get(activity, ["继续当前活动"]))
                scheduled_activity = get_activity_for_time(schedule_map[agent_id], time_str)
                social_context = get_social_context(agent, agents_by_id)

                policy_desc = None
                if policy:
                    policy_desc = policy.get("description") or policy.get("name")
                state_before = dict(agent.get("state", {}))
                step_ctx = {
                    "scheduled_activity": scheduled_activity,
                    "activity": scheduled_activity,
                    "social_context": social_context,
                    "policy_desc": policy_desc,
                }
                hook_bus.emit(
                    "on_agent_pre_step",
                    day=day,
                    time_str=time_str,
                    config=CONFIG,
                    agent=agent,
                    agents=agents,
                    agents_by_id=agents_by_id,
                    city_map=city_map,
                    city_map_text=city_map_text,
                    schedule_map=schedule_map,
                    actions=actions,
                    env_events=env_events,
                    env_context=env_context,
                    policy=policy,
                    step=step_ctx,
                    extension_state=extension_state,
                )
                scheduled_activity = step_ctx.get("scheduled_activity", scheduled_activity)
                social_context = step_ctx.get("social_context", social_context)
                policy_desc = step_ctx.get("policy_desc", policy_desc)
                # Core cognition loop: perceive -> plan -> (maybe) change routine -> act -> reflect.
                perc = perception(agent, time_str, social_context, env_context, policy_desc if policy else None)
                plan = planning(agent, perc)
                activity, change_reason, changed = maybe_adjust_activity(
                    agent,
                    time_str,
                    scheduled_activity,
                    perc,
                    plan,
                    env_context,
                    env_events,
                    policy_desc,
                )
                activity = step_ctx.get("activity", activity)
                if activity != scheduled_activity and not changed:
                    changed = True
                    hook_reason = str(step_ctx.get("change_reason", "")).strip()
                    if hook_reason:
                        change_reason = hook_reason
                if changed:
                    schedule_map[agent_id] = apply_schedule_override(
                        schedule_map[agent_id],
                        time_str,
                        activity,
                    )
                    updated = ensure_action_space_for_activity(agent, actions[agent_id], activity)
                    if updated and STATEFUL:
                        save_agent_actions(agent_id, actions[agent_id])

                location = resolve_location(agent, activity, time_str, city_map)
                agent["locations"]["current"] = location
                location_bias = get_location_action_bias(
                    agent,
                    location,
                    city_map_text,
                    actions[agent_id],
                )
                act = choose_action(
                    agent,
                    activity,
                    actions[agent_id],
                    context=f"{activity} {perc}",
                    location_bias=location_bias,
                    location=location,
                    time_str=time_str,
                )
                outcome = f"在【{activity}】中执行了【{act}】"
                refl = reflection(agent, outcome)
                if HUMAN_REALISM_ENABLED:
                    update_needs(agent, time_str, activity)

                if env_events:
                    for ev in env_events:
                        inferred = infer_event_effect(agent, ev.get("description", ev.get("name", "")), ev.get("type", "event"))
                        for k, v in inferred.items():
                            agent["state"][k] += v

                if policy:
                    inferred = infer_event_effect(agent, policy_desc, "policy")
                    for k, v in inferred.items():
                        agent["state"][k] += v

                social_influence(agent, agents_by_id)
                update_state(agent)
                if HUMAN_REALISM_ENABLED:
                    partners = list(agent.get("_recent_social_partners", []))
                    signal = infer_interaction_signal(refl)
                    for pid in partners:
                        relationship_update(agent, pid, signal, HUMAN_REALISM_CONFIG)
                    state_after = dict(agent.get("state", {}))
                    delta = {}
                    for key, before_v in state_before.items():
                        after_v = state_after.get(key)
                        if isinstance(before_v, (int, float)) and isinstance(after_v, (int, float)):
                            delta[key] = float(after_v) - float(before_v)
                    event_intensity = min(1.0, 0.2 * len(env_events) + (0.2 if policy else 0.0))
                    recent_actions = [
                        e.get("action", "")
                        for e in agent.get("episodes", [])[-20:]
                        if isinstance(e, dict)
                    ]
                    novelty = 1.0 if act not in recent_actions else 0.2
                    priorities = agent.get("intentions", {}).get("priorities", [])
                    goal_relevance = 0.2
                    for p in priorities:
                        if p and (p in activity or p in plan or p in refl):
                            goal_relevance = 0.8
                            break
                    salience = compute_episode_salience(
                        delta.get("stress", 0.0),
                        event_intensity,
                        novelty,
                        goal_relevance,
                    )
                    tags = infer_episode_tags(
                        activity,
                        act,
                        refl,
                        env_events=[ev.get("description", ev.get("name", "")) for ev in env_events],
                        policy_event=policy_desc if policy else "",
                    )
                    episode = {
                        "episode_id": str(uuid.uuid4()),
                        "day": day,
                        "time": time_str,
                        "scheduled_activity": scheduled_activity,
                        "final_activity": activity,
                        "action": act,
                        "location": location,
                        "env_events": [ev.get("description", ev.get("name", "")) for ev in env_events],
                        "policy_event": policy_desc if policy else "",
                        "social_partners": partners,
                        "perception": perc,
                        "plan": plan,
                        "outcome": outcome,
                        "reflection": refl,
                        "state_before": state_before,
                        "state_after": state_after,
                        "delta": delta,
                        "tags": tags,
                        "salience": salience,
                        "valence": float(np.clip(delta.get("emotion", 0.0), -1.0, 1.0)),
                        "created_at_day": day,
                    }
                    agent.setdefault("episodes", []).append(episode)
                    update_habits_from_episode(agent, episode, HUMAN_REALISM_CONFIG)
                    append_agent_episode(agent_id, episode)
                    episode_text = (
                        f"Day {day} {time_str} {activity}/{act} @ {location} "
                        f"tags={','.join(tags)} salience={salience:.2f} reflection={refl}"
                    )
                    vector_db_add_entry(agent_id, "episode", episode_text, sim_day=day, sim_time=time_str)
                    agent["last_activity"] = activity
                    agent["last_action"] = act
                for metric in state_history[agent["id"]]:
                    state_history[agent["id"]][metric].append(agent["state"][metric])

                routine_line = ""
                if changed:
                    reason_text = change_reason or "临时改变"
                    routine_line = f"RoutineChange: {scheduled_activity} -> {activity} ({reason_text})\n"

                log = f"""
[{agent['name']} @ {time_str}]
Scheduled: {scheduled_activity}
Activity: {activity}
{routine_line}Location: {location}
Environment: {env_context}
Perception: {perc}
Plan: {plan}
Action: {act}
Outcome: {outcome}
Reflection: {refl}
"""
                print(log)
                daily_logs[agent["id"]] += log
                append_agent_log(agent, log)
                vector_db_add_entry(agent["id"], "log", log, sim_day=day, sim_time=time_str)
                vector_db_add_entry(agent["id"], "plan", plan, sim_day=day, sim_time=time_str)
                vector_db_add_entry(agent["id"], "reflection", refl, sim_day=day, sim_time=time_str)
                vector_db_add_entry(agent["id"], "action", outcome, sim_day=day, sim_time=time_str)
                step_ctx.update({
                    "perception": perc,
                    "plan": plan,
                    "activity": activity,
                    "action": act,
                    "outcome": outcome,
                    "reflection": refl,
                    "log": log,
                    "changed": changed,
                    "change_reason": change_reason,
                    "location": location,
                })
                hook_bus.emit(
                    "on_agent_post_step",
                    day=day,
                    time_str=time_str,
                    config=CONFIG,
                    agent=agent,
                    agents=agents,
                    agents_by_id=agents_by_id,
                    city_map=city_map,
                    city_map_text=city_map_text,
                    schedule_map=schedule_map,
                    actions=actions,
                    daily_logs=daily_logs,
                    env_events=env_events,
                    env_context=env_context,
                    policy=policy,
                    step=step_ctx,
                    extension_state=extension_state,
                )

            time.sleep(sleep_step)

        for agent in agents:
            if HUMAN_REALISM_ENABLED:
                agent_id = agent["id"]
                budget = llm_budget_by_agent.get(agent_id, {"remaining": 0})
                day_eps = [
                    ep for ep in agent.get("episodes", [])
                    if int(ep.get("day", 0) or 0) == day
                ]
                consolidated = consolidate_day(
                    agent,
                    day,
                    day_eps,
                    HUMAN_REALISM_CONFIG,
                    budget,
                )
                agent["intentions"] = consolidated.get("intentions", agent.get("intentions", {}))
                if STATEFUL:
                    save_agent_intentions(agent_id, agent.get("intentions", {}))
                    save_agent_habits(agent_id, agent.get("habits", {}))
                    save_agent_relationships(agent_id, agent.get("relationships", {}))
                    mem_cfg = dict(HUMAN_REALISM_CONFIG.get("memory", {}))
                    mem_cfg["current_day"] = day
                    prune_and_decay_episodes(agent_id, mem_cfg)
                    agent["episodes"] = load_agent_episodes(agent_id)
                memory_text = consolidated.get("memory_text", "").strip()
                if memory_text:
                    agent["memory"].append(memory_text)
                    save_agent_memory(agent)
                    vector_db_add_entry(agent_id, "memory", memory_text, sim_day=day, sim_time="consolidation")
                    print(f"🧩 {agent['name']} 的经验整合：{memory_text}")
            mem = daily_summary(agent, daily_logs[agent["id"]], day=day)
            print(f"🧠 {agent['name']} 的今日长期记忆：{mem}")
        hook_bus.emit(
            "on_day_end",
            day=day,
            config=CONFIG,
            agents=agents,
            agents_by_id=agents_by_id,
            city_map=city_map,
            city_map_text=city_map_text,
            schedule_map=schedule_map,
            actions=actions,
            daily_logs=daily_logs,
            state_history=state_history,
            extension_state=extension_state,
        )
        if STATEFUL:
            save_sim_state({
                "last_day": day,
                "memory_model_version": MEMORY_MODEL_VERSION,
            })

    print("\n✅ 模拟完成")
    hook_bus.emit(
        "on_simulation_end",
        config=CONFIG,
        agents=agents,
        agents_by_id=agents_by_id,
        city_map=city_map,
        city_map_text=city_map_text,
        schedules=schedules,
        actions=actions,
        state_history=state_history,
        extension_state=extension_state,
    )
    visualize_social_network(agents)
    save_state_history(state_history)
    visualize_agent_state_changes(state_history, agent_names, metrics=state_metrics)


# =========================================================
# 入口
# =========================================================
def _parse_question_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).splitlines() if v.strip()]

def _cli_interview_agent(agent_id, questions, context=None):
    df = pd.read_csv(CSV_PATH)
    city_map = load_city_map(MAP_PATH)
    agent = build_agent(agent_id, df, city_map=city_map)
    if STATEFUL:
        agent["memory"] = load_agent_memory(agent["id"])
        seed_vector_db_from_memory(agent)
    else:
        agent["memory"] = []
    answers = interview_agent(agent, questions, context=context)
    print(json.dumps(answers, ensure_ascii=False, indent=2))

def _build_arg_parser():
    import argparse
    parser = argparse.ArgumentParser(description="GAWorld simulator")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run the full simulation")
    subparsers.add_parser("reset", help="Reset simulation memory/logs/cache")

    interview = subparsers.add_parser("interview", help="Interview a specific agent by ID")
    interview.add_argument("--agent-id", type=int, required=True, help="Agent ID to interview")
    interview.add_argument(
        "--question",
        action="append",
        dest="questions",
        help="Interview question (can be used multiple times)",
    )
    interview.add_argument(
        "--questions-file",
        help="Path to a UTF-8 text file with one question per line",
    )
    interview.add_argument(
        "--context",
        default=None,
        help="Optional background context for the interview",
    )
    return parser

def _load_questions_from_file(path):
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        return []

def _main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.command == "reset":
        reset_simulation()
        print("✅ 已重置模拟：清空记忆、日志与缓存。")
        return

    if args.command == "interview":
        questions = []
        questions.extend(_parse_question_list(args.questions))
        questions.extend(_load_questions_from_file(args.questions_file))
        if not questions:
            parser.error("Provide at least one --question or a --questions-file.")
        _cli_interview_agent(args.agent_id, questions, context=args.context)
        return

    run_simulation()

if __name__ == "__main__":
    _main()
