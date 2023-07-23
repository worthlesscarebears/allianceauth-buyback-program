"""Delete contract duplicates."""

from django.db import migrations
from collections import Counter
import logging
from typing import Set

logger = logging.getLogger(__name__)


def forwards(apps, schema_editor):
    Contract = apps.get_model("buybackprogram", "Contract")
    duplicate_ids = _identify_duplicates(Contract)
    logger.debug("Found %d duplicate contract IDs", len(duplicate_ids))
    if not duplicate_ids:
        logger.info("No duplicate contracts to delete.")
        return
    for contract_id in duplicate_ids:
        _cleanup_contract_id(Contract, contract_id)

    print(f"Cleaned up approx. {len(duplicate_ids)} duplicate contracts.", end="")
    if remaining_duplicates := _identify_duplicates(Contract):
        logger.error(
            "Failed to clean up all duplicate contracts. "
            f"These duplicate contract IDs remain: {remaining_duplicates}"
        )
        print("ERROR: Failed to cleanup all duplicate contracts. Aborting.")
        exit(1)


def _identify_duplicates(Contract) -> Set[int]:
    ids = list(Contract.objects.values_list("contract_id", flat=True))
    ids_counted = Counter(ids)
    return {id for id, count in ids_counted.items() if count > 1}


def _cleanup_contract_id(Contract, contract_id):
    """Cleanup contracts with the same contract ID.

    We try to find one good contract to keep and then delete the others.
    """
    duplicates = Contract.objects.filter(contract_id=contract_id).order_by("id")
    logger.debug(
        "Trying to cleanup %d contracts with ID %d", duplicates.count(), contract_id
    )
    contracts_with_tracking = {"tracking__isnull": False, "no_tracking": False}
    contracts_without_tracking = {"tracking__isnull": True, "no_tracking": True}
    contracts_with_tracking_2 = {"tracking__isnull": True, "no_tracking": False}
    contracts_without_tracking_2 = {"tracking__isnull": False, "no_tracking": True}
    if duplicates.filter(**contracts_with_tracking).count() > 0:
        _reduce_contracts(duplicates, contracts_with_tracking)
    elif duplicates.filter(**contracts_without_tracking).count() > 0:
        _reduce_contracts(duplicates, contracts_without_tracking)
    elif duplicates.filter(**contracts_with_tracking_2).count() > 0:
        _reduce_contracts(duplicates, contracts_with_tracking_2)
    elif duplicates.filter(**contracts_without_tracking_2).count() > 0:
        _reduce_contracts(duplicates, contracts_without_tracking_2)


def _reduce_contracts(duplicates, params: dict):
    """Delete all contracts from duplicates except one chosen as primary."""
    primary_contract = duplicates.filter(**params).last()
    count, _ = duplicates.exclude(pk=primary_contract.pk).delete()
    if count > 0:
        logger.info(
            "Deleted %d duplicates for contract ID %d",
            count,
            primary_contract.contract_id,
        )
        logger.debug("Contract reduction success with params: %s", params)


class Migration(migrations.Migration):
    dependencies = [
        ("buybackprogram", "0010_contract_no_tracking_alter_tracking_tracking_number"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
