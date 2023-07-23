from django.test import TestCase

from buybackprogram.helpers import get_tracking_number

from .testdata.factories import ProgramFactory, UserIssuerFactory
from .testdata.load_eveuniverse import load_eveuniverse


class TestHelpers(TestCase):
    def test_should_create_tracking_when_first(self):
        # given
        load_eveuniverse()
        user = UserIssuerFactory()
        program = ProgramFactory()
        contract_net_prices = {
            "total_all_items_raw": 1,
            "total_all_items": 1,
            "total_tax_amount": 1,
            "total_donation_amount": 1,
            "hauling_cost": 0,
            "total_hauling_cost": 0,
            "contract_net_total": 1,
        }
        # when
        tracking = get_tracking_number(user, program, None, [], contract_net_prices)
        # then
        self.assertEqual(tracking.program, program)
        self.assertEqual(tracking.issuer_user, user)
