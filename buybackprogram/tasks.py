from datetime import timedelta

import requests
from bravado.exception import HTTPBadGateway, HTTPGatewayTimeout, HTTPServiceUnavailable
from celery import shared_task

from django.db import Error
from django.utils import timezone
from eveuniverse.models import EveMarketPrice
from esi.errors import TokenError

from allianceauth.services.hooks import get_extension_logger
from allianceauth.services.tasks import QueueOnce

from buybackprogram.app_settings import (
    BUYBACKPROGRAM_PRICE_JANICE_API_KEY,
    BUYBACKPROGRAM_PRICE_METHOD,
    BUYBACKPROGRAM_PRICE_SOURCE_ID,
    BUYBACKPROGRAM_PRICE_SOURCE_NAME,
)
from buybackprogram.models import ItemPrices, Owner, Tracking

from .app_settings import (
    BUYBACKPROGRAM_TASKS_TIME_LIMIT,
    BUYBACKPROGRAM_UNUSED_TRACKING_PURGE_LIMIT,
)

logger = get_extension_logger(__name__)

NORMAL_TASK_PRIORITY = 4

# Create your tasks here
TASK_DEFAULT_KWARGS = {
    "time_limit": BUYBACKPROGRAM_TASKS_TIME_LIMIT,
}

TASK_ESI_KWARGS = {
    **TASK_DEFAULT_KWARGS,
    **{
        "bind": True,
        "autoretry_for": (
            OSError,
            HTTPBadGateway,
            HTTPGatewayTimeout,
            HTTPServiceUnavailable,
        ),
        "retry_kwargs": {"max_retries": 3},
        "retry_backoff": 30,
    },
}


def valid_janice_api_key():
    c = requests.get(
        "https://janice.e-351.com/api/rest/v2/markets",
        headers={
            "Content-Type": "text/plain",
            "X-ApiKey": BUYBACKPROGRAM_PRICE_JANICE_API_KEY,
            "accept": "application/json",
        },
    ).json()

    if "status" in c:
        logger.debug("Janice API status: %s" % c)
        return False
    else:
        return True


def get_bulk_prices(type_ids):
    r = None
    if BUYBACKPROGRAM_PRICE_METHOD == "Fuzzwork":
        r = requests.get(
            "https://market.fuzzwork.co.uk/aggregates/",
            params={
                "types": ",".join([str(x) for x in type_ids]),
                "station": BUYBACKPROGRAM_PRICE_SOURCE_ID,
            },
        ).json()
    elif BUYBACKPROGRAM_PRICE_METHOD == "Janice":
        r = requests.post(
            "https://janice.e-351.com/api/rest/v2/pricer?market=2",
            data="\n".join([str(x) for x in type_ids]),
            headers={
                "Content-Type": "text/plain",
                "X-ApiKey": BUYBACKPROGRAM_PRICE_JANICE_API_KEY,
                "accept": "application/json",
            },
        ).json()

        # Make Janice data look like Fuzzworks
        output = {}
        for item in r:
            output[str(item["itemType"]["eid"])] = {
                "buy": {"max": str(item["top5AveragePrices"]["buyPrice5DayMedian"])},
                "sell": {"min": str(item["top5AveragePrices"]["sellPrice5DayMedian"])},
            }
        r = output
    else:
        raise f"Unknown pricing method: {BUYBACKPROGRAM_PRICE_METHOD}"

    return r


