import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS postings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            company TEXT,
            description TEXT,
            salary_text TEXT,
            location TEXT,
            remote_type TEXT,
            date_posted TEXT,
            date_found TEXT NOT NULL,
            raw_html TEXT
        );

        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            posting_id INTEGER NOT NULL REFERENCES postings(id),
            score INTEGER NOT NULL,
            hard_constraint_pass BOOLEAN NOT NULL,
            flags TEXT,
            reasoning TEXT,
            application_angle TEXT,
            date_scored TEXT NOT NULL
        );
    """)
    conn.close()


def add_posting(source, url, title, company=None, description=None,
                salary_text=None, location=None, remote_type=None,
                date_posted=None, raw_html=None):
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO postings
               (source, url, title, company, description, salary_text,
                location, remote_type, date_posted, date_found, raw_html)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source, url, title, company, description, salary_text,
             location, remote_type, date_posted,
             datetime.now().isoformat(), raw_html)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_unscored_postings():
    conn = get_connection()
    rows = conn.execute(
        """SELECT p.* FROM postings p
           LEFT JOIN scores s ON p.id = s.posting_id
           WHERE s.id IS NULL"""
    ).fetchall()
    conn.close()
    return rows


# NOTE: If adding --rescore, carry over starred/notes from the previous row for this posting_id
def add_score(posting_id, score, hard_constraint_pass, flags=None,
              reasoning=None, application_angle=None, skill_gaps=None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO scores
           (posting_id, score, hard_constraint_pass, flags, reasoning,
            application_angle, skill_gaps, date_scored)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (posting_id, score, hard_constraint_pass,
         json.dumps(flags) if flags else None,
         reasoning, application_angle,
         json.dumps(skill_gaps) if skill_gaps else None,
         datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_digest_postings(min_score=7, hours=24):
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """SELECT p.*, s.score, s.hard_constraint_pass, s.flags,
                  s.reasoning, s.application_angle, s.date_scored
           FROM postings p
           JOIN scores s ON p.id = s.posting_id
           WHERE s.score >= ? AND s.date_scored >= ?
           ORDER BY s.score DESC""",
        (min_score, cutoff)
    ).fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()

    # Add a fake posting
    pid = add_posting(
        source="test",
        url="https://example.com/jobs/ai-engineer-123",
        title="Senior AI Engineer",
        company="TestCorp",
        description="Build LLM pipelines for production use.",
        salary_text="$150,000 - $180,000",
        location="Remote",
        remote_type="fully_remote",
        date_posted="2026-03-30"
    )
    print(f"Added posting id: {pid}")

    # Duplicate should return None
    dup = add_posting(source="test", url="https://example.com/jobs/ai-engineer-123",
                      title="Senior AI Engineer")
    print(f"Duplicate insert returned: {dup}")

    # Should show 1 unscored posting
    unscored = get_unscored_postings()
    print(f"Unscored postings: {len(unscored)}")
    print(f"  → {unscored[0]['title']} at {unscored[0]['company']}")

    # Score it
    add_score(
        posting_id=pid,
        score=8,
        hard_constraint_pass=True,
        flags=["work_auth_question"],
        reasoning="Strong LLM pipeline match, remote-first, good salary range.",
        application_angle="Lead with the 1.5M pipeline project."
    )

    # Should show 0 unscored now
    unscored = get_unscored_postings()
    print(f"Unscored after scoring: {len(unscored)}")

    # Should appear in digest
    digest = get_digest_postings(min_score=7)
    print(f"Digest postings (score >= 7): {len(digest)}")
    print(f"  → {digest[0]['title']} — score {digest[0]['score']}: {digest[0]['reasoning']}")

    # Clean up test db
    Path(DB_PATH).unlink()
    print("\nTest passed — database deleted.")
