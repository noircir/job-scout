import json
import logging
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "career_pages.json"

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
GREENHOUSE_JOB_API = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"
ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{board_token}"
LEVER_API = "https://api.lever.co/v0/postings/{board_token}?mode=json&limit=100"

TITLE_FILTERS = ["ai", "llm", "machine learning", "ml engineer", "nlp", "data scientist",
                 "deep learning", "ai engineer", "ml infrastructure", "generative"]


def _load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _title_matches(title):
    title_lower = title.lower()
    return any(term in title_lower for term in TITLE_FILTERS)


def _strip_html(text):
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _scrape_greenhouse(client, company_name, board_token):
    results = []
    url = GREENHOUSE_API.format(board_token=board_token)

    try:
        resp = client.get(url, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"  {company_name}: Greenhouse API failed: {e}")
        return []

    data = resp.json()
    jobs = data.get("jobs", [])
    logger.info(f"  {company_name}: {len(jobs)} total jobs on Greenhouse")

    matching = [j for j in jobs if _title_matches(j.get("title", ""))]
    logger.info(f"  {company_name}: {len(matching)} match keyword filters")

    for job in matching:
        job_id = job["id"]
        title = job.get("title", "")
        location = job.get("location", {}).get("name", "")
        job_url = job.get("absolute_url", "")

        description = ""
        detail_url = GREENHOUSE_JOB_API.format(board_token=board_token, job_id=job_id)
        try:
            detail_resp = client.get(detail_url, timeout=20)
            detail_resp.raise_for_status()
            detail_data = detail_resp.json()
            description = _strip_html(detail_data.get("content", ""))
        except httpx.HTTPError as e:
            logger.warning(f"    Failed to fetch details for {title}: {e}")

        results.append({
            "source": f"greenhouse_{board_token}",
            "url": job_url,
            "title": title,
            "company": company_name,
            "description": description,
            "salary_text": None,
            "location": location,
            "remote_type": None,
            "date_posted": job.get("updated_at", ""),
            "raw_html": None,
        })

        time.sleep(0.5)

    return results


def _scrape_ashby(client, company_name, board_token):
    results = []
    url = ASHBY_API.format(board_token=board_token)

    try:
        resp = client.get(url, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"  {company_name}: Ashby API failed: {e}")
        return []

    data = resp.json()
    jobs = data.get("jobs", [])
    logger.info(f"  {company_name}: {len(jobs)} total jobs on Ashby")

    matching = [j for j in jobs if _title_matches(j.get("title", ""))]
    logger.info(f"  {company_name}: {len(matching)} match keyword filters")

    for job in matching:
        title = job.get("title", "")
        location = job.get("location", "")
        job_url = job.get("jobUrl", "")
        description = _strip_html(job.get("descriptionHtml", "")) or job.get("descriptionPlain", "")

        results.append({
            "source": f"ashby_{board_token}",
            "url": job_url,
            "title": title,
            "company": company_name,
            "description": description,
            "salary_text": None,
            "location": location,
            "remote_type": "fully_remote" if job.get("isRemote") else None,
            "date_posted": job.get("publishedAt", ""),
            "raw_html": None,
        })

    return results


def _scrape_lever(client, company_name, board_token):
    results = []
    url = LEVER_API.format(board_token=board_token)

    try:
        resp = client.get(url, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"  {company_name}: Lever API failed: {e}")
        return []

    jobs = resp.json()
    if not isinstance(jobs, list):
        logger.error(f"  {company_name}: unexpected Lever response format")
        return []

    logger.info(f"  {company_name}: {len(jobs)} total jobs on Lever")

    matching = [j for j in jobs if _title_matches(j.get("text", ""))]
    logger.info(f"  {company_name}: {len(matching)} match keyword filters")

    for job in matching:
        title = job.get("text", "")
        categories = job.get("categories", {})
        location = categories.get("location", "")
        job_url = job.get("hostedUrl", "")
        description = job.get("descriptionPlain", "") or _strip_html(job.get("description", ""))
        workplace = job.get("workplaceType", "")

        results.append({
            "source": f"lever_{board_token}",
            "url": job_url,
            "title": title,
            "company": company_name,
            "description": description,
            "salary_text": None,
            "location": location,
            "remote_type": "fully_remote" if workplace == "remote" else None,
            "date_posted": "",
            "raw_html": None,
        })

    return results


def scrape():
    config = _load_config()
    all_results = []

    client = httpx.Client(headers={"User-Agent": "job-scout/1.0"})

    try:
        # Greenhouse companies
        for company in config.get("greenhouse", {}).get("companies", []):
            name = company["name"]
            token = company["board_token"]
            try:
                results = _scrape_greenhouse(client, name, token)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"  {name}: unexpected error: {e}")

        # Ashby companies
        for company in config.get("ashby", {}).get("companies", []):
            name = company["name"]
            token = company["board_token"]
            try:
                results = _scrape_ashby(client, name, token)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"  {name}: unexpected error: {e}")

        # Lever companies
        for company in config.get("lever", {}).get("companies", []):
            name = company["name"]
            token = company["board_token"]
            try:
                results = _scrape_lever(client, name, token)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"  {name}: unexpected error: {e}")

    finally:
        client.close()

    logger.info(f"Career pages: {len(all_results)} matching jobs total")
    return all_results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    postings = scrape()
    print(f"\nFound {len(postings)} matching jobs\n")
    for p in postings:
        print(f"  {p['title']} @ {p['company']}")
        print(f"    {p['url']}")
        print(f"    location: {p['location']}")
        print()
