# forms.py (সম্পূর্ণ আপডেট করা কোড)

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Review


# -----------------------------
# Custom Signup Form (কোনো পরিবর্তন করা হয়নি)
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
# Review Form (এখানে পরিবর্তন করা হয়েছে)
# -----------------------------
class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            # ✅ পরিবর্তন: স্টার রেটিং সিস্টেমের জন্য rating ফিল্ডকে hidden করা হয়েছে
            "rating": forms.NumberInput(
                attrs={
                    'type': 'hidden',
                    'id': 'rating_input' # জাভাস্ক্রিপ্ট দিয়ে টার্গেট করার জন্য আইডি
                }
            ),
            "comment": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Write your feedback...", "class": "form-control"}
            ),
        }
    
    # সেফগার্ড—1..5 এর বাইরে গেলে আটকাবে (এটি ঠিকই আছে)
    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        if rating is None:
             raise ValidationError("Please provide a rating.")
        if not 1 <= rating <= 5:
            raise ValidationError("Rating must be between 1 and 5.")
        return rating