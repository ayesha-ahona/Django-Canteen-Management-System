from django.contrib import admin
from .models import UserProfile, Category, MenuItem, Order, OrderItem

admin.site.register(UserProfile)
admin.site.register(Category)
admin.site.register(MenuItem)
admin.site.register(Order)
admin.site.register(OrderItem)
