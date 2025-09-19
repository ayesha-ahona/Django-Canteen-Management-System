from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from .models import MenuItem, UserProfile, Order
from .forms import CustomSignupForm

# Home page (popular items)
def home(request):
    popular_items = MenuItem.objects.filter(is_popular=True, is_active=True)[:6]
    return render(request, 'my_canteen/home.html', {"popular_items": popular_items})

# Menu page (search + filter)
def menu_page(request):
    query = request.GET.get('q')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    items = MenuItem.objects.filter(is_active=True)

    if query:
        items = items.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if min_price:
        items = items.filter(price__gte=min_price)
    if max_price:
        items = items.filter(price__lte=max_price)

    return render(request, 'my_canteen/menu.html', {'items': items})

def orders_page(request):
    return render(request, 'my_canteen/orders.html')

def about_page(request):
    return render(request, 'my_canteen/about.html')

def contact_page(request):
    return render(request, 'my_canteen/contact.html')

# Signup
def signup_page(request):
    if request.method == 'POST':
        form = CustomSignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.save()
            role = form.cleaned_data['role']
            phone = form.cleaned_data.get('phone')
            if User.objects.count() == 1:
                role = 'superadmin'
            UserProfile.objects.create(user=user, role=role, phone=phone)
            return redirect('login')
    else:
        form = CustomSignupForm()
    return render(request, 'my_canteen/signup.html', {'form': form})

# Role Based Dashboard
@login_required
def dashboard(request):
    profile, created = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={'role': 'guest'}
    )

    role = profile.role

    if role == "superadmin":
        orders = Order.objects.all().order_by('-created_at')
    elif role == "admin":
        orders = Order.objects.all().order_by('-created_at')
    elif role == "staff":
        orders = Order.objects.filter(status="processing").order_by('-created_at')
    elif role == "vendor":
        orders = []  # vendor-specific later
    else:  # student, faculty, guest
        orders = Order.objects.filter(user=request.user).order_by('-created_at')

    template_name = f"my_canteen/dashboard/{role}.html"
    return render(request, template_name, {"profile": profile, "orders": orders})
