from django.db.models.signals import post_save
from django.dispatch import receiver
from scheduling.models import Semester, Schedule, Section, SubjectOffering, GenEdSchedule, Subject

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

@receiver(post_save, sender=Subject)
def update_sections_on_subject_change(sender, instance, **kwargs):
    related_sections = Section.objects.filter(subject=instance)
    for section in related_sections:
        section.units = instance.units
        section.lectureMinutes = instance.durationMinutes
        section.hasLab = instance.hasLab
        section.labMinutes = instance.labDurationMinutes or 0
        section.isPriorityForRooms = instance.isPriorityForRooms
        section.save(update_fields=[
            'units',
            'lectureMinutes',
            'hasLab',
            'labMinutes',
            'isPriorityForRooms'
        ])
