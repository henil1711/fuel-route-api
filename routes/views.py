from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import RouteRequestSerializer
from .services.planner import plan_route


class RouteView(APIView):
    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(plan_route(serializer.validated_data["start"], serializer.validated_data["finish"]))


@require_GET
def map_view(request):
    return render(request, "route.html", {"tile_url": settings.TILE_URL})


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})
