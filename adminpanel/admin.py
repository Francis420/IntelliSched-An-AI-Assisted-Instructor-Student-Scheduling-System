from django.contrib import admin
from .models import AuditLog, Notification

admin.site.register(AuditLog)
admin.site.register(Notification)
