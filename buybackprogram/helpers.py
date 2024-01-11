import statistics
import uuid

import requests

from django.db import Error
from django.utils import timezone
from eveuniverse.models import EveMarketPrice, EveType, EveTypeMaterial

from allianceauth.services.hooks import get_extension_logger

from buybackprogram.app_settings import (
    BUYBACKPROGRAM_PRICE_AGE_WARNING_LIMIT,
    BUYBACKPROGRAM_PRICE_INSTANT_PRICES,
    BUYBACKPROGRAM_PRICE_JANICE_API_KEY,
    BUYBACKPROGRAM_PRICE_METHOD,
    BUYBACKPROGRAM_PRICE_SOURCE_ID,
    BUYBACKPROGRAM_TRACKING_PREFILL,
)
from buybackprogram.constants import (
    BLUE_LOOT_TYPE_IDS,
    BONDS_EVE_GROUPS,
    OPE_EVE_GROUPS,
    ORE_EVE_GROUPS,
    RED_LOOT_TYPE_IDS,
)
from buybackprogram.models import ItemPrices, ProgramItem, Tracking, TrackingItem
from buybackprogram.notes import (
    note_compressed_price_used,
    note_item_disallowed,
    note_item_specific_tax,
    note_missing_jita_buy,
    note_missing_npc_price,
    note_missing_typematerials,
    note_no_price_data,
    note_npc_price,
    note_price_dencity_tax,
    note_price_outdated,
    note_raw_price_used,
    note_refined_price_used,
    note_unpublished_item,
)
from buybackprogram.tasks import valid_janice_api_key

logger = get_extension_logger(__name__)


def get_item_tax(program, item_id):
    try:
        program_item_settings = ProgramItem.objects.get(
            program=program, item_type__id=item_id
        )

        return program_item_settings.item_tax

    except ProgramItem.DoesNotExist:
        return False


def use_npc_price(item, program):
    if item.id in BLUE_LOOT_TYPE_IDS and program.blue_loot_npc_price:
        return True
    elif item.id in RED_LOOT_TYPE_IDS and program.red_loot_npc_price:
        return True
    elif item.eve_group.id in OPE_EVE_GROUPS and program.ope_npc_price:
        return True
    elif item.eve_group.id in BONDS_EVE_GROUPS and program.ope_npc_price:
        return True
    else:
        return False


def get_or_create_prices(item_id):
    try:
        return ItemPrices.objects.get(eve_type_id=item_id)

    except ItemPrices.DoesNotExist:
        if BUYBACKPROGRAM_PRICE_METHOD == "Fuzzwork":
            response_fuzzwork = requests.get(
                "https://market.fuzzwork.co.uk/aggregates/",
                params={
                    "types": item_id,
                    "station": BUYBACKPROGRAM_PRICE_SOURCE_ID,
                },
            )

            items_fuzzwork = response_fuzzwork.json()

            buy = int(float(items_fuzzwork[str(item_id)]["buy"]["max"]))
            sell = int(float(items_fuzzwork[str(item_id)]["sell"]["min"]))
            buy_average = int(float(items_fuzzwork[str(item_id)]["buy"]["percentile"]))
            sell_average = int(
                float(items_fuzzwork[str(item_id)]["sell"]["percentile"])
            )

        elif BUYBACKPROGRAM_PRICE_METHOD == "Janice":
            if valid_janice_api_key():
                response_janice = requests.get(
                    f"https://janice.e-351.com/api/rest/v2/pricer/{item_id}",
                    headers={
                        "Content-Type": "text/plain",
                        "X-ApiKey": BUYBACKPROGRAM_PRICE_JANICE_API_KEY,
                        "accept": "application/json",
                    },
                )

                item_janice = response_janice.json()

                buy = int(float(item_janice["immediatePrices"]["buyPrice5DayMedian"]))
                sell = int(float(item_janice["immediatePrices"]["sellPrice5DayMedian"]))
                buy_average = int(
                    float(item_janice["top5AveragePrices"]["buyPrice5DayMedian"])
                )
                sell_average = int(
                    float(item_janice["top5AveragePrices"]["sellPrice5DayMedian"])
                )
            else:
                logger.error(
                    "Price setup failed for Janice, invalid API key! Provide a working key or change price source to Fuzzwork"
                )

                buy = False
                sell = False

        else:
            raise f"Unknown pricing method: {BUYBACKPROGRAM_PRICE_METHOD}"

        updated = timezone.now()

        try:
            # Check what prices we should use either instant prices or top 5% percentile
            logger.debug(
                "Price type instant price is set to %s"
                % BUYBACKPROGRAM_PRICE_INSTANT_PRICES
            )
            if not BUYBACKPROGRAM_PRICE_INSTANT_PRICES:
                price = ItemPrices.objects.create(
                    eve_type_id=item_id,
                    buy=buy_average,
                    sell=sell_average,
                    updated=updated,
                )
            else:
                price = ItemPrices.objects.create(
                    eve_type_id=item_id, buy=buy, sell=sell, updated=updated
                )

            return price
        except Error as e:
            logger.error("Error updating prices: %s" % e)


