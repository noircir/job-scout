import json
import os
import sqlite3
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from storage.database import get_connection, init_db

app = FastAPI()

PORT = 8502


def _ensure_dashboard_columns():
    """Add starred and notes columns to scores table if they don't exist."""
    conn = get_connection()
    cursor = conn.execute("PRAGMA table_info(scores)")
    columns = {row["name"] for row in cursor.fetchall()}
    if "starred" not in columns:
        conn.execute("ALTER TABLE scores ADD COLUMN starred BOOLEAN DEFAULT 0")
    if "notes" not in columns:
        conn.execute("ALTER TABLE scores ADD COLUMN notes TEXT DEFAULT NULL")
    if "skill_gaps" not in columns:
        conn.execute("ALTER TABLE scores ADD COLUMN skill_gaps TEXT DEFAULT NULL")
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup():
    init_db()
    _ensure_dashboard_columns()


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE


@app.get("/api/listings")
def api_listings(
    min_score: int = Query(0),
    days: int = Query(0),
    source: str = Query(""),
    starred_only: bool = Query(False),
    has_notes: bool = Query(False),
):
    conn = get_connection()

    where = ["s.score IS NOT NULL", "s.score > 0"]
    params = []

    if min_score > 0:
        where.append("s.score >= ?")
        params.append(min_score)

    if days > 0:
        where.append(f"s.date_scored >= datetime('now', '-{int(days)} day')")

    if source:
        where.append("p.source LIKE ?")
        params.append(f"%{source}%")

    if starred_only:
        where.append("s.starred = 1")

    if has_notes:
        where.append("s.notes IS NOT NULL AND s.notes != ''")

    where_sql = " AND ".join(where)

    rows = conn.execute(
        f"""SELECT p.id, p.source, p.url, p.title, p.company, p.description,
                   p.salary_text, p.location, p.remote_type, p.date_posted, p.date_found,
                   s.score, s.hard_constraint_pass, s.flags,
                   s.reasoning, s.application_angle, s.date_scored,
                   s.skill_gaps, s.starred, s.notes
            FROM postings p
            JOIN scores s ON s.id = (
                SELECT s2.id FROM scores s2
                WHERE s2.posting_id = p.id
                ORDER BY s2.id DESC LIMIT 1
            )
            WHERE {where_sql}
            ORDER BY COALESCE(s.starred, 0) DESC, s.score DESC, s.date_scored DESC""",
        params,
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        if d.get("flags") and isinstance(d["flags"], str):
            try:
                d["flags"] = json.loads(d["flags"])
            except json.JSONDecodeError:
                pass
        if d.get("skill_gaps") and isinstance(d["skill_gaps"], str):
            try:
                d["skill_gaps"] = json.loads(d["skill_gaps"])
            except json.JSONDecodeError:
                pass
        d["starred"] = bool(d.get("starred"))
        results.append(d)

    return results


@app.post("/api/listings/{posting_id}/star")
def toggle_star(posting_id: int):
    conn = get_connection()
    current = conn.execute(
        "SELECT starred FROM scores WHERE posting_id = ?", (posting_id,)
    ).fetchone()
    if not current:
        conn.close()
        return JSONResponse({"error": "not found"}, status_code=404)
    new_val = 0 if current["starred"] else 1
    conn.execute(
        "UPDATE scores SET starred = ? WHERE posting_id = ?", (new_val, posting_id)
    )
    conn.commit()
    conn.close()
    return {"posting_id": posting_id, "starred": bool(new_val)}


@app.post("/api/listings/{posting_id}/notes")
def save_notes(posting_id: int, body: dict):
    conn = get_connection()
    conn.execute(
        "UPDATE scores SET notes = ? WHERE posting_id = ?",
        (body.get("notes", ""), posting_id),
    )
    conn.commit()
    conn.close()
    return {"posting_id": posting_id, "notes": body.get("notes", "")}


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>job-scout</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🍃</text></svg>">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f0f0; color: #222; }

.header { background: #1a1a2e; color: #fff; padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
.header h1 { font-size: 18px; font-weight: 600; }
.header .port { font-size: 12px; color: #888; margin-left: 8px; }
.header nav a { color: #556; font-size: 12px; margin-left: 12px; text-decoration: none; }
.header nav a:hover { color: #aaa; }
.header nav a.active { color: #6cf; }

.filters { background: #fff; padding: 16px 24px; border-bottom: 1px solid #ddd; display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
.filter-group { display: flex; flex-direction: column; gap: 4px; }
.filter-group label { font-size: 11px; font-weight: 600; text-transform: uppercase; color: #666; }
.filter-group select, .filter-group input { padding: 6px 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 13px; }
.filter-group .checkbox-wrap { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.filter-group .checkbox-wrap input { width: auto; }

.stats { padding: 8px 24px; font-size: 13px; color: #666; background: #fafafa; border-bottom: 1px solid #eee; }

.toolbar { padding: 8px 24px; background: #fff; border-bottom: 1px solid #eee; display: flex; gap: 8px; align-items: center; }
.map-toggle { background: none; border: 1px solid #ccc; border-radius: 12px; padding: 3px 10px; font-size: 12px; color: #666; cursor: pointer; margin-left: auto; }
.map-toggle:hover { background: #f5f5f5; }

.cards { max-width: 960px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }

.card { background: #fff; border-radius: 10px; padding: 16px 20px; border: 2px solid #e8e8e8; transition: border-color 0.2s; }
.card.starred { border-color: #d4a017; }
.card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 10px; }
.card-main { flex: 1; }

.badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 13px; font-weight: 700; color: #fff; min-width: 36px; text-align: center; }
.badge.high { background: #2e7d32; }
.badge.mid { background: #1565c0; }
.badge.low { background: #888; }
.badge.zero { background: #c62828; }

.source-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-left: 6px; vertical-align: middle; }
.source-tag.remoteok { background: #e8f5e9; color: #2e7d32; }
.source-tag.himalayas { background: #e3f2fd; color: #1565c0; }
.source-tag.career_pages { background: #f3e5f5; color: #6a1b9a; }
.source-tag.other { background: #f5f5f5; color: #666; }

.card h3 { font-size: 15px; margin: 4px 0; }
.card .meta { font-size: 13px; color: #555; line-height: 1.6; }
.card .meta span { margin-right: 14px; }
.card .reasoning { font-size: 13px; color: #333; margin-top: 8px; line-height: 1.5; }

.flags { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
.flag { background: #fff8e1; border: 1px solid #ffe082; border-radius: 4px; padding: 2px 8px; font-size: 11px; color: #6d4c00; }

.skill-gaps { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
.skill-gap { background: #fce4ec; border: 1px solid #ef9a9a; border-radius: 4px; padding: 2px 8px; font-size: 11px; color: #b71c1c; }

.angle { margin-top: 6px; background: #e8f5e9; border-radius: 4px; padding: 6px 10px; font-size: 12px; color: #2e7d32; }

.card-actions { display: flex; gap: 8px; align-items: flex-start; margin-top: 8px; padding-top: 8px; border-top: 1px solid #f0f0f0; }
.star-btn { background: none; border: 1px solid #ccc; border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 16px; }
.star-btn.active { border-color: #d4a017; background: #fff8e1; }
.notes-input { flex: 1; padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 12px; font-family: inherit; }
.save-btn { background: #1565c0; color: #fff; border: none; border-radius: 6px; padding: 6px 12px; cursor: pointer; font-size: 12px; }
.save-btn:hover { background: #0d47a1; }
.title-link { color: #1565c0; text-decoration: none; }
.title-link:hover { text-decoration: underline; }

.map-modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 200; }
.cmd-card { background: #1e1e2e; border-radius: 12px; padding: 24px 32px; max-width: 900px; width: 90vw; box-shadow: 0 8px 32px rgba(0,0,0,0.4); position: relative; }
.cmd-card h3 { color: #ccc; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; margin: 16px 0 8px 0; }
.cmd-card h3:first-child { margin-top: 0; }
.cmd-card pre { margin: 0; font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; line-height: 1.8; color: #a0a0a0; }
.cmd-card .cmd { color: #e0e0e0; }
.cmd-card .arr { color: #555; }
.cmd-card .desc { color: #888; }

@media (max-width: 640px) {
  .filters { padding: 12px; gap: 10px; }
  .cards { padding: 10px; }
  .card { padding: 12px; }
  .card-top { flex-direction: column; }
}
</style>
</head>
<body>

<div class="header">
  <div style="display:flex;align-items:center;">
    <h1>job-scout</h1>
    <span class="port">:8502</span>
  </div>
  <nav>
    <a href="http://localhost:8501">:8501 listings</a>
    <a href="#" class="active">:8502 jobs</a>
    <a href="#">:8503</a>
    <a href="#">:8504</a>
    <a href="#">:8505</a>
  </nav>
</div>

<div class="filters">
  <div class="filter-group">
    <label>Date Range</label>
    <select id="f-days">
      <option value="1">Last 24h</option>
      <option value="7" selected>Last 7 days</option>
      <option value="30">Last 30 days</option>
      <option value="0">All time</option>
    </select>
  </div>
  <div class="filter-group">
    <label>Min Score</label>
    <select id="f-score">
      <option value="0">All</option>
      <option value="5">5+</option>
      <option value="7" selected>7+</option>
      <option value="8">8+</option>
      <option value="9">9+</option>
    </select>
  </div>
  <div class="filter-group">
    <label>Source</label>
    <select id="f-source">
      <option value="">All</option>
      <option value="remoteok">RemoteOK</option>
      <option value="himalayas">Himalayas</option>
      <option value="career_pages">Career Pages</option>
    </select>
  </div>
  <div class="filter-group">
    <label>Filter</label>
    <div class="checkbox-wrap">
      <input type="checkbox" id="f-starred">
      <label for="f-starred" style="font-size:13px;text-transform:none;color:#333;">Starred only</label>
    </div>
    <div class="checkbox-wrap">
      <input type="checkbox" id="f-notes">
      <label for="f-notes" style="font-size:13px;text-transform:none;color:#333;">Has notes</label>
    </div>
  </div>
</div>

<div class="toolbar">
  <button class="map-toggle" id="legend-toggle">Legend</button>
  <button class="map-toggle" id="cmd-toggle">Commands</button>
</div>

<div class="stats" id="stats"></div>
<div class="cards" id="cards"></div>

<script>
document.getElementById('legend-toggle').addEventListener('click', function() {
  var modal = document.createElement('div');
  modal.className = 'map-modal';
  modal.innerHTML = '<div class="cmd-card">' +
    '<button class="close-btn" style="position:absolute;top:8px;right:8px;background:#333;color:#aaa;border:none;border-radius:50%;width:28px;height:28px;font-size:16px;cursor:pointer;line-height:28px;text-align:center;">\\u00d7</button>' +
    '<h3>Sources</h3>' +
    '<pre style="line-height:2.4;">' +
    '<span style="background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;">remoteok</span>  <span class="desc">RemoteOK job board</span>\\n' +
    '<span style="background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;">himalayas</span>  <span class="desc">Himalayas job board</span>\\n' +
    '<span style="background:#f3e5f5;color:#6a1b9a;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;">stripe</span>  <span class="desc">Career pages via Greenhouse, Ashby, or Lever APIs (shows company name)</span>\\n' +
    '<span style="background:#f5f5f5;color:#666;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;">other</span>  <span class="desc">Other sources</span>' +
    '</pre>' +
    '<h3>Card elements</h3>' +
    '<pre style="line-height:2.4;">' +
    '<span style="background:#2e7d32;color:#fff;padding:2px 8px;border-radius:12px;font-weight:700;">9</span> <span style="background:#1565c0;color:#fff;padding:2px 8px;border-radius:12px;font-weight:700;">7</span> <span style="background:#888;color:#fff;padding:2px 8px;border-radius:12px;font-weight:700;">5</span>  <span class="desc">Score badge: green 9+, blue 7-8, grey below 7</span>\\n' +
    '<span style="background:#fff8e1;border:1px solid #ffe082;padding:2px 8px;border-radius:4px;font-size:11px;color:#6d4c00;">flag</span>  <span class="desc">Flags: work auth, timezone, salary not listed, location ambiguity</span>\\n' +
    '<span style="background:#fce4ec;border:1px solid #ef9a9a;padding:2px 8px;border-radius:4px;font-size:11px;color:#b71c1c;">skill gap</span>  <span class="desc">Skill gaps: required skills not in your profile</span>\\n' +
    '<span style="background:#e8f5e9;padding:4px 8px;border-radius:4px;font-size:11px;color:#2e7d32;">angle</span>  <span class="desc">Application angle: which experience to emphasize</span>\\n' +
    '<span style="font-size:16px;">\\u2606</span> / <span style="font-size:16px;">\\u2605</span>  <span class="desc">Star: bookmark postings to revisit</span>' +
    '</pre></div>';
  function closeModal() { if (modal.parentNode) modal.parentNode.removeChild(modal); }
  modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });
  modal.querySelector('.close-btn').addEventListener('click', closeModal);
  document.addEventListener('keydown', function handler(e) { if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', handler); } });
  document.body.appendChild(modal);
});

document.getElementById('cmd-toggle').addEventListener('click', function() {
  var modal = document.createElement('div');
  modal.className = 'map-modal';
  modal.innerHTML = '<div class="cmd-card">' +
    '<button class="close-btn" style="position:absolute;top:8px;right:8px;background:#333;color:#aaa;border:none;border-radius:50%;width:28px;height:28px;font-size:16px;cursor:pointer;line-height:28px;text-align:center;">\\u00d7</button>' +
    '<h3>Pipeline</h3>' +
    '<pre>' +
    '<span class="cmd">python run.py</span>                          <span class="arr">\\u2192</span> <span class="desc">Full pipeline: scrape, pre-filter, score, build digest</span>\\n' +
    '<span class="cmd">python run.py --batch</span>                   <span class="arr">\\u2192</span> <span class="desc">Same but uses Batch API (50% cheaper, slower)</span>\\n' +
    '<span class="cmd">python run.py --dry-run</span>                 <span class="arr">\\u2192</span> <span class="desc">Scrape and save to DB only, no scoring</span>\\n' +
    '<span class="cmd">python run.py --source remoteok</span>         <span class="arr">\\u2192</span> <span class="desc">Run single scraper (remoteok, himalayas, career_pages)</span>' +
    '</pre>' +
    '<h3>Digest</h3>' +
    '<pre>' +
    '<span class="cmd">python -m digest.build_digest</span>           <span class="arr">\\u2192</span> <span class="desc">Build HTML digest (last 24h, score 7+)</span>\\n' +
    '<span class="cmd">python -m digest.build_digest --history</span> <span class="arr">\\u2192</span> <span class="desc">Build digest for last 7 days</span>' +
    '</pre>' +
    '<h3>Resume Tailoring</h3>' +
    '<pre>' +
    '<span class="cmd">python -m resume.tailor --company X --jd file.txt</span>              <span class="arr">\\u2192</span> <span class="desc">Tailor resume + cover letter for a job</span>\\n' +
    '<span class="cmd">python -m resume.tailor --company X --jd file.txt --cover-only</span> <span class="arr">\\u2192</span> <span class="desc">Regenerate cover letter only</span>\\n' +
    '<span class="cmd">python -m resume.tailor --company X --jd file.txt --resume-only</span><span class="arr"> \\u2192</span> <span class="desc">Regenerate resume only</span>' +
    '</pre>' +
    '<h3>Dashboard</h3>' +
    '<pre>' +
    '<span class="cmd">python dashboard.py</span>                     <span class="arr">\\u2192</span> <span class="desc">Start dashboard at localhost:8502</span>' +
    '</pre></div>';
  function closeModal() { if (modal.parentNode) modal.parentNode.removeChild(modal); }
  modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });
  modal.querySelector('.close-btn').addEventListener('click', closeModal);
  document.addEventListener('keydown', function handler(e) { if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', handler); } });
  document.body.appendChild(modal);
});

function badgeClass(score) {
  if (score >= 9) return 'high';
  if (score >= 7) return 'mid';
  if (score >= 5) return 'low';
  return 'zero';
}

function sourceClass(source) {
  if (source && source.indexOf('remoteok') >= 0) return 'remoteok';
  if (source && source.indexOf('himalayas') >= 0) return 'himalayas';
  if (source && (source.indexOf('greenhouse') >= 0 || source.indexOf('ashby') >= 0 || source.indexOf('lever') >= 0)) return 'career_pages';
  return 'other';
}

function sourceName(source) {
  if (!source) return '';
  if (source.indexOf('remoteok') >= 0) return 'remoteok';
  if (source.indexOf('himalayas') >= 0) return 'himalayas';
  if (source.indexOf('greenhouse') >= 0) return source.replace('greenhouse_', '');
  if (source.indexOf('ashby') >= 0) return source.replace('ashby_', '');
  if (source.indexOf('lever') >= 0) return source.replace('lever_', '');
  return source;
}

function renderCard(item) {
  const flags = (item.flags || []).map(function(f) {
    var text = typeof f === 'object' ? (f.flag + (f.note ? ': ' + f.note : '')) : f;
    return '<span class="flag">' + esc(text) + '</span>';
  }).join('');

  const skillGaps = (item.skill_gaps || []).map(function(g) {
    return '<span class="skill-gap">' + esc(g) + '</span>';
  }).join('');

  var starred = item.starred ? 'starred' : '';
  var starActive = item.starred ? 'active' : '';
  var starSymbol = item.starred ? '\\u2605' : '\\u2606';
  var notes = item.notes || '';

  var sc = sourceClass(item.source);
  var sn = sourceName(item.source);

  return '<div class="card ' + starred + '" data-id="' + item.id + '">' +
    '<div class="card-top">' +
      '<div class="card-main">' +
        '<span class="badge ' + badgeClass(item.score) + '">' + item.score + '</span>' +
        (sn ? ' <span class="source-tag ' + esc(sc) + '">' + esc(sn) + '</span>' : '') +
        (item.url ? '<h3><a href="' + esc(item.url) + '" target="_blank" class="title-link">' + esc(item.title || 'Untitled') + '</a></h3>' :
                    '<h3>' + esc(item.title || 'Untitled') + '</h3>') +
        '<div class="meta">' +
          '<span>' + esc(item.company || '') + '</span>' +
          (item.location ? '<span>' + esc(item.location) + '</span>' : '') +
          (item.salary_text ? '<span>' + esc(item.salary_text) + '</span>' : '') +
        '</div>' +
        (item.reasoning ? '<div class="reasoning">' + esc(item.reasoning) + '</div>' : '') +
        (flags ? '<div class="flags">' + flags + '</div>' : '') +
        (skillGaps ? '<div class="skill-gaps">' + skillGaps + '</div>' : '') +
        (item.application_angle ? '<div class="angle"><strong>Application angle:</strong> ' + esc(item.application_angle) + '</div>' : '') +
      '</div>' +
    '</div>' +
    '<div class="card-actions">' +
      '<button class="star-btn ' + starActive + '" onclick="toggleStar(' + item.id + ', this)">' + starSymbol + '</button>' +
      '<input class="notes-input" placeholder="Add a note..." value="' + esc(notes) + '" id="notes-' + item.id + '">' +
      '<button class="save-btn" onclick="saveNotes(' + item.id + ')">Save</button>' +
    '</div>' +
  '</div>';
}

function esc(s) {
  if (!s) return '';
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

async function loadListings() {
  var params = new URLSearchParams({
    min_score: document.getElementById('f-score').value,
    days: document.getElementById('f-days').value,
    source: document.getElementById('f-source').value,
    starred_only: document.getElementById('f-starred').checked,
    has_notes: document.getElementById('f-notes').checked,
  });
  var resp = await fetch('/api/listings?' + params);
  var data = await resp.json();
  document.getElementById('stats').textContent = data.length + ' posting(s)';
  document.getElementById('cards').innerHTML = data.map(renderCard).join('');
}

async function toggleStar(id, btn) {
  await fetch('/api/listings/' + id + '/star', { method: 'POST' });
  loadListings();
}

async function saveNotes(id) {
  var notes = document.getElementById('notes-' + id).value;
  await fetch('/api/listings/' + id + '/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes: notes }),
  });
}

document.querySelectorAll('.filters select, .filters input').forEach(function(el) {
  el.addEventListener('change', loadListings);
});

loadListings();
</script>
</body>
</html>"""


if __name__ == "__main__":
    print(f"Dashboard running at http://localhost:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
