from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.utils import timezone
from eveuniverse.models import EveMarketPrice, EveType

from allianceauth.services.hooks import get_extension_logger

from buybackprogram.app_settings import (
    BUYBACKPROGRAM_PRICE_INSTANT_PRICES,
    BUYBACKPROGRAM_PRICE_METHOD,
    BUYBACKPROGRAM_PRICE_SOURCE_ID,
    BUYBACKPROGRAM_PRICE_SOURCE_NAME,
)
from buybackprogram.models import ItemPrices
from buybackprogram.tasks import get_bulk_prices, valid_janice_api_key

logger = get_extension_logger(__name__)


class Command(BaseCommand):
    help = (
        "Preloads price data required for the buyback program from Fuzzwork market API"
    )

    def handle(self, *args, **options):
        item_count = 0
        type_ids = []
        market_data = {}
        api_up = True

        # Get all type ids
        typeids = EveType.objects.values_list("id", flat=True).filter(published=True)

        if BUYBACKPROGRAM_PRICE_METHOD == "Fuzzwork":
            print(
                "Price setup starting for %s items from Fuzzworks API from station id %s (%s). Use instant prices instead of average is set to %s, this may take up to 30 seconds..."
                % (
                    len(typeids),
                    BUYBACKPROGRAM_PRICE_SOURCE_ID,
                    BUYBACKPROGRAM_PRICE_SOURCE_NAME,
                    BUYBACKPROGRAM_PRICE_INSTANT_PRICES,
                )
            )
        elif BUYBACKPROGRAM_PRICE_METHOD == "Janice":
            if valid_janice_api_key():
                print(
                    "Price setup starting for %s items from Janice API from station id %s (%s). Use instant prices instead of average is set to %s, this may take up to 30 seconds..."
                    % (
                        len(typeids),
                        BUYBACKPROGRAM_PRICE_SOURCE_ID,
                        BUYBACKPROGRAM_PRICE_SOURCE_NAME,
                        BUYBACKPROGRAM_PRICE_INSTANT_PRICES,
                    )
                )
            else:
                print(
                    "\033[91mPrice setup failed for Janice, invalid API key! Provide a working key or change price source to Fuzzwork\033[91m\033[0m"
                )

                api_up = False

        else:
            return (
                "Unknown pricing method: '%s', skipping" % BUYBACKPROGRAM_PRICE_METHOD
            )

        if api_up:
            # Build suitable bulks to fetch prices from API
            for item in typeids:
                type_ids.append(item)

                if len(type_ids) == 1000:
                    market_data.update(get_bulk_prices(type_ids))
                    type_ids.clear()

            # Get leftover data from the bulk
            market_data.update(get_bulk_prices(type_ids))

            objs = []

            for key, value in market_data.items():
                item_count += 1

                if not BUYBACKPROGRAM_PRICE_INSTANT_PRICES:
                    item = ItemPrices(
                        eve_type_id=key,
                        buy=int(float(value["buy"]["percentile"])),
                        sell=int(float(value["sell"]["percentile"])),
                        updated=timezone.now(),
                    )
                else:
                    item = ItemPrices(
                        eve_type_id=key,
                        buy=int(float(value["buy"]["max"])),
                        sell=int(float(value["sell"]["min"])),
                        updated=timezone.now(),
                    )

                objs.append(item)
            try:
                ItemPrices.objects.bulk_create(objs)

                print("Succesfully setup %s prices." % item_count)
            except IntegrityError:
                print(
                    "Error: Prices already loaded into database, did you mean to run task.update_all_prices instead?"
                )

                delete_arg = input("Would you like to delete current prices? (y/n): ")

                if delete_arg == "y":
                    ItemPrices.objects.all().delete()
                    return "All price data removed from database. Run the command again to populate the price data."
                else:
                    return "No changes done to price table."
            else:
                print("Starting to update NPC market prices for all fetched items...")

                EveMarketPrice.objects.update_from_esi()

                logger.debug("Updated all eveuniverse market prices.")

                return "Price preload completed!"
