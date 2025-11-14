from .models import Favorite, Notification

def favorites_processor(request):
    if request.user.is_authenticated:
        fav_ids = Favorite.objects.filter(user=request.user).values_list('item_id', flat=True)
        return {"favorite_items": set(fav_ids)}
    return {"favorite_items": set()}

def cart_count(request):
    cart = request.session.get("cart", {})
    return {"cart_count": sum(cart.values())}


def notifications_context(request):
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    else:
        unread_count = 0

    return {
        "unread_notifications": unread_count
    }