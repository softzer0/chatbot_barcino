"""
ASGI config for chatbot project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.sessions import SessionMiddlewareStack
from django.core.asgi import get_asgi_application
import main.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chatbot.settings')

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(SessionMiddlewareStack(
        URLRouter(
            main.routing.websocket_urlpatterns
        )
    )),
})
