from django.contrib import admin
from .models import MenuItem, Category, Order, OrderItem, Review, UserProfile

admin.site.register(MenuItem)
admin.site.register(Category)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Review)
admin.site.register(UserProfile)