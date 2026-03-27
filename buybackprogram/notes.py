from allianceauth.services.hooks import get_extension_logger

from buybackprogram.app_settings import (
    BUYBACKPROGRAM_PRICE_AGE_WARNING_LIMIT,
    BUYBACKPROGRAM_PRICE_SOURCE_NAME,
)

logger = get_extension_logger(__name__)


def note_missing_jita_buy(buy_price, name):
    if buy_price == 0:
        note = {
            "icon": "fa-question",
            "color": "red",
            "message": "%s has no buy orders in %s"
            % (name, BUYBACKPROGRAM_PRICE_SOURCE_NAME),
        }
        return note
    else:
        return False


def note_price_dencity_tax(name, price_dencity, price_dencity_tax):
    if price_dencity_tax:
        note = {
            "icon": "fa-weight-hanging",
            "color": "orange",
            "message": "%s has price density of %s isk/m³, %s %s low price dencity tax applied"
            % (name, round(price_dencity, 2), price_dencity_tax, "%"),
        }

        return note
    else:
        return False


def note_item_disallowed(item_disallowed, name):
    if item_disallowed:
        note = {
            "icon": "fa-hand-paper",
            "color": "red",
            "message": "%s is disallowed in this program" % name,
        }
        return note
    else:
        return False


def note_unpublished_item(item_type):
    if not item_type.published:
        note = {
            "icon": "fa-hand-paper",
            "color": "red",
            "message": "%s is not a published item. It is either an expired item or a copy paste of an item that should not exists ingame."
            % item_type.name,
        }
    if not item_type.market_group:
        note = {
            "icon": "fa-hand-paper",
            "color": "red",
            "message": "%s has no market information. Most likely a mission item or a special commondite item that can't be valued by market."
            % item_type.name,
        }
    return note


def note_missing_typematerials(type_materials, name):
    if type_materials.count() == 0:
        logger.error(
            "TypeMaterials not found for %s. Did you forget to run buybackprogram_load_data?"
            % name
        )

        note = {
            "icon": "fa-exclamation-triangle",
            "color": "red",
            "message": "Refined price valuation is used in this program but TypeMaterials for %s are missing from the database."
            % name,
        }
        return note
    else:
        return False


def note_item_specific_tax(name, item_tax):
    if item_tax:
        if item_tax > 0:
            note = {
                "icon": "fa-percentage",
                "color": "orange",
                "message": "%s has an additional %s %s item specific tax applied on it"
                % (name, item_tax, "%"),
            }
            return note
        else:
            note = {
                "icon": "fa-percentage",
                "color": "green",
                "message": "%s has an decreased %s %s item specific tax applied on it"
                % (name, item_tax, "%"),
            }
        return note
    else:
        return False


def note_no_price_data(name):
    note = {
        "icon": "fa-question",
        "color": "red",
        "message": "%s has no price data" % name,
    }
    return note


def note_refined_price_used(name):
    note = {
        "icon": "fa-industry",
        "color": "#5858df",
        "message": "Best price: Using refined price for %s" % name,
    }

    return note


def note_compressed_price_used(name):
    note = {
        "icon": "fa-file-archive",
        "color": "#5858df",
        "message": "Best price: Using compressed price for %s" % name,
    }
    return note


def note_npc_price(name):
    note = {
        "icon": "fa-robot",
        "color": "#5858df",
        "message": "Using NPC buy price for %s instead of %s buy prices"
        % (name, BUYBACKPROGRAM_PRICE_SOURCE_NAME),
    }
    return note


def note_raw_price_used(name):
    note = {
        "icon": "fa-icicles",
        "color": "#5858df",
        "message": "Best price: Using raw price for %s" % name,
    }
    return note


def note_missing_npc_price(name):
    note = {
        "icon": "fa-question",
        "color": "red",
        "message": "%s is missing price on database. Run `buybackprogram_load_prices` to fix."
        % (name),
    }

    return note


def note_price_outdated(updated, name):
    note = {
        "icon": "fa-history",
        "color": "red",
        "message": "Price data for %s has not been updated for more than %s hours"
        % (name, BUYBACKPROGRAM_PRICE_AGE_WARNING_LIMIT),
    }
    return note


def note_missing_from_contract(name):
    note = {
        "icon": "fa-question",
        "color": "red",
        "message": "%s is missing from the created contract" % (name),
    }

    return note


def note_missing_from_tracking(name):
    note = {
        "icon": "fa-question",
        "color": "red",
        "message": "%s is missing from the original calculation" % (name),
    }

    return note


def note_quantity_missing_from_contract(name):
    note = {
        "icon": "fa-calculator",
        "color": "red",
        "message": "Calculated item quantity for %s does not match with contract"
        % (name),
    }

    return note


def note_quantity_missing_from_tracking(name):
    note = {
        "icon": "fa-calculator",
        "color": "red",
        "message": "Calculated item quantity for %s does not match with tracking"
        % (name),
    }

    return note
