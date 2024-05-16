from django import template

register = template.Library()


@register.filter
def BsTabColorClass(color):
    if color == "red":
        return "bg-danger"
    elif color == "orange":
        return "bg-warning"
    elif color == "green":
        return "bg-success"
    else:
        return "bg-primary"
