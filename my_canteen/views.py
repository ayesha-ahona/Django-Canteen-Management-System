from datetime import datetime, timedelta
import io

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import (
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
    HttpResponse,
)
from django.db.models import Q, Avg, Count, Sum, F
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.core.paginator import Paginator

# ========= PDF =========


from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors

# ========= Notifications helper =========


from .utils import send_notification

# ========= Email verification imports =========


from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db.models.functions import TruncDate

from .models import (
    MenuItem,
    Category,
    UserProfile,
    Order,
    OrderItem,
    Review,
    Payment,
    Favorite,
    Notification,
    Address,
)
from .forms import (
    CustomSignupForm,
    ReviewForm,
    CheckoutPaymentForm,
    MenuItemForm,
    AddressForm,
)

# ----------COUPON /PROMO CODES ----------


COUPON_CODES = {
    "FOOD10": 10,
    "WELCOME20": 20,
    "STUDENT5": 5,
    "FESTIVE15": 15,
    "VIP25": 25,
    "HAPPY30": 30,
    "SAVE30": 30,
    "MEAL40": 40,
    "BUDGET35": 35,
    "SNACK15": 15,
    "LUNCH20": 20,
}


# ========== Email Verification Token ==========


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        profile = getattr(user, "userprofile", None)
        verified = "1" if profile and profile.email_verified else "0"
        return f"{user.pk}{timestamp}{user.is_active}{verified}"


email_token_generator = EmailVerificationTokenGenerator()


# ========== Send Verification Email ==========


def send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_token_generator.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse("verify_email", kwargs={"uidb64": uid, "token": token})
    )

    subject = "Verify your email - Canteen"
    message = (
        f"Hello {user.username},\n\n"
        f"Please verify your account by clicking the link below:\n{verify_url}\n\nThanks!"
    )
    send_mail(subject, message, None, [user.email])


# ========== Custom Login View ==========


class CustomLoginView(auth_views.LoginView):
    template_name = "my_canteen/login.html"

    def form_valid(self, form):
        user = form.get_user()
        if not user.userprofile.email_verified:
            messages.error(self.request, "⚠ Please verify your email before login.")
            return redirect("login")
        return super().form_valid(form)


# ========== Signup ==========


def signup_page(request):
    if request.method == "POST":
        form = CustomSignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"]
            user.is_active = True
            user.save()

            role = form.cleaned_data.get("role", "guest")
            phone = form.cleaned_data.get("phone")

            # First user → admin


            if User.objects.count() == 1:
                role = "admin"

            profile = user.userprofile
            valid_roles = ["admin", "student", "faculty", "staff", "vendor", "guest"]
            profile.role = role if role in valid_roles else "guest"
            profile.phone = phone
            profile.email_verified = False
            profile.save()

            # verification mail


            send_verification_email(request, user)
            messages.success(
                request,
                "✅ Account created! We sent a verification link to your email.",
            )
            return redirect("login")
    else:
        form = CustomSignupForm()

    return render(request, "my_canteen/signup.html", {"form": form})


# ========== Verify Email ==========


def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and email_token_generator.check_token(user, token):
        profile = user.userprofile
        profile.email_verified = True
        profile.save()
        login(request, user)
        messages.success(request, "🎉 Email verified! You are now logged in.")
        return redirect("dashboard")
    else:
        messages.error(request, "Invalid or expired verification link.")
        return redirect("login")


# ========== Resend Verification ==========


@login_required
def resend_verification(request):
    profile = request.user.userprofile
    if profile.email_verified:
        messages.info(request, "Your email is already verified.")
        return redirect("dashboard")

    send_verification_email(request, request.user)
    messages.success(request, "Verification link sent again to your email.")
    return redirect("login")


# ----------Helpers ----------


def get_role(user):
    """If UserProfile does not exist, return 'guest'."""
    try:
        return user.userprofile.role
    except UserProfile.DoesNotExist:
        return "guest"


def get_effective_role(real_role: str) -> str:
    """
    UI তে real_role দেখাবো, কিন্তু permission/data side এ swap:
    - admin → vendor permission
    - vendor → admin permission
    """
    if real_role == "admin":
        return "vendor"
    if real_role == "vendor":
        return "admin"
    return real_role


