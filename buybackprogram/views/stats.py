import json
import os
from datetime import datetime

from django.conf import settings
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
    Program,
    Tracking,
    TrackingItem,
)

logger = get_extension_logger(__name__)


@login_required
@permission_required("buybackprogram.basic_access")
def my_stats(request):
    # List for valid contracts to be displayed
    valid_contracts = []
    contract_notes = []

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
        contract_notes.append(tracking.contract.notes)

    context = {
        "contracts": valid_contracts,
        "contract_notes": contract_notes,
        "values": values,
        "mine": True,
    }

    return render(request, "buybackprogram/stats.html", context)


@login_required
@permission_required("buybackprogram.basic_access")
def leaderboard(request, program_pk):
    program = Program.objects.get(pk=program_pk)

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
        "program": program,
    }

    return render(request, "buybackprogram/leaderboards.html", context)


@login_required
@permission_required("buybackprogram.manage_programs")
def program_performance(request, program_pk):
    static_path = os.path.join(settings.STATIC_ROOT, "buybackprogram/performance_data")
    filename = f"program_performance_{program_pk}.json"
    file_path = os.path.join(static_path, filename)

    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            context = json.load(file)

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
