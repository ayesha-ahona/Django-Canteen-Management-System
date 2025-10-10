from django.contrib import admin
from django.urls import path
from my_canteen import views
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Core
    path('', views.home, name='home'),
    path('menu/', views.menu_page, name='menu'),

    # Item detail + feedback
    path('item/<int:item_id>/', views.item_detail, name='item_detail'),
    path('item/<int:item_id>/review/', views.submit_review, name='submit_review'),

    # Cart + Checkout
    path('cart/', views.view_cart, name='cart'),
    path('cart/add/<int:item_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/add/<int:item_id>/<int:qty>/', views.add_to_cart_qty, name='add_to_cart_qty'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/inc/<int:item_id>/', views.increase_cart_qty, name='increase_cart_qty'),
    path('cart/dec/<int:item_id>/', views.decrease_cart_qty, name='decrease_cart_qty'),
    path('cart/update/<int:item_id>/', views.update_cart, name='update_cart'),
    path('checkout/', views.checkout, name='checkout'),

    # Orders
    path('orders/', views.orders_page, name='orders'),

    # Order lifecycle
    path('orders/<int:order_id>/accept/', views.order_accept, name='order_accept'),
    path('orders/<int:order_id>/preparing/', views.order_preparing, name='order_preparing'),
    path('orders/<int:order_id>/ready/', views.order_ready, name='order_ready'),
    path('orders/<int:order_id>/delivered/', views.order_delivered, name='order_delivered'),
    path('orders/<int:order_id>/completed/', views.order_completed, name='order_completed'),
    path('orders/<int:order_id>/cancel/', views.order_cancel, name='order_cancel'),
    path('orders/<int:order_id>/paid/', views.order_mark_paid, name='order_mark_paid'),

    # Static pages
    path('about/', views.about_page, name='about'),
    path('contact/', views.contact_page, name='contact'),

    # Auth
    path('signup/', views.signup_page, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='my_canteen/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),

    # Dashboard & profile
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_page, name='profile'),
    path('settings/', views.settings_page, name='settings'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)