def require_roles(user, allowed):
    """Simple permission check"""
    return get_role(user) in allowed


def can_user_cancel(order, user) -> bool:
    """
    Student/Faculty/Guest নিজের order cancel করতে পারবে
    যতক্ষণ পর্যন্ত status pending/accepted.
    """
    role = get_role(user)
    if role not in {"student", "faculty", "guest"}:
        return False
    if order.user_id != user.id:
        return False
    return order.status in {"pending", "accepted"}


# ========= Recommendation helpers ==========


def get_user_top_categories(user, limit=3):
    """
    User has eaten more food from any category
    (calculated from delivered/completed order)
    """
    if not user.is_authenticated:
        return Category.objects.none()

    qs = (
        OrderItem.objects.filter(
            order__user=user,
            order__status__in=["delivered", "completed"],
        )
        .exclude(item__category__isnull=True)
        .values("item__category")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")
    )

    cat_ids = [row["item__category"] for row in qs[:limit]]
    return Category.objects.filter(id__in=cat_ids)


def get_recommended_items(user, base_item=None, limit=6):
    """
    If base_item → same category
    If not → user top categories
    All fallback → popular items
    """
    qs = MenuItem.objects.filter(is_active=True)

    if base_item and base_item.category:
        qs = qs.filter(category=base_item.category).exclude(id=base_item.id)
    elif user.is_authenticated:
        top_cats = get_user_top_categories(user)
        if top_cats:
            qs = qs.filter(category__in=top_cats)

    qs = qs.order_by("-is_popular", "name")
    return qs[:limit]


# ----------Home ----------


def home(request):
    popular_items = MenuItem.objects.filter(is_popular=True, is_active=True)[:6]
    return render(request, "my_canteen/home.html", {"popular_items": popular_items})


# ----------Menu ----------


def menu_page(request):
    q = request.GET.get("q", "").strip()
    min_price = request.GET.get("min_price") or ""
    max_price = request.GET.get("max_price") or ""
    sort = request.GET.get("sort") or ""
    active_cat = request.GET.get("cat") or ""

    items = MenuItem.objects.filter(is_active=True)

    # category filter


    if active_cat:
        try:
            items = items.filter(category_id=int(active_cat))
        except ValueError:
            active_cat = ""

    # search filter


    if q:
        items = items.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )

    # price range


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

    categories = Category.objects.all().order_by("name")

    recommended_items = MenuItem.objects.filter(
        is_active=True, is_popular=True
    )[:6]

    context = {
        "items": items,
        "categories": categories,
        "active_cat": active_cat,
        "q": q,
        "min_price": min_price,
        "max_price": max_price,
        "sort": sort,
        "recommended_items": recommended_items,
    }
    return render(request, "my_canteen/menu.html", context)


# ----------Item Detail + Reviews ----------


