from django.urls import path

from nats_auth import views


urlpatterns = [
    path("token/", views.token, name="nats-token"),
    path("authorize/", views.authorize, name="nats-authorize"),
]
