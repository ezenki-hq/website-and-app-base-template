from django.urls import path, re_path

from events.consumers import EventsConsumer


websocket_urlpatterns = [
    path("ws/events/<str:token>", EventsConsumer.as_asgi()),
    re_path(r"^ws/events/.*$", EventsConsumer.as_asgi()),
]