def get_npc_price(item_id):
    try:
        logger.error("Getting NPC price from EveMarketPrice for item: %s" % (item_id))
        return EveMarketPrice.objects.get(eve_type=item_id)
    except EveMarketPrice.DoesNotExist:
        logger.error(
            "NPC price missing from EveMarketPrice for: %s. Did you forget to run buybackprogram_load_data and buybackprogram_load_prices on setup?"
            % (item_id)
        )
        return EveMarketPrice.objects.none()

    except Error as e:
        logger.error("Error getting NPC prices for %s: %s" % (item_id, e))


def getList(dict):
    return dict.keys()


def is_ore(item_id):
    if item_id in ORE_EVE_GROUPS:
        return True
    else:
        return False


def has_buy_price(item):
    logger.debug("Has buy price: Value is set to %s" % item)

    if (
        not item["raw_prices"]
        and not item["material_prices"]
        and not item["compression_prices"]
        and not item["npc_prices"]
    ):
        return False
    else:
        return True


def get_price_dencity_tax(
    program, item_value, item_volume, item_quantity, is_ore=False
):
    # If price dencity tax should be applied
    if program.price_dencity_modifier:
        # Check that the item has a volume and the volume is positive. Some items do not have volumes
        if not item_volume <= 0:
            # Check if the item should be excluded from density tax (compressable ore)
            if not program.compression_price_dencity_modifier and is_ore:
                item_isk_dencity = False
                logger.debug(
                    "ISK density: Our item is type ORE and compression_price_dencity_modifier is set to %s, no density tax applied."
                    % (program.compression_price_dencity_modifier)
                )
            else:
                item_isk_dencity = item_value / item_volume

                logger.debug(
                    "ISK density: Our item isk dencity is at %s ISK/m³ with value: %s, volume: %s"
                    % (item_isk_dencity, item_value, item_volume)
                )
        else:
            item_isk_dencity = False

            logger.debug(
                "ISK density: Item has no volume, no density calculations applied"
            )

        if item_isk_dencity < program.price_dencity_treshold and item_isk_dencity:
            logger.debug(
                "ISK density: Isk dencity %s is under threshold value %s, applying extra taxes of %s"
                % (
                    item_isk_dencity,
                    program.price_dencity_treshold,
                    program.price_dencity_tax,
                )
            )

            return program.price_dencity_tax
        else:
            logger.debug(
                "ISK density: Isk dencity %s is above threshold value %s, no extra taxes added"
                % (item_isk_dencity, program.price_dencity_treshold)
            )
            return False
    else:
        logger.debug(
            "ISK density: Program price density modifier is set to %s, no density calculations applied"
            % (program.price_dencity_modifier)
        )
        return False


