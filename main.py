import json
from searchResults import perform_google_search
from scrap import scrape_landing_page

# NEW: import both modules
from classification import classify_content_with_openai
from content_analysis import analyze_page_for_milestone2


def main():
    # Get search query from user
    search_query = input("Enter your search query: ")

    # Perform Google search and get results
    print("[INFO] Running search…")
    search_data = perform_google_search(search_query)

    # Initialize combined results
    combined_results = {
        "search_query": search_query,
        "search_results": search_data,
        "scraped_pages": {},
        # Ensure the key exists so it never 'disappears'
        "classifications": [],
        "milestone2": {}
    }

    top_results = search_data.get("top_results", []) or []
    print(f"[INFO] Found {len(top_results)} top results.")

    # Scrape each URL from the search results and run BOTH analyses
    for idx, result in enumerate(top_results, start=1):
        url = (result or {}).get("url")
        title = (result or {}).get("title") or ""
        if not url:
            print(f"[WARN] Result #{idx} missing URL, skipping.")
            continue

        print(f"\n[STEP] #{idx}: {title}  ->  {url}")

        try:
            # ---- SCRAPE ----
            print("[INFO] Scraping page text…")
            scraped_content = scrape_landing_page(url)  # returns { url: "text..." }
            content_text = scraped_content.get(url, "") or ""
            combined_results["scraped_pages"][url] = content_text
            print(f"[OK] Scraped chars: {len(content_text)}")

            # ---- CLASSIFICATION (classification.py) ----
            try:
                print("[INFO] Running content-type classification…")
                content_type = classify_content_with_openai(content_text, title, url)
                combined_results["classifications"].append({
                    "url": url,
                    "title": title,
                    "content_type": content_type
                })
                print(f"[OK] Classification: {content_type}")
            except Exception as e:
                print(f"[ERROR] classification.py failed: {e}")
                # still append a visible placeholder so you know the entry was processed
                combined_results["classifications"].append({
                    "url": url,
                    "title": title,
                    "content_type": "Error"
                })

            # ---- MILESTONE 2 (content_analysis.py) ----
            try:
                print("[INFO] Running Milestone 2 analysis (blueprint/intro/links)…")
                analysis = analyze_page_for_milestone2(content_text, title, url)
                combined_results["milestone2"][url] = analysis
                print("[OK] Milestone 2 analysis stored.")
            except Exception as e:
                print(f"[ERROR] content_analysis.py failed: {e}")
                combined_results["milestone2"][url] = {
                    "blueprint": {"h2": [], "h3": []},
                    "intro_style": {"intro_sample": "", "label": "fluffy", "reason": "Error"},
                    "internal_links": {"links": []}
                }

        except Exception as e:
            print(f"[FATAL] Scrape failed: {e}")
            combined_results["scraped_pages"][url] = {"error": str(e)}
            # still create placeholders so JSON always has consistent shape
            combined_results["classifications"].append({
                "url": url,
                "title": title,
                "content_type": "Error"
            })
            combined_results["milestone2"][url] = {
                "blueprint": {"h2": [], "h3": []},
                "intro_style": {"intro_sample": "", "label": "fluffy", "reason": "Scrape error"},
                "internal_links": {"links": []}
            }

    # Save combined results to JSON
    output_file = "combined_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(combined_results, f, ensure_ascii=False, indent=2)

    print("\n================ SUMMARY ================")
    print(f"Classifications added: {len(combined_results['classifications'])}")
    print(f"Milestone2 pages:      {len(combined_results['milestone2'])}")
    print(f"Saved → {output_file}")


if __name__ == "__main__":
    main()
