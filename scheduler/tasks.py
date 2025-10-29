# scheduler/tasks.py
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from scheduling.models import Semester
from scheduler.models import SchedulerProgress
import subprocess, sys

@shared_task(bind=True)
def run_scheduler_task(self, batch_id=None):
    channel_layer = get_channel_layer()
    progress = SchedulerProgress.objects.get(batch_id=batch_id)
    progress.task_id = self.request.id
    progress.status = "running"
    progress.message = "Starting scheduler..."
    progress.save()

    async_to_sync(channel_layer.group_send)(
        f"scheduler_{batch_id}",
        {"type": "progress.update", "data": {"status": "running", "message": "Scheduler started", "progress": 0}},
    )

    semester = Semester.objects.filter(isActive=True).first()
    if not semester:
        progress.status = "error"
        progress.message = "❌ No active semester found."
        progress.add_log(progress.message)
        progress.save()
        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "error", "message": progress.message}},
        )
        return

    try:
        cmd = [sys.executable, "manage.py", "test_scheduler", str(semester.semesterId)]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

        progress.process_pid = process.pid
        progress.save()

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            refreshed = SchedulerProgress.objects.get(batch_id=batch_id)
            if refreshed.status == "stopped":
                process.terminate()
                refreshed.add_log("⏹ Scheduler stopped by user.")
                async_to_sync(channel_layer.group_send)(
                    f"scheduler_{batch_id}",
                    {"type": "progress.update", "data": {"status": "stopped", "message": "Scheduler stopped by user."}},
                )
                return

            refreshed.add_log(line)  # 🧩 Log live updates
            async_to_sync(channel_layer.group_send)(
                f"scheduler_{batch_id}",
                {"type": "progress.update", "data": {"status": "running", "message": line}},
            )

        process.wait()
        progress.status = "done"
        progress.message = "✅ Scheduling completed!"
        progress.add_log(progress.message)
        progress.save()

        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "done", "message": progress.message}},
        )

    except Exception as e:
        progress.status = "error"
        progress.message = f"❌ Error: {str(e)}"
        progress.add_log(progress.message)
        progress.save()
        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "error", "message": str(e)}},
        )
