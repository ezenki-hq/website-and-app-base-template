import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

http_application = get_asgi_application()

from events.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": http_application,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
