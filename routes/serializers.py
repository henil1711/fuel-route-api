from rest_framework import serializers


class StrictLocationField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class RouteRequestSerializer(serializers.Serializer):
    start = StrictLocationField(max_length=200, min_length=2, trim_whitespace=True)
    finish = StrictLocationField(max_length=200, min_length=2, trim_whitespace=True)
