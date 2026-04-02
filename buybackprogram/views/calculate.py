from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from eve_sde.models import ItemType

from allianceauth.services.hooks import get_extension_logger

from buybackprogram import tasks
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

logger = get_extension_logger(__name__)


@login_required
@permission_required("buybackprogram.basic_access")
def program_calculate(request, program_pk):
    program = Program.objects.filter(pk=program_pk).first()

    buyback_data = []
    additional_notes = False

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
            additional_notes = form.cleaned_data[
                "additional_notes"
            ]  # Capture additional notes

            appraisal = tasks.appraise_items(form_items)

            # Split items by rows
            for item in appraisal.items or []:
                item_accepted = True
                notes = []

                item_type = ItemType.objects.get(id=item.item_type.eid)

                # Check if we have a match from the database for the item
                if item_type:
                    item_category = item_type.group.category

                    # Check if item is a blueprint
                    if item_category.name == "Blueprint":
                        item_accepted = False
                        note = {
                            "icon": "fa-print",
                            "color": "orange",
                            "message": "%s belongs to category %s. Blueprints are not accepted."
                            % (item_type.name, item_category),
                        }
                        notes.append(note)
                else:
                    item_category = False
                    item_accepted = False
                    note = {
                        "icon": "fa-skull-crossbones",
                        "color": "red",
                        "message": "%s not found from database. It is most likely a new item still not added to database or a renamed unpacked item."
                        % item_type.name,
                    }
                    notes.append(note)

                # Get details for the item
                if item_accepted:
                    # Get item material, compression and price information
                    item_prices = get_item_prices(
                        item_type,
                        item,
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
                    item_values = item_missing(item_type.name, item.amount)

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

    # Get item values after other expenses and the total value for the contract
    contract_price_data = get_item_buy_value(buyback_data, program, form_donation)

    logger.debug(
        "Calculated contract net total is %s"
        % contract_price_data["contract_net_total"]
    )

    # Get item values after other expenses and the total value for the contract
    tracking = get_tracking_number(
        request.user,
        program,
        form_donation,
        buyback_data,
        contract_price_data,
        additional_notes,
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
