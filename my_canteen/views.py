from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseForbidden
from django.db.models import Q, Avg, Count
from django.contrib import messages
from django.http import (
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
    HttpResponse,
)
import io
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

# PDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors

# Notifications helper
from .utils import send_notification

# ✅ Email verification imports
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.core.paginator import Paginator
from django.db.models import Count as CountAgg  
from django.db.models import Count   

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
    Address
)
from .forms import CustomSignupForm, ReviewForm, CheckoutPaymentForm, MenuItemForm, AddressForm

# ---------- COUPON / PROMO CODES (simple fixed list) ----------
COUPON_CODES = {
    "FOOD10": 10,      # 10% off
    "WELCOME20": 20,   # 20% off
    "STUDENT5": 5,     # 5% off
    "FESTIVE15": 15,   # 15% off
    "VIP25": 25,       # 25% off
    "HAPPY30": 30,     # 30% off
    "SAVE30": 30,      # 30% off
    "MEAL40": 40,      # 40% off
    "BUDGET35": 35,    # 35% off
    "SNACK15": 15,     # 15% off
    "LUNCH20": 20,     # 20% off
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

        
            if User.objects.count() == 1:
                role = "admin"

            profile = user.userprofile
            valid_roles = ["admin", "student", "faculty", "staff", "vendor", "guest"]
            profile.role = role if role in valid_roles else "guest"
            profile.phone = phone
            profile.email_verified = False
            profile.save()

            # ✅ Send verification email
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


# ---------- Helpers ----------
def get_role(user):
    """If UserProfile does not exist, it will return 'guest'."""
    try:
        return user.userprofile.role
    except UserProfile.DoesNotExist:
        return "guest"


def get_effective_role(real_role: str) -> str:
    """
    In the UI/heading, we will show the real_role, but for permissions/data, we use effective_role.
    - admin -> vendor permissions
    - vendor -> admin permissions
    - others (student/faculty/staff/guest) -> as before
    """
    if real_role == "admin":
        return "vendor"
    if real_role == "vendor":
        return "admin"
    return real_role


def require_roles(user, allowed):
    """easy permission check"""
    return get_role(user) in allowed


def can_user_cancel(order, user) -> bool:
    "End-user smart cancel: Students, faculty, and guests can cancel their orders until preparation begins."

    role = get_role(user)
    if role not in {"student", "faculty", "guest"}:
        return False
    if order.user_id != user.id:
        return False
    return order.status in {"pending", "accepted"}


# ========= AI Recommendation Helpers =========

def get_user_top_categories(user, limit=3):
    """
    ইউজার কোন কোন category থেকে বেশি খাবার খেয়েছে
    (delivered/completed অর্ডার থেকে হিসাব করব)
    """
    if not user.is_authenticated:
        return Category.objects.none()

    qs = (
        OrderItem.objects
        .filter(
            order__user=user,
            order_status_in=["delivered", "completed"],
        )
        # category না থাকলে বাদ দেই
        .exclude(item_category_isnull=True)
        .values("item__category")          # শুধু category id নিলাম
        .annotate(cnt=Count("id"))
        .order_by("-cnt")
    )

    cat_ids = [row["item__category"] for row in qs[:limit]]
    return Category.objects.filter(id__in=cat_ids)



def get_recommended_items(user, base_item=None, limit=6):
    """
    - base_item থাকলে → similar category + popular
    - না থাকলে → ইউজারের top categories
    - new user হলে → popular items
    """
    qs = MenuItem.objects.filter(is_active=True)

    # 1) base_item থাকলে similar category
    if base_item and base_item.category:
        qs = qs.filter(category=base_item.category).exclude(id=base_item.id)

    # 2) logged-in user → top categories
    elif user.is_authenticated:
        top_cats = get_user_top_categories(user)
        if top_cats:
            qs = qs.filter(category__in=top_cats)

    # 3) fallback: সব active items
    qs = qs.order_by("-is_popular", "name")

    return qs[:limit]


# ---------- Home ----------
def home(request):
    popular_items = MenuItem.objects.filter(is_popular=True, is_active=True)[:6]
    return render(request, "my_canteen/home.html", {"popular_items": popular_items})


# ---------- Menu ----------
def menu_page(request):
    # query params
    q = request.GET.get("q", "").strip()
    min_price = request.GET.get("min_price") or ""
    max_price = request.GET.get("max_price") or ""
    sort = request.GET.get("sort") or ""
    active_cat = request.GET.get("cat") or ""  # keep as string for template

    # base queryset
    items = MenuItem.objects.filter(is_active=True)

    # category filter
    if active_cat:
        try:
            items = items.filter(category_id=int(active_cat))
        except ValueError:
            active_cat = ""  # invalid cat id -> treat as "All"

    # search filter  ✅ এখানে দুইটা টাইপো ছিল
    if q:
        items = items.filter(
            Q(name_icontains=q) | Q(description_icontains=q)
        )

    # price range
    if min_price:
        items = items.filter(price__gte=min_price)
    if max_price:
        items = items.filter(price__lte=max_price)

    # sorting
    if sort == "price_asc":
        items = items.order_by("price")
    elif sort == "price_desc":
        items = items.order_by("-price")
    else:
        items = items.order_by("-is_popular", "name")

    # all categories for chips
    categories = Category.objects.all().order_by("name")

    # ✅ Simple recommendation: শুধু popular items
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

# ---------- Item Detail + Reviews ----------
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

    if request.user.is_authenticated:
        purchased = OrderItem.objects.filter(
            order__user=request.user,
            order_status_in=["delivered", "completed"],
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

    # ✅ আবার সিকিউরিটি চেক
    purchased = OrderItem.objects.filter(
        order__user=request.user,
        order_status_in=["delivered", "completed"],
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
    items = []
    total = 0
    item_ids = []

    # মূল cart items + total হিসাব
    for item_id, qty in cart.items():
        try:
            item = MenuItem.objects.get(id=item_id, is_active=True)
        except MenuItem.DoesNotExist:
            continue

        subtotal = float(item.price) * qty
        items.append({"item": item, "qty": qty, "subtotal": subtotal})
        total += subtotal
        item_ids.append(item.id)

    # ---------- SMART EXTRA ITEMS ----------
    suggested_items = []
    if items:  # cart এ কিছু থাকলেই extra suggest করব
        # cart এ থাকা item গুলোর category গুলো বের করি
        cat_ids = {
            entry["item"].category_id
            for entry in items
            if entry["item"].category_id
        }

        qs = MenuItem.objects.filter(is_active=True)

        # সেই category গুলো থেকে popular items
        if cat_ids:
            qs = qs.filter(category_id__in=cat_ids)

        # ইতিমধ্যে cart এ আছে এমন গুলো বাদ
        if item_ids:
            qs = qs.exclude(id__in=item_ids)

        suggested_items = list(
            qs.order_by("-is_popular", "name")[:4]  # সর্বোচ্চ ৪টা extra
        )

    context = {
        "items": items,
        "total": total,
        "suggested_items": suggested_items,
    }
    return render(request, "my_canteen/cart.html", context)


# ---------- Checkout + Payment ----------
@login_required
def checkout(request):
    cart = request.session.get("cart", {})
    if not cart:
        messages.error(request, "Your cart is empty!")
        return redirect("menu")

    # --- Build cart items list + subtotal ---
    cart_items = []
    total = 0
    for item_id, qty in cart.items():
        item = get_object_or_404(MenuItem, id=item_id, is_active=True)
        subtotal = float(item.price) * qty
        cart_items.append({"item": item, "qty": qty, "subtotal": subtotal})
        total += subtotal

    # ✅ Address book: current user-er saved addresses
    addresses = Address.objects.filter(user=request.user).order_by("-is_default", "-id")

    # default values
    coupon_code = ""
    discount_amount = 0
    grand_total = total

    # form er jonno extra helper variable
    selected_address_id = None
    address_text = ""

    if request.method == "POST":
        form = CheckoutPaymentForm(request.POST)

        # ----- address form data niye nei -----
        selected_address_id = request.POST.get("address_id") or None
        address_text = request.POST.get("address_text", "").strip()

        # ---------- COUPON ----------
        coupon_code = request.POST.get("coupon_code", "").strip().upper()
        discount_percent = COUPON_CODES.get(coupon_code, 0)
        if discount_percent:
            discount_amount = total * discount_percent / 100
            grand_total = total - discount_amount
        else:
            grand_total = total

        # শুধু coupon apply করা হচ্ছে? (Apply button e name="apply_coupon")
        if "apply_coupon" in request.POST:
            if coupon_code and not discount_percent:
                messages.error(request, "Invalid or expired coupon code.")
            elif discount_percent:
                messages.success(
                    request,
                    f"Coupon {coupon_code} applied ({discount_percent}% off)."
                )
            # order create না করে শুধু page re-render
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

        # ---------- PLACE ORDER & PAY ----------
        if form.is_valid():
            method = form.cleaned_data["payment_method"]

            # 🔹 কোন address string use korbo?
            address_str = "Default Address"

            # 1) jodi saved address select kore
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

            # 2) jodi nijer likha one-time address thake
            elif address_text:
                address_str = address_text

            # Order create
            order = Order.objects.create(
                user=request.user,
                total_price=grand_total,
                address=address_str,
                status="pending",
                payment_status="unpaid",
                payment_method=method,
            )

            # Order items + stock কমানো
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

            # Payment row
            payment = Payment.objects.create(
                order=order,
                method=method,
                amount=order.total_price,
                status="pending",
            )

            # সবগুলোই demo: cash, mock_card, bkash, nagad
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

                # আলাদা আলাদা message
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

            # future: stripe / sslcommerz থাকলে এখানে handle করো
            messages.info(request, "Selected gateway is not ready yet.")
            return redirect("payment_failed")

    else:
        # GET request
        form = CheckoutPaymentForm()
        grand_total = total  # no coupon yet

        # default address select korte chaile ekhane logic dite paro

    # --- Render page (default / GET / invalid form) ---
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

    # ডেটা লোডিং effective_role দিয়ে
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

    # হেডিং real_role দিয়ে (UI)
    title_map = {
        "admin": "🛠 Admin Dashboard",
        "vendor": "🏪 Vendor Dashboard",
        "staff": "👨‍🍳 Staff Dashboard",
        "student": "🎓 Student Dashboard",
        "faculty": "🎓 Faculty Dashboard",
        "guest": "👋 Welcome",
    }
    dashboard_title = title_map.get(real_role, "Dashboard")

    # কনটেন্ট টেমপ্লেট effective_role দিয়ে নির্বাচন (swap)
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

# ---------- Address Book ----------
@login_required
def address_book(request):
    """
    User নিজে তাঁর address গুলো manage করবে (list + add new).
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

# ---------- Order lifecycle (vendor & admin) ----------
@login_required
def order_accept(request, order_id):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")
    order = get_object_or_404(Order, id=order_id)
    order.status = "accepted"
    order.save()

    # Notification
    send_notification(
        order.user,
        title=f"Order #{order.id} Accepted",
        message="Vendor accepted your order. Preparing will start soon.",
        link="/orders/",
        email=True,
    )

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

    send_notification(
        order.user,
        title=f"Order #{order.id} is being prepared",
        message="Your food is now being prepared.",
        link="/orders/",
        email=True,
    )

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

    send_notification(
        order.user,
        title=f"Order #{order.id} Ready",
        message="Your order is ready for pickup!",
        link="/orders/",
        email=True,
    )

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

    send_notification(
        order.user,
        title=f"Order #{order.id} Delivered",
        message="Your order has been delivered. Enjoy your meal!",
        link="/orders/",
        email=True,
    )

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

    send_notification(
        order.user,
        title=f"Order #{order.id} Completed",
        message="Your order is now marked as completed.",
        link="/orders/",
        email=True,
    )

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

    send_notification(
        order.user,
        title=f"Order #{order.id} Cancelled by vendor",
        message="Your order has been cancelled by canteen staff.",
        link="/orders/",
        email=True,
    )

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

    send_notification(
        order.user,
        title=f"Payment received for Order #{order.id}",
        message="Your payment has been marked as paid.",
        link="/orders/",
        email=True,
    )

    messages.success(request, f"Order #{order.id} marked as PAID.")
    return redirect("dashboard")


# ---------- End-user Smart Cancel ----------
@login_required
def user_order_cancel(request, order_id):
    """
    Student / Faculty / Guest নিজের অর্ডার preparing-এর আগে পর্যন্ত ক্যানসেল করতে পারবে।
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # চেক করো ক্যানসেল করা যাবে কিনা
    if not can_user_cancel(order, request.user):
        messages.error(request, "You can no longer cancel this order.")
        return redirect("orders")

    # স্টক ফেরত দাও
    for oi in OrderItem.objects.filter(order=order).select_related("item"):
        oi.item.stock += oi.quantity
        oi.item.save(update_fields=["stock"])

    # অর্ডারের স্ট্যাটাস আপডেট
    order.status = "cancelled"
    order.save(update_fields=["status"])

    send_notification(
        request.user,
        title=f"Order #{order.id} Cancelled",
        message="Your order has been cancelled successfully.",
        link="/orders/",
        email=True,
    )

    messages.success(request, f"Order #{order.id} cancelled successfully.")
    return redirect("orders")


# ---------- Reorder Previous Order ----------
@login_required
def reorder_order(request, order_id):
    """
    Previous order থেকে সব available item আবার cart এ add করে।
    শুধু নিজে যে order করেছিল সেটা এবং delivered/completed order এর জন্য।
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # শুধুমাত্র delivered / completed order থেকে reorder allow করব
    if order.status not in ["delivered", "completed"]:
        messages.error(request, "You can reorder only delivered or completed orders.")
        return redirect("orders")

    # current cart
    cart = request.session.get("cart", {})
    added_any = False

    # অর্ডারের সব item ঘুরে দেখা
    for oi in order.orderitem_set.select_related("item"):
        item = oi.item

        # item ইনঅ্যাকটিভ বা stock নেই → skip
        if not item.is_active or item.stock <= 0:
            continue

        # আগের order এ যত ছিল, stock এর মধ্যে থাকলে ততটাই add করবে
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


# ---------- Vendor CRUD for Menu Items ----------
@login_required
def vendor_item_list(request):
    if not require_roles(request.user, ["vendor", "admin"]):
        messages.error(request, "You are not authorized to view this page.")
        return redirect("home")

    q = request.GET.get("q", "").strip()

    qs = MenuItem.objects.all().order_by("-is_active", "name")

    if q:
        qs = qs.filter(Q(name_icontains=q) | Q(description_icontains=q))

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


# ---------- Favorites ----------
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


# ---------- PDF Invoice Generation ----------
@login_required
def order_invoice_pdf(request, order_id):
    # নিজের order ছাড়া আর কেউ download করতে পারবে না
    order = get_object_or_404(Order, id=order_id, user=request.user)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 20 * mm

    # ========== HEADER BAND ==========
    header_h = 25 * mm
    c.setFillColor(colors.HexColor("#c62828"))
    c.rect(0, height - header_h, width, header_h, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin, height - header_h + 10 * mm, "UAP CanteenX")

    c.setFont("Helvetica", 11)
    c.drawString(margin, height - header_h + 4 * mm, "Order Invoice")

    # ========== ORDER + CUSTOMER INFO ==========
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

    # Separator line
    y = min(y_left, y_right) - 22
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.8)
    c.line(margin, y, width - margin, y)

    # ========== ITEMS TABLE ==========
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

    # table header background
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
        # নতুন পেজ দরকার হলে
        if y < 40 * mm:
            c.showPage()
            width, height = A4
            margin = 20 * mm
            y = height - margin

            # নতুন পেজে ছোট শিরোনাম
            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Items (contd.)")
            y -= 18

            # আবার header row আঁকি
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

    # ========== TOTAL BOX ==========
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

    # ========== FOOTER ==========
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
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

# ---------- Notifications (In-App) ----------
@login_required
def notifications_page(request):
    """
    নিজের সব notification list আকারে দেখাবে (নতুনটাই উপরে)
    """
    notifs = Notification.objects.filter(user=request.user).order_by('-created_at')
    return render(request, "my_canteen/notifications.html", {"notifs": notifs})


@login_required
def notification_mark_read(request, pk):
    """
    একটা notification read করে, চাইলে link থাকলে সেদিকে redirect করবে
    """
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save(update_fields=["is_read"])

    # যদি notification এ link থাকে → ওদিকে পাঠাই
    if notif.link:
        return redirect(notif.link)

    return redirect("notifications")