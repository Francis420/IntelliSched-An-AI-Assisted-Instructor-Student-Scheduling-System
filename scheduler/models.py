from django.db import models

class SchedulerProgress(models.Model):
    batch_id = models.UUIDField(primary_key=True)
    task_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, default="pending")
    progress = models.IntegerField(default=0)
    message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
