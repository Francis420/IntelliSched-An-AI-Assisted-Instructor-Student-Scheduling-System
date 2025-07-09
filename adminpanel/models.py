from django.db import models
from core.models import User


# ---------- Audit Logs ----------
class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user} | {self.action} at {self.timestamp}"


# ---------- Notifications ----------
class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    date_sent = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    type = models.CharField(
        max_length=50,
        choices=[
            ('absence', 'Student Absence'),
            ('system', 'System Notice'),
            ('general', 'General Notification'),
        ],
        default='general'
    )

    def __str__(self):
        return f"To {self.recipient.username} | {self.type} | Read: {self.is_read}"
