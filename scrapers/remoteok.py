import httpx
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

API_URL = "https://remoteok.com/api"

TAG_FILTERS = {"ai", "ml", "machine learning", "llm", "data science", "deep learning"}
TEXT_FILTERS = ["machine learning", "llm", "nlp", "data pipeline", "artificial intelligence"]

# Broader tags that only count when paired with a text match
BROAD_TAGS = {"python", "data"}


def _matches_broad_tag(job):
    """Python/data tags only match if the title/description also mentions AI-related terms."""
    tags = {t.lower() for t in job.get("tags", [])}
    if not (tags & BROAD_TAGS):
        return False
    text = f"{job.get('position', '')} {job.get('description', '')}".lower()
    ai_terms = ["ai", "ml", "llm", "machine learning", "neural", "model", "nlp", "deep learning"]
    return any(term in text for term in ai_terms)


def _matches_filters(job):
    tags = {t.lower() for t in job.get("tags", [])}
    if tags & TAG_FILTERS:
        return True

    text = f"{job.get('position', '')} {job.get('description', '')}".lower()
    if any(term in text for term in TEXT_FILTERS):
        return True

    return _matches_broad_tag(job)


def _build_posting(job):
    job_id = job.get("id", "")
    slug = job.get("slug", "")
    company = job.get("company", "")

    salary_parts = []
    if job.get("salary_min"):
        salary_parts.append(str(job["salary_min"]))
    if job.get("salary_max"):
        salary_parts.append(str(job["salary_max"]))
    salary_text = " - ".join(salary_parts) if salary_parts else None

    return {
        "source": "remoteok",
        "url": f"https://remoteok.com/remote-jobs/{job_id}" if job_id else f"https://remoteok.com/{slug}",
        "title": job.get("position", ""),
        "company": company,
        "description": job.get("description", ""),
        "salary_text": salary_text,
        "location": job.get("location") or "Remote",
        "remote_type": "fully_remote",
        "date_posted": job.get("date", ""),
        "raw_html": None,
    }


def scrape():
    try:
        resp = httpx.get(API_URL, headers={"User-Agent": "job-scout/1.0"}, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"RemoteOK API request failed: {e}")
        return []

    data = resp.json()

    # First element is metadata, skip it
    jobs = data[1:] if isinstance(data, list) and len(data) > 1 else []

    results = []
    for job in jobs:
        if _matches_filters(job):
            results.append(_build_posting(job))

    logger.info(f"RemoteOK: {len(results)} matching jobs out of {len(jobs)} total")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    postings = scrape()
    print(f"\nFound {len(postings)} matching jobs\n")
    for p in postings[:5]:
        print(f"  {p['title']} @ {p['company']}")
        print(f"    {p['url']}")
        print(f"    salary: {p['salary_text'] or 'not listed'}")
        print()
