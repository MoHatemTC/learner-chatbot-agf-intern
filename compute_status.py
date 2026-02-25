from fetch_student_data import  fetch_student_data  
def compute_status(data):
    progress = data["progress"]
    targets = data["targets"]

    missing_items = []
    performance_issues = []

    COMPLETION_THRESHOLD = 0.7
    GRADE_THRESHOLD = 0.8

    # ---- Videos Completion Rate ----
    if targets["Vedios_Target"] > 0:
        video_completion = progress["Vedios_Nu"] / targets["Vedios_Target"]
        if video_completion < COMPLETION_THRESHOLD:
            missing_items.append("videos")

    # ---- Quizzes Completion + Grade ----
    if targets["Quiz_Target"] > 0:
        quiz_completion = progress["Quiz_Nu"] / targets["Quiz_Target"]
        if quiz_completion < COMPLETION_THRESHOLD:
            missing_items.append("quizzes")

    if progress["Quize_Average_Grade"] < GRADE_THRESHOLD:
        performance_issues.append("quiz performance")

    # ---- Tasks Completion + Grade ----
    if targets["Task_Target"] > 0:
        task_completion = progress["Task_Nu"] / targets["Task_Target"]
        if task_completion < COMPLETION_THRESHOLD:
            missing_items.append("tasks")

    if progress["Task_Average_Grade"] < GRADE_THRESHOLD:
        performance_issues.append("task performance")

    # ---- Projects Completion + Grade ----
    if targets["Project_Target"] > 0:
        project_completion = progress["Project_Nu"] / targets["Project_Target"]
        if project_completion < COMPLETION_THRESHOLD:
            missing_items.append("projects")

    if progress["Project_Average_Grade"] < GRADE_THRESHOLD:
        performance_issues.append("project performance")

    status = "behind" if (missing_items or performance_issues) else "on_track"

    return {
        **data,
        "status": status,
        "missing_items": missing_items,
        "performance_issues": performance_issues
    }

