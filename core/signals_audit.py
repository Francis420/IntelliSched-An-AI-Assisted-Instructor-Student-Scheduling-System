from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.dispatch import receiver

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    LogEntry.objects.create(
        actor=user,
        action=0, 
        content_type=ContentType.objects.get_for_model(user.__class__),
        object_pk=user.pk,
        object_repr=f"{user.username}",
        changes="User logged in"
    )

@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    LogEntry.objects.create(
        actor=user,
        action=2, 
        content_type=ContentType.objects.get_for_model(user.__class__),
        object_pk=user.pk,
        object_repr=f"{user.username}",
        changes="User logged out"
    )

@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    LogEntry.objects.create(
        actor=None,
        action=1,  
        content_type=ContentType.objects.get_for_model(sender),
        object_pk="-",
        object_repr=credentials.get("username", "Unknown"),
        changes="Failed login attempt"
    )