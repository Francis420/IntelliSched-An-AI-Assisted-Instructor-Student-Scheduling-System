from django.contrib import admin
from .models import InstructorExperience, InstructorCredentials

admin.site.register(InstructorCredentials)
admin.site.register(InstructorExperience)
