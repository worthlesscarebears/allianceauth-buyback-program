from esi.openapi_clients import ESIClientProvider

from . import __title__, __version__

esi = ESIClientProvider(
    compatibility_date="2025-12-16",
    ua_appname=__title__,
    ua_version=__version__,
    operations=[
        "GetCorporationsCorporationIdContracts",
        "GetCorporationsCorporationIdContractsContractIdItems",
        "GetCharactersCharacterIdContracts",
        "GetCharactersCharacterIdContractsContractIdItems",
        "GetUniverseStructuresStructureId",
        "PostUniverseNames",
    ],
)
