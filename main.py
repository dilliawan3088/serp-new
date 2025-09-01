# main.py
import json
from typing import Dict, Any, List

from searchResults import perform_google_search
from scrap import scrape_landing_page

# Milestone modules
from classification import classify_content_with_openai
from content_analysis import analyze_page_for_milestone2
from quality_gaps import analyze_quality_and_gaps


def _safe_get(d: Dict[str, Any], key: str, default=None):
    try:
        v = d.get(key, default)
        return v if v is not None else default
    except Exception:
        return default


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def _headings_from_blueprint(bp: Dict[str, Any]) -> List[str]:
    """
    Extract a flat, lowercase list of headings from a blueprint structure
    that might contain lists and/or dicts for h2/h3.
    """
    if not isinstance(bp, dict):
        return []
    collected: List[str] = []

    def add_any(x):
        if isinstance(x, str) and x.strip():
            collected.append(_normalize(x))
        elif isinstance(x, list):
            for i in x:
                add_any(i)
        elif isinstance(x, dict):
            for k, v in x.items():
                add_any(k)
                add_any(v)

    for k in ("h1", "h2", "h3", "h4"):
        if k in bp:
            add_any(bp[k])

    # de-dup while preserving order
    seen = set()
    out = []
    for h in collected:
        if h not in seen:
            out.append(h)
            seen.add(h)
    return out


def _topic_in_text_or_headings(topic: str, text: str, headings: List[str]) -> bool:
    """
    Heuristic: consider topic covered if its normalized phrase appears in text
    or any heading (case-insensitive). This is intentionally simple and fast.
    """
    t = _normalize(topic)
    if not t:
        return False
    # text match
    if t in _normalize(text):
        return True
    # heading contains the phrase or vice versa (loose match)
    for h in headings:
        if t in h or h in t:
            return True
    return False


def _recommendation_for_topic(topic: str) -> str:
    t = topic.strip().rstrip(".")
    return f"Add a clear section on '{t}', include concrete examples/screenshots, cite sources where relevant, and finish with an action-oriented CTA."


