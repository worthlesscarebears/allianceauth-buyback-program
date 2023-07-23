import datetime as dt

import factory
import factory.fuzzy
from faker import Faker

from django.utils.timezone import now
from eveuniverse.models import EveEntity, EveSolarSystem, EveType

from app_utils.testdata_factories import (
    EveAllianceInfoFactory,
    EveCharacterFactory,
    EveCorporationInfoFactory,
    UserMainFactory,
)

from buybackprogram.models import (
    Contract,
    ContractItem,
    ContractNotification,
    ItemPrices,
    Location,
    Owner,
    Program,
    ProgramItem,
    Tracking,
    TrackingItem,
    UserSettings,
)

fake = Faker()
Faker.seed(0)


def random_eve_type_id() -> int:
    ids = EveType.objects.filter(published=True).values_list("id", flat=True)
    if not ids:
        return None
    return factory.fuzzy.FuzzyChoice(ids).fuzz()


def random_eve_type() -> EveType:
    eve_type_did = random_eve_type_id()
    if not eve_type_did:
        return None
    return EveType.objects.get(id=eve_type_did)


# TODO: Move to app_utils
class EveEntityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EveEntity
        django_get_or_create = ("id", "name")

    category = EveEntity.CATEGORY_CHARACTER

    @factory.lazy_attribute
    def id(self):
        if self.category == EveEntity.CATEGORY_CHARACTER:
            obj = EveCharacterFactory()
            return obj.character_id
        if self.category == EveEntity.CATEGORY_CORPORATION:
            obj = EveCorporationInfoFactory()
            return obj.corporation_id
        if self.category == EveEntity.CATEGORY_ALLIANCE:
            obj = EveAllianceInfoFactory()
            return obj.alliance_id
        raise NotImplementedError(f"Unknown category: {self.category}")


class EveEntityCharacterFactory(EveEntityFactory):
    name = factory.Faker("name")
    category = EveEntity.CATEGORY_CHARACTER


class EveEntityCorporationFactory(EveEntityFactory):
    name = factory.Faker("company")
    category = EveEntity.CATEGORY_CORPORATION


class EveEntityAllianceFactory(EveEntityFactory):
    name = factory.Faker("company")
    category = EveEntity.CATEGORY_ALLIANCE


class UserProjectManagerFactory(UserMainFactory):
    main_character__scopes = [
        "esi-contracts.read_character_contracts.v1",
        "esi-contracts.read_corporation_contracts.v1",
        "esi-universe.read_structures.v1",
    ]
    permissions__ = ["buybackprogram.basic_access", "buybackprogram.manage_programs"]


class UserIssuerFactory(UserMainFactory):
    main_character__scopes = [
        "esi-contracts.read_character_contracts.v1",
        "esi-contracts.read_corporation_contracts.v1",
        "esi-universe.read_structures.v1",
    ]
    permissions__ = ["buybackprogram.basic_access"]


class OwnerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Owner

    user = factory.SubFactory(UserProjectManagerFactory)
    character = factory.lazy_attribute(
        lambda o: o.user.profile.main_character.character_ownership
    )

    @factory.lazy_attribute
    def corporation(self):
        return EveCorporationInfoFactory(
            corporation_id=self.user.profile.main_character.corporation_id
        )


class LocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Location

    name = factory.Faker("word")
    owner = factory.SubFactory(OwnerFactory)

    @factory.lazy_attribute
    def eve_solar_system(self):
        obj = EveSolarSystem.objects.order_by("?").first()
        if not obj:
            raise RuntimeError("No EveSolarSystem found for LocationFactory.")
        return obj


class ProgramFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Program

    name = factory.Faker("sentence")
    owner = factory.SubFactory(OwnerFactory)

    @factory.post_generation
    def location(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for obj in extracted:
                self.location.add(obj)
        else:
            obj = LocationFactory()
            self.location.add(obj)


class ProgramItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProgramItem

    program = factory.SubFactory(ProgramFactory)

    @factory.lazy_attribute
    def item_type(self):
        obj = random_eve_type()
        if not obj:
            raise RuntimeError("No EveType found for ProgramItemFactory.")
        return obj


class ItemPricesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ItemPrices

    buy = factory.fuzzy.FuzzyInteger(1, 10_000_000)
    sell = factory.fuzzy.FuzzyInteger(1, 10_000_000)
    updated = factory.lazy_attribute(lambda o: now())

    @factory.lazy_attribute
    def eve_type(self):
        obj = random_eve_type()
        if not obj:
            raise RuntimeError("No EveType found for ProgramItemFactory.")
        return obj


class ContractFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Contract

    assignee_id = factory.Sequence(lambda n: 90_000 + n)
    availability = "public"
    contract_id = factory.Sequence(lambda n: 1_000_000_000 + n)
    date_issued = factory.fuzzy.FuzzyDateTime(now() - dt.timedelta(days=3))
    for_corporation = False
    issuer_corporation_id = factory.Sequence(lambda n: 99_000 + n)
    issuer_id = factory.Sequence(lambda n: 95_000 + n)
    price = factory.fuzzy.FuzzyInteger(90_000, 99_000)
    status = "outstanding"
    title = factory.Faker("sentence")
    volume = factory.fuzzy.FuzzyInteger(10, 320)


class EsiContractFactory(factory.DictFactory):
    """Contract dictionary returned from ESI endpoint."""

    # acceptor_id
    assignee_id = factory.Sequence(lambda n: 90_000 + n)
    availability = "public"
    contract_id = factory.Sequence(lambda n: 1_000_000_000 + n)
    date_issued = factory.fuzzy.FuzzyDateTime(now() - dt.timedelta(days=3))
    for_corporation = False
    issuer_corporation_id = factory.Sequence(lambda n: 99_000 + n)
    issuer_id = factory.Sequence(lambda n: 95_000 + n)
    price = factory.fuzzy.FuzzyInteger(90_000, 99_000)
    status = "outstanding"
    start_location_id = 60003760
    title = factory.Faker("sentence")
    type = "item_exchange"
    volume = factory.fuzzy.FuzzyInteger(10, 320)

    @factory.lazy_attribute
    def date_expired(self):
        return factory.fuzzy.FuzzyDateTime(
            self.date_issued, self.date_issued + dt.timedelta(days=10)
        ).fuzz()

    @factory.lazy_attribute
    def date_completed(self):
        return factory.fuzzy.FuzzyDateTime(self.date_issued, self.date_expired).fuzz()


class EsiContractItemFactory(factory.DictFactory):
    """Contract item dictionary returned from ESI endpoint."""

    is_included = True
    is_singleton = False
    quantity = factory.fuzzy.FuzzyInteger(1, 999)
    record_id = factory.Sequence(lambda n: 1 + n)

    @factory.lazy_attribute
    def type_id(self):
        id = random_eve_type_id()
        if not id:
            raise RuntimeError("No EveType found for EsiContractItemFactory.")
        return id


class ContractItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContractItem

    contract = factory.SubFactory(ContractFactory)
    quantity = factory.fuzzy.FuzzyInteger(1, 999)

    @factory.lazy_attribute
    def eve_type(self):
        obj = random_eve_type()
        if not obj:
            raise RuntimeError("No EveType found for ProgramItemFactory.")
        return obj


class ContractNotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContractNotification

    contract = factory.SubFactory(ContractFactory)
    icon = factory.Faker("url")
    color = factory.fuzzy.FuzzyChoice(["green", "orange", "red"])
    message = factory.Faker("sentence")


class TrackingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tracking

    program = factory.SubFactory(ProgramFactory)
    issuer_user = factory.SubFactory(UserIssuerFactory)
    value = factory.fuzzy.FuzzyInteger(1_000_000, 100_000_000)
    taxes = factory.fuzzy.FuzzyInteger(1_000_000, 5_000_000)
    net_price = factory.fuzzy.FuzzyInteger(1_000_000, 100_000_000)
    hauling_cost = factory.fuzzy.FuzzyInteger(1_000_000, 5_000_000)
    tracking_number = 5  # what is this?
    created_at = factory.fuzzy.FuzzyDateTime(now() - dt.timedelta(days=3))

    @factory.lazy_attribute
    def tracking_number(self):
        return "aa-bbp-" + fake.uuid4()[:6].upper()


class TrackingItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TrackingItem

    tracking = factory.SubFactory(TrackingFactory)
    buy_value = factory.fuzzy.FuzzyInteger(1_000_000, 100_000_000)
    quantity = factory.fuzzy.FuzzyInteger(1, 999)

    @factory.lazy_attribute
    def eve_type(self):
        obj = random_eve_type()
        if not obj:
            raise RuntimeError("No EveType found for ProgramItemFactory.")
        return obj


class UserSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserSettings

    user = factory.SubFactory(UserIssuerFactory)
