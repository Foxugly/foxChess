from django.urls import path

from games import views

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("parties/nouvelle/", views.nouvelle_partie, name="nouvelle_partie"),
    path("parties/<uuid:pk>/", views.partie, name="partie"),
    path("parties/<uuid:pk>/jouer/", views.jouer, name="jouer"),
    path("parties/<uuid:pk>/moteur/", views.relancer_moteur, name="relancer_moteur"),
    path("parties/<uuid:pk>/abandonner/", views.abandonner, name="abandonner"),
]
