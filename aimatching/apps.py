from django.apps import AppConfig

class AimatchingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'aimatching'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import (
            InstructorSubjectMatch,
            InstructorSubjectMatchHistory,
            MatchingConfig,
            MatchingRun,
            MatchingProgress,
        )

        # Register models for automatic audit logging
        auditlog.register(InstructorSubjectMatch)
        auditlog.register(InstructorSubjectMatchHistory)
        auditlog.register(MatchingConfig)
        auditlog.register(MatchingRun)
        auditlog.register(MatchingProgress)
