from django.contrib import admin
from .models import (
    Attendance,
    InstructorAbsence
)

admin.site.register(Attendance)
admin.site.register(InstructorAbsence)