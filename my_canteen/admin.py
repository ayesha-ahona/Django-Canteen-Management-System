from django.contrib import admin
from .models import MenuItem, Category, Order, OrderItem, Review, UserProfile
import re

# 🧾 Menu Item Admin Customization
@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "is_popular", "stock", "category", "is_active")
    list_filter = ("is_popular", "category", "is_active")
    search_fields = ("name",)
    actions = ["remove_popular_prefix"]

    def remove_popular_prefix(self, request, queryset):
        """
        Admin Action:
        Automatically remove 'Popular ' prefix from selected item names.
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


# 🧩 Other Models Registration (Default)
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("user", "total_price", "status", "payment_status", "created_at")
    list_filter = ("status", "payment_status", "created_at")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "item", "quantity", "unit_price")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "item", "rating", "created_at")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone")
