from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Avg, Count
from django.contrib import messages

# --- Models (some may be optional in your project) ---
from .models import MenuItem, UserProfile, Order, OrderItem
try:
    from .models import Category        # optional
except Exception:
    Category = None                     # fallback if Category is not defined

try:
    from .models import Review          # optional
except Exception:
    Review = None                       # fallback if Review is not defined

# --- Forms (optional review form) ---
from .forms import CustomSignupForm
try:
    from .forms import ReviewForm       # optional
except Exception:
    ReviewForm = None


# -------------------- Helpers --------------------
def get_role(user):
    return getattr(user.userprofile, "role", "student")

def require_roles(user, allowed):
    return get_role(user) in allowed

def recommended_for_user(user, limit=8):
    """
    Recommend from user's past orders (most frequent items).
    Fallback to popular items if user has no history.
    """
    try:
        top_ids = (
            OrderItem.objects
            .filter(order__user=user)
            .values("item")
            .annotate(n=Count("id"))
            .order_by("-n")
            .values_list("item", flat=True)[:limit]
        )
        items = list(MenuItem.objects.filter(id__in=top_ids, is_active=True))
        if len(items) < 1:
            items = list(MenuItem.objects.filter(is_popular=True, is_active=True)[:limit])
        return items
    except Exception:
        # If OrderItem not available for any reason, return popular
        return list(MenuItem.objects.filter(is_popular=True, is_active=True)[:limit])


# -------------------- Home --------------------
def home(request):
    popular_items = MenuItem.objects.filter(is_popular=True, is_active=True)[:6]
    return render(request, "my_canteen/home.html", {"popular_items": popular_items})


# -------------------- Menu --------------------
def menu_page(request):
    q = request.GET.get("q", "") or ""
    min_price = request.GET.get("min_price") or ""
    max_price = request.GET.get("max_price") or ""
    sort = request.GET.get("sort") or ""
    active_cat = request.GET.get("cat") or ""

    items = MenuItem.objects.filter(is_active=True)

    # Category filter (works if you have Category FK or a 'category' field)
    if active_cat:
        if Category:
            items = items.filter(category_id=active_cat)
        else:
            # if no Category model, try by plain field name on MenuItem
            if hasattr(MenuItem, "category_id"):
                items = items.filter(category_id=active_cat)
            elif hasattr(MenuItem, "category"):
                items = items.filter(category=active_cat)

    # Search
    if q:
        items = items.filter(Q(name__icontains=q) | Q(description__icontains=q))

    # Price filter
    if min_price:
        items = items.filter(price__gte=min_price)
    if max_price:
        items = items.filter(price__lte=max_price)

    # Sorting
    if sort == "price_asc":
        items = items.order_by("price")
    elif sort == "price_desc":
        items = items.order_by("-price")
    else:
        items = items.order_by("-is_popular", "name")

    # Category list for chips
    if Category:
        categories = Category.objects.all().order_by("name")
    else:
        # build from MenuItem if Category absent
        categories = (
            MenuItem.objects.filter(is_active=True)
            .values("category__id", "category__name")
            .distinct()
        )
        # normalize to simple objects with id & name
        categories = [
            type("Cat", (), {"id": row["category__id"], "name": row["category__name"]})
            for row in categories if row["category__id"] is not None
        ]

    # Recommended for current user
    recommended = recommended_for_user(request.user) if request.user.is_authenticated else []

    ctx = {
        "items": items,
        "q": q,
        "min_price": min_price,
        "max_price": max_price,
        "sort": sort,
        "categories": categories,
        "active_cat": str(active_cat) if active_cat else "",
        "recommended": recommended,
    }
    return render(request, "my_canteen/menu.html", ctx)


