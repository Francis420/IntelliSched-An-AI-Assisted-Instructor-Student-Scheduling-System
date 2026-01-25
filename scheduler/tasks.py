# scheduler/tasks.py
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from scheduling.models import Semester
from scheduler.models import SchedulerProgress
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

    lock_id = f"scheduler_lock_{semester.semesterId}"
    
    if cache.get(lock_id):
        msg = "⚠️ Scheduler is ALREADY running for this semester! Duplicate run is blocked."
        print(f"[Task] {msg}")
        
        progress.status = "error"
        progress.message = msg
        progress.add_log(msg)
        progress.save()
        
        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "error", "message": msg}},
        )
        return  # STOP HERE

    cache.set(lock_id, "running", timeout=3600)
    print(f"[Task] Lock ACQUIRED for semester {semester.semesterId}")

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

        for line in iter(process.stdout.readline, ''):
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
    
    finally:
        cache.delete(lock_id)
        print(f"[Task] Lock RELEASED for semester {semester.semesterId}")