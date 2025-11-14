from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Review, MenuItem


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

    def _init_(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.item = kwargs.pop("item", None)
        super()._init_(*args, **kwargs)

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

        # যদি mock_card সিলেক্ট করে, তখনই card info চেক করব
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