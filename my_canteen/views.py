# from django.shortcuts import render

# def home(request):
#     demo_items = [
#         {"name": "Chicken Burger", "price": 150, "img": "https://via.placeholder.com/150"},
#         {"name": "Beef Pizza", "price": 300, "img": "https://via.placeholder.com/150"},
#         {"name": "French Fries", "price": 80, "img": "https://via.placeholder.com/150"},
#     ]
#     return render(request, 'my_canteen/home.html', {"items": demo_items})

from django.shortcuts import render
from .models import MenuItem

def home(request):
    items = MenuItem.objects.all()   # DB থেকে সব খাবার আনে
    return render(request, 'my_canteen/home.html', {"items": items})

def menu_page(request):
    return render(request, 'my_canteen/menu.html')

def orders_page(request):
    return render(request, 'my_canteen/orders.html')

def about_page(request):
    return render(request, 'my_canteen/about.html')

def contact_page(request):
    return render(request, 'my_canteen/contact.html')
