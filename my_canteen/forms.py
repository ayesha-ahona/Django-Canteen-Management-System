from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Review


# -----------------------------
# Custom Signup Form
# -----------------------------
class CustomSignupForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    phone = forms.CharField(max_length=15, required=False, label="Phone")

    # Signup-এ যে রোলগুলো সিলেক্ট করা যাবে
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('faculty', 'Faculty'),
        ('staff', 'Staff'),
        ('guest', 'Visitor / Guest'),
        ('vendor', 'Vendor / Supplier'),
        # admin কে ফর্ম থেকে selectable করা হয়নি (প্রয়োজনে view প্রথম ইউজারকে admin করবে)
    ]
    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True, label="Role")

    class Meta:
        model = User
        fields = ["username", "email", "phone", "role", "password1", "password2"]

    # একটু সুন্দর ইনপুট UI (class/placeholder)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "username": "Choose a username",
            "email": "you@example.com",
            "phone": "Optional",
            "password1": "Create a strong password",
            "password2": "Confirm password",
        }
        for name, field in self.fields.items():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " form-control").strip()
            if name in placeholders:
                field.widget.attrs["placeholder"] = placeholders[name]

        # ছোট help text clean-up
        self.fields["username"].help_text = ""
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

    # ইমেইল unique থাকা উচিত
    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered.")
        return email

    # ইউজারনেম একটু normalize
    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if " " in username:
            raise ValidationError("Username cannot contain spaces.")
        return username


# -----------------------------
# Review Form
# -----------------------------
class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.Select(
                attrs={"class": "form-control"},
                choices=[(i, str(i)) for i in range(1, 6)],
            ),
            "comment": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Write your feedback...", "class": "form-control"}
            ),
        }

    # সেফগার্ড—1..5 এর বাইরে গেলে আটকাবে
    def clean_rating(self):
        rating = int(self.cleaned_data.get("rating"))
        if rating < 1 or rating > 5:
            raise ValidationError("Rating must be between 1 and 5.")
        return rating
