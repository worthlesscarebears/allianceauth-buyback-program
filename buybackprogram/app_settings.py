import re

from django.conf import settings

from .utils import clean_setting

# put your app settings here


def get_site_url():  # regex sso url
    regex = r"^(.+)\/s.+"
    matches = re.finditer(regex, settings.ESI_SSO_CALLBACK_URL, re.MULTILINE)
    url = "http://"

    for m in matches:
        url = m.groups()[0]  # first match

    return url


# Hard timeout for tasks in seconds to reduce task accumulation during outages
BUYBACKPROGRAM_TASKS_TIME_LIMIT = clean_setting("BUYBACKPROGRAM_TASKS_TIME_LIMIT", 7200)

# Warning limit for Jita price updates if prices have not been updated
BUYBACKPROGRAM_PRICE_AGE_WARNING_LIMIT = clean_setting(
    "BUYBACKPROGRAM_PRICE_AGE_WARNING_LIMIT", 48
)

# Unused tracking purge limit
BUYBACKPROGRAM_UNUSED_TRACKING_PURGE_LIMIT = clean_setting(
    "BUYBACKPROGRAM_UNUSED_TRACKING_PURGE_LIMIT", 48
)

BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS = clean_setting(
    "BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS", True
)

# Tracking number tag
BUYBACKPROGRAM_TRACKING_PREFILL = clean_setting(
    "BUYBACKPROGRAM_TRACKING_PREFILL", "aa-bbp"
)

BUYBACKPROGRAM_PRICE_SOURCE_ID = clean_setting(
    "BUYBACKPROGRAM_PRICE_SOURCE_ID", 60003760
)

BUYBACKPROGRAM_PRICE_SOURCE_NAME = clean_setting(
    "BUYBACKPROGRAM_PRICE_SOURCE_NAME", "Jita"
)

BUYBACKPROGRAM_PRICE_INSTANT_PRICES = clean_setting(
    "BUYBACKPROGRAM_PRICE_INSTANT_PRICES", False
)

BUYBACKPROGRAM_PRICE_METHOD = clean_setting("BUYBACKPROGRAM_PRICE_METHOD", "Fuzzwork")

BUYBACKPROGRAM_PRICE_JANICE_API_KEY = clean_setting(
    "BUYBACKPROGRAM_PRICE_JANICE_API_KEY", ""
)


def allianceauth_discordbot_active():
    """
    check if allianceauth-dicordbot is installed and active
    :return:
    """
    return "aadiscordbot" in settings.INSTALLED_APPS


def aa_discordnotify_active():
    """
    check if allianceauth-dicordbot is installed and active
    :return:
    """
    return "discordnotify" in settings.INSTALLED_APPS
