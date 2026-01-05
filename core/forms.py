from django import forms
from .models import User, Instructor

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
    
class InstructorChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        # This uses the 'full_name' property from your Instructor model
        return f"{obj.full_name} ({obj.instructorId})" 

class DepartmentHeadAssignmentForm(forms.Form):
    # 2. Use the custom field here instead of forms.ModelChoiceField
    newHead = InstructorChoiceField(
        queryset=Instructor.objects.filter(
            userlogin__user__isActive=True
        ).select_related().order_by('instructorId'), # Added select_related for performance
        label="Select New Department Head",
        widget=forms.Select(attrs={
            'class': 'w-full p-2 border border-emerald-300 rounded focus:ring-2 focus:ring-emerald-500 outline-none bg-white text-sm'
        }),
        empty_label="-- Choose an Instructor --"
    )
    
    confirmPassword = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full p-2 border border-emerald-300 rounded focus:ring-2 focus:ring-emerald-500 outline-none bg-white text-sm',
            'placeholder': 'Enter your password to confirm transfer'
        }),
        label="Confirm Password",
        required=False
    )