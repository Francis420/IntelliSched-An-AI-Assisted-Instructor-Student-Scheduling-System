from django.db import models
import uuid

class SchedulerProgress(models.Model):
    batch_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    task_id = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=20, default="idle")  
    message = models.TextField(blank=True, null=True)
    progress = models.IntegerField(default=0)
    process_pid = models.IntegerField(null=True, blank=True)
    logs = models.JSONField(default=list, blank=True)  
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def add_log(self, text):
        logs = self.logs or []
        logs.append(text)
        self.logs = logs[-20:]
        self.save(update_fields=["logs"])

class SchedulerSettings(models.Model):
    time_limit_minutes = models.IntegerField(default=60)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Global Settings (Last updated: {self.updated_at})"

    class Meta:
        verbose_name_plural = "Scheduler Settings"
