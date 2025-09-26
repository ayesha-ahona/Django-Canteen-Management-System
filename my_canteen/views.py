from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.contrib import messages
from .models import MenuItem, UserProfile, Order, OrderItem
from .forms import CustomSignupForm

# ---------- Helpers ----------
def get_role(user):
    return user.userprofile.role

def require_roles(user, allowed):
    return get_role(user) in allowed


# ---------- Home ----------
def home(request):
    popular_items = MenuItem.objects.filter(is_popular=True, is_active=True)[:6]
    return render(request, 'my_canteen/home.html', {"popular_items": popular_items})


# ---------- Menu ----------
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

    # 🔥 Recommendations
    recommended = []
    if request.user.is_authenticated:
        previous_items = MenuItem.objects.filter(orderitem__order__user=request.user).distinct()
        recommended = previous_items[:4]

    return render(
        request,
        'my_canteen/menu.html',
        {'items': items, 'recommended': recommended}
    )


# ---------- Cart ----------
@login_required
def add_to_cart(request, item_id):
    cart = request.session.get("cart", {})
    cart[str(item_id)] = cart.get(str(item_id), 0) + 1
    request.session["cart"] = cart
    messages.success(request, "Item added to cart!")
    return redirect("menu")

@login_required
def remove_from_cart(request, item_id):
    cart = request.session.get("cart", {})
    cart.pop(str(item_id), None)
    request.session["cart"] = cart
    messages.info(request, "Item removed from cart.")
    return redirect("cart")

@login_required
def increase_cart_qty(request, item_id):
    cart = request.session.get("cart", {})
    if str(item_id) in cart:
        cart[str(item_id)] += 1
    request.session["cart"] = cart
    return redirect("cart")

@login_required
def decrease_cart_qty(request, item_id):
    cart = request.session.get("cart", {})
    if str(item_id) in cart:
        cart[str(item_id)] -= 1
        if cart[str(item_id)] <= 0:
            cart.pop(str(item_id))
    request.session["cart"] = cart
    return redirect("cart")

@login_required
def update_cart(request, item_id):
    if request.method == "POST":
        qty = int(request.POST.get("qty", 1))
        cart = request.session.get("cart", {})

        if qty > 0:
            cart[str(item_id)] = qty
        else:
            cart.pop(str(item_id), None)

        request.session["cart"] = cart
        messages.success(request, "Cart updated successfully!")

    return redirect("cart")

@login_required
def view_cart(request):
    cart = request.session.get("cart", {})
    items = []
    total = 0

    for item_id, qty in cart.items():
        try:
            item = MenuItem.objects.get(id=item_id, is_active=True)
            subtotal = float(item.price) * qty
            items.append({"item": item, "qty": qty, "subtotal": subtotal})
            total += subtotal
        except MenuItem.DoesNotExist:
            continue

    return render(request, "my_canteen/cart.html", {"items": items, "total": total})


# ---------- Checkout ----------
@login_required
def checkout(request):
    cart = request.session.get("cart", {})
    if not cart:
        messages.error(request, "Your cart is empty!")
        return redirect("menu")

    order = Order.objects.create(
        user=request.user,
        total_price=0,
        address="Default Address",
        status='pending',
        payment_status='unpaid',
        payment_method='cash'
    )

    total = 0
    for item_id, qty in cart.items():
        item = get_object_or_404(MenuItem, id=item_id)
        if item.stock < qty:
            messages.error(request, f"{item.name} is out of stock!")
            order.delete()
            return redirect("cart")

        item.stock -= qty
        item.save()

        OrderItem.objects.create(order=order, item=item, quantity=qty, unit_price=item.price)
        total += float(item.price) * qty

    order.total_price = total
    order.save()

    request.session["cart"] = {}
    messages.success(request, f"Order placed successfully! Total: {total} Tk (status: Pending)")
    return redirect("orders")


# ---------- Orders ----------
@login_required
def orders_page(request):
    profile = UserProfile.objects.get(user=request.user)
    if get_role(request.user) in ["superadmin", "admin"]:
        orders = Order.objects.all().order_by("-created_at")
    elif get_role(request.user) == "staff":
        orders = Order.objects.filter(status__in=["accepted", "preparing"]).order_by("-created_at")
    elif get_role(request.user) == "vendor":
        orders = Order.objects.filter(status__in=["ready", "delivered"]).order_by("-created_at")
    else:
        orders = Order.objects.filter(user=request.user).order_by("-created_at")

    return render(request, 'my_canteen/orders.html', {"orders": orders, "profile": profile})


