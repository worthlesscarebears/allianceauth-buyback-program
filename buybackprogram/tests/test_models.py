from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from eveuniverse.models import EveType

from app_utils.esi import EsiStatus
from app_utils.esi_testing import EsiClientStub, EsiEndpoint
from app_utils.testing import NoSocketsTestCase

from buybackprogram.models import Contract

from .testdata.factories import (
    ContractFactory,
    ContractItemFactory,
    ContractNotificationFactory,
    EsiContractFactory,
    EsiContractItemFactory,
    EveEntityCharacterFactory,
    ItemPricesFactory,
    LocationFactory,
    OwnerFactory,
    ProgramFactory,
    ProgramItemFactory,
    TrackingFactory,
    TrackingItemFactory,
    UserProjectManagerFactory,
    UserSettingsFactory,
)
from .testdata.load_eveuniverse import load_eveuniverse

MODULE_PATH = "buybackprogram.models"


class TestOwners(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()
        cls.project_manager = UserProjectManagerFactory()

    def test_should_have_str_method(self):
        # given
        obj = OwnerFactory(user=self.project_manager)
        # when/then
        self.assertIsInstance(str(obj), str)


@patch(MODULE_PATH + ".send_user_notification")
@patch(MODULE_PATH + ".Owner._get_location_name")
@patch(MODULE_PATH + ".esi")
class TestOwnersUpdateContractFromEsi(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()
        cls.project_manager = UserProjectManagerFactory()

    def test_should_create_new_contract(
        self, mock_esi, mock_get_location_name, mock_send_user_notification
    ):
        # given
        tracking_number = "AB1"
        eve_type = EveType.objects.get(name="Pyerite")
        owner = OwnerFactory(user=self.project_manager)
        owner_character_id = owner.character.character.character_id
        owner_corporation_id = owner.corporation.corporation_id
        issuer = EveEntityCharacterFactory()
        esi_contract = EsiContractFactory(title=tracking_number, issuer_id=issuer.id)
        esi_contract_item = EsiContractItemFactory(type_id=eve_type.id)
        endpoints = [
            EsiEndpoint(
                "Contracts",
                "get_characters_character_id_contracts",
                "character_id",
                needs_token=True,
                data={str(owner_character_id): [esi_contract]},
            ),
            EsiEndpoint(
                "Contracts",
                "get_characters_character_id_contracts_contract_id_items",
                ("character_id", "contract_id"),
                needs_token=True,
                data={
                    str(owner_character_id): {
                        str(esi_contract["contract_id"]): [esi_contract_item]
                    }
                },
            ),
            EsiEndpoint(
                "Contracts",
                "get_corporations_corporation_id_contracts",
                "corporation_id",
                needs_token=True,
                data={str(owner_corporation_id): []},
            ),
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        program = ProgramFactory(owner=owner)
        tracking = TrackingFactory(program=program, tracking_number=tracking_number)
        TrackingItemFactory(tracking=tracking, eve_type=eve_type)
        mock_get_location_name.return_value = "Unknown"
        # when
        owner.update_contracts_esi()
        # then
        self.assertEqual(Contract.objects.count(), 1)
        contract = Contract.objects.first()
        self.assertEqual(contract.contract_id, esi_contract["contract_id"])
        self.assertEqual(contract.title, esi_contract["title"])
        self.assertEqual(contract.contractitem_set.count(), 1)
        item = contract.contractitem_set.first()
        self.assertEqual(item.eve_type_id, esi_contract_item["type_id"])
        self.assertEqual(item.quantity, esi_contract_item["quantity"])

    def test_should_update_existing_contract(
        self, mock_esi, mock_get_location_name, mock_send_user_notification
    ):
        # given
        tracking_number = "AB1"
        eve_type = EveType.objects.get(name="Pyerite")
        owner = OwnerFactory(user=self.project_manager)
        owner_character_id = owner.character.character.character_id
        owner_corporation_id = owner.corporation.corporation_id
        issuer = EveEntityCharacterFactory()
        contract = ContractFactory(title=tracking_number, issuer_id=issuer.id)
        esi_contract = EsiContractFactory(
            contract_id=contract.contract_id,
            title=tracking_number,
            issuer_id=issuer.id,
            status="finished",
        )
        endpoints = [
            EsiEndpoint(
                "Contracts",
                "get_characters_character_id_contracts",
                "character_id",
                needs_token=True,
                data={str(owner_character_id): [esi_contract]},
            ),
            EsiEndpoint(
                "Contracts",
                "get_corporations_corporation_id_contracts",
                "corporation_id",
                needs_token=True,
                data={str(owner_corporation_id): []},
            ),
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        program = ProgramFactory(owner=owner)
        tracking = TrackingFactory(program=program, tracking_number=tracking_number)
        TrackingItemFactory(tracking=tracking, eve_type=eve_type)
        UserSettingsFactory(user=tracking.issuer_user)
        mock_get_location_name.return_value = "Unknown"
        # when
        owner.update_contracts_esi()
        # then
        contract.refresh_from_db()
        self.assertEqual(contract.status, "finished")
        self.assertTrue(mock_send_user_notification.called)


@patch(MODULE_PATH + ".EveEntity.objects.resolve_name", spec=True)
@patch(MODULE_PATH + ".fetch_esi_status")
@patch(MODULE_PATH + ".esi")
class TestOwnerGetLocationName(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()
        cls.owner = OwnerFactory()

    def test_should_return_name_for_station(
        self, mock_esi, mock_fetch_esi_status, mock_resolve_name
    ):
        # given
        mock_fetch_esi_status.return_value = EsiStatus(True, 99, 99)
        mock_resolve_name.return_value = "Jita 4-4"
        # when
        result = self.owner._get_location_name(60003760)
        # then
        self.assertEqual(result, "Jita 4-4")

    def test_should_return_name_for_structure(
        self, mock_esi, mock_fetch_esi_status, mock_resolve_name
    ):
        # given
        mock_fetch_esi_status.return_value = EsiStatus(True, 99, 99)
        endpoints = [
            EsiEndpoint(
                "Universe",
                "get_universe_structures_structure_id",
                "structure_id",
                needs_token=True,
                data={"100000001": {"name": "My structure"}},
            )
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        # when
        result = self.owner._get_location_name(100000001)
        # then
        self.assertEqual(result, "My structure")

    def test_should_return_unknown_when_esi_is_down(
        self, mock_esi, mock_fetch_esi_status, mock_resolve_name
    ):
        # given
        mock_fetch_esi_status.return_value = EsiStatus(False, 99, 99)
        mock_resolve_name.return_value = "Jita 4-4"
        # when
        result = self.owner._get_location_name(60003760)
        # then
        self.assertEqual(result, "Unknown")

    def test_should_return_unknown_when_structure_endpoints_returns_error(
        self, mock_esi, mock_fetch_esi_status, mock_resolve_name
    ):
        # given
        mock_fetch_esi_status.return_value = EsiStatus(True, 99, 99)
        mock = mock_esi.client.Universe
        mock.get_universe_structures_structure_id.return_value.result.side_effect = (
            OSError
        )
        # when
        result = self.owner._get_location_name(100000001)
        # then
        self.assertEqual(result, "Unknown")


class TestLocations(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()

    def test_should_have_str_method(self):
        # given
        obj = LocationFactory()
        # when/then
        self.assertIsInstance(str(obj), str)


class TestProgram(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()

    def test_should_have_str_method(self):
        # given
        obj = ProgramFactory()
        # when/then
        self.assertIsInstance(str(obj), str)


class TestProgramItem(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()

    def test_should_have_str_method(self):
        # given
        obj = ProgramItemFactory()
        # when/then
        self.assertIsInstance(str(obj), str)


class TestItemPrices(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()

    def test_should_have_str_method(self):
        # given
        obj = ItemPricesFactory()
        # when/then
        self.assertIsInstance(str(obj), str)


class TestContracts(TestCase):
    def test_should_have_str_method(self):
        # given
        obj = ContractFactory()
        # when/then
        self.assertIsInstance(str(obj), str)

    def test_contract_id_should_be_unique(self):
        # given
        contract = ContractFactory()
        # when/then
        with self.assertRaises(IntegrityError):
            ContractFactory(contract_id=contract.contract_id)


class TestContractItems(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()

    def test_should_have_str_method(self):
        # given
        obj = ContractItemFactory()
        # when/then
        self.assertIsInstance(str(obj), str)


class TestContractNotifications(TestCase):
    def test_should_have_str_method(self):
        # given
        obj = ContractNotificationFactory()
        # when/then
        self.assertIsInstance(str(obj), str)


class TestTrackings(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()

    def test_should_have_str_method(self):
        # given
        obj = TrackingFactory()
        # when/then
        self.assertIsInstance(str(obj), str)


class TestTrackingItems(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()

    def test_should_have_str_method(self):
        # given
        obj = TrackingItemFactory()
        # when/then
        self.assertIsInstance(str(obj), str)