def item_detail(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, is_active=True)

    reviews = (
        Review.objects.filter(item=item)
        .select_related("user")
        .order_by("-created_at")
    )
    agg = reviews.aggregate(avg=Avg("rating"), cnt=Count("id"))
    avg_rating = round(agg["avg"] or 0, 1)
    total_reviews = agg["cnt"] or 0

    can_review, already, form = False, False, None
    favorite_items = set()

    if request.user.is_authenticated:
        # Check if bought


        purchased = OrderItem.objects.filter(
            order__user=request.user,
            order__status__in=["delivered", "completed"],
            item=item,
        ).exists()

        already = Review.objects.filter(user=request.user, item=item).exists()
        can_review = purchased and not already

        if can_review:
            form = ReviewForm()

        # favorites list (template-এ: item.id in favorite_items)


        favorite_items = set(
            Favorite.objects.filter(user=request.user)
            .values_list("item_id", flat=True)
        )

    context = {
        "item": item,
        "reviews": reviews,
        "avg_rating": avg_rating,
        "total_reviews": total_reviews,
        "can_review": can_review,
        "already": already,
        "form": form,
        "favorite_items": favorite_items,
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
        # Here I am taking rating + comment directly from POST,
        # So that it works even if there is a form mismatch


        try:
            rating = int(request.POST.get("rating", 0))
        except ValueError:
            rating = 0

        comment = request.POST.get("comment", "").strip()

        if rating < 1 or rating > 5:
            messages.error(request, "Please select a rating between 1 and 5 stars.")
            return redirect("item_detail", item_id=item.id)

        Review.objects.create(
            user=request.user,
            item=item,
            rating=rating,
            comment=comment,
        )
        messages.success(request, "Thank you for your feedback!")

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

    return render(
        request, "my_canteen/review_edit.html", {"item": item, "form": form}
    )


@login_required
def delete_review(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, is_active=True)
    review = get_object_or_404(Review, item=item, user=request.user)

    if request.method == "POST":
        review.delete()
        messages.success(request, "Your review has been deleted.")
        return redirect("item_detail", item_id=item.id)

    return HttpResponseForbidden("Invalid request")


# ----------Cart ----------


@login_required
def add_to_cart(request, item_id):
    cart = request.session.get("cart", {})
    cart[str(item_id)] = cart.get(str(item_id), 0) + 1
    request.session["cart"] = cart
    messages.success(request, "Added to cart ✔")

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("menu")


@login_required
def add_to_cart_qty(request, item_id, qty):
    cart = request.session.get("cart", {})
    qty = int(qty)
    cart[str(item_id)] = cart.get(str(item_id), 0) + qty
    request.session["cart"] = cart
    messages.success(request, f"Added {qty} items ✔")

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
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
    item_ids = []

    for item_id, qty in cart.items():
        try:
            item = MenuItem.objects.get(id=item_id, is_active=True)
        except MenuItem.DoesNotExist:
            continue

        subtotal = float(item.price) * qty
        items.append({"item": item, "qty": qty, "subtotal": subtotal})
        total += subtotal
        item_ids.append(item.id)

    # smart suggestion


    suggested_items = []
    if items:
        cat_ids = {
            entry["item"].category_id
            for entry in items
            if entry["item"].category_id
        }

        qs = MenuItem.objects.filter(is_active=True)

        if cat_ids:
            qs = qs.filter(category_id__in=cat_ids)

        if item_ids:
            qs = qs.exclude(id__in=item_ids)

        suggested_items = list(
            qs.order_by("-is_popular", "name")[:4]
        )

    context = {
        "items": items,
        "total": total,
        "suggested_items": suggested_items,
    }
    return render(request, "my_canteen/cart.html", context)


# ----------Checkout + Payment ----------


@login_required
def checkout(request):
    cart = request.session.get("cart", {})
    if not cart:
        messages.error(request, "Your cart is empty!")
        return redirect("menu")

    cart_items = []
    total = 0
    for item_id, qty in cart.items():
        item = get_object_or_404(MenuItem, id=item_id, is_active=True)
        subtotal = float(item.price) * qty
        cart_items.append({"item": item, "qty": qty, "subtotal": subtotal})
        total += subtotal

    addresses = Address.objects.filter(user=request.user).order_by(
        "-is_default", "-id"
    )

    coupon_code = ""
    discount_amount = 0
    grand_total = total

    selected_address_id = None
    address_text = ""

    if request.method == "POST":
        form = CheckoutPaymentForm(request.POST)

        selected_address_id = request.POST.get("address_id") or None
        address_text = request.POST.get("address_text", "").strip()

        # Coupon


        coupon_code = request.POST.get("coupon_code", "").strip().upper()
        discount_percent = COUPON_CODES.get(coupon_code, 0)
        if discount_percent:
            discount_amount = total * discount_percent / 100
            grand_total = total - discount_amount
        else:
            grand_total = total

        # Just apply the coupon


        if "apply_coupon" in request.POST:
            if coupon_code and not discount_percent:
                messages.error(request, "Invalid or expired coupon code.")
            elif discount_percent:
                messages.success(
                    request,
                    f"Coupon {coupon_code} applied ({discount_percent}% off)."
                )
            return render(
                request,
                "my_canteen/checkout.html",
                {
                    "items": cart_items,
                    "total": total,
                    "form": form,
                    "coupon_code": coupon_code,
                    "discount_amount": discount_amount,
                    "grand_total": grand_total,
                    "addresses": addresses,
                    "selected_address_id": selected_address_id,
                    "address_text": address_text,
                },
            )

        # place order


        if form.is_valid():
            method = form.cleaned_data["payment_method"]

            address_str = "Default Address"

            # saved address


            if selected_address_id:
                try:
                    addr_obj = Address.objects.get(
                        id=selected_address_id, user=request.user
                    )
                    line2_part = f", {addr_obj.line2}" if addr_obj.line2 else ""
                    address_str = (
                        f"{addr_obj.label}: {addr_obj.line1}{line2_part}, "
                        f"{addr_obj.city}"
                    )
                except Address.DoesNotExist:
                    pass
            # one-time address


            elif address_text:
                address_str = address_text

            order = Order.objects.create(
                user=request.user,
                total_price=grand_total,
                address=address_str,
                status="pending",
                payment_status="unpaid",
                payment_method=method,
            )

            # order items + stock minus


            for item_id, qty in cart.items():
                item = get_object_or_404(MenuItem, id=item_id)
                item.stock -= qty
                item.save()
                OrderItem.objects.create(
                    order=order,
                    item=item,
                    quantity=qty,
                    unit_price=item.price,
                )

            # payment row


            payment = Payment.objects.create(
                order=order,
                method=method,
                amount=order.total_price,
                status="pending",
            )

            # demo methods


            if method in ["cash", "mock_card", "bkash", "nagad"]:
                payment.status = "paid"
                payment.paid_at = timezone.now()
                payment.transaction_id = (
                    f"{method.upper()}-{order.id}-{int(timezone.now().timestamp())}"
                )
                payment.save()

                order.payment_status = "paid"
                order.save()

                # cart clear


                request.session["cart"] = {}

                msg_map = {
                    "cash": "Cash payment order placed successfully!",
                    "mock_card": "Mock Card payment successful!",
                    "bkash": "bKash payment recorded (demo).",
                    "nagad": "Nagad payment recorded (demo).",
                }
                messages.success(
                    request,
                    msg_map.get(method, "Order placed successfully!")
                )
                return redirect("payment_success")

            messages.info(request, "Selected gateway is not ready yet.")
            return redirect("payment_failed")

    else:
        form = CheckoutPaymentForm()
        grand_total = total

    return render(
        request,
        "my_canteen/checkout.html",
        {
            "items": cart_items,
            "total": total,
            "form": form,
            "coupon_code": coupon_code,
            "discount_amount": discount_amount,
            "grand_total": grand_total,
            "addresses": addresses,
            "selected_address_id": selected_address_id,
            "address_text": address_text,
        },
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


# ----------Orders list page ----------


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

    cancelable_ids = {o.id for o in orders if can_user_cancel(o, request.user)}

    return render(
        request,
        "my_canteen/orders.html",
        {"orders": orders, "profile": profile, "cancelable_ids": cancelable_ids},
    )


# ----------Static pages ----------


def about_page(request):
    return render(request, "my_canteen/about.html")


def contact_page(request):
    return render(request, "my_canteen/contact.html")


def about_anchor(request):
    return HttpResponseRedirect(f"{reverse('home')}#about")


def contact_anchor(request):
    return HttpResponseRedirect(f"{reverse('home')}#contact")


# ----------Dashboard (role swap) ----------


@login_required
def dashboard(request):
    """
    Template & heading real_role দিয়ে, data/permission effective_role দিয়ে।
    """
    profile = UserProfile.objects.select_related("user").get(user=request.user)

    real_role = profile.role
    effective_role = get_effective_role(real_role)

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

    title_map = {
        "admin": "🛠 Admin Dashboard",
        "vendor": "🏪 Vendor Dashboard",
        "staff": "👨‍🍳 Staff Dashboard",
        "student": "🎓 Student Dashboard",
        "faculty": "🎓 Faculty Dashboard",
        "guest": "👋 Welcome",
    }
    dashboard_title = title_map.get(real_role, "Dashboard")

    template_name = f"my_canteen/dashboard/{real_role}.html"

    ctx = {
        "profile": profile,
        "orders": orders,
        "items": items,
        "real_role": real_role,
        "effective_role": effective_role,
        "dashboard_title": dashboard_title,
    }
    return render(request, template_name, ctx)


# (optional) old vendor dashboard


@login_required
def vendor_dashboard(request):
    if get_role(request.user) != "vendor":
        messages.error(request, "Only vendor can access this dashboard.")
        return redirect("home")
    return render(request, "my_canteen/dashboard/superadmin.html")


# ----------Profile /Settings ----------


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


# ----------Address Book ----------


@login_required
def address_book(request):
    """
    User নিজে address manage করবে।
    """
    addresses = Address.objects.filter(user=request.user).order_by(
        "-is_default", "-created_at"
    )

    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            addr = form.save(commit=False)
            addr.user = request.user
            addr.save()
            messages.success(request, "Address saved successfully.")
            return redirect("address_book")
    else:
        form = AddressForm()

    return render(
        request,
        "my_canteen/address_book.html",
        {"addresses": addresses, "form": form},
    )


@login_required
def address_delete(request, pk):
    addr = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        addr.delete()
        messages.info(request, "Address removed.")
        return redirect("address_book")
    return HttpResponseForbidden("Invalid request")


@login_required
def address_set_default(request, pk):
    addr = get_object_or_404(Address, pk=pk, user=request.user)
    Address.objects.filter(user=request.user).update(is_default=False)
    addr.is_default = True
    addr.save(update_fields=["is_default"])
    messages.success(request, "Default address updated.")
    return redirect("address_book")


# ----------Order lifecycle (vendor & admin) ----------


@login_required
def order_accept(request, order_id):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")

    order = get_object_or_404(Order, id=order_id)
    order.status = "accepted"
    order.save(update_fields=["status"])
    messages.success(request, f"Order #{order.id} accepted.")

    send_notification(
        user=order.user,
        title="Order accepted",
        message=f"Your order #{order.id} has been accepted and will be prepared soon.",
        category="order",
        link="/orders/",
        send_email=True,
    )
    return redirect("dashboard")


@login_required
def order_preparing(request, order_id):
    if not require_roles(request.user, ["vendor", "admin", "staff"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")

    order = get_object_or_404(Order, id=order_id)
    order.status = "preparing"
    order.save(update_fields=["status"])
    messages.success(request, f"Order #{order.id} set to Preparing.")

    send_notification(
        user=order.user,
        title="Order is being prepared",
        message=f"Your order #{order.id} is now being prepared.",
        category="order",
        link="/orders/",
        send_email=True,
    )
    return redirect("dashboard")


@login_required
def order_ready(request, order_id):
    if not require_roles(request.user, ["vendor", "admin", "staff"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")

    order = get_object_or_404(Order, id=order_id)
    order.status = "ready"
    order.save(update_fields=["status"])
    messages.success(request, f"Order #{order.id} marked Ready.")

    send_notification(
        user=order.user,
        title="Order ready for pick-up",
        message=f"Your order #{order.id} is ready. Please collect it from the counter.",
        category="order",
        link="/orders/",
        send_email=True,
    )
    return redirect("dashboard")


@login_required
def order_delivered(request, order_id):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")

    order = get_object_or_404(Order, id=order_id)
    order.status = "delivered"
    order.save(update_fields=["status"])
    messages.success(request, f"Order #{order.id} marked Delivered.")

    send_notification(
        user=order.user,
        title="Order delivered",
        message=f"Your order #{order.id} has been delivered.",
        category="order",
        link="/orders/",
        send_email=True,
    )
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
    order.save(update_fields=["status"])
    messages.success(request, f"Order #{order.id} Completed.")

    send_notification(
        user=order.user,
        title="Order completed",
        message=f"Thank you! Your order #{order.id} has been completed.",
        category="order",
        link="/orders/",
        send_email=True,
    )
    return redirect("dashboard")


@login_required
def order_cancel(request, order_id):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")

    order = get_object_or_404(Order, id=order_id)
    order.status = "cancelled"
    order.save(update_fields=["status"])
    messages.info(request, f"Order #{order.id} Cancelled.")

    send_notification(
        user=order.user,
        title="Order cancelled",
        message=f"Your order #{order.id} has been cancelled by canteen.",
        category="order",
        link="/orders/",
        send_email=True,
    )
    return redirect("dashboard")


@login_required
def order_mark_paid(request, order_id):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")

    order = get_object_or_404(Order, id=order_id)
    order.payment_status = "paid"
    order.save(update_fields=["payment_status"])
    messages.success(request, f"Order #{order.id} marked as PAID.")

    send_notification(
        user=order.user,
        title="Payment received",
        message=f"Payment for order #{order.id} has been recorded.",
        category="payment",
        link="/orders/",
        send_email=True,
    )
    return redirect("dashboard")


# ----------End-user Smart Cancel ----------


@login_required
def user_order_cancel(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if not can_user_cancel(order, request.user):
        messages.error(request, "You can no longer cancel this order.")
        return redirect("orders")

    for oi in OrderItem.objects.filter(order=order).select_related("item"):
        oi.item.stock += oi.quantity
        oi.item.save(update_fields=["stock"])

    order.status = "cancelled"
    order.save(update_fields=["status"])

    send_notification(
        user=request.user,
        title=f"Order #{order.id} cancelled",
        message="Your order has been cancelled successfully.",
        category="order",
        link="/orders/",
        send_email=True,
    )

    messages.success(request, f"Order #{order.id} cancelled successfully.")
    return redirect("orders")


# ----------Reorder Previous Order ----------


@login_required
def reorder_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if order.status not in ["delivered", "completed"]:
        messages.error(request, "You can reorder only delivered or completed orders.")
        return redirect("orders")

    cart = request.session.get("cart", {})
    added_any = False

    for oi in order.orderitem_set.select_related("item"):
        item = oi.item

        if not item.is_active or item.stock <= 0:
            continue

        qty = min(oi.quantity, item.stock)
        if qty <= 0:
            continue

        cart_key = str(item.id)
        cart[cart_key] = cart.get(cart_key, 0) + qty
        added_any = True

    request.session["cart"] = cart

    if added_any:
        messages.success(
            request,
            f"Items from order #{order.id} have been added to your cart.",
        )
        return redirect("cart")
    else:
        messages.warning(
            request,
            "No items from this order are available to reorder right now.",
        )
        return redirect("orders")


# ----------Vendor CRUD ----------


@login_required
def vendor_item_list(request):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "You are not authorized to view this page.")
        return redirect("home")

    q = request.GET.get("q", "").strip()

    qs = MenuItem.objects.all().order_by("-is_active", "name")

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

    items = Paginator(qs, 10).get_page(request.GET.get("page"))
    return render(
        request, "my_canteen/vendor/items_list.html", {"items": items, "q": q}
    )


@login_required
def vendor_item_create(request):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "You are not authorized to add items.")
        return redirect("home")

    if request.method == "POST":
        form = MenuItemForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ New menu item created successfully!")
            return redirect("vendor_item_list")
    else:
        form = MenuItemForm()
    return render(
        request,
        "my_canteen/vendor/item_form.html",
        {"form": form, "mode": "create"},
    )


@login_required
def vendor_item_edit(request, pk):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "You are not authorized to edit items.")
        return redirect("home")

    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == "POST":
        form = MenuItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"✅ '{item.name}' updated successfully!")
            return redirect("vendor_item_list")
    else:
        form = MenuItemForm(instance=item)
    return render(
        request,
        "my_canteen/vendor/item_form.html",
        {"form": form, "mode": "edit", "item": item},
    )


@login_required
def vendor_item_delete(request, pk):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "You are not authorized to delete items.")
        return redirect("home")

    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == "POST":
        item.delete()
        messages.info(request, f"🗑 '{item.name}' deleted successfully.")
        return redirect("vendor_item_list")
    return render(
        request, "my_canteen/vendor/item_confirm_delete.html", {"item": item}
    )


@login_required
def vendor_item_toggle_active(request, pk):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("home")

    item = get_object_or_404(MenuItem, pk=pk)
    item.is_active = not item.is_active
    item.save(update_fields=["is_active"])
    messages.success(
        request,
        f"'{item.name}' has been "
        f"{'activated ✅' if item.is_active else 'deactivated ❌'}.",
    )
    return redirect("vendor_item_list")


# ----------Favorites ----------


@login_required
def toggle_favorite(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)

    fav, created = Favorite.objects.get_or_create(user=request.user, item=item)

    if not created:
        fav.delete()
        messages.info(request, "Removed from favorites.")
    else:
        messages.success(request, "Added to favorites!")

    return redirect("item_detail", item_id=item.id)


@login_required
def favorites_page(request):
    fav_items = Favorite.objects.filter(user=request.user).select_related("item")
    return render(
        request, "my_canteen/favorites.html", {"fav_items": fav_items}
    )


# ----------PDF Invoice ----------


@login_required
def order_invoice_pdf(request, order_id):
    role = get_role(request.user)
    if role in ["vendor", "admin"]:
        qs = Order.objects.all()
    else:
        qs = Order.objects.filter(user=request.user)

    order = get_object_or_404(qs, id=order_id)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 20 * mm

    # Header


    header_h = 25 * mm
    c.setFillColor(colors.HexColor("#c62828"))
    c.rect(0, height - header_h, width, header_h, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin, height - header_h + 10 * mm, "UAP CanteenX")

    c.setFont("Helvetica", 11)
    c.drawString(margin, height - header_h + 4 * mm, "Order Invoice")

    # ORDER + CUSTOMER INFO


    c.setFillColor(colors.black)

    # Left: order info


    y_left = height - header_h - 15 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y_left, "Order Details")

    c.setFont("Helvetica", 11)
    y_left -= 16
    c.drawString(margin, y_left, f"Order ID: #{order.id}")
    y_left -= 14
    c.drawString(
        margin, y_left, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}"
    )

    # Right: customer info


    info_x = width / 2
    y_right = height - header_h - 15 * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(info_x, y_right, "Customer")

    c.setFont("Helvetica", 11)
    y_right -= 16
    c.drawString(info_x, y_right, f"Name: {order.user.username}")
    y_right -= 14
    c.drawString(info_x, y_right, f"Payment: {order.payment_status.title()}")
    y_right -= 14
    c.drawString(info_x, y_right, f"Status: {order.status.title()}")

    # Separator


    y = min(y_left, y_right) - 22
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.8)
    c.line(margin, y, width - margin, y)

    # ITEMS TABLE


    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.black)
    c.drawString(margin, y + 8, "Items")

    y -= 18
    row_h = 18
    col_name = margin
    col_qty = margin + 72 * mm
    col_price = margin + 97 * mm
    col_subtotal = margin + 127 * mm

    # header row


    c.setFillColor(colors.whitesmoke)
    c.rect(margin, y, width - 2 * margin, row_h, fill=1, stroke=0)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(col_name + 4, y + 4, "Item")
    c.drawString(col_qty + 4, y + 4, "Qty")
    c.drawString(col_price + 4, y + 4, "Price")
    c.drawString(col_subtotal + 4, y + 4, "Subtotal")

    y -= row_h
    c.setFont("Helvetica", 10)

    for oi in order.orderitem_set.all():
        # If you like new page


        if y < 40 * mm:
            c.showPage()
            width, height = A4
            margin = 20 * mm
            y = height - margin

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Items (contd.)")
            y -= 18

            c.setFillColor(colors.whitesmoke)
            c.rect(margin, y, width - 2 * margin, row_h, fill=1, stroke=0)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(col_name + 4, y + 4, "Item")
            c.drawString(col_qty + 4, y + 4, "Qty")
            c.drawString(col_price + 4, y + 4, "Price")
            c.drawString(col_subtotal + 4, y + 4, "Subtotal")
            y -= row_h
            c.setFont("Helvetica", 10)

        # data row


        c.setFillColor(colors.white)
        c.rect(margin, y, width - 2 * margin, row_h, fill=1, stroke=0)
        c.setFillColor(colors.black)

        c.drawString(col_name + 4, y + 4, oi.item.name[:35])
        c.drawString(col_qty + 4, y + 4, str(oi.quantity))
        c.drawRightString(col_price + 35, y + 4, f"{oi.item.price:.2f} Tk")

        subtotal = float(oi.item.price) * oi.quantity
        c.drawRightString(col_subtotal + 40, y + 4, f"{subtotal:.2f} Tk")

        y -= row_h

    # TOTAL BOX


    y -= 25
    c.setStrokeColor(colors.HexColor("#c62828"))
    c.setLineWidth(1.2)
    c.rect(
        col_price - 10,
        y - 6,
        (width - margin) - (col_price - 10),
        24,
        fill=0,
        stroke=1,
    )

    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.black)
    c.drawString(col_price, y + 2, "Total:")
    c.drawRightString(
        width - margin - 6, y + 2, f"{order.total_price:.2f} Tk"
    )

    # Footer


    footer_y = 25 * mm
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.6)
    c.line(margin, footer_y + 10, width - margin, footer_y + 10)

    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.grey)
    c.drawString(
        margin, footer_y, "Thank you for ordering from UAP CanteenX ❤"
    )
    c.drawRightString(
        width - margin,
        footer_y,
        "This is a system generated invoice.",
    )

    c.save()
    buffer.seek(0)

    filename = f"order_{order.id}_invoice.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename=\"{filename}\"'
    return response


