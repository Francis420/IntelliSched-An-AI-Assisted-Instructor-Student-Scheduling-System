from django.db import models
from core.models import Student
from scheduling.models import Schedule


# ---------- Attendance ----------
class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
    ]

    attendanceId = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    qrCode = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.student.studentId} - {self.date} ({self.status})"
