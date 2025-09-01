# content_analysis.py
# Milestone 2: "Blueprint" (H2/H3), intro style ("fluffy" vs "direct"), internal links to product/CTAs
# Uses GPT-4o-mini via Completions API and falls back gracefully.

import os
import re
from urllib.parse import urlparse
from dotenv import load_dotenv
import openai

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ---- small helpers ----
def _first_n_words(text: str, n: int = 150) -> str:
    words = re.split(r"\s+", text.strip())
    return " ".join(words[:n])

def _truncate_chars(text: str, max_chars: int = 12000) -> str:
    # keep prompt sizes safe for gpt-4o-mini
    return text[:max_chars] if text and len(text) > max_chars else (text or "")

def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except:
        return ""

def _completion(prompt: str, max_tokens: int = 300):
    # single place to call gpt-4o-mini
    return openai.Completion.create(
        model="gpt-4o-mini",
        prompt=prompt,
        temperature=0.0,
        max_tokens=max_tokens
    ).choices[0].text.strip()

# ---- 1) BLUEPRINT (H2/H3) ----
def extract_blueprint_with_openai(page_text: str, title: str, url: str) -> dict:
    """
    Returns: {"h2": [...], "h3": [...]}
    If no tags are present in the text, the model will infer likely section headings.
    """
    content = _truncate_chars(page_text, 10000)
    prompt = f"""
You are a precise SEO content auditor.

Task: Build a "blueprint" of what's ranking by extracting H2 and H3 headings from the page content.
- If real HTML headings like <h2> or <h3> exist, list those.
- If tags are not present (plain text), infer likely section headings (short, title-like lines) and map them to H2/H3 by importance.
- Return STRICT JSON with keys exactly "h2" and "h3" (arrays of strings). No extra text.

Page Title: {title}
URL: {url}

Page Content:
\"\"\" 
{content}
\"\"\"

JSON ONLY:
"""
    try:
        raw = _completion(prompt, max_tokens=400)
        # naive JSON safety: if model slips, try to coerce minimal structure
        import json
        data = json.loads(raw)
        return {"h2": data.get("h2", []), "h3": data.get("h3", [])}
    except Exception:
        return {"h2": [], "h3": []}

# ---- 2) INTRO STYLE (fluffy vs direct) ----
def analyze_intro_style_with_openai(page_text: str, title: str, url: str) -> dict:
    """
    Returns: {"intro_sample": "...first_100_150_words...", "label": "fluffy|direct", "reason": "..."}
    """
    intro = _first_n_words(page_text or "", 150)
    prompt = f"""
You are a concise editor. Classify the introduction style as "fluffy" or "direct".

Definitions:
- fluffy: vague, hypey, filler, slow to state purpose/value.
- direct: clear, concise, quickly states purpose/value or problem/solution.

Return STRICT JSON with keys: "label" (fluffy|direct) and "reason" (one sentence).
No extra commentary.

Title: {title}
URL: {url}

Intro (first 100-150 words):
\"\"\"
{intro}
\"\"\" 

JSON ONLY:
"""
    try:
        raw = _completion(prompt, max_tokens=120)
        import json
        obj = json.loads(raw)
        label = obj.get("label", "").lower().strip()
        if label not in ("fluffy", "direct"):
            label = "fluffy" if "fluff" in label else ("direct" if "direct" in label else "fluffy")
        return {
            "intro_sample": intro,
            "label": label,
            "reason": obj.get("reason", "")
        }
    except Exception:
        # safe fallback: quick heuristic if model fails
        direct_cues = len(re.findall(r"\b(how|what|why|guide|steps|in this|you will|we will|this page|overview)\b", intro.lower()))
        return {
            "intro_sample": intro,
            "label": "direct" if direct_cues >= 2 else "fluffy",
            "reason": "Heuristic fallback."
        }

# ---- 3) INTERNAL LINKS (product pages / CTAs) ----
_LINK_RE = re.compile(r'https?://[^\s)>\]]+', flags=re.I)

def _heuristic_internal_links(page_text: str, base_url: str):
    dom = _domain(base_url)
    links = _LINK_RE.findall(page_text or "")
    internals = [u for u in links if _domain(u).endswith(dom) and dom]
    tagged = []
    for u in internals:
        t = "cta" if re.search(r"(buy|get-started|get started|sign\s?up|start\s?free|learn\s?more|contact|pricing)", u, re.I) else \
            ("product" if re.search(r"(product|pricing|plans|features)", u, re.I) else "internal")
        tagged.append({"url": u, "type": t})
    return tagged[:20]

def identify_internal_links_with_openai(page_text: str, title: str, url: str) -> dict:
    """
    Returns: {"links":[{"url":"...", "type":"product|cta|internal"}]}
    Uses OpenAI first; falls back to regex heuristic if needed.
    """
    content = _truncate_chars(page_text, 9000)
    base_dom = _domain(url)
    prompt = f"""
You are auditing internal linking for conversions.

Task:
1) From the page content, list INTERNAL links (same domain as "{base_dom}") that point to:
   - product/pricing/features pages
   - strong CTAs (buy now, get started, sign up, learn more, pricing, contact)
2) If you can't see actual URLs in the text, infer likely internal CTA targets from anchor text (e.g., "Pricing", "Get Started") and mark type.

Return STRICT JSON:
{{"links":[{{"url":"<absolute-or-inferred>", "type":"product|cta|internal"}}]}}

Title: {title}
URL: {url}

Page Content:
\"\"\" 
{content}
\"\"\" 

JSON ONLY:
"""
    try:
        raw = _completion(prompt, max_tokens=350)
        import json
        obj = json.loads(raw)
        # If the model returns empty, use heuristic extraction
        links = obj.get("links", [])
        if not links:
            links = _heuristic_internal_links(page_text, url)
        return {"links": links}
    except Exception:
        return {"links": _heuristic_internal_links(page_text, url)}

# ---- One-shot convenience wrapper per page ----
def analyze_page_for_milestone2(page_text: str, title: str, url: str) -> dict:
    """
    Combined result for one page:
    {
      "blueprint": {"h2":[...], "h3":[...]},
      "intro_style": {"intro_sample":"...", "label":"fluffy|direct", "reason":"..."},
      "internal_links": {"links":[{"url":"..","type":"product|cta|internal"}]}
    }
    """
    return {
        "blueprint": extract_blueprint_with_openai(page_text, title, url),
        "intro_style": analyze_intro_style_with_openai(page_text, title, url),
        "internal_links": identify_internal_links_with_openai(page_text, title, url),
    }
