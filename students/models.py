from django.db import models
from core.models import Department, User
from scheduling.models import Schedule, Subject
from django.utils import timezone



# ---------- Student ----------
class Student(models.Model):
    studentId = models.CharField(primary_key=True, max_length=20)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.studentId} - {self.user.lastName}, {self.user.firstName}"


# ---------- Enrollments ----------
class Enrollment(models.Model):
    enrollmentId = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.studentId} enrolled in {self.subject.subjectCode}"


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