@shared_task
def update_all_prices():
    type_ids = []
    market_data = {}
    api_up = True

    # Get all type ids
    prices = ItemPrices.objects.all()

    if BUYBACKPROGRAM_PRICE_METHOD == "Fuzzwork":
        logger.debug(
            "Price setup starting for %s items from Fuzzworks API from station id %s (%s), this may take up to 30 seconds..."
            % (
                len(prices),
                BUYBACKPROGRAM_PRICE_SOURCE_ID,
                BUYBACKPROGRAM_PRICE_SOURCE_NAME,
            )
        )
    elif BUYBACKPROGRAM_PRICE_METHOD == "Janice":
        if valid_janice_api_key():
            logger.debug(
                "Price setup starting for %s items from Janice API for Jita 4-4, this may take up to 30 seconds..."
                % (len(prices),)
            )
        else:
            logger.debug(
                "Price setup failed for Janice, invalid API key! Provide a working key or change price source to Fuzzwork"
            )
            api_up = False
    else:
        logger.error(
            "Unknown pricing method: '%s', skipping" % BUYBACKPROGRAM_PRICE_METHOD
        )
        return

    if api_up:
        # Build suitable bulks to fetch prices from API
        for item in prices:
            type_ids.append(item.eve_type_id)

            if len(type_ids) == 1000:
                market_data.update(get_bulk_prices(type_ids))
                type_ids.clear()

        # Get leftover data from the bulk
        market_data.update(get_bulk_prices(type_ids))

        logger.debug("Market data fetched, starting database update...")
        missing_items = []
        for price in prices:
            # Check if we received data from the API for the item. This will fix errors when using Janice as the POST endpoint does not return anything when there are no prices.
            if str(price.eve_type_id) in market_data:
                # Get the price values from the API data
                buy = int(float(market_data[str(price.eve_type_id)]["buy"]["max"]))
                sell = int(float(market_data[str(price.eve_type_id)]["sell"]["min"]))

            # If API did not return any values we remove prices for the item
            else:
                missing_items.append(price.eve_type.name)

                # Reset prices for items not found from API
                buy = 0
                sell = 0

            price.buy = buy
            price.sell = sell
            price.updated = timezone.now()

        try:
            ItemPrices.objects.bulk_update(prices, ["buy", "sell", "updated"])
            logger.debug("All prices succesfully updated")
        except Error as e:
            logger.error("Error updating prices: %s" % e)

        EveMarketPrice.objects.update_from_esi()

        logger.debug("Updated all eveuniverse market prices.")

        if len(missing_items) > 0:
            logger.error(
                "%s items missing items from source API, prices set to 0."
                % len(missing_items)
            )

    else:
        logger.error("Price source API is not up! Prices not updated.")

    if BUYBACKPROGRAM_UNUSED_TRACKING_PURGE_LIMIT > 0:
        """cleanup unused tracking objects"""
        logger.debug(
            "Starting tracking objects cleanup. Removing tracking objects with no contracts assigned to them that are more than %s hours old "
            % BUYBACKPROGRAM_UNUSED_TRACKING_PURGE_LIMIT
        )

        try:
            trackings, t = Tracking.objects.filter(
                contract_id__isnull=True,
                created_at__lte=timezone.now()
                - timedelta(hours=BUYBACKPROGRAM_UNUSED_TRACKING_PURGE_LIMIT),
            ).delete()
            logger.debug("%s old unlinked tracking objects deleted." % len(t))
        except Error as e:
            logger.error("Error deleting old tracking objects: %s" % e)
    else:
        logger.debug(
            "Tracking object time limit is set to %s, no old tracking object purging will happen. "
            % BUYBACKPROGRAM_UNUSED_TRACKING_PURGE_LIMIT
        )


@shared_task(
    **{
        **TASK_ESI_KWARGS,
        **{
            "base": QueueOnce,
            "once": {"keys": ["owner_pk"], "graceful": True},
            "max_retries": None,
        },
    }
)
def update_contracts_for_owner(self, owner_pk):
    """fetches all contracts for owner from ESI"""

    try:
        return _get_owner(owner_pk).update_contracts_esi()
    except TokenError:
        print("Invalid token provided.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
        return None


@shared_task(**TASK_DEFAULT_KWARGS)
def update_all_contracts():
    logger.debug("Starting all contract updates")
    for owner in Owner.objects.all():
        logger.debug("Updating contracts for %s" % owner)
        update_contracts_for_owner.apply_async(
            kwargs={"owner_pk": owner.pk},
            priority=NORMAL_TASK_PRIORITY,
        )


def _get_owner(owner_pk: int) -> Owner:
    """returns the owner or raises exception"""
    try:
        owner = Owner.objects.get(pk=owner_pk)
    except Owner.DoesNotExist:
        raise Owner.DoesNotExist(
            "Requested owner with pk {} does not exist".format(owner_pk)
        )
    return owner
