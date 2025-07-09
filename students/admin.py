from django.contrib import admin
from .models import Student, Enrollment, Attendance

admin.site.register(Student)
admin.site.register(Enrollment)
admin.site.register(Attendance)
