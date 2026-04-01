from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils.html import format_html
from eve_sde.models import ItemMarketGroup, ItemType

from allianceauth.services.hooks import get_extension_logger

from buybackprogram.forms import ProgramItemForm, ProgramMarketGroupForm
from buybackprogram.models import Program, ProgramItem
from buybackprogram.utils import messages_plus

logger = get_extension_logger(__name__)


@login_required
@permission_required("buybackprogram.basic_access")
def program_special_taxes(request, program_pk):
    program = Program.objects.get(pk=program_pk)
    program_items = ProgramItem.objects.filter(program=program)

    context = {
        "program": program,
        "program_items": program_items,
    }

    return render(request, "buybackprogram/program_special_taxes.html", context)


@login_required
@permission_required("buybackprogram.manage_programs")
def program_edit_item(request, program_pk):
    program = Program.objects.get(pk=program_pk)

    program_items = ProgramItem.objects.filter(program=program)

    if request.method != "POST":
        form = ProgramItemForm()
    else:
        form = ProgramItemForm(
            request.POST,
            value=int(request.POST["item_type"]),
        )

        if form.is_valid():
            item_tax = form.cleaned_data["item_tax"]
            disallow_item = form.cleaned_data["disallow_item"]

            item_type = form.cleaned_data["item_type"]

            ProgramItem.objects.update_or_create(
                item_type=item_type,
                program=program,
                defaults={
                    "item_tax": item_tax,
                    "disallow_item": disallow_item,
                },
            )

            if disallow_item:
                messages_plus.warning(
                    request,
                    format_html(
                        "Disallowed <strong>{}</strong> in program",
                        item_type.name,
                    ),
                )

            else:
                messages_plus.success(
                    request,
                    format_html(
                        "Adjusted <strong>{}</strong> tax in program with <strong>{}</strong> %, tax is now set at {} %",
                        item_type.name,
                        item_tax,
                        program.tax + item_tax,
                    ),
                )

            return HttpResponseRedirect(request.path_info)

    context = {
        "program": program,
        "program_items": program_items,
        "form": form,
    }

    return render(request, "buybackprogram/program_edit_item.html", context)


@login_required
@permission_required("buybackprogram.manage_programs")
def program_edit_marketgroup(request, program_pk):
    program = Program.objects.get(pk=program_pk)

    program_items = ProgramItem.objects.filter(program=program)

    if request.method != "POST":
        form = ProgramMarketGroupForm()
    else:
        form = ProgramMarketGroupForm(
            request.POST,
            value=int(request.POST["marketgroup"]),
        )

        if form.is_valid():
            item_types = []
            item_count = 0

            item_tax = form.cleaned_data["item_tax"]
            disallow_item = form.cleaned_data["disallow_item"]

            marketgroups = ItemMarketGroup.objects.get(
                pk=form.cleaned_data["marketgroup"].id
            )

            item_type = ItemType.objects.filter(
                market_group=form.cleaned_data["marketgroup"]
            )

            item_types.append(item_type)

            for m in marketgroups.market_group_children.all():
                item_type = ItemType.objects.filter(market_group=m)

                item_types.append(item_type)

                for m2 in m.market_group_children.all():
                    item_type = ItemType.objects.filter(market_group=m2)

                    item_types.append(item_type)

            for sub_types in item_types:
                for item in sub_types:
                    logger.debug("Adjusting tax for %s" % item)

                    ProgramItem.objects.update_or_create(
                        item_type=item,
                        program=program,
                        defaults={
                            "item_tax": item_tax,
                            "disallow_item": disallow_item,
                        },
                    )

                    item_count += 1

            if disallow_item:
                messages_plus.warning(
                    request,
                    format_html(
                        "Disallowed <strong>{}</strong> items from market group {} in program",
                        item_count,
                        form.cleaned_data["marketgroup"],
                    ),
                )
            else:
                messages_plus.success(
                    request,
                    format_html(
                        "Added <strong>{}</strong> items from market group {} to program with <strong>{}</strong> % tax",
                        item_count,
                        form.cleaned_data["marketgroup"],
                        item_tax,
                    ),
                )

            return HttpResponseRedirect(request.path_info)

    context = {
        "program": program,
        "program_items": program_items,
        "form": form,
    }

    return render(request, "buybackprogram/program_edit_marketgroup.html", context)


@login_required
@permission_required("buybackprogram.manage_programs")
def program_item_remove(request, item_pk, program_pk):
    program_item = ProgramItem.objects.get(item_type=item_pk, program=program_pk)

    name = program_item.item_type

    program_item.delete()

    messages_plus.warning(
        request,
        format_html(
            "Deleted <strong>{}</strong> from program",
            name,
        ),
    )

    return redirect("buybackprogram:program_special_taxes", program_pk)


@login_required
@permission_required("buybackprogram.manage_programs")
def program_item_remove_all(request, program_pk):
    program_item = ProgramItem.objects.filter(program=program_pk)

    program_item.delete()

    messages_plus.warning(
        request,
        format_html(
            "Deleted all special taxation items from program",
        ),
    )

    return redirect("buybackprogram:program_special_taxes", program_pk)
