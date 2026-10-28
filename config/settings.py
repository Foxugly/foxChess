"""Réglages de foxChess.

Repris de Chronos (site Django rendu côté serveur de la flotte) : configuration
lue dans l'environnement (SSM `/foxchess/prod` → `/run/foxchess/.env` en
production), sûre par défaut — sans `DJANGO_DEBUG=True`, pas de clé de
développement, pas de SQLite, pas d'`ALLOWED_HOSTS` vide.
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Sans valeur par défaut « True » : un déploiement qui oublie la variable
# obtient la configuration sûre, pas la page d'erreur bavarde.
DEBUG = os.environ.get("DJANGO_DEBUG") == "True"

# Clé de développement : utilisable uniquement en DEBUG. Hors DEBUG, l'absence
# de SECRET_KEY (SSM) arrête le démarrage plutôt que de signer les sessions
# avec une clé publiée dans le code.
DEVELOPMENT_SECRET_KEY = "dev-only-foxchess-0dq7v!k2m#x9r@p4w8z$c1n6b3j5h-not-for-production"

SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "SECRET_KEY doit être défini : la clé de développement est publiée "
            "dans le code et ne peut pas servir hors DEBUG."
        )
    SECRET_KEY = DEVELOPMENT_SECRET_KEY


def hotes_autorises(valeur):
    """`"a.com, b.com"` → `["a.com", "b.com"]` (espaces et entrées vides écartés)."""
    return [hote.strip() for hote in (valeur or "").split(",") if hote.strip()]


ALLOWED_HOSTS = hotes_autorises(
    os.environ.get("ALLOWED_HOSTS") or os.environ.get("DJANGO_ALLOWED_HOSTS")
)
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured("ALLOWED_HOSTS doit nommer les domaines servis (jamais « * ») hors DEBUG.")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "games",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "games.context_processors.application",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Modèle d'utilisateur de la flotte (OPERATIONS.md §3.16) : e-mail seul, pas de
# `username`, pas d'allauth. Fixé avant la première migration — en changer
# ensuite est une migration à la main.
AUTH_USER_MODEL = "accounts.User"


# Base de données — convention de la flotte (DB_ENGINE, DB_NAME, DB_HOST,
# DB_PORT, DB_USER, DB_PASSWORD) : PostgreSQL en production, SQLite en
# développement quand DB_ENGINE est absent. Une valeur inconnue arrête tout.
_DB_ENGINE = os.environ.get("DB_ENGINE", "").strip().lower()
if _DB_ENGINE in ("", "sqlite", "sqlite3", "django.db.backends.sqlite3"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
elif _DB_ENGINE in ("postgres", "postgresql", "django.db.backends.postgresql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "foxchess"),
            "USER": os.environ.get("DB_USER", "foxchess"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            # gunicorn (WSGI) : connexions persistantes permises (§3.22).
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    raise ImproperlyConfigured(f"DB_ENGINE inconnu : {_DB_ENGINE!r} (sqlite ou postgresql).")


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr"
TIME_ZONE = "Europe/Brussels"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Version affichée dans le footer et par /health/ (standard de la flotte).
VERSION = os.environ.get("FOXCHESS_VERSION", "").strip() or "0.1.0"

LOGIN_URL = "/admin/login/"


# --- Stockfish -------------------------------------------------------------
# Le binaire du moteur. En production, le paquet Ubuntu (`apt install
# stockfish`) l'installe en /usr/games/stockfish. En local, le chemin du .exe
# téléchargé (voir CLAUDE.md).
STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "/usr/games/stockfish")
# Bornes de la machine partagée : un fil, une petite table de hachage. Un coup
# du moteur ne dure jamais plus que la limite de temps de son niveau
# (games/moteur.py), et le processus s'arrête après chaque coup.
STOCKFISH_THREADS = int(os.environ.get("STOCKFISH_THREADS", "1"))
STOCKFISH_HASH_MB = int(os.environ.get("STOCKFISH_HASH_MB", "16"))

# Parties anonymes sans activité : effacées après ce délai (RGPD, OPERATIONS.md
# §3.25 ; `manage.py purger_parties`, foxchess-purge.timer).
RETENTION_PARTIES_JOURS = int(os.environ.get("RETENTION_PARTIES_JOURS", "30"))


# Tests : hachage de mot de passe rapide, limité à `manage.py test`.
if sys.argv[1:2] == ["test"]:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


# --- Production ------------------------------------------------------------
# Derrière nginx (TLS terminé par lui). Rien de ceci ne s'applique en DEBUG.
if not DEBUG:
    if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3" and sys.argv[1:2] != ["test"]:
        raise ImproperlyConfigured("DB_ENGINE=postgresql est requis hors DEBUG.")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True") == "True"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "63072000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

CSRF_TRUSTED_ORIGINS = hotes_autorises(os.environ.get("CSRF_TRUSTED_ORIGINS"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "WARNING")},
}

# Sentry (org foxugly-srl, projet foxchess-backend). Rien n'est envoyé sans DSN.
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    from config.sentry_filtres import reglages_sentry

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("SENTRY_RELEASE", "") or None,
        integrations=[DjangoIntegration()],
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        **reglages_sentry(),
    )


# Politique de sécurité du contenu (OPERATIONS.md §3.6 : nonce, sans
# `unsafe-inline` pour les scripts). jQuery, chessboard.js et Bootstrap sont
# copiés dans `static/vendor/` (empreinte SRI sur la balise) : aucun CDN de
# scripts. Les styles restent permis en ligne — chessboard.js dimensionne
# l'échiquier par des attributs `style` — et la feuille Bootstrap vient de
# jsdelivr, comme dans Chronos.
from django.utils.csp import CSP  # noqa: E402

_CDN = ["https://cdn.jsdelivr.net"]
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE, *_CDN],
    "font-src": [CSP.SELF, "data:", *_CDN],
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
}
