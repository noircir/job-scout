import json
import logging
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PROFILE_PATH = Path(__file__).parent.parent / "config" / "profile.json"
MODEL = "claude-haiku-4-5-20251001"


def _load_profile():
    with open(PROFILE_PATH) as f:
        return json.load(f)


PROFILE = _load_profile()


def get_system_prompt():
    return PROFILE["scoring_instructions"]["system_prompt"]


def get_user_prompt(posting):
    return f"""## Candidate Profile
{json.dumps(PROFILE, indent=2)}

## Job Posting
Title: {posting.get('title', 'N/A')}
Company: {posting.get('company', 'N/A')}
Location: {posting.get('location', 'N/A')}
Remote type: {posting.get('remote_type', 'N/A')}
Salary: {posting.get('salary_text', 'Not listed')}
Source: {posting.get('source', 'N/A')}

Description:
{posting.get('description', 'No description available.')}

## Country-Restricted Remote Roles
When a job EXPLICITLY lists specific countries alongside "Remote" (e.g., "France, Remote; Germany, Remote"
or "Remote - US only" or "must reside in one of the following countries"), the candidate must be a resident
with work authorization in one of those countries. Apply these rules:
- Specific countries listed AND Canada is included: score normally
- Specific countries listed AND only US states: flag work auth, score normally (contractor/EOR path exists)
- Specific countries listed AND only European countries without Canada: flag as "requires residency in listed country, not currently accessible from Canada. Negotiable via contractor arrangement or after France relocation." Still score the role but note the restriction.
- Posting just says "Remote" with NO country list: score normally, do not assume country restrictions
- Posting says "work from anywhere" or "worldwide": score normally
Only apply country-restriction logic when countries are explicitly stated. Never penalize for "Remote" without qualifiers.

## Instructions
Score this job match. Return ONLY valid JSON with exactly these fields:
{{
  "score": <integer 0-10>,
  "hard_constraint_pass": <boolean>,
  "hard_constraint_failures": [<list of failed constraints, empty if none>],
  "flags": [<list of {{"flag": "<name>", "note": "<detail>"}}>],
  "title_match": "<ideal|acceptable|poor|avoid>",
  "skill_overlap_pct": <integer 0-100>,
  "skill_gaps": [<list of required skills not in profile>],
  "positives": [<list of matching preference signals>],
  "negatives": [<list of matching negative signals>],
  "salary_estimate": "<salary if posted, or 'not listed'>",
  "reasoning": "<2-3 sentence explanation>",
  "application_angle": "<specific angle to emphasize if applying>"
}}

Return ONLY the JSON object. No markdown, no code fences, no commentary."""


def parse_score_response(raw_text):
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON object from surrounding text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        logger.error(f"Failed to parse JSON from Claude response:\n{raw_text[:500]}")
        return None


def score_posting(posting):
    client = Anthropic()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=get_system_prompt(),
            messages=[{"role": "user", "content": get_user_prompt(posting)}],
        )
        raw = response.content[0].text
    except Exception as e:
        logger.error(f"Anthropic API call failed: {e}")
        return None

    return parse_score_response(raw)


SAMPLE_POSTING = {
    "source": "test",
    "url": "https://example.com/jobs/ai-eng-42",
    "title": "Senior AI Engineer",
    "company": "NovaMind AI",
    "description": """We're building the next generation of AI-powered document processing.
Looking for a Senior AI Engineer to own our LLM pipeline end-to-end.

Requirements:
- 5+ years Python experience
- Production LLM pipeline experience (RAG, embeddings, vector DBs)
- Experience with Claude or OpenAI APIs
- Strong understanding of NLP and transformer architectures
- FastAPI or similar web framework experience
- Docker and basic cloud infrastructure (AWS preferred)

Nice to have:
- Experience processing large unstructured datasets (1M+ documents)
- Multilingual NLP experience
- GPU infrastructure experience

We're a remote-first team of 40, mostly in US/Canada timezones.
Competitive salary: $160,000 - $200,000 USD.
Open to contractors (1099) or full-time employees.""",
    "salary_text": "$160,000 - $200,000",
    "location": "Remote",
    "remote_type": "fully_remote",
    "date_posted": "2026-03-28",
}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if "--test" not in sys.argv:
        print("Usage: python scorer/score.py --test")
        sys.exit(1)

    print("Scoring sample posting against profile...")
    print(f"  Job: {SAMPLE_POSTING['title']} @ {SAMPLE_POSTING['company']}")
    print()

    result = score_posting(SAMPLE_POSTING)

    if result is None:
        print("Scoring failed — check logs above.")
        sys.exit(1)

    print(json.dumps(result, indent=2))
