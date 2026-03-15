import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# ── Module-level setup (runs once) ────────────────────────────────────────── #
load_dotenv()
logger = logging.getLogger(__name__)

def _init_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_KEY must be set in environment variables."
        )
    return create_client(url, key)

# Singleton client — created once, reused on every call
_supabase: Client = _init_supabase()


def fetch_student_data(student_id: str, week_number: int) -> dict:
    """
    Fetch a single student's progress row and the weekly targets row
    for the given week.

    Returns:
        {
            "progress": { ...row from 'student progress' table },
            "targets":  { ...row from 'weekly targets' table }
        }

    Raises:
        ValueError  – if no data found for the given student/week.
        RuntimeError – on unexpected Supabase errors.
    """
    try:
        progress_resp = (
            _supabase.table("student progress")
            .select("*")
            .eq("Student_Id", student_id)
            .eq("Week_Nu", week_number)
            .execute()
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch student progress: {e}") from e

    try:
        targets_resp = (
            _supabase.table("weekly targets")
            .select("*")
            .eq("Week_Nu", week_number)
            .execute()
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch weekly targets: {e}") from e

    if not progress_resp.data:
        raise ValueError(
            f"No progress record found for student '{student_id}' in week {week_number}."
        )
    if not targets_resp.data:
        raise ValueError(f"No target record found for week {week_number}.")

    # Warn if more than one row returned (take first, but surface the anomaly)
    if len(progress_resp.data) > 1:
        logger.warning(
            f"Multiple progress rows found for student '{student_id}' "
            f"week {week_number}. Using the first row."
        )
    if len(targets_resp.data) > 1:
        logger.warning(
            f"Multiple target rows found for week {week_number}. Using the first row."
        )

    return {
        "progress": progress_resp.data[0],
        "targets":  targets_resp.data[0],
    }