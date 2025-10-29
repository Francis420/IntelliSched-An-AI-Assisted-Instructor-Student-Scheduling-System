from celery import shared_task, current_app
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from scheduling.models import Semester
from scheduler.models import SchedulerProgress
from scheduler.solver import solve_schedule_for_semester
import time

@shared_task(bind=True)
def run_scheduler_task(self, batch_id=None):
    channel_layer = get_channel_layer()
    progress = SchedulerProgress.objects.get(batch_id=batch_id)
    progress.task_id = self.request.id
    progress.status = "running"
    progress.save()

    semester = Semester.objects.filter(isActive=True).first()
    if not semester:
        progress.status = "error"
        progress.message = "❌ No active semester found."
        progress.save()
        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "error", "message": progress.message, "progress": 0}},
        )
        return

    try:
        for i in range(0, 101, 10):
            # Check if task was revoked
            refreshed = SchedulerProgress.objects.get(batch_id=batch_id)
            if refreshed.status == "stopped":
                async_to_sync(channel_layer.group_send)(
                    f"scheduler_{batch_id}",
                    {"type": "progress.update", "data": {"status": "stopped", "message": "⏹ Scheduler stopped by user.", "progress": i}},
                )
                return

            progress.progress = i
            progress.message = f"Scheduling progress: {i}%"
            progress.save()

            async_to_sync(channel_layer.group_send)(
                f"scheduler_{batch_id}",
                {"type": "progress.update", "data": {"status": "running", "message": progress.message, "progress": i}},
            )

            time.sleep(1)

        # Run actual solver (optional)
        solve_schedule_for_semester(semester, time_limit_seconds=60)

        progress.status = "completed"
        progress.progress = 100
        progress.message = "✅ Scheduling complete!"
        progress.save()

        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "done", "message": progress.message, "progress": 100}},
        )

    except Exception as e:
        progress.status = "error"
        progress.message = str(e)
        progress.save()
        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "error", "message": str(e)}},
        )
