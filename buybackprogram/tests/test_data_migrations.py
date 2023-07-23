import unittest
from importlib import import_module

from buybackprogram.models import Contract
from django.apps import apps
from django.db import connection
from django.test import TestCase
from app_utils.testing import set_test_logger
from .testdata.factories import ContractFactory, ProgramFactory, TrackingFactory
from .testdata.load_eveuniverse import load_eveuniverse

data_migration = import_module(
    "buybackprogram.migrations.0011_delete_duplicated_contracts"
)

set_test_logger(data_migration.logger.name, __file__)


def all_contracts() -> set:
    return set(Contract.objects.all())


@unittest.skip  # Test no longer works after migration 0012 is applied
class TestDataMigration(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()
        cls.program = ProgramFactory()

    def test_should_do_nothing_when_no_duplicates(self):
        # given
        contract = ContractFactory()
        # when
        data_migration.forwards(apps, connection.schema_editor())
        # then
        self.assertSetEqual(all_contracts(), {contract})

    def test_should_cleanup_variant_1(self):
        # given
        contract_1 = ContractFactory(contract_id=1)
        contract_2a = ContractFactory(contract_id=2, no_tracking=False)
        contract_2b = ContractFactory(contract_id=2, no_tracking=False)
        ContractFactory(contract_id=2, no_tracking=False)
        ContractFactory(contract_id=2, no_tracking=True)
        TrackingFactory(program=self.program, contract=contract_2a)
        TrackingFactory(program=self.program, contract=contract_2b)
        # when
        data_migration.forwards(apps, connection.schema_editor())
        # then
        self.assertSetEqual(all_contracts(), {contract_1, contract_2b})

    def test_should_cleanup_variant_2(self):
        # given
        contract_1 = ContractFactory(contract_id=1)
        ContractFactory(contract_id=2, no_tracking=True)
        contract_2b = ContractFactory(contract_id=2, no_tracking=True)
        contract_2c = ContractFactory(contract_id=2, no_tracking=True)
        ContractFactory(contract_id=2, no_tracking=False)
        TrackingFactory(program=self.program, contract=contract_2c)
        # when
        data_migration.forwards(apps, connection.schema_editor())
        # then
        self.assertSetEqual(all_contracts(), {contract_1, contract_2b})

    def test_should_cleanup_variant_3(self):
        # given
        contract_1 = ContractFactory(contract_id=1)
        ContractFactory(contract_id=2, no_tracking=False)
        contract_2b = ContractFactory(contract_id=2, no_tracking=False)
        contract_2c = ContractFactory(contract_id=2, no_tracking=True)
        TrackingFactory(program=self.program, contract=contract_2c)
        # when
        data_migration.forwards(apps, connection.schema_editor())
        # then
        self.assertSetEqual(all_contracts(), {contract_1, contract_2b})

    def test_should_cleanup_variant_4(self):
        # given
        contract_1 = ContractFactory(contract_id=1)
        contract_2a = ContractFactory(contract_id=2, no_tracking=True)
        contract_2b = ContractFactory(contract_id=2, no_tracking=True)
        TrackingFactory(program=self.program, contract=contract_2a)
        TrackingFactory(program=self.program, contract=contract_2b)
        # when
        data_migration.forwards(apps, connection.schema_editor())
        # then
        self.assertSetEqual(all_contracts(), {contract_1, contract_2b})
