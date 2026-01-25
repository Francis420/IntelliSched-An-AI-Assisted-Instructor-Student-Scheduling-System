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
        msg = "⚠️ Scheduler is ALREADY running for this semester. Duplicate run blocked."
        print(f"[Task] {msg}")
        
        progress.status = "error"
        progress.message = msg
        progress.add_log(msg)
        progress.save()
        
        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "error", "message": msg}},
        )
        return 

    cache.set(lock_id, "running", timeout=1200)
    print(f"[Task] Lock ACQUIRED for semester {semester.semesterId}")

    try:
        cmd = [sys.executable, "manage.py", "run_solver_script", str(semester.semesterId)]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            
            line = line.strip()
            print(f"[Solver Script] {line}")

            refreshed = SchedulerProgress.objects.get(batch_id=batch_id)
            if refreshed.status == "stopped":
                process.terminate()
                msg = "⏹ Scheduler stopped by user."
                refreshed.add_log(msg)
                async_to_sync(channel_layer.group_send)(
                    f"scheduler_{batch_id}",
                    {"type": "progress.update", "data": {"status": "stopped", "message": msg}},
                )
                return

            # Log normal progress
            refreshed.add_log(line)
            async_to_sync(channel_layer.group_send)(
                f"scheduler_{batch_id}",
                {"type": "progress.update", "data": {"status": "running", "message": line}},
            )

        process.wait()
        
        if process.returncode != 0:
            stderr_output = process.stderr.read()
            raise Exception(f"Script failed with error code {process.returncode}: {stderr_output}")

        progress.status = "done"
        progress.message = "✅ Scheduling completed!"
        progress.add_log(progress.message)
        progress.save()

        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "done", "message": progress.message}},
        )

    except Exception as e:
        msg = f"❌ Error: {str(e)}"
        progress.status = "error"
        progress.message = msg
        progress.add_log(msg)
        progress.save()
        async_to_sync(channel_layer.group_send)(
            f"scheduler_{batch_id}",
            {"type": "progress.update", "data": {"status": "error", "message": msg}},
        )
    
    finally:
        cache.delete(lock_id)
        print(f"[Task] Lock RELEASED for semester {semester.semesterId}")