from django.contrib import admin
from .models import (
    MenuItem, Category, Order, OrderItem, Review,
    UserProfile, Payment
)
import re


# --------------------------------------------------
# 🧾 Menu Item Admin Customization
# --------------------------------------------------
@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = (
        "name", "price", "stock", "category",
        "is_popular", "is_active", "rating_avg", "rating_count"
    )
    list_filter = ("is_popular", "category", "is_active")
    search_fields = ("name", "description")
    actions = ["remove_popular_prefix", "mark_as_popular"]

    def remove_popular_prefix(self, request, queryset):
        """
        🧹 Admin Action:
        Remove 'Popular ' prefix from selected item names.
        """
        pattern = re.compile(r'^\s*(popular)\s+', re.IGNORECASE)
        changed = 0
        for item in queryset:
            new_name = pattern.sub('', item.name).strip()
            new_name = re.sub(r'\s{2,}', ' ', new_name)
            if new_name != item.name:
                item.name = new_name
                item.save(update_fields=["name"])
                changed += 1
        self.message_user(request, f"✅ Fixed {changed} item name(s).")

    remove_popular_prefix.short_description = "🧹 Remove 'Popular ' prefix from selected names"

    def mark_as_popular(self, request, queryset):
        """
        🌟 Mark selected items as popular.
        """
        updated = queryset.update(is_popular=True)
        self.message_user(request, f"⭐ {updated} item(s) marked as popular.")

    mark_as_popular.short_description = "🌟 Mark as Popular"


# --------------------------------------------------
# 🧩 Category Admin
# --------------------------------------------------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


# --------------------------------------------------
# 💳 Payment Admin
# --------------------------------------------------
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "amount", "status", "transaction_id", "paid_at")
    list_filter = ("method", "status", "paid_at")
    search_fields = ("transaction_id", "order__user__username")


# --------------------------------------------------
# 🧺 Order and OrderItem Admin
# --------------------------------------------------
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("line_total",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "total_price", "status",
        "payment_status", "payment_method", "created_at"
    )
    list_filter = ("status", "payment_status", "payment_method", "created_at")
    search_fields = ("user__username", "id")
    inlines = [OrderItemInline]
    readonly_fields = ("created_at",)

    def payment_info(self, obj):
        if hasattr(obj, 'payment'):
            return f"{obj.payment.method} - {obj.payment.status}"
        return "—"
    payment_info.short_description = "Payment Info"


# --------------------------------------------------
# 📦 OrderItem Admin
# --------------------------------------------------
@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "item", "quantity", "unit_price", "line_total")
    search_fields = ("order__user__username", "item__name")


# --------------------------------------------------
# ⭐ Review Admin
# --------------------------------------------------
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "item", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("user__username", "item__name", "comment")
    readonly_fields = ("created_at", "updated_at")


# --------------------------------------------------
# 👤 User Profile Admin
# --------------------------------------------------
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "email_verified")
    list_filter = ("role", "email_verified")
    search_fields = ("user__username", "user__email", "phone")
