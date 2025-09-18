from django.contrib import admin
from django.urls import path
from my_canteen import views
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('menu/', views.menu_page, name='menu'),
    path('orders/', views.orders_page, name='orders'),
    path('about/', views.about_page, name='about'),
    path('contact/', views.contact_page, name='contact'),

    # Authentication
    path('signup/', views.signup_page, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='my_canteen/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