# This method will get the price information for the item. It will not calculate the values as in price including taxes.
def get_item_prices(item_type, name, quantity, program):
    notes = []
    has_price_variants = False

    # Get special taxes and see if our item belongs to this table
    program_item_settings = ProgramItem.objects.filter(
        program=program, item_type__id=item_type.id
    ).first()

    # Get item raw price information
    item_price = get_or_create_prices(item_type.id)

    # Check what items are allowed
    if program.allow_all_items:
        if program_item_settings:
            item_disallowed = program_item_settings.disallow_item

            notes.append(note_item_disallowed(item_disallowed, name))

        else:
            item_disallowed = False
    else:
        if program_item_settings:
            item_disallowed = program_item_settings.disallow_item

            notes.append(note_item_disallowed(item_disallowed, name))

        else:
            item_disallowed = True

            notes.append(note_item_disallowed(item_disallowed, name))

    # If item is somehow not published (expired items etc.)
    if not item_type.published or not item_type.eve_market_group:
        item_disallowed = True

        notes.append(note_unpublished_item(item_type))

        logger.debug(
            "%s published status is %s and market group is %s, item disallowed: %s"
            % (name, item_type.published, item_type.eve_market_group, item_disallowed)
        )

    logger.debug("%s is disallowed: %s" % (name, item_disallowed))

    if not item_disallowed:
        # If raw ore value should not be taken into account
        if is_ore(item_type.eve_group.id) and not program.use_raw_ore_value:
            logger.debug("Raw price not used for %s" % item_type.name)

            item_raw_price = {
                "id": item_type.id,
                "volume": item_type.volume,
                "quantity": quantity,
                "buy": item_price.buy,
                "sell": item_price.sell,
                "raw_price_used": False,
            }

        else:
            item_raw_price = {
                "id": item_type.id,
                "volume": item_type.volume,
                "quantity": quantity,
                "buy": item_price.buy,
                "sell": item_price.sell,
                "raw_price_used": True,
            }

        notes.append(note_missing_jita_buy(item_price.buy, name))

        # Get time difference since price update
        update_timediff = timezone.now() - item_price.updated

        # Convert to hours
        update_timediff = update_timediff.total_seconds() / 3600

        logger.debug("Raw price data was updated %s hours a go" % update_timediff)

        if update_timediff > BUYBACKPROGRAM_PRICE_AGE_WARNING_LIMIT:
            notes.append(note_price_outdated(update_timediff, name))

        # Check if we should get refined value for the item
        if is_ore(item_type.eve_group.id) and program.use_refined_value:
            item_material_price = []

            # Get all refining materials for item
            type_materials = EveTypeMaterial.objects.filter(
                eve_type_id=item_type.id
            ).prefetch_related("eve_type")

            notes.append(note_missing_typematerials(type_materials, name))

            # Get price details for the materials inside the item
            for material in type_materials:
                material_price = get_or_create_prices(material.material_eve_type.id)

                # Quantity of refined materials
                material_quantity = (
                    material.quantity * quantity
                ) / item_type.portion_size

                material_type_prices = {
                    "id": material.material_eve_type.id,
                    "quantity": material_quantity,
                    "unit_quantity": material.quantity / item_type.portion_size,
                    "buy": material_price.buy,
                    "sell": material_price.sell,
                }

                item_material_price.append(material_type_prices)

            has_price_variants = True

            logger.debug("Prices: Got refined values for %s" % name)

        else:
            item_material_price = False
            type_materials = False
            logger.debug("Prices: No refined value used for %s" % name)

        # Get compressed versions of the ores that are not yet compressed
        if is_ore(item_type.eve_group.id):
            if "Compressed" in name:
                compresed_name = name
            else:
                compresed_name = "Compressed " + name

            compresed_type = EveType.objects.filter(name=compresed_name).first()

            compression_price = get_or_create_prices(compresed_type.id)

            compressed_type_prices = {
                "id": compression_price.eve_type_id,
                "quantity": quantity,
                "buy": compression_price.buy,
                "sell": compression_price.sell,
            }

            has_price_variants = True

            logger.debug(
                "Prices: Got compression prices %s ISK for %s based on original item %s"
                % (compression_price.buy, compresed_name, name)
            )

        # If item can't or should not be compressed
        else:
            logger.debug("Prices: No compression required/available for %s" % name)
            compressed_type_prices = False

        # Get NPC prices
        if use_npc_price(item_type, program):
            item_npc_price = get_npc_price(item_type.id)

            if item_npc_price:
                npc_type_prices = {
                    "id": item_type.id,
                    "quantity": quantity,
                    "buy": item_npc_price.average_price,
                    "sell": False,
                }
            else:
                npc_type_prices = {
                    "id": item_type.id,
                    "quantity": quantity,
                    "buy": 0,
                    "sell": False,
                }

                notes.append(note_missing_npc_price(name))

            logger.debug("Prices: Got NPC buy price for %s" % name)

        else:
            logger.debug("Prices: No NPC prices required/available for %s" % name)
            npc_type_prices = False

        prices = {
            "quantity": quantity,
            "type_prices": item_price,
            "raw_prices": item_raw_price,
            "material_prices": item_material_price,
            "compression_prices": compressed_type_prices,
            "npc_prices": npc_type_prices,
            "has_price_variants": has_price_variants,
            "notes": notes,
        }

    else:
        prices = {
            "quantity": quantity,
            "type_prices": item_price,
            "raw_prices": False,
            "material_prices": False,
            "compression_prices": False,
            "npc_prices": False,
            "has_price_variants": has_price_variants,
            "notes": notes,
        }

    return prices