# -------------------- Item Detail + Reviews (optional) --------------------
def item_detail(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, is_active=True)

    reviews = []
    avg_rating = 0
    reviews_count = 0
    can_review = False
    already = False
    form = None

    if Review:
        try:
            reviews_qs = Review.objects.filter(item=item).select_related("user").order_by("-created_at")
            agg = reviews_qs.aggregate(avg=Avg("rating"), cnt=Count("id"))
            avg_rating = round(agg.get("avg") or 0, 1)
            reviews_count = agg.get("cnt") or 0
            reviews = list(reviews_qs)
        except Exception:
            pass

        # can current user review?
        if request.user.is_authenticated:
            purchased = OrderItem.objects.filter(
                order__user=request.user,
                order__status__in=["delivered", "completed"],
                item=item,
            ).exists()
            already = Review.objects.filter(user=request.user, item=item).exists()
            can_review = purchased and not already
            if can_review and ReviewForm:
                form = ReviewForm()

    return render(
        request,
        "my_canteen/item_detail.html",
        {
            "item": item,
            "reviews": reviews,
            "avg_rating": avg_rating,
            "reviews_count": reviews_count,
            "can_review": can_review,
            "already": already,
            "form": form,
        },
    )


@login_required
def submit_review(request, item_id):
    if not (Review and ReviewForm):
        messages.error(request, "Review system is not enabled.")
        return redirect("item_detail", item_id=item_id)

    item = get_object_or_404(MenuItem, id=item_id, is_active=True)

    # verify purchase
    purchased = OrderItem.objects.filter(
        order__user=request.user,
        order__status__in=["delivered", "completed"],
        item=item,
    ).exists()
    if not purchased:
        messages.error(request, "You can review only after you have received this item.")
        return redirect("item_detail", item_id=item.id)

    if Review.objects.filter(user=request.user, item=item).exists():
        messages.info(request, "You already reviewed this item.")
        return redirect("item_detail", item_id=item.id)

    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            Review.objects.create(
                user=request.user,
                item=item,
                rating=form.cleaned_data["rating"],
                comment=form.cleaned_data["comment"],
            )
            messages.success(request, "Thanks for your feedback!")
        else:
            messages.error(request, "Invalid input.")
    return redirect("item_detail", item_id=item.id)


# -------------------- Cart --------------------
@login_required
def add_to_cart(request, item_id):
    cart = request.session.get("cart", {})
    cart[str(item_id)] = cart.get(str(item_id), 0) + 1
    request.session["cart"] = cart
    messages.success(request, "Item added to cart!")
    return redirect("menu")

@login_required
def add_to_cart_qty(request, item_id, qty=1):
    try:
        qty = int(qty)
        if qty <= 0:
            qty = 1
    except Exception:
        qty = 1
    cart = request.session.get("cart", {})
    cart[str(item_id)] = cart.get(str(item_id), 0) + qty
    request.session["cart"] = cart
    messages.success(request, f"Added {qty}x to cart!")
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
        try:
            qty = int(request.POST.get("qty", 1))
        except Exception:
            qty = 1
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
    total = 0.0
    for item_id, qty in cart.items():
        try:
            item = MenuItem.objects.get(id=item_id, is_active=True)
            subtotal = float(item.price) * int(qty)
            items.append({"item": item, "qty": qty, "subtotal": subtotal})
            total += subtotal
        except MenuItem.DoesNotExist:
            continue
    return render(request, "my_canteen/cart.html", {"items": items, "total": total})


# -------------------- Checkout --------------------
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
        status="pending",
        payment_status="unpaid",
        payment_method="cash",
    )

    total = 0.0
    for item_id, qty in cart.items():
        item = get_object_or_404(MenuItem, id=item_id)
        qty = int(qty)
        if item.stock < qty:
            messages.error(request, f"{item.name} is out of stock!")
            order.delete()
            return redirect("cart")

        # deduct stock
        item.stock -= qty
        item.save()

        OrderItem.objects.create(
            order=order, item=item, quantity=qty, unit_price=item.price
        )
        total += float(item.price) * qty

    order.total_price = total
    order.save()

    request.session["cart"] = {}
    messages.success(request, f"Order placed successfully! Total: {total} Tk (status: Pending)")
    return redirect("orders")


# -------------------- Orders --------------------
@login_required
def orders_page(request):
    profile = UserProfile.objects.get(user=request.user)
    role = get_role(request.user)

    if role in ["superadmin", "admin"]:
        orders = Order.objects.all().order_by("-created_at")
    elif role == "staff":
        orders = Order.objects.filter(status__in=["accepted", "preparing"]).order_by("-created_at")
    elif role == "vendor":
        orders = Order.objects.filter(status__in=["ready", "delivered"]).order_by("-created_at")
    else:
        orders = Order.objects.filter(user=request.user).order_by("-created_at")

    return render(request, "my_canteen/orders.html", {"orders": orders, "profile": profile})


