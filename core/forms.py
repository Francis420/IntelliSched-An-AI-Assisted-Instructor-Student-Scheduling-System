from django import forms
from .models import User

class InstructorProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'firstName', 'lastName', 'email', 'profilePic']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none'}),
            'firstName': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none'}),
            'lastName': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-4 py-2 border rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none'}),
            'profilePic': forms.FileInput(attrs={'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        # Check if username exists and doesn't belong to the current user
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This username is already taken. Please choose another one.")
        return username