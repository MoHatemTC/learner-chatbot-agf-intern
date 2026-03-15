import logging

logger = logging.getLogger(__name__)

COMPLETION_THRESHOLD = 0.7   # must complete ≥70 % of items
GRADE_THRESHOLD      = 0.8   # must score   ≥80 % on graded work


def _safe_rate(numerator, denominator) -> float | None:
    """Return numerator/denominator, or None if denominator is 0 / None."""
    try:
        if not denominator:
            return None
        return float(numerator) / float(denominator)
    except (TypeError, ValueError):
        return None


def _safe_grade(value) -> float | None:
    """Return grade as float, or None if missing/non-numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_status(data: dict) -> dict:
    """
    Compare a student's progress against weekly targets and return
    an enriched dict with 'status', 'missing_items', and 'performance_issues'.

    Rules:
      - missing_items  : completion rate < COMPLETION_THRESHOLD
      - performance_issues : grade < GRADE_THRESHOLD
                             (only checked when the student has submitted work)
    """
    progress = data.get("progress", {})
    targets  = data.get("targets",  {})

    if not progress or not targets:
        raise ValueError("compute_status requires non-empty 'progress' and 'targets' dicts.")

    missing_items      = []
    performance_issues = []

    # ── Videos ──────────────────────────────────────────────────────────── #
    video_rate = _safe_rate(progress.get("Vedios_Nu"), targets.get("Vedios_Target"))
    if video_rate is not None and video_rate < COMPLETION_THRESHOLD:
        missing_items.append("videos")

    # ── Quizzes ──────────────────────────────────────────────────────────── #
    quiz_rate = _safe_rate(progress.get("Quiz_Nu"), targets.get("Quiz_Target"))
    if quiz_rate is not None:
        if quiz_rate < COMPLETION_THRESHOLD:
            missing_items.append("quizzes")
        else:
            # Only evaluate grade if the student actually did meaningful work
            quiz_grade = _safe_grade(progress.get("Quize_Average_Grade"))
            if quiz_grade is not None and quiz_grade < GRADE_THRESHOLD:
                performance_issues.append("quiz performance")
            elif quiz_grade is None:
                logger.debug("Quiz grade missing — skipping quiz grade check.")

    # ── Tasks ─────────────────────────────────────────────────────────────── #
    task_rate = _safe_rate(progress.get("Task_Nu"), targets.get("Task_Target"))
    if task_rate is not None:
        if task_rate < COMPLETION_THRESHOLD:
            missing_items.append("tasks")
        else:
            task_grade = _safe_grade(progress.get("Task_Average_Grade"))
            if task_grade is not None and task_grade < GRADE_THRESHOLD:
                performance_issues.append("task performance")
            elif task_grade is None:
                logger.debug("Task grade missing — skipping task grade check.")

    # ── Projects ─────────────────────────────────────────────────────────── #
    project_rate = _safe_rate(progress.get("Project_Nu"), targets.get("Project_Target"))
    if project_rate is not None:
        if project_rate < COMPLETION_THRESHOLD:
            missing_items.append("projects")
        else:
            project_grade = _safe_grade(progress.get("Project_Average_Grade"))
            if project_grade is not None and project_grade < GRADE_THRESHOLD:
                performance_issues.append("project performance")
            elif project_grade is None:
                logger.debug("Project grade missing — skipping project grade check.")

    status = "behind" if (missing_items or performance_issues) else "on_track"

    logger.info(
        f"compute_status → status={status} | "
        f"missing={missing_items} | issues={performance_issues}"
    )

    return {
        **data,
        "status":            status,
        "missing_items":     missing_items,
        "performance_issues": performance_issues,
    }