from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Review, Payment


# ------------------------------------------------
# 🧍 Custom Signup Form
# ------------------------------------------------
class CustomSignupForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    phone = forms.CharField(max_length=15, required=False, label="Phone")

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "username": "Choose a username",
            "email": "you@example.com",
            "phone": "Optional phone number",
            "password1": "Create a strong password",
            "password2": "Confirm password",
        }

        for name, field in self.fields.items():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " form-control").strip()
            if name in placeholders:
                field.widget.attrs["placeholder"] = placeholders[name]

        self.fields["username"].help_text = ""
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if " " in username:
            raise ValidationError("Username cannot contain spaces.")
        return username


# ------------------------------------------------
# ⭐ Review + Feedback Form (User Side)
# ------------------------------------------------
class ReviewForm(forms.ModelForm):
    """
    User feedback form — allows a logged-in user to rate and review a MenuItem.
    """
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.Select(
                choices=[(i, f"{i} ⭐") for i in range(1, 6)],
                attrs={"class": "form-select"},
            ),
            "comment": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Write your honest feedback about this item...",
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.item = kwargs.pop("item", None)
        super().__init__(*args, **kwargs)

    def clean_rating(self):
        rating = int(self.cleaned_data.get("rating"))
        if rating < 1 or rating > 5:
            raise ValidationError("Rating must be between 1 and 5.")
        return rating

    def clean(self):
        """
        Prevents duplicate reviews by the same user for the same item.
        """
        cleaned_data = super().clean()
        if self.user and self.item:
            from .models import Review
            if Review.objects.filter(user=self.user, item=self.item).exists():
                raise ValidationError("You have already reviewed this item.")
        return cleaned_data

    def save(self, commit=True):
        """
        Automatically attach user & item before saving.
        """
        review = super().save(commit=False)
        if self.user:
            review.user = self.user
        if self.item:
            review.item = self.item
        if commit:
            review.save()
        return review


# ------------------------------------------------
# 💳 Checkout Payment Form
# ------------------------------------------------
class CheckoutPaymentForm(forms.Form):
    """
    Form used during checkout to select a payment method.
    """
    payment_method = forms.ChoiceField(
        choices=Payment.METHOD_CHOICES,
        widget=forms.RadioSelect,
        label="Select Payment Method",
    )
    card_number = forms.CharField(
        required=False,
        max_length=16,
        label="Mock Card Number",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "1234 5678 9012 3456"})
    )
    card_cvc = forms.CharField(
        required=False,
        max_length=4,
        label="CVC",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "123"})
    )

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("payment_method")
        card_number = cleaned_data.get("card_number", "").strip()
        cvc = cleaned_data.get("card_cvc", "").strip()

        # Validation for mock card payments only
        if method == "mock_card":
            if not card_number or not cvc:
                raise ValidationError("Card number and CVC are required for card payments.")
            if not card_number.isdigit() or len(card_number) != 16:
                raise ValidationError("Card number must be 16 digits.")
            if not cvc.isdigit() or not (3 <= len(cvc) <= 4):
                raise ValidationError("CVC must be 3 or 4 digits.")
        return cleaned_data
