from django.contrib import admin
from .models import InstructorExperience, InstructorAvailability, InstructorCredentials

admin.site.register(InstructorCredentials)
admin.site.register(InstructorExperience)
admin.site.register(InstructorAvailability)
