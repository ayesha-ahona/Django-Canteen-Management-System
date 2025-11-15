from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Review, MenuItem, Payment, Address


# ------------------------------------------------
# 🧍 Custom Signup Form
# ------------------------------------------------


class CustomSignupForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    phone = forms.CharField(max_length=15, required=False, label="Phone")

    ROLE_CHOICES = [
        ("student", "Student"),
        ("faculty", "Faculty"),
        ("staff", "Staff"),
        ("guest", "Visitor / Guest"),
        ("vendor", "Vendor / Supplier"),
    ]
    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True, label="Role")

    class Meta:
        model = User
        fields = ["username", "email", "phone", "role", "password1", "password2"]

    def _init_(self, *args, **kwargs):
        super()._init_(*args, **kwargs)
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

        # default help_text hide


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


# my_canteen/forms.py
from django import forms
from .models import Review

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")

        # 1) rating absent হলে ValidationError দাও, int() কোরো না
        if rating in (None, ""):
            raise forms.ValidationError("Please select a rating.")

        # 2) string হলে int এ convert করো
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            raise forms.ValidationError("Invalid rating value.")

        # 3) range check
        if not (1 <= rating <= 5):
            raise forms.ValidationError("Rating must be between 1 and 5.")

        return rating



# ------------------------------------------------
# 💳 Checkout Payment Form
# ------------------------------------------------


class CheckoutPaymentForm(forms.Form):
    PAYMENT_CHOICES = [
        ("cash", "Cash"),
        ("mock_card", "Card (Demo)"),
        ("bkash", "bKash (Demo)"),
        ("nagad", "Nagad (Demo)"),
    ]

    payment_method = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        widget=forms.RadioSelect,
    )

    # Mock card fields (demo)


    card_number = forms.CharField(
        required=False,
        label="Card Number",
        widget=forms.TextInput(attrs={"placeholder": "1111 2222 3333 4444"}),
    )
    card_cvc = forms.CharField(
        required=False,
        label="CVC",
        widget=forms.TextInput(attrs={"placeholder": "123"}),
    )

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("payment_method")
        card_number = cleaned.get("card_number")
        card_cvc = cleaned.get("card_cvc")

        # if it is mock_card, info is  mandatory


        if method == "mock_card":
            if not card_number or not card_cvc:
                raise ValidationError(
                    "For demo card payment, please enter any card number and CVC."
                )
        return cleaned


# ------------------------------------------------
# 🍽 Menu Item Management Form (Admin/Vendor Side)
# ------------------------------------------------


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = [
            "name",
            "category",
            "price",
            "stock",
            "image",
            "description",
            "is_active",
            "is_popular",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Item name"}
            ),
            "category": forms.Select(attrs={"class": "form-control"}),
            "price": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "stock": forms.NumberInput(
                attrs={"class": "form-control", "min": 0}
            ),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_popular": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


# ------------------------------------------------
# 📮 Address Book Form
# ------------------------------------------------


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["label", "line1", "line2", "city", "phone", "is_default"]
        widgets = {
            "label": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Home / Office / Hostel"}
            ),
            "line1": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "House, road, area"}
            ),
            "line2": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Floor / Landmark (optional)",
                }
            ),
            "city": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "City"}
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Contact phone (optional)",
                }
            ),
            "is_default": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }