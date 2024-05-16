from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from . import urls


class BuybackProgramMenuItem(MenuItemHook):
    """This class ensures only authorized users will see the menu entry"""

    def __init__(self):
        # setup menu entry for sidebar
        MenuItemHook.__init__(
            self,
            _("Buyback Program"),
            "fa-solid fa-store",
            "buybackprogram:index",
            navactive=["buybackprogram:"],
        )

    def render(self, request):
        if request.user.has_perm("buybackprogram.basic_access"):
            return MenuItemHook.render(self, request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return BuybackProgramMenuItem()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "buybackprogram", r"^buybackprogram/")
