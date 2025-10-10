from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from aimatching.matcher.run_matching import run_matching
from aimatching.models import MatchingProgress
from core.models import User  # ✅ Import your custom User

@shared_task
def run_matching_task(semester_id, batch_id, user_id):
    channel_layer = get_channel_layer()

    # ✅ Get the User object instead of passing raw id
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        user = None  # fallback if user was deleted

    progress, created = MatchingProgress.objects.get_or_create(
        batchId=batch_id,
        defaults={
            "semester_id": semester_id,
            "totalTasks": 0,
            "completedTasks": 0,
            "status": "running",
            "generated_by": user,  # ✅ assign object, not ID
        }
    )

    run_matching(semester_id, batch_id, generated_by=user)

    progress.refresh_from_db()
    data = {
        "totalTasks": progress.totalTasks,
        "completedTasks": progress.completedTasks,
        "status": progress.status,
        "percentage": (progress.completedTasks / progress.totalTasks) * 100 if progress.totalTasks > 0 else 0,
    }

    async_to_sync(channel_layer.group_send)(
        f"progress_{batch_id}",
        {"type": "progress_update", "data": data}
    )




from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from scheduling.models import Subject
from core.models import User as CoreUser

def notify_progress(batch_id, progress, current_instructor=None, current_subject=None,
                    subject_count=None, instructor_count=None, total_tasks=None):
    channel_layer = get_channel_layer()

    try:
        if subject_count is None or instructor_count is None or total_tasks is None:
            progress_obj = MatchingProgress.objects.get(batchId=batch_id)
            term_map = {'1st': 0, '2nd': 1, 'Midyear': 2}
            default_term = term_map.get(progress_obj.semester.term)

            subject_count = Subject.objects.filter(defaultTerm=default_term, isActive=True).count()
            instructor_count = CoreUser.objects.filter(roles__name="Instructor", isActive=True).distinct().count()
            total_tasks = subject_count * instructor_count
    except MatchingProgress.DoesNotExist:
        subject_count = instructor_count = total_tasks = 0

    percentage = (
        (progress.completedTasks / total_tasks) * 100
        if total_tasks > 0 else 0
    )

    async_to_sync(channel_layer.group_send)(
        f"progress_{batch_id}",
        {
            "type": "progress_update",
            "data": {
                "totalTasks": total_tasks,
                "completedTasks": progress.completedTasks,
                "status": progress.status,
                "percentage": percentage,
                "subjectCount": subject_count,
                "instructorCount": instructor_count,
                "currentInstructor": current_instructor,
                "currentSubject": current_subject,
            }
        }
    )