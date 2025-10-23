# my_canteen/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Avg, Count
from django.contrib import messages
from django.http import (
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
    HttpResponse,
)
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from .models import MenuItem, UserProfile, Order, OrderItem, Review, Payment
from .forms import CustomSignupForm, ReviewForm, CheckoutPaymentForm


# ---------- Helpers ----------
def get_role(user):
    """UserProfile না থাকলে guest রিটার্ন করবে"""
    try:
        return user.userprofile.role
    except UserProfile.DoesNotExist:
        return "guest"


def get_effective_role(real_role: str) -> str:
    """
    UI/হেডিং-এ real_role দেখাবো, কিন্তু ক্ষমতা/ডেটা effective_role দিয়ে।
    - admin -> vendor ক্ষমতা
    - vendor -> admin ক্ষমতা
    - অন্যরা (student/faculty/staff/guest) -> আগের মতই
    """
    if real_role == "admin":
        return "vendor"
    if real_role == "vendor":
        return "admin"
    return real_role


def require_roles(user, allowed):
    """সহজ পারমিশন চেক"""
    return get_role(user) in allowed


def can_user_cancel(order, user) -> bool:
    """
    End-user smart cancel:
    student/faculty/guest নিজের অর্ডার preparing-এর আগ পর্যন্ত (pending/accepted) ক্যানসেল করতে পারবে।
    """
    role = get_role(user)
    if role not in {"student", "faculty", "guest"}:
        return False
    if order.user_id != user.id:
        return False
    return order.status in {"pending", "accepted"}


# ---------- Home ----------
def home(request):
    popular_items = MenuItem.objects.filter(is_popular=True, is_active=True)[:6]
    return render(request, "my_canteen/home.html", {"popular_items": popular_items})


# ---------- Menu ----------
def menu_page(request):
    query = request.GET.get("q")
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")

    items = MenuItem.objects.filter(is_active=True)

    if query:
        items = items.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if min_price:
        items = items.filter(price__gte=min_price)
    if max_price:
        items = items.filter(price__lte=max_price)

    return render(request, "my_canteen/menu.html", {"items": items})


# ---------- Item Detail + Reviews ----------
def item_detail(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, is_active=True)

    reviews = Review.objects.filter(item=item).select_related("user").order_by("-created_at")
    agg = reviews.aggregate(avg=Avg("rating"), cnt=Count("id"))
    avg_rating = round(agg["avg"] or 0, 1)
    total_reviews = agg["cnt"] or 0

    can_review, already, form = False, False, None
    if request.user.is_authenticated:
        purchased = OrderItem.objects.filter(
            order__user=request.user,
            order__status__in=["delivered", "completed"],
            item=item,
        ).exists()
        already = Review.objects.filter(user=request.user, item=item).exists()
        can_review = purchased and not already
        if can_review:
            form = ReviewForm()

    context = {
        "item": item,
        "reviews": reviews,
        "avg_rating": avg_rating,
        "total_reviews": total_reviews,
        "can_review": can_review,
        "already": already,
        "form": form,
    }
    return render(request, "my_canteen/item_detail.html", context)


@login_required
def submit_review(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, is_active=True)

    purchased = OrderItem.objects.filter(
        order__user=request.user,
        order__status__in=["delivered", "completed"],
        item=item,
    ).exists()
    if not purchased:
        messages.error(request, "You can review only after you received the item.")
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
            messages.success(request, "Thank you for your feedback!")
        else:
            messages.error(request, "Invalid input.")
    return redirect("item_detail", item_id=item.id)


@login_required
def edit_review(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, is_active=True)
    review = get_object_or_404(Review, item=item, user=request.user)

    if request.method == "POST":
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, "Your review has been updated.")
            return redirect("item_detail", item_id=item.id)
    else:
        form = ReviewForm(instance=review)

    return render(request, "my_canteen/review_edit.html", {"item": item, "form": form})


