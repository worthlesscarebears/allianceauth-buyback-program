from django import template

register = template.Library()


@register.filter
def price(value):
    if value:
        return value + " ISK"
    else:
        return "-"


@register.filter
def tax(value):
    if value:
        return str(value) + " %"
    else:
        return "-"


@register.filter
def comparison(value):
    if float(value) > 0:
        return "+ " + str(value) + " %"
    else:
        return str(value) + " %"


@register.filter
def custom_number_format(value, decimal_places=2):
    try:
        # Convert the value to a float
        value = float(value)
        # Format with a space as the thousand separator and a period as the decimal separator
        formatted_number = f"{value:,.{decimal_places}f}".replace(",", " ").replace(
            ".", "."
        )
        return formatted_number
    except (ValueError, TypeError):
        return ""
