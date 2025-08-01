from django.db import models
import datetime
from scheduling.models import Semester

class SchedulingConfig(models.Model):
    normalStartTime = models.TimeField(default=datetime.time(8, 0))
    normalEndTime = models.TimeField(default=datetime.time(17, 0))
    overtimeEndTime = models.TimeField(default=datetime.time(20, 0))
    allowWeekends = models.BooleanField(default=True)
    maxSectionsPerSubject = models.IntegerField(default=5)
    createdAt = models.DateTimeField(auto_now_add=True)

class ScheduleConstraint(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)

    maxClassesPerInstructorPerDay = models.IntegerField(default=4)
    maxClassesPerInstructorPerWeek = models.IntegerField(default=20)
    roomsPerTimeslotLimit = models.IntegerField(default=1)
    minBreakBetweenClasses = models.IntegerField(default=1)
    enforceRoomCapacity = models.BooleanField(default=True)

    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("semester",)
        verbose_name = "Schedule Constraint"
        verbose_name_plural = "Schedule Constraints"

    def __str__(self):
        return f"Constraints for {self.semester}"
