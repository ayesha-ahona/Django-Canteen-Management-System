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
        # ('superadmin', 'Super Administrator'),   # ⛔️ removed: এখন vendor-ই full access
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

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_vendor(self) -> bool:
        return self.role == 'vendor'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    # নতুন ইউজার হলে default guest প্রোফাইল
    if created:
        UserProfile.objects.create(user=instance, role='guest')


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # fallback: profile না থাকলে তৈরি কর
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
    PAYMENT_METHOD_CHOICES = [('cash', 'Cash')]  # ভবিষ্যতে 'card', 'online' যোগ করা হবে

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_price = models.DecimalField(max_digits=8, decimal_places=2)
    address = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='cash')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} by {self.user.username}"

    # optional helper—template/view এ কাজে লাগতে পারে
    @property
    def is_paid(self) -> bool:
        return self.payment_status == 'paid'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=6, decimal_places=2)

    def line_total(self):
        return self.unit_price * self.quantity


# ---------------------------
# Reviews
# ---------------------------
class Review(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]  # 1..5

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # useful for edits

    class Meta:
        unique_together = ('user', 'item')  # প্রতি user প্রতি item একটাই রিভিউ
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.item.name} - {self.user.username} ({self.rating})"


# ✅ Recalculate cached rating on create/update/delete
def _recalc_item_rating(item: MenuItem):
    agg = Review.objects.filter(item=item).aggregate(
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
