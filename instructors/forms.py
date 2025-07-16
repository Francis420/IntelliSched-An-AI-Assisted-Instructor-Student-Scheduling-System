from django import forms
from .models import InstructorExperience

class InstructorExperienceForm(forms.ModelForm):
    class Meta:
        model = InstructorExperience
        exclude = ['instructor', 'isVerified', 'createdAt']
