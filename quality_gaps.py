# quality_gaps.py
# Milestone: "Quality & Gaps"
# - Substance vs Fluff: local metrics (sentence length, data points) + GPT scoring
# - Compare all H2/H3 outlines to find common topics and "missing angles"

import os
import re
import math
import json
from collections import Counter, defaultdict
from typing import List, Dict, Any
from dotenv import load_dotenv
import openai

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# -----------------------
# Helpers
# -----------------------
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')
_NUM_RE = re.compile(r'(?<!\w)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?')   # numbers, 1,234, 12.5, 10%
_DATE_WORDS = re.compile(r'\b(20\d{2}|19\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b', re.I)
_CITATION_RE = re.compile(r'\[(\d+)\]|\b(source|study|report|research|dataset|reference)\b', re.I)
_HEADING_NORM = re.compile(r'[^a-z0-9\s\-]')

def _completion(prompt: str, max_tokens: int = 350, temperature: float = 0.0) -> str:
    return openai.Completion.create(
        model="gpt-4o-mini",
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    ).choices[0].text.strip()

def _words(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())

def _avg(lst: List[float]) -> float:
    return sum(lst)/len(lst) if lst else 0.0

def _norm_heading(h: str) -> str:
    # normalize headings to compare across sites
    h = h or ""
    h = h.strip()
    h = _HEADING_NORM.sub("", h.lower())
    h = re.sub(r"\s+", " ", h).strip()
    return h

