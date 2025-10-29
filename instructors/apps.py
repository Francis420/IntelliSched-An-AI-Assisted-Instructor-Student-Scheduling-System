from django.apps import AppConfig

class InstructorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'instructors'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import (
            InstructorExperience,
            TeachingHistory,
            InstructorCredentials,
            InstructorSubjectPreference,
            InstructorDesignation,
            InstructorRank,
            InstructorAcademicAttainment,
            InstructorAbsence,
            InstructorAvailability,
        )

        auditlog.register(InstructorExperience)
        auditlog.register(TeachingHistory)
        auditlog.register(InstructorCredentials)
        auditlog.register(InstructorSubjectPreference)
        auditlog.register(InstructorDesignation)
        auditlog.register(InstructorRank)
        auditlog.register(InstructorAcademicAttainment)
        auditlog.register(InstructorAbsence)
        auditlog.register(InstructorAvailability)
