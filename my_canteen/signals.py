# my_canteen/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.utils import timezone
from .models import Payment, Order

@receiver(post_save, sender=Payment)
def on_payment_change(sender, instance: Payment, created, **kwargs):
    # paid হলে paid_at সেট + Order.payment_status সিঙ্ক
    if instance.status == 'paid':
        if instance.paid_at is None:
            instance.paid_at = timezone.now()
            instance.save(update_fields=['paid_at'])

        ord: Order = instance.order
        if hasattr(ord, 'payment_status') and ord.payment_status != 'paid':
            ord.payment_status = 'paid'
            ord.save(update_fields=['payment_status'])

        # কনফার্মেশন ইমেইল (dev-এ কনসোলে প্রিন্ট হবে)
        try:
            send_mail(
                subject=f"Payment Confirmed for Order #{ord.id}",
                message=f"Amount {instance.amount} via {instance.method}. Txn: {instance.transaction_id}",
                from_email=None,
                recipient_list=[ord.user.email],
                fail_silently=True
            )
        except Exception:
            pass
