from django.urls import path
from routes.views import RouteView, map_view, health

urlpatterns = [path("api/v1/route/", RouteView.as_view()), path("route/", map_view), path("health/", health)]
