import argparse
import json
import logging
import re
import time

from scrapers import remoteok
from scrapers import himalayas
from scrapers import career_pages
from storage.database import init_db, add_posting, get_unscored_postings, add_score
from scorer.score import score_posting
from scorer.batch import score_batch
from digest.build_digest import build_digest

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SCRAPERS = {
    "remoteok": remoteok.scrape,
    "himalayas": himalayas.scrape,
    "career_pages": career_pages.scrape,
}

# Pre-filter: reject these before sending to the scorer
TITLE_REJECT = [
    "intern", "co-op", "junior", "entry level",
    "director of nursing", "nurse", "physician", "dentist",
    "veterinary", "pharmacist", "therapist", "social worker",
    "teacher", "professor", "accountant", "legal counsel", "attorney",
    "sales representative", "account executive", "business development rep",
]

DESCRIPTION_REJECT = [
    "must work on-site", "no remote", "in-office required",
]


def _word_boundary_pattern(phrase):
    return re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)


TITLE_PATTERNS = [_word_boundary_pattern(p) for p in TITLE_REJECT]
DESCRIPTION_PATTERNS = [_word_boundary_pattern(p) for p in DESCRIPTION_REJECT]


def _pre_filter(postings):
    passed = []
    rejected_count = 0
    title_rejects = 0
    desc_rejects = 0

    for posting in postings:
        title = posting["title"] or ""
        description = posting["description"] or ""
        rejected = False

        for i, pattern in enumerate(TITLE_PATTERNS):
            if pattern.search(title):
                logger.info(f"  Pre-filtered: \"{title}\" (title matched: \"{TITLE_REJECT[i]}\")")
                add_score(
                    posting_id=posting["id"], score=0,
                    hard_constraint_pass=False,
                    reasoning=f"Pre-filtered: title matched \"{TITLE_REJECT[i]}\"",
                )
                title_rejects += 1
                rejected = True
                break

        if not rejected:
            for i, pattern in enumerate(DESCRIPTION_PATTERNS):
                if pattern.search(description):
                    logger.info(f"  Pre-filtered: \"{title}\" (description matched: \"{DESCRIPTION_REJECT[i]}\")")
                    add_score(
                        posting_id=posting["id"], score=0,
                        hard_constraint_pass=False,
                        reasoning=f"Pre-filtered: description matched \"{DESCRIPTION_REJECT[i]}\"",
                    )
                    desc_rejects += 1
                    rejected = True
                    break

        if rejected:
            rejected_count += 1
        else:
            passed.append(posting)

    if rejected_count:
        logger.info(f"\nPre-filtered {rejected_count} postings ({title_rejects} title, {desc_rejects} description)")

    return passed


def main():
    parser = argparse.ArgumentParser(description="job-scout pipeline")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape and save to DB, but skip API scoring")
    parser.add_argument("--source", choices=list(SCRAPERS.keys()),
                        help="Run only one scraper (default: all)")
    parser.add_argument("--batch", action="store_true",
                        help="Use Batch API for scoring (50%% cheaper, slower)")
    args = parser.parse_args()

    init_db()

    # 1. Scrape
    sources = [args.source] if args.source else list(SCRAPERS.keys())
    all_postings = []
    for source in sources:
        logger.info(f"Scraping {source}...")
        postings = SCRAPERS[source]()
        all_postings.extend(postings)
        logger.info(f"  {source}: {len(postings)} matching jobs")

    # 2. Add to database (skips duplicates)
    new_count = 0
    for posting in all_postings:
        pid = add_posting(**posting)
        if pid is not None:
            new_count += 1
    skipped = len(all_postings) - new_count
    logger.info(f"\n{new_count} new postings added, {skipped} duplicates skipped")

    # 3. Get unscored postings
    unscored = get_unscored_postings()
    logger.info(f"{len(unscored)} unscored postings to process")

    # 4. Pre-filter obvious rejects
    logger.info("\nPre-filtering...")
    to_score = _pre_filter(unscored)
    logger.info(f"{len(to_score)} postings remaining for scoring")

    if args.dry_run:
        logger.info("\n--dry-run: skipping scoring")
        return

    # 5. Score postings
    scored_results = []

    if args.batch:
        # Batch API mode (50% cheaper, async)
        logger.info(f"\nSubmitting {len(to_score)} postings to Batch API...")
        batch_results = score_batch(to_score)

        for posting in to_score:
            result = batch_results.get(posting["id"])
            if result is None:
                continue

            add_score(
                posting_id=posting["id"],
                score=result["score"],
                hard_constraint_pass=result["hard_constraint_pass"],
                flags=result.get("flags"),
                reasoning=result.get("reasoning"),
                application_angle=result.get("application_angle"),
                skill_gaps=result.get("skill_gaps"),
            )

            scored_results.append({
                "title": posting["title"],
                "company": posting["company"],
                "url": posting["url"],
                **result,
            })
    else:
        # Individual API calls (instant results)
        for i, posting in enumerate(to_score):
            logger.info(f"\nScoring {i+1}/{len(to_score)}: {posting['title']} @ {posting['company']}")

            result = score_posting(dict(posting))
            if result is None:
                logger.warning(f"  Scoring failed, skipping")
                continue

            add_score(
                posting_id=posting["id"],
                score=result["score"],
                hard_constraint_pass=result["hard_constraint_pass"],
                flags=result.get("flags"),
                reasoning=result.get("reasoning"),
                application_angle=result.get("application_angle"),
                skill_gaps=result.get("skill_gaps"),
            )

            scored_results.append({
                "title": posting["title"],
                "company": posting["company"],
                "url": posting["url"],
                **result,
            })

            if i < len(to_score) - 1:
                time.sleep(1)

    # 6. Summary
    high_scores = [r for r in scored_results if r["score"] >= 7]

    print("\n" + "=" * 60)
    print(f"PIPELINE SUMMARY")
    print(f"=" * 60)
    print(f"New postings found:  {new_count}")
    print(f"Postings scored:     {len(scored_results)}")
    print(f"Scored 7+:           {len(high_scores)}")
    print(f"=" * 60)

    if high_scores:
        print(f"\nTOP MATCHES:\n")
        for r in sorted(high_scores, key=lambda x: x["score"], reverse=True):
            print(f"  [{r['score']}/10] {r['title']} @ {r['company']}")
            print(f"    {r['url']}")
            print(f"    {r['reasoning']}")
            if r.get("flags"):
                flags = ", ".join(f["flag"] for f in r["flags"] if isinstance(f, dict))
                if flags:
                    print(f"    Flags: {flags}")
            print()
    else:
        print("\nNo postings scored 7+ in this run.")

    # 7. Build digest
    digest_count = build_digest()
    if digest_count:
        print(f"Digest saved to storage/digest.html ({digest_count} postings)")


if __name__ == "__main__":
    main()
