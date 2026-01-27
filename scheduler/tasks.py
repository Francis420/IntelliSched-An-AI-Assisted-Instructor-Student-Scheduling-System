# scheduler/tasks.py
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from scheduling.models import Semester
from scheduler.models import SchedulerProgress, SchedulerSettings 
from django.core.cache import cache
import subprocess, sys

@shared_task(bind=True)
def run_scheduler_task(self, batch_id=None):
    channel_layer = get_channel_layer()
    
    try:
        progress = SchedulerProgress.objects.get(batch_id=batch_id)
    except SchedulerProgress.DoesNotExist:
        return

    progress.task_id = self.request.id
    progress.status = "running"
    progress.message = "Starting scheduler..."
    progress.save()

    async_to_sync(channel_layer.group_send)(
        f"scheduler_{batch_id}",
        {"type": "progress.update", "data": {"status": "running", "message": "Scheduler started", "progress": 0}},
    )

    try:
        settings_obj = SchedulerSettings.objects.first()
        mins = settings_obj.time_limit_minutes if settings_obj else 60
    except:
        mins = 60

    secs = mins * 60
    
    lock_id = f"scheduler_lock_{batch_id}"
    cache.set(lock_id, "running", timeout=secs + 300)

    semester = Semester.objects.filter(isActive=True).first()
    if not semester:
        msg = "❌ No active semester found."
        progress.status = "error"
        progress.message = msg
        progress.add_log(msg)
        progress.save()
        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "error", "message": msg}},
        )
        return

    try:
        process = subprocess.Popen(
            [
                sys.executable, "manage.py", "test_scheduler", 
                str(semester.pk), 
                "--time", str(secs)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            
            if line:
                line = line.strip()
                # Check cancellation
                if cache.get(lock_id) != "running":
                    process.terminate()
                    progress.status = "stopped"
                    progress.message = "Scheduler stopped by user."
                    progress.add_log("🛑 STOP signal received. Terminating process...")
                    progress.save()
                    async_to_sync(channel_layer.group_send)(
                        f"scheduler_{batch_id}",
                        {"type": "progress.update", "data": {"status": "stopped", "message": "Scheduler stopped by user."}},
                    )
                    return

                try:
                    refreshed = SchedulerProgress.objects.get(batch_id=batch_id)
                except SchedulerProgress.DoesNotExist:
                    break
                    
                refreshed.add_log(line)
                async_to_sync(channel_layer.group_send)(
                    f"scheduler_{batch_id}",
                    {"type": "progress.update", "data": {"status": "running", "message": line}},
                )

        process.wait()
        
        if process.returncode != 0:
            raise Exception("Scheduler script failed (check logs above).")

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