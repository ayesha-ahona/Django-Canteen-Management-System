from django.core.mail import send_mail
from django.conf import settings
from .models import Notification


def send_notification(user, message, email_subject=None, email_body=None):
    """
    One function → creates in-app notification + sends email.
    """

    # 1) In-app notification save
    Notification.objects.create(user=user, message=message)

    # 2) Email send (optional)
    if user.email and email_subject and email_body:
        try:
            send_mail(
                subject=email_subject,
                message=email_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            pass