import json
from datetime import datetime

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.services.hooks import get_extension_logger

from buybackprogram.app_settings import BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS
from buybackprogram.notes import (
    note_missing_from_contract,
    note_missing_from_tracking,
    note_quantity_missing_from_contract,
    note_quantity_missing_from_tracking,
)

from ..models import (
    Contract,
    ContractItem,
    ContractNotification,
    Tracking,
    TrackingItem,
)

logger = get_extension_logger(__name__)


@login_required
@permission_required("buybackprogram.basic_access")
def my_stats(request):
    # List for valid contracts to be displayed
    valid_contracts = []

    # Tracker values
    values = {
        "outstanding": 0,
        "finished": 0,
        "outstanding_count": 0,
        "finished_count": 0,
    }

    # Request user owned characters
    characters = CharacterOwnership.objects.filter(user=request.user).values_list(
        "character__character_id", flat=True
    )

    # Get all tracking objects that have a linked contract to them for the user
    tracking_numbers = (
        Tracking.objects.filter(contract__isnull=False)
        .filter(contract__issuer_id__in=characters)
        .filter(contract__date_expired__gte=timezone.now())
        .prefetch_related("contract")
    )

    # Loop tracking objects to see if we have any contracts
    for tracking in tracking_numbers:
        # Get notes for this contract
        tracking.contract.notes = ContractNotification.objects.filter(
            contract=tracking.contract
        )

        # Walk the tracker values for contracts
        if tracking.contract.status == "outstanding":
            values["outstanding"] += tracking.contract.price
            values["outstanding_count"] += 1
        if tracking.contract.status == "finished":
            values["finished"] += tracking.contract.price
            values["finished_count"] += 1

        # Get the name for the issuer
        tracking.contract.issuer_name = EveEntity.objects.resolve_name(
            tracking.contract.issuer_id
        )

        # Get the name for the assignee
        tracking.contract.assignee_name = EveEntity.objects.resolve_name(
            tracking.contract.assignee_id
        )

        # Add contract to the valid contract list
        valid_contracts.append(tracking)

    context = {
        "contracts": valid_contracts,
        "values": values,
        "mine": True,
    }

    return render(request, "buybackprogram/stats.html", context)


@login_required
@permission_required("buybackprogram.basic_access")
def leaderboard(request, program_pk):
    # Tracker values
    monthstats = {
        "users": {},  # monthly stats per user
        "userinfo": {},  # profile information per user
        "months": None,  # all months
    }
    # Get all tracking objects that have a linked contract to them for the user
    tracking_numbers = (
        Tracking.objects.filter(program_id=program_pk)
        .filter(contract__isnull=False)
        .prefetch_related("contract")
    )

    # Loop all tracking objects
    for tracking in tracking_numbers:
        # For finished contracts, gather more data
        if tracking.contract.status == "finished":
            month = datetime.strftime(tracking.contract.date_issued, "%Y-%m:%B %Y")
            if month not in monthstats["users"]:
                monthstats["users"][month] = {}  # User data per month

            # Collect ISK data per user
            user = tracking.contract.issuer_id
            if user not in monthstats["users"][month]:
                monthstats["users"][month][user] = [
                    0,  # contract total
                    0,  # donation total
                ]
            monthstats["users"][month][user][0] += tracking.contract.price
            monthstats["users"][month][user][1] += tracking.donation

            if user not in monthstats["userinfo"]:
                monthstats["userinfo"][user] = {
                    "name": EveEntity.objects.resolve_name(user),
                    "pic": f"https://images.evetech.net/characters/{user}/portrait?size=32",
                }

    monthstats["months"] = sorted(list(monthstats["users"].keys()))
    context = {
        "stats": json.dumps(monthstats),
    }

    return render(request, "buybackprogram/leaderboards.html", context)


@login_required
@permission_required("buybackprogram.manage_programs")
def program_performance(request, program_pk):
    firstbench = datetime.now()
    lastbench = datetime.now()
    # Tracker values
    monthstats = {
        "status": {},
        "overall": {"all": {}},
        "items": {},
        "categories": {},
        "donations": {"all": {}},
    }
    allmonths = set()

    # Category to Item mapping
    category2items = {}

    # Export data
    dumpdata = [
        [
            "Contract ID",
            "Date Issued",
            "Date Finished",
            "User ID",
            "Total ISK",
            "Object Cateogry",
            "Object ID",
            "Object Name",
            "Object Quant",
            "Object ISK",
        ]
    ]

    # Get all tracking objects that have a linked contract to them for the user
    tracking_numbers = (
        Tracking.objects.filter(program_id=program_pk)
        .filter(contract__isnull=False)
        .prefetch_related("contract")
    )

    logger.debug(
        "Performance bench: %.2f" % (datetime.now() - lastbench).total_seconds()
    )
    lastbench = datetime.now()
    # Loop all tracking objects
    for tracking in tracking_numbers:
        month = datetime.strftime(tracking.contract.date_issued, "%Y-%m") + "-15"
        allmonths.add(month)

        if month not in monthstats["status"]:
            monthstats["status"][
                month
            ] = {}  # status of all contracts issued during a given month

        # Gather stats on all contracts' statuses
        if tracking.contract.status not in monthstats["status"][month]:
            monthstats["status"][month][tracking.contract.status] = 0
        monthstats["status"][month][tracking.contract.status] += 1

        # For finished contracts, gather more data
        if tracking.contract.status == "finished":
            # "overall": {"all": {"isk": {}, "q": {}, }
            if month not in monthstats["overall"]["all"]:
                monthstats["overall"]["all"][month] = [0, 0]  # isk, q
                monthstats["donations"]["all"][month] = [0, 0]  # isk, q

            monthstats["overall"]["all"][month][0] += tracking.contract.price
            monthstats["overall"]["all"][month][1] += 1

            monthstats["donations"]["all"][month][0] += tracking.donation
            if tracking.donation > 0:
                monthstats["donations"]["all"][month][1] += 1

            logger.debug(
                "Performance loop bench: %.2f"
                % (datetime.now() - lastbench).total_seconds()
            )
            lastbench = datetime.now()
            # Collect ISK data per items
            tracking_items = TrackingItem.objects.filter(tracking=tracking)
            for item in tracking_items:
                if item.eve_type.name not in monthstats["items"]:
                    monthstats["items"][item.eve_type.name] = {}
                if month not in monthstats["items"][item.eve_type.name]:
                    monthstats["items"][item.eve_type.name][month] = [0, 0]
                monthstats["items"][item.eve_type.name][month][0] += item.buy_value
                monthstats["items"][item.eve_type.name][month][1] += item.quantity
                # cache[tracking.contract.issuer_id] = EveEntity.objects.resolve_name(tracking.contract.issuer_id)

                # Collect item category data
                catid = item.eve_type.eve_group.name
                if catid not in category2items:
                    category2items[catid] = set()
                category2items[catid].add(item.eve_type.name)

                if catid not in monthstats["categories"]:
                    monthstats["categories"][catid] = {}
                if month not in monthstats["categories"][catid]:
                    monthstats["categories"][catid][month] = [0, 0]
                monthstats["categories"][catid][month][0] += item.buy_value
                monthstats["categories"][catid][month][1] += item.quantity

                # Collect data for export
                dumpdata.append(
                    [
                        tracking.id,
                        datetime.strftime(
                            tracking.contract.date_issued, "%Y-%m-%d %H:%M:%S"
                        ),
                        datetime.strftime(
                            tracking.contract.date_completed, "%Y-%m-%d %H:%M:%S"
                        ),
                        tracking.contract.issuer_id,
                        tracking.contract.price,
                        item.eve_type.eve_group.name,
                        item.eve_type.id,
                        item.eve_type.name,
                        item.quantity,
                        item.buy_value,
                    ]
                )

    logger.debug(
        "Performance exit loop bench: %.2f"
        % (datetime.now() - lastbench).total_seconds()
    )
    lastbench = datetime.now()
    # Reformat data so that it is easier to use billboard.js
    allmonths = sorted(list(allmonths))

    scaling = {}
    hscaling = {}
    for strata in ("overall", "items", "categories", "donations"):
        scaling[strata] = []
        for yi in monthstats[strata].keys():
            scaling[strata] += [
                monthstats[strata][yi][x][0] for x in monthstats[strata][yi].keys()
            ]
        if len(scaling[strata]) == 0:
            scaling[strata] = 1
        else:
            scaling[strata] = sum(scaling[strata]) / len(scaling[strata])
        for s, h in ((1e9, "Billions"), (1e6, "Millions")):
            if scaling[strata] > s:
                scaling[strata] = s
                hscaling[strata] = h
                break
        if scaling[strata] < 1e6:
            scaling[strata] = 1
            hscaling[strata] = ""

    # Always set donations to be the same scale as overall since they are plotted together.
    scaling["donations"] = scaling["overall"]
    hscaling["donations"] = hscaling["overall"]

    for strata in ("overall", "items", "categories", "donations"):
        for yi in monthstats[strata].keys():
            y = [[yi], [yi]]
            # Overall ISK
            if strata == "overall":
                y = [["Bought"], ["Contract count"]]
            # Donation ISK
            if strata == "donations":
                y = [["Donations"], ["Donation count"]]

            for m in allmonths:
                if m not in (monthstats[strata][yi]):
                    monthstats[strata][yi][m] = [0, 0]
                y[0].append(round(monthstats[strata][yi][m][0] / scaling[strata], 3))
                y[1].append(monthstats[strata][yi][m][1])
            monthstats[strata][yi] = y
    monthstats["x"] = ["x"] + allmonths

    for cat in category2items:
        category2items[cat] = list(category2items[cat])

    # Break down of categories by last three months:
    lastthree = {}
    for yi in monthstats["categories"].keys():
        calc = monthstats["categories"][yi][0].copy()
        calc.pop(0)
        lastthree[yi] = sum(calc[-3:])

    if len(lastthree.keys()) > 10:
        th = lastthree[sorted(lastthree.keys(), key=lambda x: -lastthree[x])[10]]
        lastthree["Other"] = 0
        for k in list(lastthree.keys()):
            if k != "Other" and lastthree[k] <= th:
                lastthree["Other"] += lastthree[k]
                del lastthree[k]

        monthstats["categories"]["Other"] = None
        for k in list(monthstats["categories"].keys()):
            if k not in lastthree:
                if monthstats["categories"]["Other"] is None:
                    monthstats["categories"]["Other"] = monthstats["categories"][k]
                else:
                    monthstats["categories"]["Other"][0][1:] = [
                        sum(x)
                        for x in zip(
                            monthstats["categories"]["Other"][0][1:],
                            monthstats["categories"][k][0][1:],
                        )
                    ]
                    monthstats["categories"]["Other"][1][1:] = [
                        sum(x)
                        for x in zip(
                            monthstats["categories"]["Other"][1][1:],
                            monthstats["categories"][k][1][1:],
                        )
                    ]
                del monthstats["categories"][k]
        monthstats["categories"]["Other"][0][0] = "Other"
        monthstats["categories"]["Other"][1][0] = "Other"

    lastthree = list(lastthree.items())

    # Sanitize CSV data
    for i in range(len(dumpdata)):
        for j in range(len(dumpdata[i])):
            dumpdata[i][j] = str(dumpdata[i][j]).replace(",", " ")

    context = {
        "stats": json.dumps(monthstats),
        "lastthree": json.dumps(lastthree),
        "categories": json.dumps(category2items),
        "export": json.dumps(dumpdata),
        "hscaling": json.dumps(hscaling),
    }
    logger.debug(
        "Performance finished: %.2f" % (datetime.now() - lastbench).total_seconds()
    )
    logger.debug(
        "Performance total: %.2f" % (datetime.now() - firstbench).total_seconds()
    )

    return render(request, "buybackprogram/performance.html", context)