@login_required
def delete_review(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, is_active=True)
    review = get_object_or_404(Review, item=item, user=request.user)

    if request.method == "POST":
        review.delete()
        messages.success(request, "Your review has been deleted.")
        return redirect("item_detail", item_id=item.id)

    return HttpResponseForbidden("Invalid request")


# ---------- Cart ----------
@login_required
def add_to_cart(request, item_id):
    cart = request.session.get("cart", {})
    cart[str(item_id)] = cart.get(str(item_id), 0) + 1
    request.session["cart"] = cart
    messages.success(request, "Item added to cart!")
    return redirect("menu")


@login_required
def add_to_cart_qty(request, item_id, qty):
    qty = max(int(qty), 1)
    cart = request.session.get("cart", {})
    cart[str(item_id)] = cart.get(str(item_id), 0) + qty
    request.session["cart"] = cart
    messages.success(request, f"Added {qty} item(s) to cart.")
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
    items, total = [], 0

    for item_id, qty in cart.items():
        try:
            item = MenuItem.objects.get(id=item_id, is_active=True)
            subtotal = float(item.price) * qty
            items.append({"item": item, "qty": qty, "subtotal": subtotal})
            total += subtotal
        except MenuItem.DoesNotExist:
            continue

    return render(request, "my_canteen/cart.html", {"items": items, "total": total})


# ---------- Checkout + Payment ----------
@login_required
def checkout(request):
    cart = request.session.get("cart", {})
    if not cart:
        messages.error(request, "Your cart is empty!")
        return redirect("menu")

    total = 0
    cart_items = []
    for item_id, qty in cart.items():
        item = get_object_or_404(MenuItem, id=item_id, is_active=True)
        if item.stock < qty:
            messages.error(request, f"{item.name} is out of stock!")
            return redirect("cart")
        subtotal = float(item.price) * qty
        cart_items.append({"item": item, "qty": qty, "subtotal": subtotal})
        total += subtotal

    if request.method == "POST":
        form = CheckoutPaymentForm(request.POST)
        if form.is_valid():
            method = form.cleaned_data["payment_method"]

            order = Order.objects.create(
                user=request.user,
                total_price=total,
                address="Default Address",
                status="pending",
                payment_status="unpaid",
                payment_method=method,
            )

            for item_id, qty in cart.items():
                item = get_object_or_404(MenuItem, id=item_id)
                item.stock -= qty
                item.save()
                OrderItem.objects.create(
                    order=order, item=item, quantity=qty, unit_price=item.price
                )

            payment = Payment.objects.create(
                order=order, method=method, amount=order.total_price, status="pending"
            )

            if method == "cash":
                payment.status = "paid"
                payment.paid_at = timezone.now()
                payment.transaction_id = f"CASH-{order.id}-{int(timezone.now().timestamp())}"
                payment.save()
                order.payment_status = "paid"
                order.save()
                request.session["cart"] = {}
                messages.success(
                    request, f"Order placed successfully! Total: {total} Tk (Cash)"
                )
                return redirect("payment_success")

            elif method == "mock_card":
                payment.status = "paid"
                payment.paid_at = timezone.now()
                payment.transaction_id = f"MOCK-{order.id}-{int(timezone.now().timestamp())}"
                payment.save()
                order.payment_status = "paid"
                order.save()
                request.session["cart"] = {}
                messages.success(request, f"Payment successful! Order #{order.id}")
                return redirect("payment_success")

            request.session["cart"] = {}
            return redirect("payment_start", order_id=order.id)
    else:
        form = CheckoutPaymentForm()

    return render(
        request,
        "my_canteen/checkout.html",
        {"items": cart_items, "total": total, "form": form},
    )


