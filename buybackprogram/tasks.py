import json
import os
from datetime import datetime, timedelta

import requests
from bravado.exception import HTTPBadGateway, HTTPGatewayTimeout, HTTPServiceUnavailable
from celery import shared_task

from django.conf import settings
from django.db import Error
from django.utils import timezone
from esi.errors import TokenError
from eveuniverse.models import EveMarketPrice

from allianceauth.services.hooks import get_extension_logger
from allianceauth.services.tasks import QueueOnce

from buybackprogram.app_settings import (
    BUYBACKPROGRAM_PRICE_INSTANT_PRICES,
    BUYBACKPROGRAM_PRICE_JANICE_API_KEY,
    BUYBACKPROGRAM_PRICE_METHOD,
    BUYBACKPROGRAM_PRICE_SOURCE_ID,
    BUYBACKPROGRAM_PRICE_SOURCE_NAME,
)
from buybackprogram.models import ItemPrices, Owner, Program, Tracking, TrackingItem

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
                "buy": {
                    "max": str(item["immediatePrices"]["buyPrice5DayMedian"]),
                    "percentile": str(item["top5AveragePrices"]["buyPrice5DayMedian"]),
                },
                "sell": {
                    "min": str(item["immediatePrices"]["sellPrice5DayMedian"]),
                    "percentile": str(item["top5AveragePrices"]["sellPrice5DayMedian"]),
                },
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
        if len(type_ids) > 0:
            market_data.update(get_bulk_prices(type_ids))

        logger.debug("Market data fetched, starting database update...")
        missing_items = []
        for price in prices:
            # Check if we received data from the API for the item. This will fix errors when using Janice as the POST endpoint does not return anything when there are no prices.
            if str(price.eve_type_id) in market_data:
                # Check what prices we should use either instant prices or top 5% percentile
                if not BUYBACKPROGRAM_PRICE_INSTANT_PRICES:
                    # Get the price values from the API data
                    buy = int(
                        float(market_data[str(price.eve_type_id)]["buy"]["percentile"])
                    )
                    sell = int(
                        float(market_data[str(price.eve_type_id)]["sell"]["percentile"])
                    )
                else:
                    # Get the price values from the API data
                    buy = int(float(market_data[str(price.eve_type_id)]["buy"]["max"]))
                    sell = int(
                        float(market_data[str(price.eve_type_id)]["sell"]["min"])
                    )

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