# -------------------- Static Pages --------------------
def about_page(request):
    return render(request, "my_canteen/about.html")

def contact_page(request):
    return render(request, "my_canteen/contact.html")


# -------------------- Signup --------------------
def signup_page(request):
    if request.method == "POST":
        form = CustomSignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"]
            user.save()

            role = form.cleaned_data["role"]
            phone = form.cleaned_data.get("phone")

            # first user becomes superadmin
            if User.objects.count() == 1:
                role = "superadmin"

            profile = user.userprofile
            profile.role = role
            profile.phone = phone
            profile.save()

            messages.success(request, "Account created successfully! Please login.")
            return redirect("login")
    else:
        form = CustomSignupForm()
    return render(request, "my_canteen/signup.html", {"form": form})


# -------------------- Dashboard --------------------
@login_required
def dashboard(request):
    profile = UserProfile.objects.get(user=request.user)
    role = profile.role

    if role in ["superadmin", "admin"]:
        orders = Order.objects.all().order_by("-created_at")
        items = MenuItem.objects.all()
    elif role == "staff":
        orders = Order.objects.filter(status__in=["accepted", "preparing"]).order_by("-created_at")
        items = None
    elif role == "vendor":
        orders = Order.objects.filter(status__in=["ready", "delivered"]).order_by("-created_at")
        items = MenuItem.objects.all()
    else:
        orders = Order.objects.filter(user=request.user).order_by("-created_at")
        items = None

    template_name = f"my_canteen/dashboard/{role}.html"
    return render(request, template_name, {"profile": profile, "orders": orders, "items": items})


# -------------------- Profile & Settings --------------------
@login_required
def profile_page(request):
    profile = UserProfile.objects.get(user=request.user)
    return render(request, "my_canteen/profile.html", {"profile": profile})

@login_required
def settings_page(request):
    profile = UserProfile.objects.get(user=request.user)
    if request.method == "POST":
        email = request.POST.get("email") or request.user.email
        phone = request.POST.get("phone") or profile.phone

        request.user.email = email
        request.user.save()

        profile.phone = phone
        profile.save()

        messages.success(request, "Profile updated successfully!")
        return redirect("settings")

    return render(request, "my_canteen/settings.html", {"profile": profile})


# -------------------- Order Lifecycle Actions --------------------
@login_required
def order_accept(request, order_id):
    if not require_roles(request.user, ["superadmin", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "accepted"
    order.save()
    messages.success(request, f"Order #{order.id} accepted.")
    return redirect("dashboard")

@login_required
def order_preparing(request, order_id):
    if not require_roles(request.user, ["superadmin", "admin", "staff"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "preparing"
    order.save()
    messages.success(request, f"Order #{order.id} set to Preparing.")
    return redirect("dashboard")

@login_required
def order_ready(request, order_id):
    if not require_roles(request.user, ["superadmin", "admin", "staff"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "ready"
    order.save()
    messages.success(request, f"Order #{order.id} marked Ready.")
    return redirect("dashboard")

@login_required
def order_delivered(request, order_id):
    if not require_roles(request.user, ["superadmin", "admin", "vendor"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "delivered"
    order.save()
    messages.success(request, f"Order #{order.id} marked Delivered.")
    return redirect("dashboard")

@login_required
def order_completed(request, order_id):
    if not require_roles(request.user, ["superadmin", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    if order.payment_status != "paid":
        messages.warning(request, "Mark as Paid before completing.")
        return redirect("dashboard")
    order.status = "completed"
    order.save()
    messages.success(request, f"Order #{order.id} Completed.")
    return redirect("dashboard")

@login_required
def order_cancel(request, order_id):
    if not require_roles(request.user, ["superadmin", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "cancelled"
    order.save()
    messages.info(request, f"Order #{order.id} Cancelled.")
    return redirect("dashboard")

@login_required
def order_mark_paid(request, order_id):
    if not require_roles(request.user, ["superadmin", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.payment_status = "paid"
    order.save()
    messages.success(request, f"Order #{order.id} marked as PAID.")
    return redirect("dashboard")