from django.shortcuts import render, redirect
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
        items = items.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    if min_price:
        items = items.filter(price__gte=min_price)
    if max_price:
        items = items.filter(price__lte=max_price)

    return render(request, 'my_canteen/menu.html', {'items': items})


# ---------------- Orders ----------------
@login_required
def orders_page(request):
    profile = UserProfile.objects.get(user=request.user)
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return render(request, 'my_canteen/orders.html', {"orders": orders, "profile": profile})


# ---------------- Static Pages ----------------
def about_page(request):
    return render(request, 'my_canteen/about.html')

def contact_page(request):
    return render(request, 'my_canteen/contact.html')


# ---------------- Signup ----------------
def signup_page(request):
    if request.method == 'POST':
        form = CustomSignupForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data['role']

            # ❌ Restrict new SuperAdmin or Admin signup
            if role in ['superadmin', 'admin']:
                messages.error(request, "SuperAdmin and Admin roles are reserved. Please select another role.")
                return redirect('signup')

            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.save()

            phone = form.cleaned_data.get('phone')

            profile = user.userprofile
            profile.role = role   # allowed roles only
            profile.phone = phone
            profile.save()

            messages.success(request, f"Account created successfully as {role.capitalize()}! Please login.")
            return redirect('login')
    else:
        form = CustomSignupForm()
    return render(request, 'my_canteen/signup.html', {'form': form})


# ---------------- Dashboard ----------------
@login_required
def dashboard(request):
    profile = UserProfile.objects.get(user=request.user)
    role = profile.role

    # Orders by role
    if role in ["superadmin", "admin"]:
        orders = Order.objects.all().order_by('-created_at')
    elif role == "staff":
        orders = Order.objects.filter(status="processing").order_by('-created_at')
    elif role == "vendor":
        orders = []  # vendor future এ নিজের products দেখতে পারবে
    else:  # student, faculty, guest
        orders = Order.objects.filter(user=request.user).order_by('-created_at')

    # Auto template choose
    template_name = f"my_canteen/dashboard/{role}.html"
    return render(request, template_name, {"profile": profile, "orders": orders})


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

        # update email
        request.user.email = email
        request.user.save()

        # update phone
        profile.phone = phone
        profile.save()

        messages.success(request, "Profile updated successfully!")
        return redirect("settings")

    return render(request, 'my_canteen/settings.html', {"profile": profile})
