# my_canteen/utils.py

from django.core.mail import send_mail
from django.conf import settings
from .models import Notification


def send_notification(
    *,
    user,
    title,
    message,
    category="general",  # optional, শুধু future use
    link=None,           # optional
    send_email=True,
):
    """
    একসাথে in-app notification + (optional) email পাঠায়।

    ব্যবহার:
    send_notification(
        user=order.user,
        title="Order accepted",
        message="Your order #5 has been accepted.",
        category="order",
        link="/orders/",
    )
    """

    # ---------- In-app notification ----------
    data = {
        "user": user,
        "message": message,
    }

    # model-এ title ফিল্ড থাকলে সেটাও পাঠাই
    if hasattr(Notification, "title"):
        data["title"] = title

    # model-এ category থাকলে তবেই পাঠাই
    if hasattr(Notification, "category"):
        data["category"] = category

    # model-এ link থাকলে তবেই পাঠাই
    if hasattr(Notification, "link"):
        data["link"] = link

    Notification.objects.create(**data)

    # ---------- Email (optional) ----------
    if send_email and getattr(user, "email", None):
        subject = title
        body = message
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
        try:
            send_mail(
                subject,
                body,
                from_email,
                [user.email],
                fail_silently=True,
            )
        except Exception:
            # ইমেইল fail হলেও server crash করবে না
            pass