from django.urls import path

from events.consumers import EventsConsumer


websocket_urlpatterns = [
    path("ws/events/<str:token>", EventsConsumer.as_asgi()),
]