def main():
    # 1) Input
    search_query = input("Enter your search query: ").strip()
    if not search_query:
        print("[FATAL] No search query provided.")
        return

    # 2) Search
    print(f"[STEP] Searching Google for: {search_query!r}")
    try:
        search_data = perform_google_search(search_query) or {}
    except Exception as e:
        print(f"[FATAL] perform_google_search() failed: {e}")
        return

    top_results = _safe_get(search_data, "top_results", []) or []
    print(f"[INFO] Found {len(top_results)} top results.")

    # 3) Initialize output structure
    combined_results: Dict[str, Any] = {
        "search_query": search_query,
        "search_results": search_data,
        "scraped_pages": {},   # url -> text
        "classifications": [], # [{url,title,content_type}]
        "milestone2": {},      # url -> {blueprint, intro_style, internal_links}
        "quality_gaps": {}     # batch results
    }

    # 4) Per-URL pipeline: scrape → classify → Milestone-2 analysis
    for idx, result in enumerate(top_results, start=1):
        url = _safe_get(result, "url", "")
        title = _safe_get(result, "title", "")
        if not url:
            print(f"[WARN] Result #{idx} has no URL, skipping.")
            continue

        print(f"\n[STEP] #{idx}: {title} -> {url}")

        # ---- SCRAPE ----
        try:
            print("[INFO] Scraping page text…")
            scraped_content = scrape_landing_page(url)  # expected: { url: "visible text..." }
            content_text = _safe_get(scraped_content, url, "") or ""
            combined_results["scraped_pages"][url] = content_text
            print(f"[OK] Scraped chars: {len(content_text)}")
        except Exception as e:
            print(f"[FATAL] Scrape failed for {url}: {e}")
            combined_results["scraped_pages"][url] = {"error": str(e)}
            # keep shape consistent for downstream
            combined_results["classifications"].append({
                "url": url, "title": title, "content_type": "Error"
            })
            combined_results["milestone2"][url] = {
                "blueprint": {"h2": [], "h3": []},
                "intro_style": {"intro_sample": "", "label": "fluffy", "reason": "Scrape error"},
                "internal_links": {"links": []}
            }
            continue

        # ---- CLASSIFICATION ----
        try:
            print("[INFO] Running content-type classification…")
            content_type = classify_content_with_openai(content_text, title, url)
            combined_results["classifications"].append({
                "url": url, "title": title, "content_type": content_type
            })
            print(f"[OK] Classification: {content_type}")
        except Exception as e:
            print(f"[ERROR] classification failed for {url}: {e}")
            combined_results["classifications"].append({
                "url": url, "title": title, "content_type": "Error"
            })

        # ---- MILESTONE 2 (blueprint/intro/links) ----
        try:
            print("[INFO] Running Milestone 2 analysis (blueprint/intro/links)…")
            analysis = analyze_page_for_milestone2(content_text, title, url)
            # expected keys: blueprint {h2,h3}, intro_style {intro_sample,label,reason}, internal_links {links}
            # be defensive:
            bp = _safe_get(analysis, "blueprint", {"h2": [], "h3": []})
            intro = _safe_get(analysis, "intro_style", {"intro_sample": "", "label": "", "reason": ""})
            links = _safe_get(analysis, "internal_links", {"links": []})
            combined_results["milestone2"][url] = {
                "blueprint": bp,
                "intro_style": intro,
                "internal_links": links
            }
            print("[OK] Milestone 2 analysis stored.")
        except Exception as e:
            print(f"[ERROR] milestone2 analysis failed for {url}: {e}")
            combined_results["milestone2"][url] = {
                "blueprint": {"h2": [], "h3": []},
                "intro_style": {"intro_sample": "", "label": "fluffy", "reason": "Error"},
                "internal_links": {"links": []}
            }

    # 5) Batch: Quality & Gaps on Top-5 (by rank; prefer pages with enough text)
    try:
        print("\n[INFO] Preparing batch for Quality & Gaps…")
        pages_batch: List[Dict[str, Any]] = []

        # Select top 5 pages for deep-dive, prioritizing higher rank and usable text
        TOP_K = 5
        selected = []
        for r in top_results:
            url = _safe_get(r, "url", "")
            title = _safe_get(r, "title", "")
            if not url:
                continue
            text_val = _safe_get(combined_results.get("scraped_pages", {}), url, "")
            text = text_val if isinstance(text_val, str) else ""
            # keep only pages with enough content
            if len(text) < 500:
                continue
            # ensure we also captured a blueprint from milestone 2
            m2 = _safe_get(combined_results.get("milestone2", {}), url, {})
            bp = _safe_get(m2, "blueprint", {"h2": [], "h3": []})
            selected.append({
                "url": url,
                "title": title,
                "text": text,
                "blueprint": bp,
                "intro": _safe_get(m2, "intro_style", {}),
                "links": _safe_get(m2, "internal_links", {})
            })
            if len(selected) >= TOP_K:
                break

        # Fallback: if we couldn't collect 5 with threshold, relax criteria but keep order
        if len(selected) < TOP_K:
            for r in top_results:
                if len(selected) >= TOP_K:
                    break
                url = _safe_get(r, "url", "")
                title = _safe_get(r, "title", "")
                if not url or any(u["url"] == url for u in selected):
                    continue
                text_val = _safe_get(combined_results.get("scraped_pages", {}), url, "")
                text = text_val if isinstance(text_val, str) else ""
                m2 = _safe_get(combined_results.get("milestone2", {}), url, {})
                bp = _safe_get(m2, "blueprint", {"h2": [], "h3": []})
                selected.append({
                    "url": url,
                    "title": title,
                    "text": text,
                    "blueprint": bp,
                    "intro": _safe_get(m2, "intro_style", {}),
                    "links": _safe_get(m2, "internal_links", {})
                })

        # Build payload for quality_gaps.py
        for item in selected:
            pages_batch.append({
                "url": item["url"],
                "title": item["title"],
                "text": item["text"],
                "blueprint": item["blueprint"]
            })

        # Compact summary to surface Milestone-2 deliverables
        combined_results["milestone2_summary_top5"] = [
            {
                "rank": i + 1,
                "url": it["url"],
                "title": it["title"],
                "intro_label": _safe_get(it.get("intro", {}), "label", ""),
                "h2": _safe_get(it.get("blueprint", {}), "h2", [])[:10],
                "cta_links_sample": _safe_get(it.get("links", {}), "links", [])[:5],
            }
            for i, it in enumerate(selected)
        ]

        print(f"[INFO] Selected {len(selected)} pages for deep-dive (target={TOP_K}).")
        print("[INFO] Running Quality & Gaps batch analysis…")
        qg = analyze_quality_and_gaps(pages_batch, search_query)
        combined_results["quality_gaps"] = qg
        print("[OK] Quality & Gaps analysis stored.")

        # === Per-competitor gap report (top 5) with metrics ===
        outline_cmp = _safe_get(qg, "outline_comparison", {})
        agg_missing = _safe_get(outline_cmp, "gpt_missing_angles", []) or []
        missing_topics_universe: List[str] = []
        for item in agg_missing:
            if isinstance(item, dict):
                t = _safe_get(item, "topic", "")
                if t and t not in missing_topics_universe:
                    missing_topics_universe.append(t)

        per_page_metrics = _safe_get(qg, "per_page", {}) or {}

        per_competitor_report = []
        for i, it in enumerate(selected, start=1):
            url = it["url"]
            title = it["title"]
            text = it["text"]
            headings = _headings_from_blueprint(_safe_get(it, "blueprint", {}))

            # Page-specific gaps vs aggregate topics
            missing_for_page: List[str] = []
            for topic in missing_topics_universe:
                if not _topic_in_text_or_headings(topic, text, headings):
                    missing_for_page.append(topic)

            # Pull metrics from qg.per_page[url] if available
            page_metrics_obj = _safe_get(per_page_metrics, url, {}) or {}
            local_metrics = _safe_get(page_metrics_obj, "local_metrics", {})
            gpt_quality = _safe_get(page_metrics_obj, "gpt_quality", {})

            recommendations = [_recommendation_for_topic(t) for t in missing_for_page]

            per_competitor_report.append({
                "rank": i,
                "url": url,
                "title": title,
                "missing_topics": missing_for_page,
                "recommendations": recommendations,
                "local_metrics": local_metrics,
                "gpt_quality": gpt_quality
            })

        combined_results["per_competitor_gap_report_top5"] = per_competitor_report

    except Exception as e:
        print(f"[ERROR] quality_gaps.py failed: {e}")
        combined_results["quality_gaps"] = {"error": str(e)}

    # 6) Save
    output_file = "combined_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(combined_results, f, ensure_ascii=False, indent=2)

    # 7) Summary
    print("\n================ SUMMARY ================")
    print(f"Top results processed: {len(top_results)}")
    print(f"Classifications added: {len(combined_results['classifications'])}")
    print(f"Milestone2 pages:      {len(combined_results['milestone2'])}")
    if isinstance(combined_results.get("quality_gaps"), dict) and "error" not in combined_results["quality_gaps"]:
        print("Quality & Gaps:        OK")
    else:
        print("Quality & Gaps:        ERROR")
    print("Reports added:")
    print(" - milestone2_summary_top5")
    print(" - per_competitor_gap_report_top5")
    print(f"Saved → {output_file}")


if __name__ == "__main__":
    main()
