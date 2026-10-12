import uuid

from django.db import models


class TripAnalysis(models.Model):
    """
    Persisted snapshot of a completed trip analysis.
    Stores user inputs and full output payload in result_json.
    Persistence failure must never crash the analysis request.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    origin_lat = models.FloatField()
    origin_lng = models.FloatField()
    origin_label = models.CharField(max_length=500)
    destination_lat = models.FloatField()
    destination_lng = models.FloatField()
    destination_label = models.CharField(max_length=500)
    departure_datetime_utc = models.DateTimeField()
    load_weight_lb = models.IntegerField()
    sample_interval_miles = models.IntegerField(default=25)
    result_json = models.JSONField(help_text="Serialized analysis result containing routes, checkpoints, and recommendation")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"TripAnalysis {self.id} ({self.origin_label} -> {self.destination_label})"
