# my_project/urls.py

from django.contrib import admin
from django.urls import path
from my_canteen import views
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),

    # Core
    path('', views.home, name='home'),
    path('menu/', views.menu_page, name='menu'),

    # --- Item detail + feedback (ফিডব্যাক ও রেটিং সিস্টেম) ---
    # ✅ এই URL-টি একটি আইটেমের বিস্তারিত পাতা দেখায় (যেখানে রিভিউগুলো লিস্ট করা থাকে)
    path('item/<int:item_id>/', views.item_detail, name='item_detail'),
    
    # ✅ এই URL-টি একটি নতুন রিভিউ সাবমিট করার জন্য (POST রিকোয়েস্ট)
    path('item/<int:item_id>/review/', views.submit_review, name='submit_review'),
    
    # ✅ এই URL-টি একজন ইউজারের নিজের রিভিউ এডিট করার পাতা দেখায় (GET) এবং সাবমিট নেয় (POST)
    path('item/<int:item_id>/review/edit/', views.edit_review, name='edit_review'),
    
    # ✅ এই URL-টি একজন ইউজারের নিজের রিভিউ ডিলিট করার জন্য (POST রিকোয়েস্ট)
    path('item/<int:item_id>/review/delete/', views.delete_review, name='delete_review'),

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

    # ===== Payment flow =====
    path('payment/start/<int:order_id>/', views.payment_start, name='payment_start'),
    path('payment/success/', views.payment_success, name='payment_success'),
    path('payment/failed/', views.payment_failed, name='payment_failed'),

    # (optional) Gateways: webhook/IPN
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
    path('ipn/sslcommerz/', views.sslcommerz_ipn, name='sslcommerz_ipn'),

    # (optional) Real-time status polling
    path('orders/<int:order_id>/status/', views.order_status_api, name='order_status_api'),

    # About/Contact -> home anchors
    path('about/', views.about_anchor, name='about'),
    path('contact/', views.contact_anchor, name='contact'),

    # Auth
    path('signup/', views.signup_page, name='signup'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),

    # ✅ Email verification routes
    path('verify-email/<uidb64>/<token>/', views.verify_email, name='verify_email'),
    path('resend-verification/', views.resend_verification, name='resend_verification'),

    # Dashboard & profile
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_page, name='profile'),
    path('settings/', views.settings_page, name='settings'),

    # Vendor Dashboard (superadmin → vendor)
    path('dashboard/vendor/', views.vendor_dashboard, name='vendor_dashboard'),
    path('dashboard/superadmin/', lambda r: redirect('vendor_dashboard'), name='superadmin_legacy'),

    # User order cancel
    path('orders/<int:order_id>/user-cancel/', views.user_order_cancel, name='user_order_cancel'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)