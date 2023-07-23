import json

from eveuniverse.tools.testdata import load_testdata_from_dict

from . import eveuniverse_test_data_filename


def _load_eveuniverse_from_file():
    with open(eveuniverse_test_data_filename(), "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


eveuniverse_testdata = _load_eveuniverse_from_file()


def load_eveuniverse():
    load_testdata_from_dict(eveuniverse_testdata)
