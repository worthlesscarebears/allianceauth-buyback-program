from django.core.management import call_command
from django.core.management.base import BaseCommand
from eveuniverse.models import EveType


class Command(BaseCommand):
    help = "Setup all needed data for buyback program to operate"

    def handle(self, *args, **options):
        call_command(
            "eveuniverse_load_data",
            "map",
            "types",
            "--types-enabled-sections",
            EveType.Section.DOGMAS,
            EveType.Section.TYPE_MATERIALS,
            EveType.Section.MARKET_GROUPS,
        )
