from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_handler


class PlanningError(APIException):
    status_code = 422
    default_code = "infeasible_route"
    default_detail = "No feasible fuel plan exists within the located station network."


class LocationError(APIException):
    status_code = 400
    default_code = "invalid_location"


class ProviderError(APIException):
    status_code = 503
    default_code = "provider_unavailable"
    default_detail = "The mapping provider is temporarily unavailable. Please try again later."


def exception_handler(exc, context):
    response = drf_handler(exc, context)
    if response is not None:
        response.data = {
            "error": {"code": getattr(exc, "default_code", "request_error"), "details": response.data}
        }
    return response
