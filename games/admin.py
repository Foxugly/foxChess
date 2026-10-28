from django.contrib import admin

from games.models import Partie


@admin.register(Partie)
class PartieAdmin(admin.ModelAdmin):
    list_display = ("id", "couleur", "niveau", "statut", "resultat", "fin", "modifiee_le")
    list_filter = ("statut", "couleur", "niveau", "fin")
    readonly_fields = ("id", "joueur", "creee_le", "modifiee_le")
