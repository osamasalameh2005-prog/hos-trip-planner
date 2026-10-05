from django.db import models


class Trip(models.Model):
    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)

    current_cycle_used = models.FloatField()

    total_distance_miles = models.FloatField(default=0)
    total_driving_hours = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.current_location} → {self.dropoff_location}"