def payment_start(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    payment = order.payment
    domain = request.build_absolute_uri("/")[:-1]

    if payment.method == "stripe":
        try:
            import stripe

            stripe.api_key = settings.STRIPE_SECRET_KEY
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "product_data": {"name": f"Canteen Order #{order.id}"},
                            "unit_amount": int(order.total_price * 100),
                        },
                        "quantity": 1,
                    }
                ],
                success_url=f"{domain}{reverse('payment_success')}",
                cancel_url=f"{domain}{reverse('payment_failed')}",
                client_reference_id=str(order.id),
            )
            payment.transaction_id = session.id
            payment.save()
            return redirect(session.url, code=303)
        except Exception as e:
            messages.error(request, f"Payment initialization failed: {str(e)}")
            return redirect("payment_failed")

    elif payment.method == "sslcommerz":
        messages.info(request, "SSLCommerz integration coming soon!")
        return redirect("payment_failed")

    return redirect("checkout")


def payment_success(request):
    return render(request, "my_canteen/payment_success.html")


def payment_failed(request):
    return render(request, "my_canteen/payment_failed.html")


@csrf_exempt
def stripe_webhook(request):
    # TODO: verify signature & mark paid
    return HttpResponse(status=200)


@csrf_exempt
def sslcommerz_ipn(request):
    # TODO: verify IPN & update payment
    return HttpResponse(status=200)