@shared_task(**TASK_DEFAULT_KWARGS)
def update_program_performance():
    programs = Program.objects.all()
    logger.debug("Got programs %s" % programs)
    for program in programs:
        logger.debug("Starting performance calculations for %s" % program.pk)
        firstbench = datetime.now()
        lastbench = datetime.now()
        # Tracker values
        monthstats = {
            "status": {},
            "overall": {"all": {}},
            "items": {},
            "categories": {},
            "donations": {"all": {}},
        }
        allmonths = set()

        # Category to Item mapping
        category2items = {}

        # Export data
        dumpdata = [
            [
                "Contract ID",
                "Date Issued",
                "Date Finished",
                "User ID",
                "Total ISK",
                "Object Cateogry",
                "Object ID",
                "Object Name",
                "Object Quant",
                "Object ISK",
            ]
        ]

        # Get all tracking objects that have a linked contract to them for the user
        tracking_numbers = (
            Tracking.objects.filter(program_id=program.pk)
            .filter(contract__isnull=False)
            .prefetch_related("contract")
        )

        logger.debug(
            "Performance bench: %.2f" % (datetime.now() - lastbench).total_seconds()
        )
        lastbench = datetime.now()
        # Loop all tracking objects
        for tracking in tracking_numbers:
            month = datetime.strftime(tracking.contract.date_issued, "%Y-%m") + "-15"
            allmonths.add(month)

            if month not in monthstats["status"]:
                monthstats["status"][
                    month
                ] = {}  # status of all contracts issued during a given month

            # Gather stats on all contracts' statuses
            if tracking.contract.status not in monthstats["status"][month]:
                monthstats["status"][month][tracking.contract.status] = 0
            monthstats["status"][month][tracking.contract.status] += 1

            # For finished contracts, gather more data
            if tracking.contract.status == "finished":
                # "overall": {"all": {"isk": {}, "q": {}, }
                if month not in monthstats["overall"]["all"]:
                    monthstats["overall"]["all"][month] = [0, 0]  # isk, q
                    monthstats["donations"]["all"][month] = [0, 0]  # isk, q

                monthstats["overall"]["all"][month][0] += tracking.contract.price
                monthstats["overall"]["all"][month][1] += 1

                monthstats["donations"]["all"][month][0] += tracking.donation
                if tracking.donation > 0:
                    monthstats["donations"]["all"][month][1] += 1

                logger.debug(
                    "Performance loop bench: %.2f"
                    % (datetime.now() - lastbench).total_seconds()
                )
                lastbench = datetime.now()
                # Collect ISK data per items
                tracking_items = TrackingItem.objects.filter(tracking=tracking)
                for item in tracking_items:
                    if item.eve_type.name not in monthstats["items"]:
                        monthstats["items"][item.eve_type.name] = {}
                    if month not in monthstats["items"][item.eve_type.name]:
                        monthstats["items"][item.eve_type.name][month] = [0, 0]
                    monthstats["items"][item.eve_type.name][month][0] += item.buy_value
                    monthstats["items"][item.eve_type.name][month][1] += item.quantity
                    # cache[tracking.contract.issuer_id] = EveEntity.objects.resolve_name(tracking.contract.issuer_id)

                    # Collect item category data
                    catid = item.eve_type.eve_group.name
                    if catid not in category2items:
                        category2items[catid] = set()
                    category2items[catid].add(item.eve_type.name)

                    if catid not in monthstats["categories"]:
                        monthstats["categories"][catid] = {}
                    if month not in monthstats["categories"][catid]:
                        monthstats["categories"][catid][month] = [0, 0]
                    monthstats["categories"][catid][month][0] += item.buy_value
                    monthstats["categories"][catid][month][1] += item.quantity

                    logger.debug("Processing contract %s" % tracking.contract.id)

                    # Collect data for export
                    dumpdata.append(
                        [
                            tracking.id,
                            datetime.strftime(
                                tracking.contract.date_issued, "%Y-%m-%d %H:%M:%S"
                            ),
                            datetime.strftime(
                                tracking.contract.date_completed, "%Y-%m-%d %H:%M:%S"
                            ),
                            tracking.contract.issuer_id,
                            tracking.contract.price,
                            item.eve_type.eve_group.name,
                            item.eve_type.id,
                            item.eve_type.name,
                            item.quantity,
                            item.buy_value,
                        ]
                    )

        logger.debug(
            "Performance exit loop bench: %.2f"
            % (datetime.now() - lastbench).total_seconds()
        )
        lastbench = datetime.now()
        # Reformat data so that it is easier to use billboard.js
        allmonths = sorted(list(allmonths))

        scaling = {}
        hscaling = {}
        for strata in ("overall", "items", "categories", "donations"):
            scaling[strata] = []
            for yi in monthstats[strata].keys():
                scaling[strata] += [
                    monthstats[strata][yi][x][0] for x in monthstats[strata][yi].keys()
                ]
            if len(scaling[strata]) == 0:
                scaling[strata] = 1
            else:
                scaling[strata] = sum(scaling[strata]) / len(scaling[strata])
            for s, h in ((1e9, "Billions"), (1e6, "Millions")):
                if scaling[strata] > s:
                    scaling[strata] = s
                    hscaling[strata] = h
                    break
            if scaling[strata] < 1e6:
                scaling[strata] = 1
                hscaling[strata] = ""

        # Always set donations to be the same scale as overall since they are plotted together.
        scaling["donations"] = scaling["overall"]
        hscaling["donations"] = hscaling["overall"]

        for strata in ("overall", "items", "categories", "donations"):
            for yi in monthstats[strata].keys():
                y = [[yi], [yi]]
                # Overall ISK
                if strata == "overall":
                    y = [["Bought"], ["Contract count"]]
                # Donation ISK
                if strata == "donations":
                    y = [["Donations"], ["Donation count"]]

                for m in allmonths:
                    if m not in (monthstats[strata][yi]):
                        monthstats[strata][yi][m] = [0, 0]
                    y[0].append(
                        round(monthstats[strata][yi][m][0] / scaling[strata], 3)
                    )
                    y[1].append(monthstats[strata][yi][m][1])
                monthstats[strata][yi] = y
        monthstats["x"] = ["x"] + allmonths

        for cat in category2items:
            category2items[cat] = list(category2items[cat])

        # Break down of categories by last three months:
        lastthree = {}
        for yi in monthstats["categories"].keys():
            calc = monthstats["categories"][yi][0].copy()
            calc.pop(0)
            lastthree[yi] = sum(calc[-3:])

        if len(lastthree.keys()) > 10:
            th = lastthree[sorted(lastthree.keys(), key=lambda x: -lastthree[x])[10]]
            lastthree["Other"] = 0
            for k in list(lastthree.keys()):
                if k != "Other" and lastthree[k] <= th:
                    lastthree["Other"] += lastthree[k]
                    del lastthree[k]

            monthstats["categories"]["Other"] = None
            for k in list(monthstats["categories"].keys()):
                if k not in lastthree:
                    if monthstats["categories"]["Other"] is None:
                        monthstats["categories"]["Other"] = monthstats["categories"][k]
                    else:
                        monthstats["categories"]["Other"][0][1:] = [
                            sum(x)
                            for x in zip(
                                monthstats["categories"]["Other"][0][1:],
                                monthstats["categories"][k][0][1:],
                            )
                        ]
                        monthstats["categories"]["Other"][1][1:] = [
                            sum(x)
                            for x in zip(
                                monthstats["categories"]["Other"][1][1:],
                                monthstats["categories"][k][1][1:],
                            )
                        ]
                    del monthstats["categories"][k]
            monthstats["categories"]["Other"][0][0] = "Other"
            monthstats["categories"]["Other"][1][0] = "Other"

        lastthree = list(lastthree.items())

        # Sanitize CSV data
        for i in range(len(dumpdata)):
            for j in range(len(dumpdata[i])):
                dumpdata[i][j] = str(dumpdata[i][j]).replace(",", " ")

        context = {
            "stats": json.dumps(monthstats),
            "lastthree": json.dumps(lastthree),
            "categories": json.dumps(category2items),
            "export": json.dumps(dumpdata),
            "hscaling": json.dumps(hscaling),
        }
        logger.debug(
            "Performance finished: %.2f" % (datetime.now() - lastbench).total_seconds()
        )
        logger.debug(
            "Performance total: %.2f" % (datetime.now() - firstbench).total_seconds()
        )

        logger.debug(context)

        static_path = os.path.join(
            settings.STATIC_ROOT, "buybackprogram/performance_data"
        )
        filename = f"program_performance_{program.pk}.json"
        file_path = os.path.join(static_path, filename)

        data = context

        if not os.path.exists(static_path):
            os.makedirs(static_path)
        with open(file_path, "w") as file:
            json.dump(data, file)