# ----------Notifications ----------


@login_required
def notifications_page(request):
    notifs = Notification.objects.filter(user=request.user).order_by('-created_at')
    return render(request, "my_canteen/notifications.html", {"notifs": notifs})


@login_required
def notification_mark_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save(update_fields=["is_read"])

    if notif.link:
        return redirect(notif.link)

    return redirect("notifications")


# ----------Address list (checkout manage link) ----------


@login_required
def address_list(request):
    addresses = Address.objects.filter(user=request.user).order_by("-is_default", "-id")
    return render(request, "my_canteen/address_list.html", {"addresses": addresses})


# ----------Daily Sales Report ----------


@login_required
def daily_sales_report(request):
    # Only vendor /admin can see


    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Only vendor/admin can see sales report.")
        return redirect("dashboard")

    # What date report? From the GET parameter, default = today


    date_str = request.GET.get("date")
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            target_date = timezone.localdate()
    else:
        target_date = timezone.localdate()

    # Paid + delivered/completed orders of that day


    orders_qs = Order.objects.filter(
        created_at__date=target_date,
        status__in=["delivered", "completed"],
        payment_status="paid",
    ).order_by("-created_at")

    total_orders = orders_qs.count()
    total_amount = orders_qs.aggregate(total=Sum("total_price"))["total"] or 0

    # payment method-wise summary


    payment_summary = (
        orders_qs.values("payment_method")
        .annotate(
            count=Count("id"),
            amount=Sum("total_price"),
        )
        .order_by("payment_method")
    )

    # How many times an item was sold on that day + how much money was received


    items_qs = (
        OrderItem.objects.filter(order__in=orders_qs)
        .values("item__name")
        .annotate(
            qty=Sum("quantity"),
            revenue=Sum(F("quantity") * F("unit_price")),
        )
        .order_by("-qty")
    )

    context = {
        "target_date": target_date,
        "orders": orders_qs,
        "total_orders": total_orders,
        "total_amount": total_amount,
        "payment_summary": payment_summary,
        "items_summary": items_qs,
    }
    return render(request, "my_canteen/reports/daily_sales.html", context)


@login_required
def spending_summary(request):
    """
    Logged-in user er simple spending summary.
    - Shudhu paid, non-cancelled order dhora hobe.
    """
    qs = Order.objects.filter(
        user=request.user,
        payment_status="paid",
    ).exclude(status="cancelled")

    agg = qs.aggregate(
        total_spent=Sum("total_price"),
        order_count=Count("id"),
    )

    total_spent = agg["total_spent"] or 0
    order_count = agg["order_count"] or 0
    avg_per_order = total_spent / order_count if order_count else 0

    context = {
        "total_spent": total_spent,
        "order_count": order_count,
        "avg_per_order": avg_per_order,
    }
    return render(request, "my_canteen/spending_summary.html", context)
