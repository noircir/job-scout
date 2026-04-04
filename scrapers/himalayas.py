import httpx
import logging
import time

logger = logging.getLogger(__name__)

SEARCH_URL = "https://himalayas.app/jobs/api/search"

SEARCH_QUERIES = [
    "AI engineer",
    "machine learning",
    "LLM",
    "NLP",
    "data pipeline",
    "ML engineer",
]

TEXT_FILTERS = ["ai", "llm", "machine learning", "nlp", "data pipeline", "artificial intelligence"]
CATEGORY_FILTERS = {"ai", "ml", "machine learning", "data science", "deep learning"}


def _matches_filters(job):
    categories = {c.lower() for c in job.get("categories", [])}
    parent_categories = {c.lower() for c in job.get("parentCategories", [])}
    all_categories = categories | parent_categories
    if all_categories & CATEGORY_FILTERS:
        return True

    text = f"{job.get('title', '')} {job.get('excerpt', '')} {job.get('description', '')}".lower()
    return any(term in text for term in TEXT_FILTERS)


def _build_posting(job):
    salary_parts = []
    if job.get("minSalary"):
        salary_parts.append(str(job["minSalary"]))
    if job.get("maxSalary"):
        salary_parts.append(str(job["maxSalary"]))
    salary_text = " - ".join(salary_parts) if salary_parts else None
    if salary_text and job.get("currency"):
        salary_text = f"{salary_text} {job['currency']}"

    url = job.get("applicationLink") or f"https://himalayas.app/jobs/{job.get('guid', '')}"

    return {
        "source": "himalayas",
        "url": url,
        "title": job.get("title", ""),
        "company": job.get("companyName", ""),
        "description": job.get("description", ""),
        "salary_text": salary_text,
        "location": ", ".join(job.get("locationRestrictions", [])) or "Remote",
        "remote_type": "fully_remote",
        "date_posted": job.get("pubDate", ""),
        "raw_html": None,
    }


def _fetch_query(client, query, max_pages=3):
    jobs = []
    for page in range(1, max_pages + 1):
        try:
            resp = client.get(SEARCH_URL, params={"q": query, "page": page}, timeout=30)
            if resp.status_code == 429:
                logger.warning(f"Rate limited on query '{query}' page {page}, stopping this query")
                break
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Himalayas request failed for '{query}' page {page}: {e}")
            break

        data = resp.json()
        page_jobs = data if isinstance(data, list) else data.get("jobs", [])

        if not page_jobs:
            break

        jobs.extend(page_jobs)

        if len(page_jobs) < 20:
            break

        time.sleep(0.5)

    return jobs


def scrape():
    client = httpx.Client(headers={"User-Agent": "job-scout/1.0"})
    seen_urls = set()
    results = []

    try:
        for query in SEARCH_QUERIES:
            logger.info(f"  Himalayas: searching '{query}'...")
            jobs = _fetch_query(client, query)

            for job in jobs:
                if not _matches_filters(job):
                    continue

                posting = _build_posting(job)
                if posting["url"] in seen_urls:
                    continue

                seen_urls.add(posting["url"])
                results.append(posting)

            time.sleep(0.5)
    finally:
        client.close()

    logger.info(f"Himalayas: {len(results)} matching jobs after dedup")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    postings = scrape()
    print(f"\nFound {len(postings)} matching jobs\n")
    for p in postings[:10]:
        print(f"  {p['title']} @ {p['company']}")
        print(f"    {p['url']}")
        print(f"    salary: {p['salary_text'] or 'not listed'}")
        print()
