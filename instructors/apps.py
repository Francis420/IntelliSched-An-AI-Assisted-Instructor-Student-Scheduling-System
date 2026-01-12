from django.apps import AppConfig

class InstructorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'instructors'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import (
            InstructorExperience,
            InstructorCredentials,
            TeachingAssignment,          
            InstructorLegacyExperience,
            InstructorDesignation,
            InstructorRank,
            InstructorAcademicAttainment,
        )

        auditlog.register(InstructorExperience)
        auditlog.register(InstructorCredentials)
        auditlog.register(TeachingAssignment)         
        auditlog.register(InstructorLegacyExperience)
        auditlog.register(InstructorDesignation)
        auditlog.register(InstructorRank)
        auditlog.register(InstructorAcademicAttainment)

        import instructors.signals