def get_item_values(item_type, item_prices, program):
    type_value = False
    compression_value = False
    item_tax = False
    refined = []
    compressed = False
    type_raw_value = False
    compression_raw_value = False

    # RAW VARIANT VALUES
    if item_prices["raw_prices"] and item_prices["raw_prices"]["raw_price_used"]:
        quantity = item_prices["raw_prices"]["quantity"]
        sell = item_prices["raw_prices"]["sell"]
        buy = item_prices["raw_prices"]["buy"]
        split = statistics.median([sell, buy])

        # Determine what price type we should use
        if program.price_type == "Buy":
            price = buy
        elif program.price_type == "Sell":
            price = sell
        elif program.price_type == "Split":
            price = split

        logger.debug(
            "Using price value type '%s' with value %s" % (program.price_type, price)
        )

        if not item_type.volume <= 0:
            price_dencity = price / item_type.volume
        else:
            price_dencity = False
        price_dencity_tax = get_price_dencity_tax(
            program, price, item_type.volume, quantity, is_ore(item_type.eve_group.id)
        )
        program_tax = program.tax
        item_tax = get_item_tax(program, item_type.id)
        tax_multiplier = (100 - (program_tax + item_tax + price_dencity_tax)) / 100

        logger.debug("Values: Calculating type value for %s" % item_type)

        type_raw_value = quantity * price
        type_value = type_raw_value * tax_multiplier

        raw_item = {
            "id": item_type.id,
            "name": item_type.name,
            "quantity": quantity,
            "buy": buy,
            "sell": sell,
            "program_tax": program_tax,
            "item_tax": item_tax,
            "price_dencity_tax": price_dencity_tax,
            "total_tax": program_tax + item_tax + price_dencity_tax,
            "price_dencity": price_dencity,
            "unit_value": price * tax_multiplier,
            "raw_value": type_raw_value,
            "value": type_value,
            "is_buy_value": False,
            "notes": [],
        }

        raw_item["notes"].append(
            note_price_dencity_tax(raw_item["name"], price_dencity, price_dencity_tax)
        )
        raw_item["notes"].append(note_item_specific_tax(item_type.name, item_tax))

    else:
        raw_item = {
            "unit_value": False,
            "value": False,
            "total_tax": False,
            "raw_value": False,
        }

    # REFINED VARIANT VALUES
    if item_prices["material_prices"] and program.use_refined_value:
        refined = {
            "materials": [],
            "buy": False,
            "unit_value": False,
            "total_tax": False,
            "raw_value": False,
            "item_tax": False,
            "value": False,
            "is_buy_value": False,
            "notes": [],
        }

        item_tax = get_item_tax(program, item_type.id)

        # Check if compressed price is used. If yes we will use compression price density. If not we will use raw price density.
        if item_prices["compression_prices"]:
            compressed_version = EveType.objects.filter(
                id=item_prices["compression_prices"]["id"]
            ).first()

            logger.debug(
                "Values: Compression price model in TRUE. Checking price density for %s based on %s density"
                % (item_type.name, compressed_version.name)
            )

            price_dencity = (
                item_prices["compression_prices"]["buy"] / compressed_version.volume
            )

            price_dencity_tax = get_price_dencity_tax(
                program,
                item_prices["compression_prices"]["buy"],
                compressed_version.volume,
                item_prices["compression_prices"]["quantity"],
                is_ore(item_type.eve_group.id),
            )

            logger.debug(
                "Values: Got price density for refined %s of %s with tax %s"
                % (item_type.name, price_dencity, price_dencity_tax)
            )

        else:
            logger.debug(
                "Values: Compression price model is FALSE. Checking price density for %s based on raw variant"
                % (item_type.name)
            )

            if not item_type.volume <= 0:
                price_dencity = item_prices["raw_prices"]["buy"] / item_type.volume
            else:
                price_dencity = False

            price_dencity_tax = get_price_dencity_tax(
                program,
                item_prices["raw_prices"]["buy"],
                item_type.volume,
                item_prices["raw_prices"]["quantity"],
                is_ore(item_type.eve_group.id),
            )

            logger.debug(
                "Values: Got price density for refined %s of %s with tax %s"
                % (item_type.name, price_dencity, price_dencity_tax)
            )

        # Add possible notes about low price density
        refined["notes"].append(
            note_price_dencity_tax(item_type.name, price_dencity, price_dencity_tax)
        )

        for material in item_prices["material_prices"]:
            materials = EveType.objects.filter(id=material["id"]).first()

            quantity = material["quantity"]
            sell = material["sell"]
            buy = material["buy"]
            split = statistics.median([sell, buy])

            # Determine what price type we should use
            if program.price_type == "Buy":
                price = buy
                logger.debug(
                    "Using price type '%s' with value %s" % (program.price_type, price)
                )
            elif program.price_type == "Sell":
                price = sell
                logger.debug(
                    "Using price type '%s' with value %s" % (program.price_type, price)
                )
            elif program.price_type == "Split":
                price = split
                logger.debug(
                    "Using price type '%s' with value %s" % (program.price_type, price)
                )
            program_tax = program.tax
            refining_rate = float(program.refining_rate) / 100
            tax_multiplier = (100 - (program_tax + item_tax + price_dencity_tax)) / 100

            raw_value = quantity * refining_rate * price
            value = raw_value * tax_multiplier

            r = {
                "id": material["id"],
                "name": materials.name,
                "quantity": quantity * refining_rate,
                "buy": buy,
                "sell": sell,
                "program_tax": program_tax,
                "item_tax": item_tax,
                "price_dencity_tax": price_dencity_tax,
                "total_tax": program_tax + item_tax + price_dencity_tax,
                "price_dencity": price_dencity,
                "unit_value": price * tax_multiplier,
                "raw_value": raw_value,
                "value": value,
                "notes": [],
            }

            r["notes"].append(
                note_price_dencity_tax(item_type.name, price_dencity, price_dencity_tax)
            )

            refined["materials"].append(r)

            refined["buy"] += buy
            refined["value"] += value
            refined["raw_value"] += raw_value
            refined["item_tax"] = item_tax
            refined["total_tax"] = program_tax + item_tax + price_dencity_tax
            refined["unit_value"] += (
                price * tax_multiplier * material["unit_quantity"] * refining_rate
            )

    else:
        refined = {
            "value": False,
            "buy": False,
            "raw_value": False,
            "total_tax": False,
            "unit_value": False,
            "notes": False,
        }

    logger.debug("Values: Item refined value is %s" % refined["unit_value"])

    # COMPRESSION VARIANT VALUES
    if item_prices["compression_prices"] and program.use_compressed_value:
        compressed_version = EveType.objects.filter(
            id=item_prices["compression_prices"]["id"]
        ).first()

        quantity = item_prices["compression_prices"]["quantity"]
        buy = item_prices["compression_prices"]["buy"]
        sell = item_prices["compression_prices"]["sell"]
        split = statistics.median([sell, buy])

        # Determine what price type we should use
        if program.price_type == "Buy":
            price = buy
            logger.debug(
                "Using price type '%s' with value %s" % (program.price_type, price)
            )
        elif program.price_type == "Sell":
            price = sell
            logger.debug(
                "Using price type '%s' with value %s" % (program.price_type, price)
            )
        elif program.price_type == "Split":
            price = split
            logger.debug(
                "Using price type '%s' with value %s" % (program.price_type, price)
            )
        price_dencity = price / compressed_version.volume

        logger.debug("Getting price density for compressed variant")

        price_dencity_tax = get_price_dencity_tax(
            program,
            price,
            compressed_version.volume,
            quantity,
            is_ore(item_type.eve_group.id),
        )
        program_tax = program.tax
        item_tax = get_item_tax(program, item_type.id)
        tax_multiplier = (100 - (program_tax + item_tax + price_dencity_tax)) / 100

        logger.debug("Values: Calculating compression value for %s" % item_type.id)

        compression_raw_value = quantity * price
        compression_value = compression_raw_value * tax_multiplier

        compressed = {
            "id": compressed_version.id,
            "name": compressed_version.name,
            "quantity": quantity,
            "buy": buy,
            "sell": sell,
            "program_tax": program_tax,
            "item_tax": item_tax,
            "price_dencity_tax": price_dencity_tax,
            "total_tax": program_tax + item_tax + price_dencity_tax,
            "price_dencity": price_dencity,
            "unit_value": price * tax_multiplier,
            "raw_value": compression_raw_value,
            "value": compression_value,
            "is_buy_value": False,
            "notes": [],
        }

        compressed["notes"].append(
            note_price_dencity_tax(
                compressed_version.name, price_dencity, price_dencity_tax
            )
        )
        compressed["notes"].append(
            note_item_specific_tax(compressed_version.name, item_tax)
        )
    else:
        compressed = {
            "value": False,
            "raw_value": False,
            "total_tax": False,
            "unit_value": False,
        }

    logger.debug("Values: Item compressed unit value is %s" % compressed["unit_value"])

    # Get value for NPC price
    if item_prices["npc_prices"]:
        quantity = item_prices["npc_prices"]["quantity"]
        sell = item_prices["npc_prices"]["sell"]
        buy = item_prices["npc_prices"]["buy"]
        split = statistics.median([sell, buy])

        # Determine what price type we should use
        if program.price_type == "Buy":
            price = buy
            logger.debug(
                "Using price type '%s' with value %s" % (program.price_type, price)
            )
        elif program.price_type == "Sell":
            price = sell
            logger.debug(
                "Using price type '%s' with value %s" % (program.price_type, price)
            )
        elif program.price_type == "Split":
            price = split
            logger.debug(
                "Using price type '%s' with value %s" % (program.price_type, price)
            )

        if not item_type.volume <= 0:
            price_dencity = price / item_type.volume
        else:
            price_dencity = False
        price_dencity_tax = get_price_dencity_tax(
            program, price, item_type.volume, quantity, is_ore(item_type.eve_group.id)
        )
        program_tax = program.tax
        item_tax = get_item_tax(program, item_type.id)
        tax_multiplier = (100 - (program_tax + item_tax + price_dencity_tax)) / 100

        logger.debug("Values: Calculating npc value for %s" % item_type)

        type_raw_value = quantity * price
        type_value = type_raw_value * tax_multiplier

        npc_item = {
            "id": item_type.id,
            "name": item_type.name,
            "quantity": quantity,
            "buy": buy,
            "sell": sell,
            "program_tax": program_tax,
            "item_tax": item_tax,
            "price_dencity_tax": price_dencity_tax,
            "total_tax": program_tax + item_tax + price_dencity_tax,
            "price_dencity": price_dencity,
            "unit_value": price * tax_multiplier,
            "raw_value": type_raw_value,
            "value": type_value,
            "is_buy_value": False,
            "notes": [],
        }

        npc_item["notes"].append(
            note_price_dencity_tax(npc_item["name"], price_dencity, price_dencity_tax)
        )
        npc_item["notes"].append(note_item_specific_tax(item_type.name, item_tax))

    else:
        npc_item = {
            "unite_value": False,
            "value": False,
            "total_tax": False,
            "raw_value": False,
        }

    # If there are no price variations at all for the item
    if not has_buy_price(item_prices):
        item_prices["notes"].append(note_no_price_data(item_type.name))

        raw_item = {
            "id": item_type.id,
            "name": item_type.name,
            "quantity": item_prices["quantity"],
            "buy": False,
            "sell": False,
            "program_tax": False,
            "item_tax": False,
            "price_dencity_tax": False,
            "total_tax": False,
            "price_dencity": False,
            "unit_value": False,
            "raw_value": False,
            "value": False,
            "is_buy_value": False,
        }

    # Get the highest value of the used pricing methods
    if not item_prices["npc_prices"]:
        buy_value = max([raw_item["value"], refined["value"], compressed["value"]])

        raw_value = max(
            [raw_item["raw_value"], refined["raw_value"], compressed["raw_value"]]
        )

        unit_value = max(
            [raw_item["unit_value"], refined["unit_value"], compressed["unit_value"]]
        )
    else:
        buy_value = npc_item["value"]
        raw_value = npc_item["raw_value"]
        unit_value = npc_item["unit_value"]

    # Determine what value we will use for buy value
    if buy_value == raw_item["value"]:
        raw_item["is_buy_value"] = True
        tax_value = raw_item["total_tax"]

        if item_prices["has_price_variants"]:
            item_prices["notes"].append(note_raw_price_used(raw_item["name"]))

        item_prices["notes"].append(
            note_price_dencity_tax(
                raw_item["name"],
                raw_item["price_dencity"],
                raw_item["price_dencity_tax"],
            )
        )
        item_prices["notes"].append(
            note_item_specific_tax(raw_item["name"], raw_item["item_tax"])
        )

        logger.debug(
            "Values: Best buy value with raw price for %s is %s ISK"
            % (item_type, buy_value)
        )

    elif buy_value == npc_item["value"]:
        npc_item["is_buy_value"] = True
        tax_value = npc_item["total_tax"]

        item_prices["notes"].append(note_npc_price(raw_item["name"]))

        item_prices["notes"].append(
            note_price_dencity_tax(
                raw_item["name"],
                raw_item["price_dencity"],
                raw_item["price_dencity_tax"],
            )
        )

        item_prices["notes"].append(
            note_item_specific_tax(raw_item["name"], raw_item["item_tax"])
        )

        logger.debug(
            "Values: Best buy value with NPC price for %s is %s ISK"
            % (item_type, buy_value)
        )

    elif buy_value == refined["value"]:
        refined["is_buy_value"] = True
        tax_value = refined["total_tax"]

        item_prices["notes"].append(note_refined_price_used(item_type.name))

        for note in refined["notes"]:
            item_prices["notes"].append(note)

        item_prices["notes"].append(
            note_item_specific_tax(item_type.name, refined["item_tax"])
        )

        logger.debug(
            "Values: Best buy value with refined price for %s is %s ISK"
            % (item_type, buy_value)
        )

    elif buy_value == compressed["value"]:
        compressed["is_buy_value"] = True
        tax_value = compressed["total_tax"]

        item_prices["notes"].append(note_compressed_price_used(compressed["name"]))

        item_prices["notes"].append(
            note_price_dencity_tax(
                compressed["name"],
                compressed["price_dencity"],
                compressed["price_dencity_tax"],
            )
        )
        item_prices["notes"].append(
            note_item_specific_tax(compressed["name"], compressed["item_tax"])
        )

        logger.debug(
            "Values: Best buy value with compressed price for %s is %s ISK"
            % (item_type, buy_value)
        )

    # Final values for this item
    values = {
        "name": item_type,
        "quantity": item_prices["quantity"],
        "normal": raw_item,
        "refined": refined,
        "compressed": compressed,
        "npc": npc_item,
        "type_value": raw_item["value"],
        "material_value": refined["value"],
        "compression_value": compressed["value"],
        "npc_value": npc_item["value"],
        "unit_value": unit_value,
        "raw_value": raw_value,
        "tax_value": tax_value,
        "buy_value": buy_value,
    }

    return values


