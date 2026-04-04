import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from storage.database import get_digest_postings

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "storage"
OUTPUT_PATH = OUTPUT_DIR / "digest.html"


def _score_color(score):
    if score >= 9:
        return "#2d8a4e"
    return "#2563eb"


def _build_html(postings, date_str):
    cards = ""
    for p in postings:
        flags_html = ""
        if p["flags"]:
            try:
                flags = json.loads(p["flags"]) if isinstance(p["flags"], str) else p["flags"]
                for f in flags:
                    if isinstance(f, dict):
                        flags_html += f'<span class="flag">{f.get("flag", "")} — {f.get("note", "")}</span>'
                    else:
                        flags_html += f'<span class="flag">{f}</span>'
            except (json.JSONDecodeError, TypeError):
                pass

        flags_section = f'<div class="flags">{flags_html}</div>' if flags_html else ""

        cards += f"""
        <div class="card">
            <div class="card-header">
                <span class="score" style="background:{_score_color(p['score'])}">{p['score']}/10</span>
                <div>
                    <a class="title" href="{p['url']}" target="_blank">{p['title']}</a>
                    <div class="company">{p['company'] or 'Unknown'}</div>
                </div>
            </div>
            <div class="reasoning">{p['reasoning'] or ''}</div>
            {flags_section}
            <div class="angle"><strong>Application angle:</strong> {p['application_angle'] or 'N/A'}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🍃</text></svg>">
    <title>job-scout digest — {date_str}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f8f9fa;
            color: #1a1a1a;
        }}
        h1 {{
            font-size: 1.4em;
            border-bottom: 2px solid #1a1a1a;
            padding-bottom: 8px;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 24px;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .card-header {{
            display: flex;
            align-items: flex-start;
            gap: 14px;
            margin-bottom: 12px;
        }}
        .score {{
            color: white;
            font-weight: 700;
            font-size: 0.9em;
            padding: 4px 10px;
            border-radius: 6px;
            white-space: nowrap;
        }}
        .title {{
            font-size: 1.15em;
            font-weight: 600;
            color: #1a1a1a;
            text-decoration: none;
        }}
        .title:hover {{
            text-decoration: underline;
        }}
        .company {{
            color: #555;
            font-size: 0.95em;
        }}
        .reasoning {{
            margin-bottom: 10px;
            line-height: 1.5;
        }}
        .flags {{
            margin-bottom: 10px;
        }}
        .flag {{
            background: #fef3c7;
            color: #92400e;
            font-size: 0.85em;
            padding: 3px 10px;
            border-radius: 12px;
            margin-right: 6px;
            display: inline-block;
            margin-bottom: 4px;
        }}
        .angle {{
            font-size: 0.9em;
            color: #444;
            border-top: 1px solid #eee;
            padding-top: 10px;
        }}
        .empty {{
            text-align: center;
            color: #888;
            padding: 40px;
        }}
    </style>
</head>
<body>
    <h1>job-scout digest</h1>
    <div class="subtitle">{date_str} — {len(postings)} match{'es' if len(postings) != 1 else ''} scoring 7+</div>
    {cards if cards else '<div class="empty">No matches scoring 7+ in this period.</div>'}
</body>
</html>"""


def build_digest(min_score=7, hours=24):
    postings = get_digest_postings(min_score=min_score, hours=hours)
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    period = "last 7 days" if hours > 24 else "last 24 hours"

    html = _build_html(postings, f"{date_str} ({period})")

    dated_path = OUTPUT_DIR / f"digest-{datetime.now().strftime('%Y-%m-%d')}.html"
    dated_path.write_text(html)
    logger.info(f"Digest saved to {dated_path}")

    OUTPUT_PATH.write_text(html)
    logger.info(f"Latest digest copied to {OUTPUT_PATH}")

    # Plain-text summary to terminal
    print(f"\nDIGEST — {date_str} ({period})")
    print(f"{len(postings)} posting{'s' if len(postings) != 1 else ''} scoring {min_score}+\n")

    if not postings:
        print("  No matches today.")
    else:
        for p in postings:
            print(f"  [{p['score']}/10] {p['title']} @ {p['company'] or 'Unknown'}")
            print(f"    {p['reasoning'] or ''}")
            flags_str = ""
            if p["flags"]:
                try:
                    flags = json.loads(p["flags"]) if isinstance(p["flags"], str) else p["flags"]
                    flag_names = [f.get("flag", str(f)) if isinstance(f, dict) else str(f) for f in flags]
                    flags_str = ", ".join(flag_names)
                except (json.JSONDecodeError, TypeError):
                    pass
            if flags_str:
                print(f"    Flags: {flags_str}")
            print()

    return len(postings)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Build job-scout digest")
    parser.add_argument("--history", action="store_true",
                        help="Show all 7+ postings from the last 7 days")
    args = parser.parse_args()
    hours = 168 if args.history else 24
    build_digest(hours=hours)
