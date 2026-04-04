# job-scout

Remote job boards post hundreds of listings a day, and it takes time to manually browse them and figure out what jobs are relevant. This program automates that process. It scrapes multiple job boards on a daily cron schedule, sends each new posting to an LLM that scores it against a configurable candidate profile, and compiles the high-scoring matches into a single HTML digest. No daily effort, no missed postings. The cost is a single-digit dollar amount per month in API calls.

## What it does

The system runs in three stages, once a day:

**1. Scrape.** Scrapers visit job boards and collect new postings. Each board has its own scraper because every site structures its data differently. Currently scanning RemoteOK, Himalayas, and individual company career pages via Greenhouse, Ashby, and Lever APIs. Easy to add more.

**2. Score.** Each new posting gets sent to an LLM along with a profile document that describes: hard constraints (remote only, salary floor, seniority level), preferred role types, skills to match against, things that lower the score, and how to handle ambiguous situations like US work authorization for non-US applicants. The LLM reads the job description against this profile and returns a structured score from 0 to 10, with reasoning, flags, skill gap analysis, and a suggested angle for the application. A pre-filter skips obviously irrelevant postings before any API call is made.

**3. Digest.** Postings that score 7 or higher get compiled into an HTML page: title, company, score, why it matched, any flags (work authorization questions, timezone concerns), and a suggested application angle. One page to check each morning instead of eight job boards.

Postings are stored in a SQLite database. The system tracks every posting it has ever seen and skips duplicates, so the same job never appears twice.

## What the scoring checks

The profile document (`config/profile.json`) controls everything the scorer evaluates. The sample file shows the full structure. Here's what it covers:

**Hard constraints** are pass/fail. If a posting fails any one of these, it scores 0 regardless of everything else. Examples: must be remote, salary must meet a floor, no entry-level roles, no security clearance.

**Work authorization** is more nuanced than a yes/no filter. The scorer understands different employment arrangements (contractor, employer-of-record, direct W-2) and knows that "must be authorized to work in the US" is often boilerplate that doesn't apply to international contractors. It flags these instead of auto-rejecting.

**Preferences** affect the score on a weighted scale. An LLM pipeline role at a remote-first startup paying in USD scores higher than a Kubernetes-heavy DevOps role at a company that says "remote but come to the office Tuesdays." The weights are configurable.

**Skill matching** compares job requirements against three tiers: skills with production experience, skills with working knowledge, and skills explicitly not claimed. The scorer estimates overlap percentage and lists gaps.

**Application angle** is a short note on which parts of the candidate's experience to emphasize for that specific role. This feeds into the resume tailoring step.

## Resume tailoring

For postings worth applying to, `resume/tailor.py` reads a master resume and the job description, then rewrites the profile summary to mirror the JD's language and reorders bullets to lead with the most relevant experience. It also drafts a cover letter. Output is markdown and PDF.

## Project structure

```
job-scout/
├── .env.sample                 ← API key template
├── config/
│   ├── profile.json.sample     ← candidate profile template
│   └── career_pages.json.sample ← company career pages and ATS types
├── scrapers/
│   ├── remoteok.py             ← RemoteOK JSON API
│   ├── himalayas.py            ← Himalayas job board
│   └── career_pages.py         ← Greenhouse, Ashby, Lever APIs
├── scorer/
│   ├── score.py                ← sends posting + profile to LLM, returns structured score
│   └── batch.py                ← batch scoring for scheduled runs (lower cost)
├── digest/
│   └── build_digest.py         ← compiles 7+ matches into dated HTML digest
├── storage/
│   └── database.py             ← SQLite schema and queries
├── resume/
│   ├── master-resume.md.sample ← resume format template
│   └── tailor.py               ← LLM-powered resume + cover letter generation
├── run.py                      ← full pipeline: scrape → score → digest
└── requirements.txt
```

## Setup

**Requirements:** Python 3.11+, an API key for an LLM provider.

```bash
git clone https://github.com/youruser/job-scout.git
cd job-scout
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy the sample configs and fill in your details:

```bash
cp .env.sample .env
cp config/profile.json.sample config/profile.json
cp config/career_pages.json.sample config/career_pages.json
cp resume/master-resume.md.sample resume/master-resume.md
```

Edit `config/profile.json` with your own constraints, target roles, skills, and preferences. Edit `config/career_pages.json` with the companies to monitor. The sample files have comments explaining every field.

Test the pipeline:

```bash
python run.py --dry-run    # scrapes and stores, skips LLM scoring
python run.py              # full run: scrape, score, digest
```

Set up a daily cron job:

```bash
crontab -e
# Runs at 7 AM daily:
0 7 * * * cd /path/to/job-scout && source venv/bin/activate && python run.py >> storage/cron.log 2>&1
```

## Adding scrapers

Each scraper is a Python file that returns a list of posting dicts matching the database schema. To add a new job board:

1. Create `scrapers/newboard.py` with a `scrape()` function
2. Use `httpx` for sites with APIs, add a `playwright` option for JavaScript-rendered pages
3. Apply keyword filters (configurable per scraper)
4. Return a list of dicts with: `source`, `url`, `title`, `company`, `description`, `salary_text`, `location`, `remote_type`, `date_posted`
5. Import and register it in `run.py`

The career pages scraper reads `config/career_pages.json` for company URLs and ATS types. Add companies there without writing new code.

## Cost

Scoring uses the cheapest available LLM tier. A pre-filter skips obviously
irrelevant postings before any API call is made, and batch mode reduces
costs further for scheduled runs. The monthly API cost for daily scanning
across all sources is negligible.

## Dashboard

```bash
python dashboard.py
```

Opens at localhost:8502. Filters by date, score, and source. Star postings and add notes. The static HTML digest (`digest/build_digest.py`) still works as a standalone fallback.

## What this is not

This is not a job application bot. It does not auto-apply, submit resumes, or interact with job boards on anyone's behalf. It reads and filters. The human still decides what to apply to, reviews the tailored resume, and submits applications.

It also does not scrape anything behind authentication. No LinkedIn login, no account credentials. Public job board pages and APIs only.

## License

MIT