from django.db.models.signals import post_save
from django.dispatch import receiver
from scheduling.models import Semester, Schedule, Section, SubjectOffering, GenEdSchedule

@receiver(post_save, sender=Semester)
def archiveOldSemesterData(sender, instance, created, **kwargs):
    if created:
        # Archive all previous active records
        Schedule.objects.filter(status="active").update(status="archived")
        Section.objects.filter(status="active").update(status="archived")
        SubjectOffering.objects.filter(status="active").update(status="archived")
        GenEdSchedule.objects.filter(status="active").update(status="archived")

        # Set other semesters inactive
        Semester.objects.exclude(pk=instance.pk).update(isActive=False)

        # Ensure the new one is active
        if not instance.isActive:
            instance.isActive = True
            instance.save()
