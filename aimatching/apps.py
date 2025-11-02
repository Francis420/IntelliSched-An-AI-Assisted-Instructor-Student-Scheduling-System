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

        auditlog.register(InstructorSubjectMatch)
        auditlog.register(InstructorSubjectMatchHistory)
        auditlog.register(MatchingConfig)
        auditlog.register(MatchingRun)
        auditlog.register(MatchingProgress)
