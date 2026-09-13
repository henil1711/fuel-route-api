from django.db import models


class FuelStation(models.Model):
    opis_id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=250)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2, db_index=True)
    retail_price = models.DecimalField(max_digits=12, decimal_places=8)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    coordinate_source = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(retail_price__gt=0), name="positive_station_price"),
            models.CheckConstraint(
                condition=(
                    models.Q(latitude__isnull=True, longitude__isnull=True)
                    | models.Q(
                        latitude__isnull=False,
                        longitude__isnull=False,
                        latitude__range=(-90, 90),
                        longitude__range=(-180, 180),
                    )
                ),
                name="valid_coordinate_pair",
            ),
        ]


class FuelPrice(models.Model):
    """Distinct source observations, preserving duplicate multiplicity and original metadata."""

    station = models.ForeignKey(FuelStation, on_delete=models.CASCADE, related_name="prices")
    fingerprint = models.CharField(max_length=64, unique=True)
    rack_id = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=8)
    occurrences = models.PositiveIntegerField(default=1)
    source_row = models.JSONField()
