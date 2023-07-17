from channels.layers import get_channel_layer
from django.dispatch import receiver
from django.db.models.signals import post_save
from asgiref.sync import async_to_sync
from .models import ChatMessage, ChatSession

@receiver(post_save, sender=ChatMessage)
def new_message(sender, instance, created, **kwargs):
    if created and instance.message:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'panel',
            {
                'type': 'chat_message',
                'command': 'new_message',
                'message': {
                    'id': instance.id,
                    'message': instance.message,
                    'response': instance.response,
                    'session_id': instance.session_id,
                    'session_name': instance.session.name
                },
            }
        )

@receiver(post_save, sender=ChatSession)
def new_session(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'panel',
            {
                'type': 'chat_session',
                'command': 'new_session',
                'session': instance.to_dict(),
            }
        )
