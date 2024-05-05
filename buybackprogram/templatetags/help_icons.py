from django import template

from buybackprogram.app_settings import BUYBACKPROGRAM_PRICE_INSTANT_PRICES

register = template.Library()


@register.simple_tag
def help(option):
    if not BUYBACKPROGRAM_PRICE_INSTANT_PRICES:
        source = "average top 5 %"
    else:
        source = "instant"

    icons = {
        "name": "The type name for this item",
        "quantity": "Quantity of items to be sold",
        "price_source": "The buy and sell prices for this item at the selected trade hub",
        "base_price": "The bace price we use for our calculations before any taxes or expenses",
        "taxes": "Our taxes applied over the base price for this item",
        "price": "Our net price that we will pay for one unit of this item",
        "total": "Our net price for all of the units sold for this item",
        "notes": "Any notes for this item row will be displayed in here",
        "price_type": "Prices are based on %s prices" % source,
    }

    return icons[option]
