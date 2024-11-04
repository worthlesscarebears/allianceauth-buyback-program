from datetime import timedelta
from random import choice, randint

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from allianceauth.eveonline.models import EveCorporationInfo

from buybackprogram.models import Contract, EveType, Program, Tracking, TrackingItem

User = get_user_model()


class Command(BaseCommand):
    help = "Generates dummy data for contracts, tracking objects, and tracking items. Only for development use"

    def add_arguments(self, parser):
        parser.add_argument(
            "-n",
            "--number",
            type=int,
            default=1000,
            help="Number of contracts and tracking objects to create",
        )

    def handle(self, *args, **options):
        # Prompt the user for confirmation
        self.stdout.write(
            self.style.WARNING(
                "This command will delete all existing contracts and tracking objects! This command is only for development use!"
            )
        )
        if input("Type 'yes' to continue, or 'no' to cancel: ").lower() != "yes":
            self.stdout.write(self.style.ERROR("Command aborted by user."))
            return

        # Delete all existing Contract and Tracking objects
        self.stdout.write(
            self.style.WARNING(
                "Deleting all existing contracts and tracking objects..."
            )
        )
        Contract.objects.all().delete()
        Tracking.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                "All existing contracts and tracking objects have been deleted."
            )
        )
        number = options["number"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting generation of {number} dummy contracts, tracking objects, and tracking items"
            )
        )

        for _ in range(number):
            user = User.objects.order_by("?").first()
            corporation = EveCorporationInfo.objects.order_by("?").first()
            program = Program.objects.order_by("?").first()

            days_ago = randint(0, 180)  # Random number of days up to 6 months
            date_issued = timezone.now() - timedelta(days=days_ago)
            date_expired = date_issued + timedelta(
                days=90
            )  # Contract expires 90 days after issue

            # Randomly selecting contract status
            status = choice(["outstanding", "finished", "in_progress"])
            date_completed = None

            # Set date_completed if the status is 'finished'
            if status == "finished":
                completion_days = randint(0, (date_expired - date_issued).days)
                date_completed = date_issued + timedelta(days=completion_days)

            contract = Contract.objects.create(
                assignee_id=randint(1000000, 9999999),
                availability="public",
                contract_id=randint(100000000, 999999999),
                date_issued=date_issued,
                date_expired=date_expired,
                date_completed=date_completed,
                for_corporation=choice([True, False]),
                issuer_corporation_id=corporation.corporation_id,
                issuer_id=1,
                start_location_id=randint(10000000, 99999999),
                price=randint(1000000, 100000000),
                status=status,
                volume=randint(100, 10000),
            )

            tracking = Tracking.objects.create(
                program=program,
                contract=contract,
                issuer_user=user,
                value=randint(500000, 50000000),
                taxes=randint(50000, 500000),
                hauling_cost=randint(10000, 200000),
                donation=randint(0, 10000),
                net_price=contract.price - randint(10000, 100000),
                tracking_number=f"TRACK-{randint(1000, 9999)}",
            )

            # Generate a few TrackingItem instances for each Tracking
            for _ in range(randint(1, 5)):  # Random number of items from 1 to 5
                eve_type = EveType.objects.order_by(
                    "?"
                ).first()  # Randomly select an item type
                if eve_type:
                    TrackingItem.objects.create(
                        tracking=tracking,
                        eve_type=eve_type,
                        quantity=randint(1, 100),
                        buy_value=randint(100, 10000),
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Generated contract {contract.contract_id}, tracking {tracking.id}, and tracking items"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished generating {number} dummy contracts, tracking objects, and tracking items"
            )
        )