@login_required
@permission_required("buybackprogram.manage_programs")
def program_stats(request):
    # List for valid contracts to be displayed
    valid_contracts = []
    untracked_contracts = False

    # Tracker values
    values = {
        "outstanding": 0,
        "finished": 0,
        "outstanding_count": 0,
        "finished_count": 0,
        "untracked_count": 0,
    }

    # Request user owned characters
    characters = CharacterOwnership.objects.filter(user=request.user).values_list(
        "character__character_id", flat=True
    )

    # Request user owned corporations
    corporations = CharacterOwnership.objects.filter(user=request.user).values_list(
        "character__corporation_id", flat=True
    )

    # Get all tracking objects that have a linked contract to them for the user
    tracking_numbers = (
        Tracking.objects.filter(contract__isnull=False)
        .filter(
            Q(contract__assignee_id__in=characters)
            | Q(contract__assignee_id__in=corporations)
        )
        .filter(contract__date_expired__gte=timezone.now())
        .prefetch_related("contract")
    )

    # Loop tracking objects to see if we have any contracts
    for tracking in tracking_numbers:
        # Get notes for this contract
        tracking.contract.notes = ContractNotification.objects.filter(
            contract=tracking.contract
        )

        # Walk the tracker values for contracts
        if tracking.contract.status == "outstanding":
            values["outstanding"] += tracking.contract.price
            values["outstanding_count"] += 1
        if tracking.contract.status == "finished":
            values["finished"] += tracking.contract.price
            values["finished_count"] += 1

        # Get the name for the issuer
        tracking.contract.issuer_name = EveEntity.objects.resolve_name(
            tracking.contract.issuer_id
        )

        # Get the name for the assignee
        tracking.contract.assignee_name = EveEntity.objects.resolve_name(
            tracking.contract.assignee_id
        )

        # Add contract to the valid contract list
        valid_contracts.append(tracking)

    if BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS:
        # Get pending contracts that have no tracking assigned to them
        untracked_contracts = Contract.objects.filter(
            Q(assignee_id__in=characters) | Q(assignee_id__in=corporations)
        ).filter(no_tracking=True, status="outstanding")

        logger.debug("Got %s untracked contracts" % len(untracked_contracts))

        for contract in untracked_contracts:
            values["untracked_count"] += 1

            # Get notes for this contract
            contract.notes = ContractNotification.objects.filter(contract=contract)

            # Get the name for the issuer
            contract.issuer_name = EveEntity.objects.resolve_name(contract.issuer_id)

            # Get the name for the assignee
            contract.assignee_name = EveEntity.objects.resolve_name(
                contract.assignee_id
            )

    context = {
        "contracts": valid_contracts,
        "untracked_contracts": untracked_contracts,
        "values": values,
        "mine": True,
        "BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS": BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS,
    }

    return render(request, "buybackprogram/stats.html", context)