# -----------------------
# 1) Local "substance vs fluff" metrics
# -----------------------
def compute_local_quality_metrics(page_text: str) -> Dict[str, Any]:
    text = (page_text or "").strip()
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    sent_lengths = [len(_words(s)) for s in sentences]
    avg_sentence_len = _avg(sent_lengths)
    long_sentence_ratio = sum(1 for n in sent_lengths if n >= 25) / len(sent_lengths) if sent_lengths else 0.0

    # data points: numbers, %, years, months
    nums = _NUM_RE.findall(text)
    dates = _DATE_WORDS.findall(text)
    citations = _CITATION_RE.findall(text)

    # crude counts
    data_point_count = len(nums) + len(dates)
    citation_count = len(citations)

    # quick "substance score" (0-100): more data points & concise sentences boost score
    # weights can be tuned
    score = 0
    score += min(data_point_count * 5, 40)          # up to 40 from data points
    score += min(citation_count * 8, 24)            # up to 24 from citations/“source” mentions
    # penalize excessively long sentences
    penalty = min(int(long_sentence_ratio * 100) // 5, 20)  # up to -20
    # reward concise avg sentence length (<=20 words)
    if avg_sentence_len <= 16:
        score += 20
    elif avg_sentence_len <= 22:
        score += 12
    elif avg_sentence_len <= 28:
        score += 5
    score = max(0, min(100, score - penalty))

    return {
        "avg_sentence_length": round(avg_sentence_len, 2),
        "long_sentence_ratio": round(long_sentence_ratio, 3),
        "data_point_count": data_point_count,
        "citation_keyword_hits": citation_count,
        "substance_score_local_0_100": score,
    }

# -----------------------
# 2) GPT "substance vs fluff" judgment (adds context)
# -----------------------
def gpt_quality_score(page_text: str, title: str, url: str) -> Dict[str, Any]:
    sample = page_text[:8000]  # keep context short enough
    prompt = f"""
You are an SEO editor. Score the page's *substance vs fluff*.

Definitions:
- Substance: specific data, concrete examples, stats, dates, named entities, clear steps, citations.
- Fluff: vague claims, hype, filler, long wind-ups, repeated generalities.

Return STRICT JSON with:
{{
  "label": "substantive" | "fluffy",
  "score_1_to_5": 1-5,  // 1=very fluffy, 5=very substantive
  "reasons": ["...","..."],  // 2-4 concise bullets
  "notable_data_points": ["..."]  // up to 5 short examples (stats, figures, named sources)
}}

Title: {title}
URL: {url}

Content (excerpt):
\"\"\"
{sample}
\"\"\"

JSON ONLY:
"""
    try:
        raw = _completion(prompt, max_tokens=280)
        obj = json.loads(raw)
        label = obj.get("label", "").lower().strip()
        if label not in ("substantive", "fluffy"):
            label = "substantive" if obj.get("score_1_to_5", 3) >= 4 else "fluffy"
        return {
            "label": label,
            "score_1_to_5": obj.get("score_1_to_5", 3),
            "reasons": obj.get("reasons", []),
            "notable_data_points": obj.get("notable_data_points", []),
        }
    except Exception:
        # safe fallback
        return {
            "label": "substantive" if compute_local_quality_metrics(page_text)["substance_score_local_0_100"] >= 60 else "fluffy",
            "score_1_to_5": 4 if compute_local_quality_metrics(page_text)["substance_score_local_0_100"] >= 60 else 2,
            "reasons": ["Fallback: based on local metrics."],
            "notable_data_points": []
        }

# -----------------------
# 3) Compare H2/H3 outlines across pages
# -----------------------
def compare_outlines_and_find_gaps(pages: List[Dict[str, Any]], search_query: str) -> Dict[str, Any]:
    """
    pages: [{"url":..., "title":..., "blueprint":{"h2":[...], "h3":[...]}}]
    Returns frequency maps and GPT suggestions for 'missing angles'.
    """
    # collect all normalized headings
    freq = Counter()
    per_url_topics = {}
    for p in pages:
        url = p["url"]
        h2 = [t for t in (p.get("blueprint", {}).get("h2") or []) if t]
        h3 = [t for t in (p.get("blueprint", {}).get("h3") or []) if t]
        topics = [ _norm_heading(t) for t in (h2 + h3) if _norm_heading(t) ]
        per_url_topics[url] = topics
        freq.update(topics)

    # common & rare topics
    common_topics = [t for t, c in freq.most_common() if c >= 3]   # appear on ≥3 pages
    rare_topics = [t for t, c in freq.items() if c == 1]           # appear only once

    # Prepare a concise outline summary for GPT
    outlines = []
    for p in pages:
        outlines.append({
            "url": p["url"],
            "title": p.get("title", ""),
            "topics": per_url_topics.get(p["url"], [])[:25]
        })
    outlines_str = json.dumps(outlines, ensure_ascii=False)

    prompt = f"""
You are mapping SERP coverage to find *missing angles*.

Input:
- Query intent: "{search_query}"
- Outlines (normalized h2/h3 tokens per URL) as JSON:
{outlines_str}

Task:
1) Identify 3–8 *common topics* (high consensus).
2) Identify 5–10 *missing angles* — important subtopics/end-user tasks/decision criteria that are NOT well covered or appear rarely.
3) For each missing angle, give a one-line rationale (why it matters for the searcher).

Return STRICT JSON:
{{
  "common_topics": ["..."],
  "missing_angles": [
     {{"topic":"...", "why_it_matters":"..."}},
     ...
  ]
}}

JSON ONLY:
"""
    try:
        raw = _completion(prompt, max_tokens=380)
        obj = json.loads(raw)
        return {
            "topic_frequency": dict(freq),
            "common_topics_by_count": common_topics,
            "rare_topics_by_count": rare_topics[:50],
            "gpt_common_topics": obj.get("common_topics", []),
            "gpt_missing_angles": obj.get("missing_angles", [])
        }
    except Exception:
        # fallback purely from counts
        # missing angles = top rare ones (best-guess)
        return {
            "topic_frequency": dict(freq),
            "common_topics_by_count": common_topics,
            "rare_topics_by_count": rare_topics[:50],
            "gpt_common_topics": [],
            "gpt_missing_angles": [{"topic": t, "why_it_matters": "Appears rarely across competitors; potential differentiation."} for t in rare_topics[:10]]
        }

# -----------------------
# 4) Entry point to analyze a batch
# -----------------------
def analyze_quality_and_gaps(pages: List[Dict[str, Any]], search_query: str) -> Dict[str, Any]:
    """
    pages: [{"url":..., "title":..., "text":..., "blueprint":{"h2":[...], "h3":[...]}}]
    Returns:
    {
      "per_page": {
        "<url>": {
          "local_metrics": {...},
          "gpt_quality": {...}
        }
      },
      "outline_comparison": {...}
    }
    """
    per_page = {}
    for p in pages:
        url = p["url"]
        text = p.get("text", "") or ""
        local_metrics = compute_local_quality_metrics(text)
        gpt_metrics = gpt_quality_score(text, p.get("title", ""), url)
        per_page[url] = {
            "local_metrics": local_metrics,
            "gpt_quality": gpt_metrics
        }

    outline_comparison = compare_outlines_and_find_gaps(pages, search_query)

    return {
        "per_page": per_page,
        "outline_comparison": outline_comparison
    }
