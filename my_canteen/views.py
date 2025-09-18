# from django.shortcuts import render, redirect
# from django.contrib.auth.decorators import login_required
# from django.contrib.auth.models import User
# from .models import MenuItem, UserProfile
# from .forms import CustomSignupForm   # ✅ custom signup form import

# # ===========================
# # Public Pages
# # ===========================

# def home(request):
#     items = MenuItem.objects.all()
#     return render(request, 'my_canteen/home.html', {"items": items})

# def menu_page(request):
#     return render(request, 'my_canteen/menu.html')

# def orders_page(request):
#     return render(request, 'my_canteen/orders.html')

# def about_page(request):
#     return render(request, 'my_canteen/about.html')

# def contact_page(request):
#     return render(request, 'my_canteen/contact.html')


# # ===========================
# # Signup Page
# # ===========================

# def signup_page(request):
#     if request.method == 'POST':
#         form = CustomSignupForm(request.POST)
#         if form.is_valid():
#             user = form.save(commit=False)
#             user.save()

#             # Get role & phone from form
#             role = form.cleaned_data['role']
#             phone = form.cleaned_data.get('phone')

#             # ✅ Auto SuperAdmin if first user
#             if User.objects.count() == 1:
#                 role = 'superadmin'

#             UserProfile.objects.create(user=user, role=role, phone=phone)
#             return redirect('login')
#     else:
#         form = CustomSignupForm()

#     return render(request, 'my_canteen/signup.html', {'form': form})


# # ===========================
# # Dashboard (Role-based)
# # ===========================

# @login_required
# def dashboard(request):
#     profile = UserProfile.objects.get(user=request.user)
#     role = profile.role
#     return render(request, f'my_canteen/dashboard/{role}.html')


from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import MenuItem, UserProfile
from .forms import CustomSignupForm   # ✅ import custom signup form

# Home (public)
def home(request):
    items = MenuItem.objects.all()
    return render(request, 'my_canteen/home.html', {"items": items})

def menu_page(request):
    return render(request, 'my_canteen/menu.html')

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

            # Get role & phone
            role = form.cleaned_data['role']
            phone = form.cleaned_data.get('phone')

            # First user will be superadmin automatically
            if User.objects.count() == 1:
                role = 'superadmin'

            UserProfile.objects.create(user=user, role=role, phone=phone)
            return redirect('login')
    else:
        form = CustomSignupForm()

    return render(request, 'my_canteen/signup.html', {'form': form})

# Dashboard (role based)
@login_required
def dashboard(request):
    profile = UserProfile.objects.get(user=request.user)
    role = profile.role
    return render(request, f'my_canteen/dashboard/{role}.html')
