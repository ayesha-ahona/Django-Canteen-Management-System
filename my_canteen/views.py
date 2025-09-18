from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from .models import MenuItem

# Home (login required)
@login_required
def home(request):
    items = MenuItem.objects.all()
    return render(request, 'my_canteen/home.html', {"items": items})

@login_required
def menu_page(request):
    return render(request, 'my_canteen/menu.html')

@login_required
def orders_page(request):
    return render(request, 'my_canteen/orders.html')

@login_required
def about_page(request):
    return render(request, 'my_canteen/about.html')

@login_required
def contact_page(request):
    return render(request, 'my_canteen/contact.html')

# Signup page (public)
def signup_page(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')  # after signup, go to login
    else:
        form = UserCreationForm()
    return render(request, 'my_canteen/signup.html', {'form': form})
