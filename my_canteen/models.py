from django.db import models
from django.contrib.auth.models import User
from django.db.models import Avg, Count
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


# ---------------------------
# User & Roles
# ---------------------------

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin / Manager'),
        ('student', 'Student'),
        ('faculty', 'Faculty'),
        ('staff', 'Staff'),
        ('guest', 'Visitor / Guest'),
        ('vendor', 'Vendor / Supplier'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='guest')
    phone = models.CharField(max_length=15, blank=True, null=True)
    email_verified = models.BooleanField(default=False)  # ✅ New field


    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_vendor(self) -> bool:
        return self.role == 'vendor'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    # Default guest profile if new user

    if created:
        UserProfile.objects.create(user=instance, role='guest')


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # fallback: Create profile if not present

    try:
        instance.userprofile.save()
    except UserProfile.DoesNotExist:
        UserProfile.objects.create(user=instance, role='guest')


# ---------------------------
# Menu & Catalog
# ---------------------------

class Category(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='menu/', blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True)
    is_active = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False)

    # ✅ Cached rating fields (fast listing/sorting/filtering)

    rating_avg = models.FloatField(default=0)
    rating_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name


# ---------------------------
# Orders
# ---------------------------

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('delivered', 'Delivered'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_STATUS_CHOICES = [('unpaid', 'Unpaid'), ('paid', 'Paid')]
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('mock_card', 'Mock Card'),
        ('stripe', 'Stripe'),
        ('sslcommerz', 'SSLCommerz'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_price = models.DecimalField(max_digits=8, decimal_places=2)
    address = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='cash')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} by {self.user.username}"

    @property
    def is_paid(self) -> bool:
        return self.payment_status == 'paid'


# ---------------------------
# Payment (moved out of Order)
# ---------------------------

class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('mock_card', 'Mock Card'),
        ('stripe', 'Stripe'),
        ('sslcommerz', 'SSLCommerz'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    gateway_payload = models.JSONField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment for Order #{self.order_id} - {self.method} - {self.status}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=6, decimal_places=2)

    def line_total(self):
        return self.unit_price * self.quantity


# ---------------------------
# Reviews & Feedback
# ---------------------------

class Review(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]  # 1..5 stars


    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES, blank=True, null=True)
    feedback_title = models.CharField(max_length=100, blank=True, null=True)  # ✅ Optional title

    comment = models.TextField(blank=True, null=True)  # ✅ Feedback text

    is_public = models.BooleanField(default=True)  # ✅ Admin control (show/hide)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'item')
        ordering = ('-created_at',)

    def __str__(self):
        rating_part = f"{self.rating}★" if self.rating else "No rating"
        return f"{self.item.name} - {self.user.username} ({rating_part})"


# ✅ Recalculate cached rating on create/update/delete

def _recalc_item_rating(item: MenuItem):
    agg = Review.objects.filter(item=item, rating__isnull=False).aggregate(
        avg=Avg('rating'),
        cnt=Count('id'),
    )
    item.rating_avg = round((agg['avg'] or 0), 2)
    item.rating_count = agg['cnt'] or 0
    item.save(update_fields=['rating_avg', 'rating_count'])


@receiver(post_save, sender=Review)
def review_saved(sender, instance, created, **kwargs):
    _recalc_item_rating(instance.item)


@receiver(post_delete, sender=Review)
def review_deleted(sender, instance, **kwargs):
    _recalc_item_rating(instance.item)

class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "item")   # A user cannot favorite the same item twice


    def __str__(self):
        return f"{self.user.username} ❤️ {self.item.name}"



# ---------------------------
# Notifications
# ---------------------------

class Notification(models.Model):
    """
    Simple in-app notification + optional email.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)  # e.g. /orders/or /dashboard/

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} – {self.title}"
    
# ---------------------------
# Address
# ---------------------------

    
class Address(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="addresses"
    )
    label = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g. Home, Office, Hostel"
    )
    line1 = models.CharField(max_length=120, verbose_name="Address line 1")
    line2 = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Address line 2"
    )
    city = models.CharField(max_length=50, default="Dhaka")
    phone = models.CharField(max_length=20, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # If it is set to default, remove the default from all other addresses

        if self.is_default:
            Address.objects.filter(user=self.user).exclude(pk=self.pk).update(
                is_default=False
            )

    def __str__(self):
        title = self.label or "Address"
        return f"{title} - {self.line1[:25]}"