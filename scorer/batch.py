import json
import logging
import time

from anthropic import Anthropic
from dotenv import load_dotenv

from scorer.score import MODEL, get_system_prompt, get_user_prompt, parse_score_response

load_dotenv()

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30


def create_batch(postings):
    client = Anthropic()

    requests = []
    for posting in postings:
        requests.append({
            "custom_id": str(posting["id"]),
            "params": {
                "model": MODEL,
                "max_tokens": 2048,
                "system": get_system_prompt(),
                "messages": [{"role": "user", "content": get_user_prompt(dict(posting))}],
            },
        })

    logger.info(f"Submitting batch of {len(requests)} scoring requests...")
    batch = client.messages.batches.create(requests=requests)
    logger.info(f"Batch created: {batch.id}")
    return batch.id


def poll_batch(batch_id):
    client = Anthropic()

    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts

        logger.info(
            f"Batch {batch_id}: {batch.processing_status} "
            f"(succeeded: {counts.succeeded}, errored: {counts.errored}, "
            f"processing: {counts.processing}, expired: {counts.expired})"
        )

        if batch.processing_status == "ended":
            return batch

        time.sleep(POLL_INTERVAL)


def get_batch_results(batch_id):
    client = Anthropic()

    results = {}
    for result in client.messages.batches.results(batch_id):
        posting_id = int(result.custom_id)

        if result.result.type == "succeeded":
            raw = result.result.message.content[0].text
            parsed = parse_score_response(raw)
            if parsed:
                results[posting_id] = parsed
            else:
                logger.warning(f"  Posting {posting_id}: failed to parse response")
        else:
            error = getattr(result.result, "error", None)
            logger.warning(f"  Posting {posting_id}: batch request failed: {error}")

    return results


def score_batch(postings):
    batch_id = create_batch(postings)
    batch = poll_batch(batch_id)

    counts = batch.request_counts
    logger.info(f"Batch complete: {counts.succeeded} succeeded, {counts.errored} errored")

    results = get_batch_results(batch_id)
    logger.info(f"Parsed {len(results)} score results")
    return results
