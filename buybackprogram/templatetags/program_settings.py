from django import template

from buybackprogram.app_settings import BUYBACKPROGRAM_PRICE_SOURCE_NAME
from buybackprogram.models import ProgramItem

register = template.Library()


def setting_icons(option, program):
    restriction_groups = [v.name for v in program.restricted_to_group.all()]
    restriction_states = [v.name for v in program.restricted_to_state.all()]

    icons = {
        "all_items": {
            "icon": "fa-globe-europe",
            "color": False,
            "message": "This program accepts all types of items.",
        },
        "fuel_cost": {
            "icon": "fa-truck",
            "color": False,
            "message": "Items sold via this program have an added freight cost of %s ISK per m³"
            % program.hauling_fuel_cost,
        },
        "price_dencity_modifier": {
            "icon": "fa-compress-arrows-alt",
            "color": False,
            "message": "Items with price density below {} isk/m³ will have an additional {} % tax on them.".format(
                program.price_dencity_treshold, program.price_dencity_tax
            ),
        },
        "compressed": {
            "icon": "fa-file-archive",
            "color": False,
            "message": "Compressed price is taken into account when calculating values for ores.",
        },
        "refined": {
            "icon": "fa-industry",
            "color": False,
            "message": (
                "Refined price is taken into account when calculating values for ores at refining rate of %s%s."
                % (program.refining_rate, "%")
            ),
        },
        "raw_ore": {
            "icon": "fa-icicles",
            "color": False,
            "message": "Raw price is taken into account when calculating values for ores.",
        },
        "npc_price": {
            "icon": "fa-robot",
            "color": False,
            "message": "Some items are using NPC prices from NPC buy orders instead of %s prices."
            % (BUYBACKPROGRAM_PRICE_SOURCE_NAME),
        },
        "unpacked": {
            "icon": "fa-box-open",
            "color": False,
            "message": "Unpacked items are accepted in this program.",
        },
        "special_items": {
            "icon": "fa-search-dollar",
            "color": False,
            "message": "This program has individual items with adjusted taxes or items that are not allowed in the program.",
        },
        "restricted_to_group": {
            "icon": "fa-user",
            "color": False,
            "message": "Only users in the following groups can access this program: %s"
            % ", ".join(restriction_groups),
        },
        "restricted_to_state": {
            "icon": "fa-users",
            "color": False,
            "message": "Only users in the following states can access this program: %s"
            % ", ".join(restriction_states),
        },
        "buy_value_buy": {
            "icon": "fa-arrow-down",
            "color": False,
            "message": "Prices are based on %s %s prices"
            % (BUYBACKPROGRAM_PRICE_SOURCE_NAME, program.price_type),
        },
        "buy_value_sell": {
            "icon": "fa-arrow-up",
            "color": False,
            "message": "Prices are based on %s %s prices"
            % (BUYBACKPROGRAM_PRICE_SOURCE_NAME, program.price_type),
        },
        "buy_value_split": {
            "icon": "fa-expand-alt",
            "color": False,
            "message": "Prices are based on %s %s prices"
            % (BUYBACKPROGRAM_PRICE_SOURCE_NAME, program.price_type),
        },
    }

    return icons[option]


@register.filter
def program_setting(program):
    settings = []

    program_items = ProgramItem.objects.filter(program=program)

    if program.allow_all_items:
        setting = setting_icons("all_items", program)

        settings.append(setting)

    if program.hauling_fuel_cost:
        setting = setting_icons("fuel_cost", program)
        settings.append(setting)

    if program.price_dencity_modifier:
        setting = setting_icons("price_dencity_modifier", program)

        settings.append(setting)

    if program.use_compressed_value:
        setting = setting_icons("compressed", program)

        settings.append(setting)

    if program.use_refined_value:
        setting = setting_icons("refined", program)

        settings.append(setting)

    if (
        program.blue_loot_npc_price
        or program.red_loot_npc_price
        or program.ope_npc_price
        or program.bonds_npc_price
    ):
        setting = setting_icons("npc_price", program)

        settings.append(setting)

    if program.use_raw_ore_value:
        setting = setting_icons("raw_ore", program)

        settings.append(setting)

    if program.allow_unpacked_items:
        setting = setting_icons("unpacked", program)

        settings.append(setting)

    if program_items:
        setting = setting_icons("special_items", program)

        settings.append(setting)

    if program.restricted_to_group.all():
        setting = setting_icons("restricted_to_group", program)

        settings.append(setting)

    if program.restricted_to_state.all():
        setting = setting_icons("restricted_to_state", program)

        settings.append(setting)

    if program.price_type == "Buy":
        setting = setting_icons("buy_value_buy", program)

        settings.append(setting)

    if program.price_type == "Sell":
        setting = setting_icons("buy_value_sell", program)

        settings.append(setting)

    if program.price_type == "Split":
        setting = setting_icons("buy_value_split", program)

        settings.append(setting)

    return settings
