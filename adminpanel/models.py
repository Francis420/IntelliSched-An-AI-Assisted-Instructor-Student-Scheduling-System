from django.db import models
from core.models import User


# ---------- Audit Log ----------
class AuditLog(models.Model):
    auditId = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    role = models.CharField(max_length=50)  # Role at time of action
    action = models.CharField(max_length=255)
    targetTable = models.CharField(max_length=100)
    targetId = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[('success', 'Success'), ('failed', 'Failed')])
    errorMessage = models.TextField(blank=True, null=True)
    ipAddress = models.GenericIPAddressField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} | {self.action} @ {self.createdAt}"


# ---------- Notification ----------
class Notification(models.Model):
    NOTIF_TYPES = [
        ('system', 'System'),
        ('message', 'Message'),
        ('reminder', 'Reminder'),
        ('scheduleUpdate', 'Schedule Update')
    ]

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed')
    ]

    notificationId = models.AutoField(primary_key=True)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sentNotifications')
    message = models.TextField()
    notificationType = models.CharField(max_length=50, choices=NOTIF_TYPES, default='system')
    referenceId = models.CharField(max_length=100, blank=True, null=True)
    targetTable = models.CharField(max_length=100, blank=True, null=True)
    targetId = models.CharField(max_length=100, blank=True, null=True)
    isRead = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"To {self.recipient.username} | {self.notificationType} | Read: {self.isRead}"
