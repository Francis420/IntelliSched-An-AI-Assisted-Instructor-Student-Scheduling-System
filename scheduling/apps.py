from django.apps import AppConfig

class SchedulingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scheduling'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import (
            Curriculum,
            Subject,
            Semester,
            Section,
            Room,
            Schedule,
            ScheduleControl,
            GenEdSchedule,
            SubjectOffering,
        )

        # Register models for automatic audit logging
        auditlog.register(Curriculum)
        auditlog.register(Subject)
        auditlog.register(Semester)
        auditlog.register(Section)
        auditlog.register(Room)
        auditlog.register(Schedule)
        auditlog.register(ScheduleControl)
        auditlog.register(GenEdSchedule)
        auditlog.register(SubjectOffering)