@login_required
@permission_required("buybackprogram.see_all_statics")
def program_stats_all(request):
    # List for valid contracts to be displayed
    valid_contracts = []

    untracked_contracts = False

    # Tracker values
    values = {
        "outstanding": 0,
        "finished": 0,
        "outstanding_count": 0,
        "finished_count": 0,
        "untracked_count": 0,
    }

    # Get all tracking objects that have a linked contract to them for the user
    tracking_numbers = (
        Tracking.objects.filter(contract__isnull=False)
        .filter(contract__date_expired__gte=timezone.now())
        .prefetch_related("contract")
    )

    # Loop tracking objects to see if we have any contracts
    for tracking in tracking_numbers:
        # Get notes for this contract
        tracking.contract.notes = ContractNotification.objects.filter(
            contract=tracking.contract
        )

        # Walk the tracker values for contracts
        if tracking.contract.status == "outstanding":
            values["outstanding"] += tracking.contract.price
            values["outstanding_count"] += 1
        if tracking.contract.status == "finished":
            values["finished"] += tracking.contract.price
            values["finished_count"] += 1

        # Get the name for the issuer
        tracking.contract.issuer_name = EveEntity.objects.resolve_name(
            tracking.contract.issuer_id
        )

        # Get the name for the assignee
        tracking.contract.assignee_name = EveEntity.objects.resolve_name(
            tracking.contract.assignee_id
        )

        valid_contracts.append(tracking)

    if BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS:
        # Get pending contracts that have no tracking assigned to them
        untracked_contracts = Contract.objects.filter(
            no_tracking=True, status="outstanding"
        )

        logger.debug("Got %s untracked contracts" % len(untracked_contracts))

        for contract in untracked_contracts:
            values["untracked_count"] += 1

            # Get notes for this contract
            contract.notes = ContractNotification.objects.filter(contract=contract)

            # Get the name for the issuer
            contract.issuer_name = EveEntity.objects.resolve_name(contract.issuer_id)

            # Get the name for the assignee
            contract.assignee_name = EveEntity.objects.resolve_name(
                contract.assignee_id
            )

    context = {
        "contracts": valid_contracts,
        "untracked_contracts": untracked_contracts,
        "values": values,
        "mine": True,
        "BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS": BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS,
    }

    return render(request, "buybackprogram/stats.html", context)