def get_item_buy_value(buyback_data, program, donation):
    total_all_items = 0
    total_hauling_cost = 0
    contract_net_total = False
    total_donation = False
    tota_all_items_raw = 0

    # Get a grand total value of all buy prices
    for item in buyback_data:
        tota_all_items_raw += item["item_values"]["raw_value"]
        total_all_items += item["item_values"]["buy_value"]

    logger.debug(
        "Final: Total buy value for all items before expenses is %s ISK"
        % total_all_items
    )

    if donation > 0:
        total_donation = total_all_items * (donation / 100)

        logger.debug(
            "Seller will donate %s a total of %s ISK" % (donation, total_donation)
        )

    # Calculate hauling expenses
    if program.hauling_fuel_cost > 0:
        for item in buyback_data:
            if has_buy_price(item["item_prices"]):
                # Check if compressed price is used. If yes we will use compression price density. If not we will use raw price density.
                if item["item_prices"]["compression_prices"]:
                    compressed_version = EveType.objects.filter(
                        id=item["item_prices"]["compression_prices"]["id"]
                    ).first()

                    item_volume = compressed_version.volume

                    logger.debug(
                        "Fuel Cost: Compression price model in TRUE. Checking fuel cost for %s based on %s volume of %s"
                        % (item["type_data"], compressed_version.name, item_volume)
                    )

                else:
                    logger.debug(
                        "Fuel Cost: Compression price model is FALSE. Checking fuel cost for %s based on raw volume"
                        % (item["type_data"])
                    )

                    item_volume = item["type_data"].volume

                quantity = item["item_values"]["quantity"]
                hauling_cost = item_volume * program.hauling_fuel_cost * quantity

                logger.debug(
                    "Fuel Cost: Fuel cost for %s pcs of %s with volume of %s is %s."
                    % (quantity, item["type_data"], item_volume, hauling_cost)
                )

                total_hauling_cost += hauling_cost

                logger.debug(
                    "Final: Hauling cost %s m³ of %s is %s ISK"
                    % (
                        item["item_values"]["quantity"],
                        item["type_data"],
                        hauling_cost,
                    )
                )

        logger.debug(
            "Final: Total hauling cost for whole contract is %s ISK"
            % total_hauling_cost
        )

    contract_net_total = total_all_items - total_hauling_cost - total_donation

    logger.debug("Final: Net total after expenses is %s ISK" % contract_net_total)

    contract_net_prices = {
        "total_all_items_raw": tota_all_items_raw,
        "total_all_items": total_all_items,
        "total_tax_amount": tota_all_items_raw - total_all_items,
        "total_donation_amount": total_donation,
        "hauling_cost": program.hauling_fuel_cost,
        "total_hauling_cost": total_hauling_cost,
        "contract_net_total": contract_net_total,
    }

    return contract_net_prices