# ---------- Static Pages ----------
def about_page(request):
    return render(request, 'my_canteen/about.html')

def contact_page(request):
    return render(request, 'my_canteen/contact.html')


# ---------- Signup ----------
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


# ---------- Dashboard ----------
@login_required
def dashboard(request):
    profile = UserProfile.objects.get(user=request.user)
    role = profile.role

    if role in ["superadmin", "admin"]:
        orders = Order.objects.all().order_by('-created_at')
        items = MenuItem.objects.all()
    elif role == "staff":
        orders = Order.objects.filter(status__in=["accepted", "preparing"]).order_by('-created_at')
        items = None
    elif role == "vendor":
        orders = Order.objects.filter(status__in=["ready", "delivered"]).order_by('-created_at')
        items = None
    else:
        orders = Order.objects.filter(user=request.user).order_by('-created_at')
        items = None

    template_name = f"my_canteen/dashboard/{role}.html"
    return render(request, template_name, {"profile": profile, "orders": orders, "items": items})


# ---------- Profile ----------
@login_required
def profile_page(request):
    profile = UserProfile.objects.get(user=request.user)
    return render(request, 'my_canteen/profile.html', {"profile": profile})


# ---------- Settings ----------
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


# ---------- Order Lifecycle Actions ----------
@login_required
def order_accept(request, order_id):
    if not require_roles(request.user, ['superadmin', 'admin']):
        messages.error(request, "Not authorized.")
        return redirect('dashboard')
    order = get_object_or_404(Order, id=order_id)
    order.status = 'accepted'
    order.save()
    messages.success(request, f"Order #{order.id} accepted.")
    return redirect('dashboard')

@login_required
def order_preparing(request, order_id):
    if not require_roles(request.user, ['superadmin', 'admin', 'staff']):
        messages.error(request, "Not authorized.")
        return redirect('dashboard')
    order = get_object_or_404(Order, id=order_id)
    order.status = 'preparing'
    order.save()
    messages.success(request, f"Order #{order.id} set to Preparing.")
    return redirect('dashboard')

@login_required
def order_ready(request, order_id):
    if not require_roles(request.user, ['superadmin', 'admin', 'staff']):
        messages.error(request, "Not authorized.")
        return redirect('dashboard')
    order = get_object_or_404(Order, id=order_id)
    order.status = 'ready'
    order.save()
    messages.success(request, f"Order #{order.id} marked Ready.")
    return redirect('dashboard')

@login_required
def order_delivered(request, order_id):
    if not require_roles(request.user, ['superadmin', 'admin', 'vendor']):
        messages.error(request, "Not authorized.")
        return redirect('dashboard')
    order = get_object_or_404(Order, id=order_id)
    order.status = 'delivered'
    order.save()
    messages.success(request, f"Order #{order.id} marked Delivered.")
    return redirect('dashboard')

@login_required
def order_completed(request, order_id):
    if not require_roles(request.user, ['superadmin', 'admin']):
        messages.error(request, "Not authorized.")
        return redirect('dashboard')
    order = get_object_or_404(Order, id=order_id)
    if order.payment_status != 'paid':
        messages.warning(request, "Mark as Paid before completing.")
        return redirect('dashboard')
    order.status = 'completed'
    order.save()
    messages.success(request, f"Order #{order.id} Completed.")
    return redirect('dashboard')

@login_required
def order_cancel(request, order_id):
    if not require_roles(request.user, ['superadmin', 'admin']):
        messages.error(request, "Not authorized.")
        return redirect('dashboard')
    order = get_object_or_404(Order, id=order_id)
    order.status = 'cancelled'
    order.save()
    messages.info(request, f"Order #{order.id} Cancelled.")
    return redirect('dashboard')

@login_required
def order_mark_paid(request, order_id):
    if not require_roles(request.user, ['superadmin', 'admin']):
        messages.error(request, "Not authorized.")
        return redirect('dashboard')
    order = get_object_or_404(Order, id=order_id)
    order.payment_status = 'paid'
    order.save()
    messages.success(request, f"Order #{order.id} marked as PAID.")
    return redirect('dashboard')
