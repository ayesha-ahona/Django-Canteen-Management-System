from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class CustomSignupForm(UserCreationForm):
    ROLE_CHOICES = [
        ('superadmin', 'Super Administrator'),
        ('admin', 'Admin / Manager'),
        ('student', 'Student'),
        ('faculty', 'Faculty'),
        ('staff', 'Staff'),
        ('guest', 'Visitor / Guest'),
        ('vendor', 'Vendor / Supplier'),
    ]
    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)
    phone = forms.CharField(required=False, max_length=15)

    class Meta:
        model = User
        fields = ['username', 'password1', 'password2', 'role', 'phone']
