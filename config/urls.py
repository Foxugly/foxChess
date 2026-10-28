from django.contrib import admin
from django.urls import include, path

from config.sante import sante

urlpatterns = [
    path("health/", sante, name="sante"),
    path("admin/", admin.site.urls),
    path("", include("games.urls")),
]
