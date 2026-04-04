import argparse
import logging
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

RESUME_PATH = Path(__file__).parent / "master-resume.md"
OUTPUT_DIR = Path(__file__).parent / "tailored"
MODEL = "claude-sonnet-4-20250514"


def _tailor_resume(client, resume, jd):
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system="""You are a resume editor. You receive a master resume and a job description.
Your job is to tailor the resume for this specific role.

Rules:
- Rewrite the PROFILE paragraph to mirror the job description's language and priorities
- Reorder bullets within each job section to lead with the most relevant experience
- Do NOT bold any text within bullet points or the profile paragraph. Plain text only.
- Only job titles, section headers (PROFILE, TECHNICAL SKILLS, EXPERIENCE, EDUCATION), and company names should be bold.
- Do NOT scatter bold keywords through body text — it looks AI-generated.
- Do NOT use em dashes (—) anywhere. Use commas, periods, or semicolons instead. Em dashes are an AI writing fingerprint.
- Do NOT invent experience, skills, or achievements that aren't in the original
- Do NOT remove any sections, jobs, education entries, or skills categories
- Do NOT add a summary of changes — output only the complete tailored resume
- Output format: clean markdown, same structure as the original""",
        messages=[{"role": "user", "content": f"""## Master Resume
{resume}

## Job Description
{jd}

Tailor this resume for the job description above. Output the complete tailored resume in markdown."""}],
    )
    return response.content[0].text


def _write_cover_letter(client, resume, jd):
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system="""You are a cover letter writer. You receive a resume and a job description.
Write a cover letter that connects specific experience from the resume to specific requirements in the JD.

Rules:
- Write in first person: "I built", "My work", "At Jacobb, I..." — never "Your" when referring to the candidate's own experience
- Professional but direct voice — write like a human, not a template
- Maximum 3 paragraphs, under 300 words total
- Paragraph 1: one specific connection between the JD and the candidate's real estate pipeline work. Open with substance, not a greeting.
- Paragraph 2: one specific technical capability that matches a JD requirement
- Paragraph 3: concrete next step
- Do NOT claim expertise beyond what the resume states. If the resume says "working knowledge" for a skill, the cover letter cannot say it "directly matches" or imply deep experience. Frame on-premises distributed work as transferable, not as cloud experience.
- Do NOT stretch old experience (MDA/Canadarm, Askida, etc.) into relevance for current AI roles. Leave that for the resume.
- Do NOT use em dashes (—) anywhere. Use commas, periods, or semicolons instead. Em dashes are an AI writing fingerprint.
- Do NOT use these phrases: "I am excited to apply", "I believe I would be a great fit",
  "I am confident that", "passionate about", "thrilled at the opportunity",
  "I would love to", "perfect fit", "unique opportunity"
- Do NOT start with "Dear Hiring Manager"
- Output format: clean markdown""",
        messages=[{"role": "user", "content": f"""## Resume
{resume}

## Job Description
{jd}

Write a cover letter connecting this candidate's experience to this role."""}],
    )
    return response.content[0].text


def tailor(company, jd_path, cover_only=False, resume_only=False):
    resume = RESUME_PATH.read_text()
    jd = Path(jd_path).read_text()

    client = Anthropic()

    OUTPUT_DIR.mkdir(exist_ok=True)

    resume_path = None
    if not cover_only:
        logger.info("Tailoring resume...")
        tailored_resume = _tailor_resume(client, resume, jd)
        resume_path = OUTPUT_DIR / f"{company}-resume.md"
        resume_path.write_text(tailored_resume)
        logger.info(f"Saved: {resume_path}")

    cover_path = None
    if not resume_only:
        logger.info("Writing cover letter...")
        cover_letter = _write_cover_letter(client, resume, jd)
        cover_path = OUTPUT_DIR / f"{company}-cover.md"
        cover_path.write_text(cover_letter)
        logger.info(f"Saved: {cover_path}")

    return resume_path, cover_path


def main():
    parser = argparse.ArgumentParser(description="Tailor resume and cover letter for a job")
    parser.add_argument("--company", required=True, help="Company name for filenames (e.g. zillow)")
    parser.add_argument("--jd", required=True, help="Path to job description text file")
    parser.add_argument("--cover-only", action="store_true", help="Skip resume tailoring, only generate cover letter")
    parser.add_argument("--resume-only", action="store_true", help="Skip cover letter, only generate tailored resume")
    args = parser.parse_args()

    if args.cover_only and args.resume_only:
        parser.error("Cannot use --cover-only and --resume-only together")

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    resume_path, cover_path = tailor(args.company, args.jd, cover_only=args.cover_only, resume_only=args.resume_only)

    print(f"\nDone:")
    if resume_path:
        print(f"  Resume: {resume_path}")
    if cover_path:
        print(f"  Cover:  {cover_path}")


if __name__ == "__main__":
    main()
