from django.core.management import call_command
from django.core.management.base import BaseCommand

from games.retention import purger_parties


class Command(BaseCommand):
    help = "Efface les parties inactives (RETENTION_PARTIES_JOURS) et les sessions expirées."

    def handle(self, *args, **options):
        nombre = purger_parties()
        call_command("clearsessions")
        self.stdout.write(f"{nombre} partie(s) effacée(s).")
