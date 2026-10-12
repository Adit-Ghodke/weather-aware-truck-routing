import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_check_endpoint():
    client = APIClient()
    url = reverse("safehaul:health")
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert "timestamp" in data
