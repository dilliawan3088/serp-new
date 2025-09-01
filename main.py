# main.py
import json
from typing import Dict, Any, List

from searchResults import perform_google_search
from scrap import scrape_landing_page

# Milestone modules
from classification import classify_content_with_openai
from content_analysis import analyze_page_for_milestone2
from quality_gaps import analyze_quality_and_gaps

# Milestone 3 (strategy layer)
try:
    from intent_strategy import run_strategy
except ImportError:
    run_strategy = None

# Milestone 4 (final outline)
try:
    from final_outline import generate_final_outline, render_outline_md
except ImportError:
    generate_final_outline = None
    render_outline_md = None


def _safe_get(d: Dict[str, Any], key: str, default=None):
    try:
        v = d.get(key, default)
        return v if v is not None else default
    except Exception:
        return default


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def _headings_from_blueprint(bp: Dict[str, Any]) -> List[str]:
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

    seen = set()
    out = []
    for h in collected:
        if h not in seen:
            out.append(h)
            seen.add(h)
    return out


def _topic_in_text_or_headings(topic: str, text: str, headings: List[str]) -> bool:
    t = _normalize(topic)
    if not t:
        return False
    if t in _normalize(text):
        return True
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

    # 3) Initialize output
    combined_results: Dict[str, Any] = {
        "search_query": search_query,
        "search_results": search_data,
        "scraped_pages": {},
        "classifications": [],
        "milestone2": {},
        "quality_gaps": {}
    }

    # 4) Per-URL pipeline
    for idx, result in enumerate(top_results, start=1):
        url = _safe_get(result, "url", "")
        title = _safe_get(result, "title", "")
        if not url:
            print(f"[WARN] Result #{idx} has no URL, skipping.")
            continue

        print(f"\n[STEP] #{idx}: {title} -> {url}")

        # Scrape
        try:
            print("[INFO] Scraping page text…")
            scraped_content = scrape_landing_page(url)
            content_text = _safe_get(scraped_content, url, "") or ""
            combined_results["scraped_pages"][url] = content_text
            print(f"[OK] Scraped chars: {len(content_text)}")
        except Exception as e:
            print(f"[FATAL] Scrape failed for {url}: {e}")
            combined_results["scraped_pages"][url] = {"error": str(e)}
            combined_results["classifications"].append(
                {"url": url, "title": title, "content_type": "Error"}
            )
            combined_results["milestone2"][url] = {
                "blueprint": {"h2": [], "h3": []},
                "intro_style": {"intro_sample": "", "label": "fluffy", "reason": "Scrape error"},
                "internal_links": {"links": []}
            }
            continue

        # Classification
        try:
            print("[INFO] Running content-type classification…")
            content_type = classify_content_with_openai(content_text, title, url)
            combined_results["classifications"].append(
                {"url": url, "title": title, "content_type": content_type}
            )
            print(f"[OK] Classification: {content_type}")
        except Exception as e:
            print(f"[ERROR] classification failed for {url}: {e}")
            combined_results["classifications"].append(
                {"url": url, "title": title, "content_type": "Error"}
            )

        # Milestone 2
        try:
            print("[INFO] Running Milestone 2 analysis…")
            analysis = analyze_page_for_milestone2(content_text, title, url)
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

    # 5) Quality & Gaps batch
    try:
        print("\n[INFO] Preparing batch for Quality & Gaps…")
        pages_batch: List[Dict[str, Any]] = []
        TOP_K = 5
        selected = []
        for r in top_results:
            url = _safe_get(r, "url", "")
            title = _safe_get(r, "title", "")
            if not url:
                continue
            text_val = _safe_get(combined_results.get("scraped_pages", {}), url, "")
            text = text_val if isinstance(text_val, str) else ""
            if len(text) < 500:
                continue
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

        for item in selected:
            pages_batch.append({
                "url": item["url"],
                "title": item["title"],
                "text": item["text"],
                "blueprint": item["blueprint"]
            })

        print(f"[INFO] Selected {len(selected)} pages for deep-dive (target={TOP_K}).")
        qg = analyze_quality_and_gaps(pages_batch, search_query)
        combined_results["quality_gaps"] = qg
        print("[OK] Quality & Gaps analysis stored.")

    except Exception as e:
        print(f"[ERROR] quality_gaps.py failed: {e}")
        combined_results["quality_gaps"] = {"error": str(e)}

    # 5.5) Strategy layer
    if run_strategy is not None:
        try:
            strategy_input = dict(combined_results)
            cls_list = strategy_input.get("classifications", []) or []
            cls_map = {}
            for item in cls_list:
                if isinstance(item, dict):
                    u = item.get("url")
                    if u:
                        cls_map[u] = {"type": item.get("content_type", "")}
            strategy_input["classifications"] = cls_map

            print("[INFO] Running Milestone 3 strategy layer…")
            strategy_block = run_strategy(strategy_input, chosen_angles=("A", "B"))
            combined_results["milestone3_strategy"] = strategy_block
            print("[OK] Strategy layer stored with status='needs_approval'.")
        except Exception as e:
            print(f"[ERROR] strategy layer failed: {e}")
            combined_results["milestone3_strategy"] = {"error": str(e), "status": "needs_approval"}
    else:
        print("[WARN] intent_strategy not found; skipping strategy layer.")
        combined_results["milestone3_strategy"] = {"status": "skipped"}

    # 5.55) User selects angle
    strategy = combined_results.get("milestone3_strategy", {})
    if isinstance(strategy, dict) and strategy.get("status") == "needs_approval":
        angles = strategy.get("proposed_angles", [])
        if angles:
            print("\n================ PROPOSED ANGLES ================")
            for a in angles:
                print(f"[{a.get('id')}] {a.get('title')}\n    HOW: {a.get('how')}\n")
            chosen = input("Select an angle ID (default=A): ").strip().upper() or "A"
            valid_ids = [a.get("id") for a in angles]
            if chosen not in valid_ids:
                print(f"[WARN] Invalid choice {chosen}, defaulting to A.")
                chosen = "A"
            combined_results["milestone3_strategy"]["approved_angle"] = chosen
            print(f"[OK] Angle {chosen} approved.")

    # 5.6) Final outline
    if generate_final_outline is not None:
        try:
            print("[INFO] Generating final content outline (Milestone 4)…")
            final_outline = generate_final_outline(combined_results)
            combined_results["final_outline"] = final_outline
            print("[OK] Final outline generated.")

            print("\n================ FINAL OUTLINE ================\n")
            print(render_outline_md(final_outline))
        except Exception as e:
            print(f"[ERROR] final_outline generation failed: {e}")
            combined_results["final_outline"] = {"error": str(e)}
    else:
        print("[WARN] final_outline module not found; skipping Milestone 4.")
        combined_results["final_outline"] = {"status": "skipped"}

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
    st = combined_results.get("milestone3_strategy", {})
    if isinstance(st, dict) and st.get("status") == "needs_approval":
        print("Strategy Layer:        READY (needs_approval)")
    elif isinstance(st, dict) and st.get("status") == "skipped":
        print("Strategy Layer:        SKIPPED")
    else:
        print("Strategy Layer:        ERROR or MISSING")
    if isinstance(combined_results.get("final_outline"), dict) and "error" not in combined_results["final_outline"]:
        print("Final Outline:         OK")
    else:
        print("Final Outline:         ERROR or SKIPPED")
    print(f"Saved → {output_file}")


if __name__ == "__main__":
    main()
