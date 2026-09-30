from django.core.management.base import BaseCommand

from apps.core.models import ApiKey
from apps.services.api_keys import create_api_key


class Command(BaseCommand):
    help = "Create a hashed API key and print the plaintext value exactly once"

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Human-readable key name")
        parser.add_argument("--scope", required=True, choices=ApiKey.Scope.values)

    def handle(self, *args, **options):
        _, raw_key = create_api_key(name=options["name"], scope=options["scope"])
        self.stdout.write(raw_key)