@login_required
@permission_required("buybackprogram.basic_access")
def contract_details(request, contract_title):
    contract = Contract.objects.get(title__contains=contract_title)

    # Get notes for this contract
    notes = ContractNotification.objects.filter(contract=contract)

    # Get items for this contract
    contract_items = ContractItem.objects.filter(contract=contract)

    # Get tracking object for this contract
    tracking = Tracking.objects.get(
        tracking_number=contract_title,
    )

    # Get tracked items
    tracking_items = TrackingItem.objects.filter(tracking=tracking)

    # Find the difference in the created contract and original calculation
    for tracking_item in tracking_items:
        tracking_notes = []

        item_match = False
        quantity_match = False

        for contract_item in contract_items:
            if contract_item.eve_type == tracking_item.eve_type:
                item_match = True

                if contract_item.quantity == tracking_item.quantity:
                    quantity_match = True
                    break

        tracking_item.item_match = item_match

        if not item_match:
            tracking_notes.append(note_missing_from_contract(tracking_item.eve_type))

        if item_match and not quantity_match:
            tracking_notes.append(
                note_quantity_missing_from_contract(tracking_item.eve_type)
            )

        tracking_item.notes = tracking_notes

    for contract_item in contract_items:
        contract_notes = []

        item_match = False
        quantity_match = False

        for tracking_item in tracking_items:
            if contract_item.eve_type == tracking_item.eve_type:
                item_match = True

                if contract_item.quantity == tracking_item.quantity:
                    quantity_match = True
                    break

        contract_item.item_match = item_match

        if not item_match:
            contract_notes.append(note_missing_from_tracking(contract_item.eve_type))

        if item_match and not quantity_match:
            contract_notes.append(
                note_quantity_missing_from_tracking(contract_item.eve_type)
            )

        contract_item.notes = contract_notes

    # Get the name for the issuer
    contract.issuer_name = EveEntity.objects.resolve_name(contract.issuer_id)

    # Get the name for the assignee
    contract.assignee_name = EveEntity.objects.resolve_name(contract.assignee_id)

    # Sort lists by reverse quantity order
    contract_items = sorted(contract_items, key=lambda x: -x.quantity)
    tracking_items = sorted(tracking_items, key=lambda x: -x.quantity)

    context = {
        "notes": notes,
        "contract": contract,
        "contract_items": contract_items,
        "tracking": tracking,
        "tracking_items": tracking_items,
    }

    return render(request, "buybackprogram/contract_details.html", context)
