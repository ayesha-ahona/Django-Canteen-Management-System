# from django.contrib import admin
# from django.urls import path
# from my_canteen import views
# from django.contrib.auth import views as auth_views
# from django.conf import settings
# from django.conf.urls.static import static

# urlpatterns = [
#     path('admin/', admin.site.urls),
#     path('', views.home, name='home'),
#     path('menu/', views.menu_page, name='menu'),
#     path('orders/', views.orders_page, name='orders'),
#     path('about/', views.about_page, name='about'),
#     path('contact/', views.contact_page, name='contact'),

#     path('signup/', views.signup_page, name='signup'),
#     path('login/', auth_views.LoginView.as_view(template_name='my_canteen/login.html'), name='login'),
#     path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),

#     path('dashboard/', views.dashboard, name='dashboard'),
#     path('profile/', views.profile_page, name='profile'),
#     path('settings/', views.settings_page, name='settings'),
# ]

# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.contrib import admin
from django.urls import path
from my_canteen import views
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django Admin
    path('admin/', admin.site.urls),

    # Public Pages
    path('', views.home, name='home'),
    path('menu/', views.menu_page, name='menu'),
    path('orders/', views.orders_page, name='orders'),
    path('about/', views.about_page, name='about'),
    path('contact/', views.contact_page, name='contact'),

    # Place Order (IMPORTANT ✅)
    path('order/<int:item_id>/', views.place_order, name='place_order'),

    # Auth
    path('signup/', views.signup_page, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='my_canteen/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),

    # User Pages
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_page, name='profile'),
    path('settings/', views.settings_page, name='settings'),
]

# Serve Media Files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