def item_missing(item_name, quantity):
    values = {
        "name": item_name,
        "quantity": quantity,
        "normal": False,
        "refined": False,
        "compressed": False,
        "type_value": False,
        "material_value": False,
        "compression_value": False,
        "unit_value": False,
        "raw_value": False,
        "buy_value": False,
    }

    return values


def get_tracking_number(
    user, program, form_donation, buyback_data, contract_price_data
):
    try:
        last_id = Tracking.objects.last().id
    except AttributeError:
        last_id = 0

    tracking_number = (
        BUYBACKPROGRAM_TRACKING_PREFILL
        + "-"
        + str(last_id)
        + "-"
        + uuid.uuid4().hex[:6].upper()
    )

    logger.debug(
        "Contract net total for tracking %s is %s"
        % (tracking_number, contract_price_data["contract_net_total"])
    )

    tracking = Tracking(
        program=program,
        issuer_user=user,
        value=contract_price_data["total_all_items_raw"],
        taxes=contract_price_data["total_tax_amount"],
        hauling_cost=contract_price_data["total_hauling_cost"],
        donation=contract_price_data["total_donation_amount"],
        net_price=round(contract_price_data["contract_net_total"]),
        tracking_number=tracking_number,
        created_at=timezone.now(),
    )

    tracking.save()

    objs = []

    for item in buyback_data:
        if item["type_data"]:
            tracking_item = TrackingItem(
                tracking=tracking,
                eve_type=item["type_data"],
                buy_value=item["item_values"]["unit_value"],
                quantity=item["item_values"]["quantity"],
            )

            objs.append(tracking_item)
    try:
        TrackingItem.objects.bulk_create(objs)
        logger.debug("Succesfully created items for tracking %s" % tracking_number)
    except Error as e:
        logger.error("Error creating tracking items: %s" % e)

    return tracking
