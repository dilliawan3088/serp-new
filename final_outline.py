# final_outline.py
"""
Milestone 4 — The Final Output: Intelligent Content Outline

Takes inputs from:
- Milestone 2 (blueprints, intros, internal links)
- Milestone 3 (quality gaps + strategy with approved_angle)
- SERP (PAA, featured snippet, AI overview)

Produces:
- final_outline: { angle, content_play, h1, sections[], faq[], notes }
"""

from typing import Dict, Any, List, Union

# --------------------------
# Helpers
# --------------------------

def _norm(s: str) -> str:
    return (s or "").strip()

def _take(lst: List[str], n: int) -> List[str]:
    return [x for x in (lst or []) if _norm(x)][:n]

def _angle(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the user-approved content angle (from Milestone 3)."""
    approved_id = (strategy or {}).get("approved_angle") or "A"
    angles = (strategy or {}).get("proposed_angles", []) or []
    for a in angles:
        if a.get("id") == approved_id:
            return a
    return angles[0] if angles else {"id": approved_id, "title": "", "how": ""}

def _content_play(intent: str, classifications: List[Dict[str, Any]]) -> str:
    """Pick content play based on intent + competitor shape."""
    if "list" in intent.lower() or any(c.get("content_type") == "List Post" for c in classifications):
        return "Create a better list"
    if "transactional" in intent.lower() or any(c.get("content_type") == "Product Page" for c in classifications):
        return "Optimize a product/service page"
    if "informational" in intent.lower() or any(c.get("content_type") == "How-To Guide" for c in classifications):
        return "Write a How-To Guide with steps + visuals"
    return "Hybrid Play (mix parity + differentiation)"

def _merge_sections(common_topics: List[Union[str, dict]], missing: List[Union[str, dict]], paa: List[str]) -> List[Dict[str, Any]]:
    """Build the section structure from common, missing, and PAA."""
    sections: List[Dict[str, Any]] = []

    def _to_str(x: Union[str, dict]) -> str:
        if isinstance(x, dict):
            return x.get("topic") or x.get("title") or ""
        return str(x)

    # consensus backbone
    for t in common_topics:
        t_str = _to_str(t)
        if not t_str:
            continue
        sections.append({
            "h2": t_str.title(),
            "h3": [],
            "notes": ["Cover as competitors do, but clearer and with examples."]
        })

    # missing angles
    for t in missing:
        t_str = _to_str(t)
        if not t_str:
            continue
        sections.append({
            "h2": t_str.title(),
            "h3": [],
            "notes": ["This is a missing angle: emphasize differentiation."]
        })

    # people also ask → FAQ block at the end
    faq = _take(paa, 6)
    if faq:
        sections.append({
            "h2": "FAQs",
            "h3": faq,
            "notes": ["Answer concisely; use schema markup if publishing."]
        })

    return sections

# --------------------------
# Main generator
# --------------------------

def generate_final_outline(cr: Dict[str, Any]) -> Dict[str, Any]:
    """
    cr = combined_results (dict from main.py after milestone 3)
    Returns final_outline dict.
    """

    strategy = cr.get("milestone3_strategy", {}) or {}
    qg = cr.get("quality_gaps", {}) or {}
    search = cr.get("search_results", {}) or {}
    classifications = cr.get("classifications", [])

    # angle & play
    angle = _angle(strategy)
    play = _content_play(strategy.get("primary_intent", ""), classifications)

    # content pieces
    common_topics = qg.get("outline_comparison", {}).get("common_topics_by_count", []) or []
    missing_angles = qg.get("outline_comparison", {}).get("gpt_missing_angles", []) or []
    paa = search.get("people_also_ask", []) or []

    sections = _merge_sections(common_topics, missing_angles, paa)

    # H1 generation
    h1 = f"{angle.get('title') or cr.get('search_query','').title()} — {play}"

    final_outline = {
        "angle": angle,
        "content_play": play,
        "h1": h1,
        "sections": sections,
        "notes_global": [
            "Insert CTAs after major value sections.",
            "Add at least 3–5 fresh 2024–25 data points.",
            "Use screenshots/visuals where possible.",
            "Keep intro direct and outcome-oriented."
        ]
    }
    return final_outline

# --------------------------
# Pretty printer (Markdown)
# --------------------------

def render_outline_md(outline: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"# {outline.get('h1','')}")
    lines.append("")
    lines.append(f"**Content Play**: {outline.get('content_play','')}")
    lines.append("")
    angle = outline.get("angle", {})
    if angle:
        lines.append(f"**Chosen Angle [{angle.get('id','')}]:** {angle.get('title','')}")
        if angle.get("how"):
            lines.append(f"_How_: {angle.get('how')}")
        lines.append("")
    for sec in outline.get("sections", []):
        lines.append(f"## {sec.get('h2','')}")
        for h3 in sec.get("h3", []):
            lines.append(f"- {h3}")
        for note in sec.get("notes", []):
            lines.append(f"[Note: {note}]")
        lines.append("")
    if outline.get("notes_global"):
        lines.append("### Global Notes")
        for n in outline["notes_global"]:
            lines.append(f"- {n}")
    return "\n".join(lines)
