from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.utils.html import format_html
from django.utils.translation import gettext_lazy
from eveuniverse.models import EveType

from allianceauth.services.hooks import get_extension_logger

from buybackprogram.app_settings import BUYBACKPROGRAM_PRICE_SOURCE_NAME
from buybackprogram.forms import CalculatorForm
from buybackprogram.helpers import (
    get_item_buy_value,
    get_item_prices,
    get_item_values,
    get_tracking_number,
    item_missing,
)
from buybackprogram.models import Program
from buybackprogram.utils import messages_plus

logger = get_extension_logger(__name__)


@login_required
@permission_required("buybackprogram.basic_access")
def program_calculate(request, program_pk):
    program = Program.objects.filter(pk=program_pk).first()

    buyback_data = []

    form_donation = False

    if program is None:
        return redirect("buybackprogram:index")

    if request.method != "POST":
        form = CalculatorForm()

    else:
        form = CalculatorForm(request.POST)

        if form.is_valid():
            form_items = form.cleaned_data["items"]
            form_donation = form.cleaned_data["donation"]

            # If we have an ingame copy paste
            if "\t" in form_items:
                # Split items by rows
                for item in form_items.split("\n"):
                    item_accepted = True
                    notes = []

                    # get item name and quantity
                    parts = item.split("\t")

                    # Get item name from the first part
                    name = parts[0].replace("*", "")

                    item_type = EveType.objects.filter(name=name).first()

                    # Check if we have a match from the database for the item
                    if item_type:
                        item_category = item_type.eve_group.eve_category

                        # Check if item is a blueprint
                        if item_category.name == "Blueprint":
                            item_accepted = False
                            note = {
                                "icon": "fa-print",
                                "color": "orange",
                                "message": "%s belongs to category %s. Blueprints are not accepted."
                                % (name, item_category),
                            }
                            notes.append(note)
                    else:
                        item_category = False
                        item_accepted = False
                        note = {
                            "icon": "fa-skull-crossbones",
                            "color": "red",
                            "message": "%s not found from database. It is most likely a new item still not added to database or a renamed unpacked item."
                            % name,
                        }
                        notes.append(note)

                    # Anything else
                    if len(parts) == 1:
                        if program.allow_unpacked_items:
                            quantity = 1

                        else:
                            quantity = 1
                            item_accepted = False

                            note = {
                                "icon": "fa-box-open",
                                "color": "red",
                                "message": "Unpacked items are now allowed at this location. Repack %s to get a price for it"
                                % name,
                            }

                            notes.append(note)

                    # Icons view
                    elif len(parts) == 2:
                        # Get item quantity.
                        if not parts[1] == "\r":
                            # Get quantities and format the different localization imputs
                            quantity = int("".join(filter(str.isdigit, parts[1])))

                        elif program.allow_unpacked_items:
                            quantity = 1

                        else:
                            quantity = 1
                            item_accepted = False

                            note = {
                                "icon": "fa-box-open",
                                "color": "red",
                                "message": "Unpacked items are now allowed at this location. Repack %s to get a price for it"
                                % name,
                            }

                            notes.append(note)

                    # Detail view
                    else:
                        # Get item quantity.
                        if parts[1]:
                            # Get quantities and format the different localization imputs
                            quantity = int("".join(filter(str.isdigit, parts[1])))

                        elif program.allow_unpacked_items:
                            quantity = 1

                        else:
                            quantity = 1
                            item_accepted = False

                            note = {
                                "icon": "fa-box-open",
                                "color": "red",
                                "message": "Unpacked items are now allowed at this location. Repack %s to get a price for it"
                                % name,
                            }

                            notes.append(note)

                    # Get details for the item
                    if item_accepted:
                        # Get item material, compression and price information
                        item_prices = get_item_prices(
                            item_type,
                            name,
                            quantity,
                            program,
                        )

                        # Get item values with taxes
                        item_values = get_item_values(item_type, item_prices, program)

                        # Final form of the built buyback item that will be pushed to the item array
                        buyback_item = {
                            "type_data": item_type,
                            "item_prices": item_prices,
                            "item_values": item_values,
                        }

                        # Append buyback item data to the total array
                        buyback_data.append(buyback_item)

                    # If items are not accepted for some reason
                    else:
                        item_values = item_missing(name, quantity)

                        buyback_item = {
                            "type_data": item_type,
                            "item_prices": {
                                "notes": notes,
                                "raw_prices": False,
                                "material_prices": False,
                                "compression_prices": False,
                                "npc_prices": False,
                            },
                            "item_values": item_values,
                        }

                        buyback_data.append(buyback_item)

            else:
                messages_plus.error(
                    request,
                    format_html(
                        gettext_lazy(
                            "Buyback calculator only accepts copy pasted item formats from ingame. To calculate a price copy the items from your inventory."
                        )
                    ),
                )

                logger.debug("TODO: add tasks to process plain text imputs here.")

    # Get item values after other expenses and the total value for the contract
    contract_price_data = get_item_buy_value(buyback_data, program, form_donation)

    logger.debug(
        "Calculated contract net total is %s"
        % contract_price_data["contract_net_total"]
    )

    # Get item values after other expenses and the total value for the contract
    tracking = get_tracking_number(
        request.user, program, form_donation, buyback_data, contract_price_data
    )

    context = {
        "program": program,
        "form": form,
        "donation": form_donation,
        "buyback_data": buyback_data,
        "contract_price_data": contract_price_data,
        "tracking_number": tracking.tracking_number,
        "price_source": BUYBACKPROGRAM_PRICE_SOURCE_NAME,
    }

    return render(request, "buybackprogram/program_calculate.html", context)
