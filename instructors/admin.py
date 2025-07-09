from django.contrib import admin
from .models import Instructor, InstructorExperience, TeachingHistory, InstructorAvailability

admin.site.register(Instructor)
admin.site.register(InstructorExperience)
admin.site.register(TeachingHistory)
admin.site.register(InstructorAvailability)
