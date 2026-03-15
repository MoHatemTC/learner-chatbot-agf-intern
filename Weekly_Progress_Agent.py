import os
import json
import logging
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from compute_status import compute_status
from fetch_student_data import fetch_student_data

# ── Setup ─────────────────────────────────────────────────────────────────── #
load_dotenv()
logger = logging.getLogger(__name__)

if not os.getenv("OPENAI_API_KEY"):
    raise EnvironmentError("OPENAI_API_KEY not found in environment variables.")


# ── Agent (defined once, reused across calls) ─────────────────────────────── #
progress_agent = Agent(
    role="Learner Success Communication Specialist",
    goal=(
        "Generate supportive weekly progress messages for learners "
        "based on ONLY their sprint performance status."
    ),
    backstory=(
        "You are a learner success AI assistant. "
        "You receive structured learner performance data. "
        "You never calculate numbers. "
        "You never fetch data. "
        "You only generate motivating and actionable messages."
    ),
    verbose=True,
)


# ── Task (defined once; uses {placeholders} for CrewAI input injection) ───── #
progress_task = Task(
    description="""
    You are given the following structured learner progress data:

    - Status            : {status}
    - Missing items     : {missing_items}
    - Performance issues: {performance_issues}

    Use ONLY the data above to generate a personalized message.

    If status = "behind":
        - Clearly mention each item in missing_items.
        - Mention each issue in performance_issues if any.
        - Provide motivating and actionable guidance.
        - Keep the message under 150 words.
        - Tone must be supportive and constructive.

    If status = "on_track":
        - Provide a short congratulatory message.
        - Encourage continued consistency.

    Do NOT calculate anything.
    Do NOT change the status.
    Do NOT invent data that was not provided.
    """,
    expected_output="""
    Return ONLY a valid JSON object with no extra text, no markdown, no code fences:
    {
        "status": "on_track" | "behind",
        "message": "Personalized message here"
    }
    """,
    agent=progress_agent,
)


# ── Crew (defined once) ───────────────────────────────────────────────────── #
_crew = Crew(
    agents=[progress_agent],
    tasks=[progress_task],
    process=Process.sequential,
)


# ── Public entry point ────────────────────────────────────────────────────── #
def run_progress_check(student_id: str, week_number: int) -> dict:
    """
    Fetch → compute → generate message.

    Returns a dict:
        { "status": "on_track"|"behind", "message": "..." }

    Raises:
        ValueError   – if student/week data is missing.
        RuntimeError – on fetch or agent failure.
    """
    # 1. Fetch raw data from Supabase
    raw_data = fetch_student_data(student_id, week_number)

    # 2. Compute structured status
    structured_data = compute_status(raw_data)

    # 3. Build the inputs CrewAI will inject into {placeholders}
    crew_inputs = {
        "status":             structured_data["status"],
        "missing_items":      structured_data["missing_items"],
        "performance_issues": structured_data["performance_issues"],
    }

    logger.info(
        f"Running progress check for student={student_id} "
        f"week={week_number} | inputs={crew_inputs}"
    )

    # 4. Run the crew
    try:
        result = _crew.kickoff(inputs=crew_inputs)
    except Exception as e:
        raise RuntimeError(f"CrewAI agent failed: {e}") from e

    # 5. Validate and parse the agent's JSON output
    raw_output = result.raw if hasattr(result, "raw") else str(result)
    return _parse_agent_output(raw_output, structured_data["status"])


def _parse_agent_output(raw_output: str, fallback_status: str) -> dict:
    """
    Parse the agent's raw string output into a clean dict.
    Falls back gracefully if the output isn't valid JSON.
    """
    try:
        # Strip markdown code fences if the agent wrapped output in them
        clean = raw_output.strip().strip("```json").strip("```").strip()
        parsed = json.loads(clean)
        if "status" not in parsed or "message" not in parsed:
            raise ValueError("Missing required keys in agent output.")
        return parsed
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Agent output parse failed ({e}). Using fallback.")
        return {
            "status":  fallback_status,
            "message": raw_output.strip() or "Progress check completed.",
        }