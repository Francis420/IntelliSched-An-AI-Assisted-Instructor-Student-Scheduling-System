# instructors/signals.py

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.apps import apps

# We use apps.get_model to avoid circular import errors
Schedule = apps.get_model('scheduling', 'Schedule')
TeachingAssignment = apps.get_model('instructors', 'TeachingAssignment')

@receiver(post_save, sender=Schedule)
def sync_schedule_to_history(sender, instance, **kwargs):
    """
    Triggered when a Schedule is saved.
    If status is 'finalized', ensure a TeachingAssignment exists and recalculate hours.
    """
    # Only process if schedule is Finalized
    if instance.status == 'finalized':
        
        # 1. Get/Create the Assignment for this specific SECTION
        # This acts as the "Master Record" for this class
        assignment, created = TeachingAssignment.objects.get_or_create(
            instructor=instance.instructor,
            subject=instance.subject,
            semester=instance.semester,
            section=instance.section
        )
        
        # 2. Recalculate Total Hours
        # We query ALL finalized schedule entries for this specific section.
        # This handles split schedules (e.g., Mon Lecture + Wed Lab) correctly.
        all_section_schedules = Schedule.objects.filter(
            instructor=instance.instructor,
            subject=instance.subject,
            semester=instance.semester,
            section=instance.section,
            status='finalized'
        )
        
        # Sum durations (using the property from your Schedule model)
        total_mins = sum(s.duration_minutes for s in all_section_schedules)
        
        # Update and Save
        assignment.totalTeachingHours = round(total_mins / 60, 2)
        assignment.save()

@receiver(post_delete, sender=Schedule)
def cleanup_history_on_delete(sender, instance, **kwargs):
    """
    If a Finalized Schedule is deleted, re-calculate the hours or remove the assignment.
    """
    if instance.status == 'finalized':
        try:
            assignment = TeachingAssignment.objects.get(
                instructor=instance.instructor,
                subject=instance.subject,
                semester=instance.semester,
                section=instance.section
            )
            
            # Check if any schedules remain for this section
            remaining_schedules = Schedule.objects.filter(
                instructor=instance.instructor,
                subject=instance.subject,
                semester=instance.semester,
                section=instance.section,
                status='finalized'
            )

            if not remaining_schedules.exists():
                # If no schedules left, delete the history record entirely
                assignment.delete()
            else:
                # Recalculate
                total_mins = sum(s.duration_minutes for s in remaining_schedules)
                assignment.totalTeachingHours = round(total_mins / 60, 2)
                assignment.save()

        except TeachingAssignment.DoesNotExist:
            pass