from django.db import models
from core.models import Student
from scheduling.models import Schedule, Subject
from instructors.models import Instructor


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


# ---------- Instructor Monitoring (Absences) ----------
class InstructorAbsence(models.Model):
    REPORT_TYPE_CHOICES = [
        ('auto-detected', 'Auto Detected'),
        ('manual', 'Manual'),
    ]

    absenceId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE)
    reportType = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    reason = models.TextField(blank=True, null=True)
    dateMissed = models.DateField()
    reportedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} missed {self.subject.code} on {self.dateMissed}"
