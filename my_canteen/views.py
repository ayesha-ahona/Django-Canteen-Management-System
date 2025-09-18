from django.shortcuts import render

def home(request):
    demo_items = [
        {"name": "Chicken Burger", "price": 150, "img": "https://via.placeholder.com/150"},
        {"name": "Beef Pizza", "price": 300, "img": "https://via.placeholder.com/150"},
        {"name": "French Fries", "price": 80, "img": "https://via.placeholder.com/150"},
    ]
    return render(request, 'my_canteen/home.html', {"items": demo_items})
