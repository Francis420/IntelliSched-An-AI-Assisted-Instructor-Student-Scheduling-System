from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import User, Role, Instructor, Student, UserLogin
        from . import signals_audit

        auditlog.register(User)
        auditlog.register(Role)
        auditlog.register(Instructor)
        auditlog.register(Student)
        auditlog.register(UserLogin)
