# intent_strategy.py
"""
Milestone 3 — Strategy Layer
Moves from analysis -> strategy:
1) Derive Primary User Intent (PUI)
2) Detect SERP red flags (mismatches, dominance issues)
3) Summarize competitor weaknesses (from M2 + quality_gaps)
4) Propose 2–3 unique content angles (A & B prioritized)
5) Differentiation Q&A:
   - What do competitors ignore?
   - Where do competitors fail?
   - Can we add original data/stories?
6) Append a human-in-the-loop checkpoint to combined_results.json

Purely heuristic/deterministic. No external APIs.
"""

from __future__ import annotations
import json
import re
from collections import Counter
from typing import Any, Dict, List, Tuple

# --------- utils

def _safe_load(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[intent_strategy] Could not load {path}: {e}")
        return {}

def _safe_write(path: str, data: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[intent_strategy] Could not write {path}: {e}")

def _norm_host(u: str) -> str:
    m = re.match(r"^https?://([^/]+)/?", u or "", flags=re.I)
    return (m.group(1) if m else (u or "")).lower()

# --------- STEP 1: Primary User Intent

INTENT_LABELS = {
    "informational": "Informational",
    "commercial": "Commercial-investigation",
    "transactional": "Transactional (buy/contact now)",
    "navigational": "Navigational (brand/site specific)",
    "mixed": "Mixed (informational + commercial)"
}

DIRECTORY_DOMAINS = {"clutch.co", "goodfirms.co", "sortlist.com", "g2.com", "designrush.com"}
JOBS_HINT = {"rozee.pk", "indeed.", "linkedin.com/jobs", "bayt.com", "glassdoor."}

def derive_primary_intent(cr: Dict[str, Any]) -> str:
    classes = cr.get("classifications", {}) or {}
    search = cr.get("search_results", {}) or {}
    top_results = search.get("top_results", []) or []
    paa = search.get("people_also_ask", []) or []
    ai_overview = (search.get("ai_overview") or "").lower()

    # count by class (from Milestone 1)
    type_counter = Counter()
    for _, meta in classes.items():
        t = ""
        if isinstance(meta, dict):
            t = (meta.get("type") or meta.get("label") or "").lower()
        elif isinstance(meta, str):
            t = meta.lower()
        if t:
            type_counter[t] += 1

    directories = 0
    listicles = 0
    services = 0
    jobs = 0
    for item in top_results:
        title = (item.get("title") or "").lower()
        url = item.get("url") or ""
        host = _norm_host(url)
        if any(h in host for h in DIRECTORY_DOMAINS):
            directories += 1
        if re.search(r"\b(top|best|10|20|list)\b", title):
            listicles += 1
        if re.search(r"\bservices?\b|\bagency\b|\bcompany\b|\bhire\b", title):
            services += 1
        if any(h in host for h in JOBS_HINT):
            jobs += 1

    score_info = 0
    score_comm = 0
    score_trans = 0
    score_comm += directories * 2 + listicles
    score_trans += services
    score_info += (1 if paa else 0) + (1 if ai_overview else 0)
    score_info += type_counter.get("blog", 0) + type_counter.get("guide", 0)
    score_trans += type_counter.get("service", 0) + type_counter.get("product", 0)
    score_comm += type_counter.get("listicle", 0) + type_counter.get("directory", 0)

    triples = [("informational", score_info), ("commercial", score_comm), ("transactional", score_trans)]
    triples.sort(key=lambda x: x[1], reverse=True)
    top_label, top_score = triples[0]
    second_label, second_score = triples[1]
    if top_score == 0 and second_score == 0:
        return INTENT_LABELS["informational"]
    if top_score - second_score <= 1:
        return INTENT_LABELS["mixed"]
    return INTENT_LABELS[top_label]

# --------- STEP 2: Red Flags

def detect_red_flags(cr: Dict[str, Any], pui: str) -> List[str]:
    flags: List[str] = []
    search = cr.get("search_results", {}) or {}
    top_results = search.get("top_results", []) or []

    directories = sum(1 for r in top_results if any(h in _norm_host(r.get("url","")) for h in DIRECTORY_DOMAINS))
    jobs = sum(1 for r in top_results if any(h in _norm_host(r.get("url","")) for h in JOBS_HINT))
    listicles = sum(1 for r in top_results if re.search(r"\b(top|best|10|20|list)\b", (r.get("title") or "").lower()))
    services = sum(1 for r in top_results if re.search(r"\bservices?\b|\bagency\b|\bcompany\b|\bhire\b", (r.get("title") or "").lower()))
    total = max(1, len(top_results))

    if directories / total >= 0.3:
        flags.append("Directory dominance in SERP (e.g., Clutch/GoodFirms) — hard to outrank with generic listicles.")
    if jobs > 0:
        flags.append("Job boards appear in SERP — may dilute buyer intent for vendor selection.")
    if listicles / total >= 0.5:
        flags.append("Listicles dominate — many thin 'Top 10' pages; need differentiation.")
    if "Transactional" in pui and listicles / total >= 0.5:
        flags.append("Intent mismatch: aiming Transactional but SERP is largely listicles (commercial-investigation).")
    if "Informational" in pui and services / total >= 0.5:
        flags.append("Intent mismatch: targeting Informational but many service pages suggest commercial intent.")

    return flags

# --------- STEP 3: Weaknesses from M2 + quality_gaps

def _collect_quality_signals(cr: Dict[str, Any]) -> Dict[str, Any]:
    qg = cr.get("milestone3_quality_gaps") or cr.get("quality_gaps") or {}
    perq = qg.get("per_url_quality", {}) or {}
    vals = {
        "avg_sentence_len": [],
        "citations": [],
        "has_struct": [],
        "uniq_bigram": [],
        "quality_score": [],
    }
    for _, m in perq.items():
        if not isinstance(m, dict):
            continue
        if "avg_sentence_length_tokens" in m:
            vals["avg_sentence_len"].append(m.get("avg_sentence_length_tokens"))
        if "citations_count" in m:
            vals["citations"].append(m.get("citations_count"))
        if "has_tables_or_figures" in m:
            vals["has_struct"].append(1 if m.get("has_tables_or_figures") else 0)
        if "unique_bigram_ratio" in m:
            vals["uniq_bigram"].append(m.get("unique_bigram_ratio"))
        if "quality_score_0_100" in m:
            vals["quality_score"].append(m.get("quality_score_0_100"))
    return vals

def _mean(xs: List[float]) -> float:
    xs = [x for x in xs if isinstance(x, (int, float))]
    return sum(xs) / max(1, len(xs))

def summarize_competitor_weaknesses(cr: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    qg = cr.get("milestone3_quality_gaps") or cr.get("quality_gaps") or {}
    gaps = qg.get("missing_angles", {}) or {}
    core_topics = gaps.get("core_topics_sample", []) or {}
    per_url_missing = (gaps.get("per_url_missing") or {})

    if core_topics:
        miss_counter = Counter()
        for _, detail in per_url_missing.items():
            for t in detail.get("missing_core_topics", []) or []:
                miss_counter[t] += 1
        for topic, n in miss_counter.most_common(5):
            out.append(f"Core topic under-covered: “{topic}” (missed by {n} competitor page(s)).")

    vals = _collect_quality_signals(cr)
    if _mean(vals["citations"]) < 2:
        out.append("Low citation density across competitors — little verifiable data.")
    if _mean(vals["has_struct"]) < 0.5:
        out.append("Few tables/charts — limited scannability and comparative depth.")
    if _mean(vals["avg_sentence_len"]) > 20:
        out.append("Long sentences on average — readability can be improved (aim 14–18 tokens).")
    if _mean(vals["uniq_bigram"]) < 0.65:
        out.append("High boilerplate patterns — limited originality in phrasing.")

    return out[:6] if out else ["Competitors rely on generic listicles with limited data and weak structure."]

# --------- STEP 4: Propose unique angles (A & B chosen)

ANGLE_LIBRARY = {
    "A": {
        "title": "Data-backed Comparison Matrix",
        "detail": (
            "Publish a live comparison table of top software houses by services, niches, certifications (ISO/CMMI), "
            "client logos, review deltas (Clutch vs. GoodFirms), delivery model, and price bands. "
            "Cite sources and link to proofs; include filters by city and industry."
        )
    },
    "B": {
        "title": "Decision Framework + Downloadable Checklist",
        "detail": (
            "Create a step-by-step selection guide: budget tiers → engagement model → SLA/security → case-fit "
            "signals. Provide a printable checklist and an interactive quiz that outputs a short-list."
        )
    },
    "C": {
        "title": "Original Case Studies & Mini-Benchmarks",
        "detail": (
            "Interview 2–3 clients per vertical; show before/after metrics and tech stacks. Add small benchmarks "
            "(e.g., delivery lead time, defect escape rate) to inject original evidence."
        )
    }
}

def propose_unique_angles(weaknesses: List[str], chosen: Tuple[str, ...] = ("A","B")) -> List[Dict[str, str]]:
    angles: List[Dict[str, str]] = []
    for key in chosen:
        if key in ANGLE_LIBRARY:
            angles.append({"id": key, "title": ANGLE_LIBRARY[key]["title"], "how": ANGLE_LIBRARY[key]["detail"]})
    hint_low_data = any("citation" in w.lower() or "data" in w.lower() for w in weaknesses)
    if len(angles) < 3 and hint_low_data and "C" in ANGLE_LIBRARY and "C" not in chosen:
        angles.append({"id": "C", "title": ANGLE_LIBRARY["C"]["title"], "how": ANGLE_LIBRARY["C"]["detail"]})
    return angles

# --------- STEP 5 — Differentiation Q&A (aggregates all sources of 'ignored topics')

def build_differentiation_qna(cr: Dict[str, Any], weaknesses: List[str]) -> Dict[str, List[str]]:
    """
    Builds explicit answers for:
      - what_competitors_ignore
      - where_competitors_fail
      - can_we_add_original_data_or_stories

    Sources for "ignore":
      1) quality_gaps.missing_angles.per_url_missing[].missing_core_topics
      2) quality_gaps.outline_comparison.gpt_missing_angles[].topic
      3) per_competitor_gap_report_top5[].missing_topics
    """
    ignore_counter = Counter()
    qg = cr.get("quality_gaps", {}) or cr.get("milestone3_quality_gaps", {}) or {}

    # (1) classic missing_angles structure
    per_url_missing = ((qg.get("missing_angles") or {}).get("per_url_missing")) or {}
    for _, detail in per_url_missing.items():
        for t in (detail.get("missing_core_topics") or []):
            if isinstance(t, str) and t.strip():
                ignore_counter[t.strip().lower()] += 1

    # (2) outline_comparison.gpt_missing_angles
    gpt_missing = (qg.get("outline_comparison") or {}).get("gpt_missing_angles") or []
    for item in gpt_missing:
        if isinstance(item, dict):
            t = item.get("topic")
            if isinstance(t, str) and t.strip():
                ignore_counter[t.strip().lower()] += 1
        elif isinstance(item, str) and item.strip():
            ignore_counter[item.strip().lower()] += 1

    # (3) per_competitor_gap_report_top5[].missing_topics
    for row in cr.get("per_competitor_gap_report_top5", []) or []:
        for t in row.get("missing_topics", []) or []:
            if isinstance(t, str) and t.strip():
                ignore_counter[t.strip().lower()] += 1

    # Build the human-readable list
    ignore_list: List[str] = []
    for topic, n in ignore_counter.most_common(8):
        ignore_list.append(f"Under-covered topic: '{topic}' (missed by {n} competitor page(s)).")

    # If still empty, offer a helpful default
    if not ignore_list:
        ignore_list = ["No clear consensus topics surfaced; many competitors cover similar surface-level items."]

    # Map weaknesses -> failure statements
    fail_list: List[str] = []
    for w in weaknesses:
        wl = w.lower()
        if "citation" in wl or "verifiable" in wl or "data" in wl:
            fail_list.append("Lack of verifiable data and citations.")
        elif "tables" in wl or "charts" in wl or "structure" in wl or "scannability" in wl:
            fail_list.append("Weak structure (few tables/charts) reducing scannability and depth.")
        elif "long sentences" in wl or "readability" in wl:
            fail_list.append("Readability issues (long sentences; aim 14–18 tokens).")
        elif "boilerplate" in wl or "originality" in wl:
            fail_list.append("High boilerplate phrasing; limited originality.")
        elif "under-covered" in wl:
            fail_list.append(w)
    # de-dup & fallback
    seen = set(); fail_list = [x for x in fail_list if not (x in seen or seen.add(x))]
    if not fail_list:
        fail_list = ["Generic listicles with thin analysis; limited decision support for buyers."]

    # Can we add original data/stories? — infer from weaknesses
    add_list: List[str] = []
    if any("citation" in w.lower() or "verifiable" in w.lower() or "data" in w.lower() for w in weaknesses):
        add_list.append("Yes — include original stats (pricing bands, delivery speed, defect rates) with cited sources.")
    if any("tables" in w.lower() or "charts" in w.lower() or "structure" in w.lower() for w in weaknesses):
        add_list.append("Yes — add a comparison matrix and visuals (tables/charts) for quick vendor evaluation.")
    add_list.append("Yes — incorporate short client case studies (problem → approach → outcome) per key vertical.")
    # de-dup
    seen2 = set(); add_list = [x for x in add_list if not (x in seen2 or seen2.add(x))]

    return {
        "what_competitors_ignore": ignore_list[:6],
        "where_competitors_fail": fail_list[:6],
        "can_we_add_original_data_or_stories": add_list[:6],
    }

# --------- Orchestrator

def run_strategy(cr: Dict[str, Any], chosen_angles: Tuple[str, ...] = ("A","B")) -> Dict[str, Any]:
    pui = derive_primary_intent(cr)
    flags = detect_red_flags(cr, pui)
    weak = summarize_competitor_weaknesses(cr)
    angles = propose_unique_angles(weak, chosen=chosen_angles)
    diff_qna = build_differentiation_qna(cr, weak)
    return {
        "primary_user_intent": pui,
        "red_flags": flags,
        "weaknesses": weak,
        "differentiation_qna": diff_qna,
        "proposed_angles": angles,
        "status": "needs_approval"  # Human-in-the-loop checkpoint
    }

def attach_strategy_to_json(
    combined_path: str = "combined_results.json",
    out_key: str = "milestone3_strategy",
    chosen_angles: Tuple[str, ...] = ("A","B")
) -> Dict[str, Any]:
    cr = _safe_load(combined_path)
    result = run_strategy(cr, chosen_angles=chosen_angles)
    cr[out_key] = result
    _safe_write(combined_path, cr)
    return result

if __name__ == "__main__":
    out = attach_strategy_to_json()
    print("[intent_strategy] Done. Added 'milestone3_strategy' with differentiation_qna and status='needs_approval'.")
