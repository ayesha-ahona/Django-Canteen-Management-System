# My canteen/utils.py


from django.core.mail import send_mail
from django.conf import settings
from .models import Notification


def send_notification(
    *,
    user,
    title,
    message,
    category="general",  # optional, future use only

    link=None,           # Optional

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

    # ----------In-app notification ----------

    data = {
        "user": user,
        "message": message,
    }

    # If the model has a title field, send that too

    if hasattr(Notification, "title"):
        data["title"] = title

    # Send only if there is category in model

    if hasattr(Notification, "category"):
        data["category"] = category

    # Send only if there is a link in the model

    if hasattr(Notification, "link"):
        data["link"] = link

    Notification.objects.create(**data)

    # ----------Email (optional) ----------

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
            # Even if the email fails, the server will not crash

            pass