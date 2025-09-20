from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.contrib import messages
from .models import MenuItem, UserProfile, Order
from .forms import CustomSignupForm


# ---------------- Home ----------------
def home(request):
    popular_items = MenuItem.objects.filter(is_popular=True, is_active=True)[:6]
    return render(request, 'my_canteen/home.html', {"popular_items": popular_items})


# ---------------- Menu ----------------
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


# ---------------- Cart System ----------------
def add_to_cart(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)
    cart = request.session.get("cart", {})

    if str(item_id) in cart:
        cart[str(item_id)]["quantity"] += 1
    else:
        cart[str(item_id)] = {
            "name": item.name,
            "price": float(item.price),
            "quantity": 1
        }

    request.session["cart"] = cart
    messages.success(request, f"{item.name} added to cart!")
    return redirect("menu")


def view_cart(request):
    cart = request.session.get("cart", {})
    total = sum(item["price"] * item["quantity"] for item in cart.values())
    return render(request, "my_canteen/cart.html", {"cart": cart, "total": total})


@login_required
def checkout(request):
    cart = request.session.get("cart", {})

    if not cart:
        messages.error(request, "Your cart is empty!")
        return redirect("menu")

    total_price = sum(item["price"] * item["quantity"] for item in cart.values())

    order = Order.objects.create(
        user=request.user,
        total_price=total_price,
        address="Sample Address"
    )

    for item_id, item_data in cart.items():
        menu_item = MenuItem.objects.get(id=int(item_id))

        if menu_item.stock < item_data["quantity"]:
            messages.error(request, f"{menu_item.name} does not have enough stock!")
            return redirect("cart")

        menu_item.stock -= item_data["quantity"]
        menu_item.save()
        order.items.add(menu_item)

    order.save()
    request.session["cart"] = {}

    messages.success(request, "✅ Order placed successfully!")
    return redirect("orders")


# ---------------- Orders ----------------
@login_required
def orders_page(request):
    profile = UserProfile.objects.get(user=request.user)
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return render(request, 'my_canteen/orders.html', {"orders": orders, "profile": profile})


# ---------------- Dashboard ----------------
@login_required
def dashboard(request):
    profile = UserProfile.objects.get(user=request.user)
    role = profile.role

    if role in ["superadmin", "admin"]:
        orders = Order.objects.all().order_by('-created_at')
        items = MenuItem.objects.all()
    elif role == "staff":
        orders = Order.objects.filter(status="processing").order_by('-created_at')
        items = None
    elif role == "vendor":
        orders = []
        items = None
    else:
        orders = Order.objects.filter(user=request.user).order_by('-created_at')
        items = None

    template_name = f"my_canteen/dashboard/{role}.html"
    return render(request, template_name, {"profile": profile, "orders": orders, "items": items})


# ---------------- Profile ----------------
@login_required
def profile_page(request):
    profile = UserProfile.objects.get(user=request.user)
    return render(request, 'my_canteen/profile.html', {"profile": profile})


# ---------------- Settings ----------------
@login_required
def settings_page(request):
    profile = UserProfile.objects.get(user=request.user)

    if request.method == "POST":
        email = request.POST.get("email")
        phone = request.POST.get("phone")

        request.user.email = email
        request.user.save()

        profile.phone = phone
        profile.save()

        messages.success(request, "Profile updated successfully!")
        return redirect("settings")

    return render(request, 'my_canteen/settings.html', {"profile": profile})


# ---------------- Signup ----------------
def signup_page(request):
    if request.method == 'POST':
        form = CustomSignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.save()

            role = form.cleaned_data['role']
            phone = form.cleaned_data.get('phone')

            if User.objects.count() == 1:
                role = 'superadmin'

            profile = user.userprofile
            profile.role = role
            profile.phone = phone
            profile.save()

            messages.success(request, "Account created successfully! Please login.")
            return redirect('login')
    else:
        form = CustomSignupForm()
    return render(request, 'my_canteen/signup.html', {'form': form})


# ---------------- Static Pages ----------------
def about_page(request):
    return render(request, 'my_canteen/about.html')

def contact_page(request):
    return render(request, 'my_canteen/contact.html')