def order_status_api(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    data = {
        "order_id": order.id,
        "payment_status": getattr(order.payment, "status", "missing"),
        "transaction_id": getattr(order.payment, "transaction_id", None),
        "order_status": order.status,
    }
    return JsonResponse(data)


# ---------- Orders list page ----------
@login_required
def orders_page(request):
    profile = UserProfile.objects.select_related("user").get(user=request.user)
    role = get_role(request.user)

    if role in ["vendor", "admin"]:
        orders = Order.objects.all().order_by("-created_at")
    elif role == "staff":
        orders = Order.objects.filter(
            status__in=["accepted", "preparing"]
        ).order_by("-created_at")
    else:
        orders = Order.objects.filter(user=request.user).order_by("-created_at")

    # smart cancel: যে অর্ডারগুলো end-user ক্যানসেল করতে পারবে
    cancelable_ids = {o.id for o in orders if can_user_cancel(o, request.user)}

    return render(
        request,
        "my_canteen/orders.html",
        {"orders": orders, "profile": profile, "cancelable_ids": cancelable_ids},
    )


# ---------- Static pages + anchor redirects ----------
def about_page(request):
    return render(request, "my_canteen/about.html")


def contact_page(request):
    return render(request, "my_canteen/contact.html")


def about_anchor(request):
    return HttpResponseRedirect(f"{reverse('home')}#about")


def contact_anchor(request):
    return HttpResponseRedirect(f"{reverse('home')}#contact")


# ---------- Signup ----------
def signup_page(request):
    if request.method == "POST":
        form = CustomSignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data.get("email")
            user.save()

            role = form.cleaned_data.get("role", "guest")
            phone = form.cleaned_data.get("phone")

            # প্রথম ইউজারকে admin
            if User.objects.count() == 1:
                role = "admin"

            profile = user.userprofile
            valid_roles = ["admin", "student", "faculty", "staff", "vendor", "guest"]
            profile.role = role if role in valid_roles else "guest"
            profile.phone = phone
            profile.save()

            messages.success(
                request, f"Account created successfully as {profile.role}! Please login."
            )
            return redirect("login")
    else:
        form = CustomSignupForm()

    return render(request, "my_canteen/signup.html", {"form": form})


# ---------- Dashboard (admin <-> vendor swap) ----------
@login_required
def dashboard(request):
    """
    UI label/heading: real_role (যেমন Admin/Vendor লিখে থাকবে)
    কনটেন্ট/টেমপ্লেট + ডেটা: effective_role (admin <-> vendor swap)
    """
    profile = UserProfile.objects.select_related("user").get(user=request.user)

    real_role = profile.role
    effective_role = get_effective_role(real_role)

    # ডেটা লোডিং effective_role দিয়ে
    if effective_role in ["admin", "vendor"]:
        orders = Order.objects.all().order_by("-created_at")
        items = MenuItem.objects.all()
    elif effective_role == "staff":
        orders = Order.objects.filter(
            status__in=["accepted", "preparing"]
        ).order_by("-created_at")
        items = None
    else:
        orders = Order.objects.filter(user=request.user).order_by("-created_at")
        items = None

    # হেডিং real_role দিয়ে (UI)
    title_map = {
        "admin": "🛠️ Admin Dashboard",
        "vendor": "🏪 Vendor Dashboard",
        "staff": "👨‍🍳 Staff Dashboard",
        "student": "🎓 Student Dashboard",
        "faculty": "🎓 Faculty Dashboard",
        "guest": "👋 Welcome",
    }
    dashboard_title = title_map.get(real_role, "Dashboard")

    # কনটেন্ট টেমপ্লেট effective_role দিয়ে নির্বাচন (swap)
    template_name = f"my_canteen/dashboard/{effective_role}.html"

    ctx = {
        "profile": profile,
        "orders": orders,
        "items": items,
        "real_role": real_role,
        "effective_role": effective_role,
        "dashboard_title": dashboard_title,
    }
    return render(request, template_name, ctx)


# ---------- Optional vendor-only view (unused) ----------
@login_required
def vendor_dashboard(request):
    if get_role(request.user) != "vendor":
        messages.error(request, "Only vendor can access this dashboard.")
        return redirect("home")
    return render(request, "my_canteen/dashboard/superadmin.html")


# ---------- Profile / Settings ----------
@login_required
def profile_page(request):
    profile = UserProfile.objects.get(user=request.user)
    return render(request, "my_canteen/profile.html", {"profile": profile})


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
    return render(request, "my_canteen/settings.html", {"profile": profile})


# ---------- Order lifecycle (vendor & admin) ----------
@login_required
def order_accept(request, order_id):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "accepted"
    order.save()
    messages.success(request, f"Order #{order.id} accepted.")
    return redirect("dashboard")


@login_required
def order_preparing(request, order_id):
    if not require_roles(request.user, ["vendor", "admin", "staff"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "preparing"
    order.save()
    messages.success(request, f"Order #{order.id} set to Preparing.")
    return redirect("dashboard")


@login_required
def order_ready(request, order_id):
    if not require_roles(request.user, ["vendor", "admin", "staff"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "ready"
    order.save()
    messages.success(request, f"Order #{order.id} marked Ready.")
    return redirect("dashboard")


@login_required
def order_delivered(request, order_id):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "delivered"
    order.save()
    messages.success(request, f"Order #{order.id} marked Delivered.")
    return redirect("dashboard")


@login_required
def order_completed(request, order_id):
    if not require_roles(request.user, ["vendor", "admin"]):
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
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "cancelled"
    order.save()
    messages.info(request, f"Order #{order.id} Cancelled.")
    return redirect("dashboard")


@login_required
def order_mark_paid(request, order_id):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.payment_status = "paid"
    order.save()
    messages.success(request, f"Order #{order.id} marked as PAID.")
    return redirect("dashboard")


# ---------- End-user Smart Cancel ----------
@login_required
def user_order_cancel(request, order_id):
    """
    End-user (student/faculty/guest) নিজের অর্ডার preparing-এর আগ পর্যন্ত
    ক্যানসেল করতে পারবে। ক্যানসেল হলে স্টক রিস্টোর করা হবে।
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if not can_user_cancel(order, request.user):
        messages.error(request, "Sorry, you can no longer cancel this order.")
        return redirect("orders")

    # স্টক ফেরত দাও
    for oi in OrderItem.objects.filter(order=order).select_related("item"):
        oi.item.stock += oi.quantity
        oi.item.save(update_fields=["stock"])

    order.status = "cancelled"
    order.save(update_fields=["status"])

    messages.success(request, f"Order #{order.id} cancelled successfully.")
    return redirect("orders")
