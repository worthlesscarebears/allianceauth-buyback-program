from django.test import TestCase
from eveuniverse.models import EveType
from eveuniverse.tools.testdata import ModelSpec, create_testdata

from . import eveuniverse_test_data_filename


class CreateEveUniverseTestData(TestCase):
    def test_create_testdata(self):
        testdata_spec = [
            ModelSpec("EveSolarSystem", ids=[30000142, 30004984, 30001161, 30002537]),
            ModelSpec(
                "EveCategory",
                ids=[25],  # Asteroid
                include_children=True,
                enabled_sections=[
                    EveType.Section.TYPE_MATERIALS,
                    EveType.Section.DOGMAS,
                ],
            ),
        ]
        create_testdata(testdata_spec, eveuniverse_test_data_filename())
