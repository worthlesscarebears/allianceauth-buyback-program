from typing import Tuple

from django.contrib.auth.models import Group, User
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import Error, models
from django.utils.translation import gettext as _
from esi.errors import TokenExpiredError, TokenInvalidError
from esi.models import Token
from eveuniverse.models import EveEntity, EveSolarSystem, EveType

from allianceauth.authentication.models import CharacterOwnership, State

# Create your models here.
from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.esi import fetch_esi_status

from buybackprogram.notification import (
    send_message_to_discord_channel,
    send_user_notification,
)

from .app_settings import (
    BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS,
    BUYBACKPROGRAM_TRACKING_PREFILL,
    get_site_url,
)
from .decorators import fetch_token_for_owner
from .providers import esi

logger = get_extension_logger(__name__)


def get_sentinel_user():
    """
    get user or create one
    :return:
    """

    return User.objects.get_or_create(username="deleted")[0]


class General(models.Model):
    """Meta model for app permissions"""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access this app and see own statics."),
            (
                "manage_programs",
                "Can manage own buyback programs and see own program statics.",
            ),
            ("see_leaderboard", "Can see leaderboards for all available programs."),
            ("see_performance", "Can see performance for all available programs."),
            ("see_all_statics", "Can see all program statics."),
        )


class Owner(models.Model):
    """A corporation that has buyback programs"""

    ERROR_NONE = 0
    ERROR_TOKEN_INVALID = 1
    ERROR_TOKEN_EXPIRED = 2
    ERROR_ESI_UNAVAILABLE = 5

    ERRORS_LIST = [
        (ERROR_NONE, "No error"),
        (ERROR_TOKEN_INVALID, "Invalid token"),
        (ERROR_TOKEN_EXPIRED, "Expired token"),
        (ERROR_ESI_UNAVAILABLE, "ESI API is currently unavailable"),
    ]

    corporation = models.ForeignKey(
        EveCorporationInfo,
        on_delete=models.deletion.CASCADE,
        related_name="+",
    )
    character = models.ForeignKey(
        CharacterOwnership,
        help_text="Character used for retrieving info",
        on_delete=models.deletion.PROTECT,
        related_name="+",
    )

    user = models.ForeignKey(
        User,
        help_text="User that manages the program",
        on_delete=models.deletion.PROTECT,
        related_name="+",
    )

    class Meta:
        default_permissions = ()

    @fetch_token_for_owner(
        [
            "esi-contracts.read_character_contracts.v1",
            "esi-contracts.read_corporation_contracts.v1",
            "esi-universe.read_structures.v1",
        ]
    )
    def update_contracts_esi(self, token):
        logger.debug("Fetching contracts for %s" % self.character)

        # Get all contracts for owner
        contracts = self._fetch_contracts()

        logger.debug("Got %s character contracts" % len(contracts))

        logger.debug("Fetching corporation contracts for %s" % self.corporation)

        # Get all contracts for owner corporation
        corporation_contracts = self._fetch_corporation_contracts()

        logger.debug("Got %s corporation contracts" % len(corporation_contracts))

        # Merge all contracts into a single list
        all_contracts = contracts + corporation_contracts
        tracked_contrats = list()

        logger.debug("Total contracts received: %s" % len(all_contracts))

        # Get all tracking objects from the database
        tracking_numbers = Tracking.objects.all()

        logger.debug("Got %s tracking numbers from database" % len(tracking_numbers))

        # Start looping for all stored tracking objects
        for tracking in tracking_numbers:
            # If the tracking has an active program (not deleted)
            if tracking.program:
                # Start checking if we find any matches from our ESI contracts
                for contract in all_contracts:
                    # Only get contracts with the correct prefill ticker
                    if tracking.tracking_number in contract["title"]:
                        self._process_contract(contract, tracking, token)

                        tracked_contrats.append(contract)

                        break  # If we have found a match from our ESI contracts wi will stop looping on the contract

        # Check for possible scam contracts that are pretending to be buyback contracts

        if BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS:
            logger.debug("Starting untracked contracts check")

            # Check what contracts we already have processed earlier
            untracked_contracts = [
                x for x in all_contracts if x not in tracked_contrats
            ]

            logger.debug(
                "Found %s untracked contracts out of %s"
                % (len(untracked_contracts), len(all_contracts))
            )

            for contract in untracked_contracts:
                if BUYBACKPROGRAM_TRACKING_PREFILL in contract["title"]:
                    try:
                        tracking = Tracking.objects.get(
                            tracking_number__contains=contract["title"]
                        )
                        logger.debug(
                            "Contract %s already tracked, passing"
                            % contract["contract_id"]
                        )

                    except Tracking.DoesNotExist:
                        logger.debug(
                            "Contract %s is not tracked, starting updates"
                            % contract["contract_id"]
                        )

                        self._process_contract_without_tracking(contract, token)
        else:
            logger.debug(
                "Track prefill contracts is set to %s, passing prefill contract checks"
                % BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS
            )

    def _process_contract(self, contract, tracking, token):
        # Check if we already have the contract stored
        try:
            old_contract = Contract.objects.get(contract_id=contract["contract_id"])

            logger.debug(
                "Contract %s is already stored in database" % contract["contract_id"]
            )

        except Contract.DoesNotExist:
            logger.debug(
                "No matching contracts stored for %s in database, new contract."
                % contract["contract_id"]
            )
            old_contract = Contract.objects.none()
            old_contract.status = False

        logger.debug("User has token: %s" % contract["start_location_id"])

        # If we have found a contract from database that is not yet finished
        if old_contract.status not in ["finished", "rejected"]:
            logger.debug(
                "Contract %s status is still pending, starting updates"
                % contract["contract_id"]
            )

            # Get location name for contract
            contract_location_name = self._get_location_name(
                contract["start_location_id"]
            )

            logger.debug("Got contract location name: %s" % contract_location_name)

            # Create or update the found contract
            obj, created = Contract.objects.update_or_create(
                contract_id=contract["contract_id"],
                defaults={
                    "contract_id": contract["contract_id"],
                    "assignee_id": contract["assignee_id"],
                    "availability": contract["availability"],
                    "date_completed": contract["date_completed"],
                    "date_expired": contract["date_expired"],
                    "date_issued": contract["date_issued"],
                    "for_corporation": contract["for_corporation"],
                    "issuer_corporation_id": contract["issuer_corporation_id"],
                    "issuer_id": contract["issuer_id"],
                    "start_location_id": contract["start_location_id"],
                    "location_name": contract_location_name,
                    "price": contract["price"],
                    "status": contract["status"],
                    "title": contract["title"],
                    "volume": contract["volume"],
                    "no_tracking": False,
                },
            )

            # If we have created a new contract
            if created:
                logger.debug(
                    "Contract %s created, linking tracking object %s"
                    % (
                        contract["contract_id"],
                        tracking.tracking_number,
                    )
                )

                try:
                    Tracking.objects.filter(pk=tracking.id).update(contract=obj)
                except Error as e:
                    logger.error(
                        "Error linking contract %s with tracking %s: %s"
                        % (
                            contract["contract_id"],
                            tracking.tracking_number,
                            e,
                        )
                    )

                logger.debug(
                    "New contract %s has been created. Starting item fetch"
                    % contract["contract_id"]
                )

                character_id = self.character.character.character_id

                corporation_id = self.character.character.corporation_id

                logger.debug(
                    "Fetching items for %s with character %s. Corporation contract: %s"
                    % (
                        contract["contract_id"],
                        character_id,
                        contract["is_corporation"],
                    )
                )

                if not contract["is_corporation"]:
                    logger.debug(
                        "Looking up items for %s via character endpoint"
                        % contract["contract_id"]
                    )
                    # Get all items in the contract
                    contract_items = esi.client.Contracts.get_characters_character_id_contracts_contract_id_items(
                        character_id=character_id,
                        contract_id=contract["contract_id"],
                        token=token.valid_access_token(),
                    ).results()

                else:
                    logger.debug(
                        "Looking up items for %s via corporation endpoint"
                        % contract["contract_id"]
                    )
                    contract_items = esi.client.Contracts.get_corporations_corporation_id_contracts_contract_id_items(
                        corporation_id=corporation_id,
                        contract_id=contract["contract_id"],
                        token=token.valid_access_token(),
                    ).results()

                logger.debug(
                    "%s items found in contract %s"
                    % (len(contract_items), contract["contract_id"])
                )

                corporations = CharacterOwnership.objects.filter(
                    user=tracking.program.owner.user
                ).values_list("character__corporation_id", flat=True)

                logger.debug("Got corporations for contract owner: %s" % corporations)

                objs = []
                items = []

                # Prepare objects for bulk create
                for item in contract_items:
                    cont = Contract.objects.get(contract_id=contract["contract_id"])
                    itm, _ = EveType.objects.get_or_create_esi(id=item["type_id"])

                    contract_item = ContractItem(
                        contract=cont,
                        eve_type=itm,
                        quantity=item["quantity"],
                    )

                    objs.append(contract_item)

                    items.append(
                        str(EveType.objects.get(id=item["type_id"]))
                        + " x "
                        + str(item["quantity"])
                    )

                try:
                    ContractItem.objects.bulk_create(objs)
                    logger.debug(
                        "Succesfully added %s items for contract %s into database"
                        % (len(objs), contract["contract_id"])
                    )
                except Error as e:
                    logger.error(
                        "Error adding items for contract %s: %s"
                        % (contract["contract_id"], e)
                    )

                # Check and see if any notifications/warnings should be set on the contract
                self._set_contract_notifications(
                    tracking, obj, corporations, tracking.program
                )

                # Notifications for users who have the notifications enabled

                if not contract["is_corporation"]:
                    assigned_to = self.character.character.character_name
                else:
                    assigned_to = self.character.character.corporation_name

                notifications = ContractNotification.objects.filter(
                    contract__contract_id=contract["contract_id"]
                )

                notes = str()

                if notifications:
                    for note in notifications:
                        notes += str(note.message)
                        notes += "\n\n"

                logger.debug("Contract contains %s" % "\n".join(items))

                # Check if the program wants to display the item list
                if tracking.program.discord_show_item_list:
                    contract_item_list = "\n".join(items)
                else:
                    contract_item_list = ""

                contract_url = (
                    get_site_url()
                    + "/buybackprogram/tracking/"
                    + tracking.tracking_number
                )

                # Limit contract items to fit into embed limitations
                if (
                    len(contract_item_list) > 2000
                    or not tracking.program.discord_show_item_list
                ):
                    contract_item_list = (
                        contract_item_list
                        + "\n[See all contract items ...]("
                        + contract_url
                        + ")"
                    )

                user_message = {
                    "contract": obj,
                    "contract_items": contract_item_list,
                    "tracking": tracking,
                    "notes": notes,
                    "title": "New buyback contract assigned for program {0}".format(
                        tracking.program.name
                    ),
                    "color": 0x5BC0DE,
                    "value": intcomma(int(contract["price"])),
                    "assigned_to": assigned_to,
                    "assigned_from": EveEntity.objects.resolve_name(
                        contract["issuer_id"]
                    ),
                }

                # If tracking is active and we should send a message for our users
                if tracking.program.discord_dm_notification:
                    send_user_notification(
                        user=self.user,
                        level="success",
                        message=user_message,
                    )
                else:
                    logger.debug(
                        "Program owner does not want DM notifications, passing"
                    )

                # Notifications for the discord channel
                if tracking.program.discord_channel_notification:
                    logger.debug(
                        "Program wants channel notification, attempting to send via webhook"
                    )
                    send_message_to_discord_channel(
                        webhook=tracking.program.discord_channel_notification,
                        message=user_message,
                    )
                else:
                    logger.debug(
                        "Program owner does not want channel notifications, passing"
                    )

            # If contract was updated instead of created
            else:
                logger.debug(
                    "Contract %s is not new, updated the old contract."
                    % obj.contract_id
                )

            # Check if the contract status has changed from ongoing to finished.
            if old_contract.status == "outstanding" and obj.status in [
                "finished",
                "rejected",
            ]:
                logger.debug(
                    "Contract %s has been completed. Status has changed to %s"
                    % (obj.contract_id, obj.status)
                )

                # Get notification settings for the contract issuer
                user_settings = UserSettings.objects.get(user=tracking.issuer_user)

                # If user has not disabled notifications
                if user_settings.disable_notifications is False:
                    if not contract["is_corporation"]:
                        assigned_to = self.character.character.character_name
                    else:
                        assigned_to = self.character.character.corporation_name

                    # Check if the contract was accepted or rejected
                    if contract["status"] == "finished":
                        status = "accepted"
                        color = 0x5CB85C
                        level = "success"
                    elif contract["status"] == "rejected":
                        status = "rejected"
                        color = 0xD9534F
                        level = "danger"
                    else:
                        status = contract["status"]

                    notifications = ContractNotification.objects.filter(
                        contract__contract_id=contract["contract_id"]
                    )

                    notes = str()
                    items = []

                    if notifications:
                        for note in notifications:
                            notes += str(note.message)
                            notes += "\n\n"

                    user_message = {
                        "contract": obj,
                        "tracking": tracking,
                        "title": "Your buyback contract has been {0}".format(status),
                        "color": color,
                        "notes": notes,
                        "value": intcomma(int(contract["price"])),
                        "assigned_to": assigned_to,
                        "assigned_from": EveEntity.objects.resolve_name(
                            contract["issuer_id"]
                        ),
                    }

                    send_user_notification(
                        user=tracking.issuer_user,
                        level=level,
                        message=user_message,
                    )
                else:
                    logger.debug(
                        "Contract assigner has notifications set to %s, passing"
                        % user_settings.disable_notifications
                    )
            else:
                logger.debug(
                    "No changes to the status of contract %s, update completed"
                    % obj.contract_id
                )

    def _process_contract_without_tracking(self, contract, token):
        # Check if we already have the contract stored
        try:
            old_contract = Contract.objects.get(contract_id=contract["contract_id"])

            logger.debug(
                "Untracked contract %s is already stored in database"
                % contract["contract_id"]
            )

        except Contract.DoesNotExist:
            logger.debug(
                "No matching contracts stored for %s in database, new untracked contract."
                % contract["contract_id"]
            )
            old_contract = Contract.objects.none()
            old_contract.status = False

        logger.debug("User has token: %s" % contract["start_location_id"])

        # If we have found a contract from database that is not yet finished
        if old_contract.status not in ["finished", "rejected"]:
            logger.debug(
                "Untracked contract %s status is still pending, starting updates"
                % contract["contract_id"]
            )

            # Get location name for contract
            contract_location_name = self._get_location_name(
                contract["start_location_id"]
            )

            logger.debug("Got contract location name: %s" % contract_location_name)

            # Create or update the found contract
            obj, created = Contract.objects.update_or_create(
                contract_id=contract["contract_id"],
                defaults={
                    "contract_id": contract["contract_id"],
                    "assignee_id": contract["assignee_id"],
                    "availability": contract["availability"],
                    "date_completed": contract["date_completed"],
                    "date_expired": contract["date_expired"],
                    "date_issued": contract["date_issued"],
                    "for_corporation": contract["for_corporation"],
                    "issuer_corporation_id": contract["issuer_corporation_id"],
                    "issuer_id": contract["issuer_id"],
                    "start_location_id": contract["start_location_id"],
                    "location_name": contract_location_name,
                    "price": contract["price"],
                    "status": contract["status"],
                    "title": contract["title"],
                    "volume": contract["volume"],
                    "no_tracking": True,
                },
            )

            # If we have created a new contract
            if created:
                logger.debug(
                    "Contract %s created without tracking object, possible scam!"
                    % (contract["contract_id"],)
                )

                character_id = self.character.character.character_id

                corporation_id = self.character.character.corporation_id

                logger.debug(
                    "Fetching items for %s with character %s. Corporation contract: %s"
                    % (
                        contract["contract_id"],
                        character_id,
                        contract["is_corporation"],
                    )
                )

                if not contract["is_corporation"]:
                    logger.debug(
                        "Looking up items for %s via character endpoint"
                        % contract["contract_id"]
                    )
                    # Get all items in the contract
                    contract_items = esi.client.Contracts.get_characters_character_id_contracts_contract_id_items(
                        character_id=character_id,
                        contract_id=contract["contract_id"],
                        token=token.valid_access_token(),
                    ).results()

                else:
                    logger.debug(
                        "Looking up items for %s via corporation endpoint"
                        % contract["contract_id"]
                    )
                    contract_items = esi.client.Contracts.get_corporations_corporation_id_contracts_contract_id_items(
                        corporation_id=corporation_id,
                        contract_id=contract["contract_id"],
                        token=token.valid_access_token(),
                    ).results()

                logger.debug(
                    "%s items found in contract %s"
                    % (len(contract_items), contract["contract_id"])
                )

                objs = []

                # Prepare objects for bulk create
                for item in contract_items:
                    cont = Contract.objects.get(contract_id=contract["contract_id"])
                    itm, _ = EveType.objects.get_or_create_esi(id=item["type_id"])

                    contract_item = ContractItem(
                        contract=cont,
                        eve_type=itm,
                        quantity=item["quantity"],
                    )

                    objs.append(contract_item)

                try:
                    ContractItem.objects.bulk_create(objs)
                    logger.debug(
                        "Succesfully added %s items for contract %s into database"
                        % (len(objs), contract["contract_id"])
                    )
                except Error as e:
                    logger.error(
                        "Error adding items for contract %s: %s"
                        % (contract["contract_id"], e)
                    )

                # Check and see if any notifications/warnings should be set on the contract
                self._set_suspicious_contract_notifications(obj)

            # If contract was updated instead of created
            else:
                logger.debug(
                    "Contract %s is not new, updated the old contract."
                    % obj.contract_id
                )

            # Check if the contract status has changed from ongoing to finished.
            if old_contract.status == "outstanding" and obj.status in [
                "finished",
                "rejected",
            ]:
                logger.debug(
                    "Contract %s has been completed. Status has changed to %s"
                    % (obj.contract_id, obj.status)
                )

            else:
                logger.debug(
                    "No changes to the status of contract %s, update completed"
                    % obj.contract_id
                )

    @fetch_token_for_owner(["esi-universe.read_structures.v1"])
    def _get_location_name(self, token, structid) -> list:
        status = fetch_esi_status()

        if not status.is_online or status.error_limit_remain < 5:
            return "Unknown"
        if structid <= 100000000:  # likely to be NPC station
            return EveEntity.objects.resolve_name(structid)

        operation = esi.client.Universe.get_universe_structures_structure_id(
            structure_id=structid, token=token.valid_access_token()
        )
        operation.request_config.also_return_response = True

        try:
            label, response = operation.result()
        except OSError as ex:
            logger.error("Error fetching location information %s" % (ex))
            return "Unknown"

        if response.status_code != 200:
            return "Unknown"
        return label["name"]

    @fetch_token_for_owner(["esi-contracts.read_character_contracts.v1"])
    def _fetch_contracts(self, token) -> list:
        character_id = self.character.character.character_id

        esi_contracts = esi.client.Contracts.get_characters_character_id_contracts(
            character_id=character_id,
            token=token.valid_access_token(),
        ).results()

        contracts = []

        for esi_contract in esi_contracts:
            contract = esi_contract
            contract["is_corporation"] = False

            contracts.append(contract)

        return contracts

    @fetch_token_for_owner(["esi-contracts.read_corporation_contracts.v1"])
    def _fetch_corporation_contracts(self, token) -> list:
        corporation_id = self.character.character.corporation_id

        esi_contracts = esi.client.Contracts.get_corporations_corporation_id_contracts(
            corporation_id=corporation_id,
            token=token.valid_access_token(),
        ).results()

        contracts = []

        for esi_contract in esi_contracts:
            contract = esi_contract
            contract["is_corporation"] = True

            contracts.append(contract)

        return contracts

    def _set_suspicious_contract_notifications(self, contract):
        # List for all notes
        notes = []

        note = ContractNotification(
            contract=contract,
            icon="fa-theater-masks",
            color="red",
            message="Contract has no tracking object but is has a buyback prefill text! Possibly a scam contract.",
        )

        notes.append(note)

        try:
            ContractNotification.objects.bulk_create(notes)

            logger.debug(
                "Succesfully added items for contract %s into database"
                % contract.contract_id
            )

        except Error as e:
            logger.error(
                "Error adding items for contract %s: %s" % (contract.contract_id, e)
            )

    def _set_contract_notifications(self, tracking, contract, corporations, program):
        # List for all notes
        notes = []

        # Get structure id for tracked contract
        structure_id = Program.objects.filter(pk=program.id).values_list(
            "location__structure_id", flat=True
        )

        logger.debug("Got valid locations for program: %s" % structure_id)

        logger.debug(
            "Checking if items in contract %s match items in tracking %s "
            % (contract.id, tracking.tracking_number)
        )

        # Get items related to tracking object
        tracking_items = list(
            TrackingItem.objects.filter(tracking=tracking)
            .values("eve_type", "quantity")
            .order_by("eve_type", "quantity")
        )

        logger.debug("Got tracking items: %s" % (tracking_items))

        # Get actual contract items
        contract_items = list(
            ContractItem.objects.filter(contract=contract)
            .values("eve_type", "quantity")
            .order_by("eve_type", "quantity")
        )

        logger.debug("Got contract items: %s" % (contract_items))

        if tracking_items != contract_items:
            note = ContractNotification(
                contract=contract,
                icon="fa-unlink",
                color="red",
                message="Tracked items do not match the actual items in the contract. See details for more info.",
            )

            notes.append(note)

        # If our tracked price is different than the actual contract price
        if tracking.net_price >= 0 and tracking.net_price != contract.price:
            # If contract price is bellow tracked price
            if contract.price > tracking.net_price:
                note = ContractNotification(
                    contract=contract,
                    icon="fa-dollar-sign",
                    color="red",
                    message="Ask price is above the calculated price for this contract",
                )

                notes.append(note)

            else:
                note = ContractNotification(
                    contract=contract,
                    icon="fa-dollar-sign",
                    color="orange",
                    message="Ask price is bellow the calculated price for this contract",
                )

                notes.append(note)

        if structure_id and contract.start_location_id not in structure_id:
            note = ContractNotification(
                contract=contract,
                icon="fa-compass",
                color="red",
                message="Contract location does not match program location",
            )

            notes.append(note)

        if contract.assignee_id in corporations and not tracking.program.is_corporation:
            note = ContractNotification(
                contract=contract,
                icon="fa-home",
                color="orange",
                message="Contract is made for corporation while it should be made directly to the program managers character",
            )

            notes.append(note)

        if contract.assignee_id not in corporations and tracking.program.is_corporation:
            note = ContractNotification(
                contract=contract,
                icon="fa-user",
                color="orange",
                message="Contract is made for the program managers character while it should be made to the managers corporation",
            )

            notes.append(note)

        if not tracking.tracking_number == contract.title:
            note = ContractNotification(
                contract=contract,
                icon="fa-exclamation",
                color="orange",
                message="Contract description contains extra characterse besides the tracking number. The description should be: '%s', instead it is: '%s'"
                % (tracking.tracking_number, contract.title),
            )

            notes.append(note)

        if tracking.donation:
            note = ContractNotification(
                contract=contract,
                icon="fa-hand-holding-usd",
                color="green",
                message="Contact contains a donation",
            )

            notes.append(note)

        try:
            ContractNotification.objects.bulk_create(notes)

            logger.debug(
                "Succesfully added items for contract %s into database"
                % contract.contract_id
            )

        except Error as e:
            logger.error(
                "Error adding items for contract %s: %s" % (contract.contract_id, e)
            )

    def token(self, scopes=None) -> Tuple[Token, int]:
        """returns a valid Token for the owner"""
        token = None
        error = None

        # abort if character is not configured
        if self.character is None:
            logger.error("%s: No character configured to sync", self)
            error = self.ERROR_NO_CHARACTER

        # abort if character does not have sufficient permissions
        elif self.corporation and not self.character.user.has_perm(
            "buybackprogram.manage_programs"
        ):
            logger.error(
                "%s: This character does not have sufficient permission to sync contracts",
                self,
            )
            error = self.ERROR_INSUFFICIENT_PERMISSIONS

        # abort if character does not have sufficient permissions
        elif not self.character.user.has_perm("buybackprogram.manage_programs"):
            logger.error(
                "%s: This character does not have sufficient permission to sync contracts",
                self,
            )
            error = self.ERROR_INSUFFICIENT_PERMISSIONS

        else:
            try:
                # get token
                token = (
                    Token.objects.filter(
                        user=self.character.user,
                        character_id=self.character.character.character_id,
                    )
                    .require_scopes(scopes)
                    .require_valid()
                    .first()
                )
            except TokenInvalidError:
                logger.error("%s: Invalid token for fetching calendars", self)
                error = self.ERROR_TOKEN_INVALID
            except TokenExpiredError:
                logger.error("%s: Token expired for fetching calendars", self)
                error = self.ERROR_TOKEN_EXPIRED
            else:
                if not token:
                    logger.error("%s: No token found with sufficient scopes", self)
                    error = self.ERROR_TOKEN_INVALID

        return token, error

    def __str__(self):
        return (
            self.character.character.character_name
            + " ["
            + self.corporation.corporation_ticker
            + "]"
        )


class Location(models.Model):
    """Location where the buyback program is operated at"""

    name = models.CharField(
        max_length=32, help_text="Structure name where the contracts are accepted at"
    )

    eve_solar_system = models.ForeignKey(
        EveSolarSystem,
        verbose_name="Solar system",
        help_text="System where the buyback structure is located",
        blank=True,
        default=None,
        null=True,
        on_delete=models.deletion.SET_DEFAULT,
        related_name="+",
    )

    owner = models.ForeignKey(
        Owner,
        verbose_name="Manager",
        help_text="Player managing this location",
        null=True,
        on_delete=models.deletion.CASCADE,
    )

    structure_id = models.BigIntegerField(
        verbose_name="Ingame unique ID for structure",
        default=None,
        blank=True,
        null=True,
        help_text="The ID for the structure you wish to accept the contracts at. If left empty the program statistics page will not track if the contract is actually made at the correct structure or not. To get the ID for the structure see readme for getting structure IDs",
    )

    def __str__(self):
        return (
            self.eve_solar_system.name
            + " | "
            + self.name
            + ", ID: "
            + str(self.structure_id)
        )

    @property
    def location_display_name(self):
        return self.eve_solar_system.name + ": " + self.name


class Program(models.Model):
    """An Eve Online buyback program"""

    class Expiration(models.TextChoices):
        DAY1 = "1 Day", _("1 Day")
        DAY3 = "3 Days", _("3 Days")
        WEEK1 = "1 Week", _("1 Week")
        WEEK2 = "2 Weeks", _("2 Weeks")
        WEEK4 = "4 Weeks", _("4 Weeks")

    class PriceType(models.TextChoices):
        BUY = "Buy", _("Buy")
        SELL = "Sell", _("Sell")
        SPLIT = "Split", _("Split")

    name = models.CharField(
        verbose_name="Name/description",
        max_length=64,
        help_text="A name or a description for this program",
        blank=True,
        default="",
    )

    owner = models.ForeignKey(
        Owner,
        verbose_name="Manager",
        help_text="Character that is used to manage this program.",
        on_delete=models.deletion.CASCADE,
        related_name="+",
    )

    is_corporation = models.BooleanField(
        default=False,
        help_text="If we should use the corporation of the manager as the contract receiver instead of the character.",
    )

    location = models.ManyToManyField(
        Location,
        help_text="The location where contracts should be created at.",
        related_name="+",
    )

    expiration = models.CharField(
        max_length=7,
        choices=Expiration.choices,
        default=Expiration.WEEK2,
        help_text="Expiration time the contracts should bet set to.",
    )

    price_type = models.CharField(
        max_length=7,
        choices=PriceType.choices,
        default=PriceType.BUY,
        help_text="What prices should we use as the source for prices. Default: Buy",
    )

    tax = models.IntegerField(
        verbose_name="Default tax",
        default=0,
        blank=False,
        null=False,
        help_text="A default tax rate in this program that is applied on all items.",
        validators=[MaxValueValidator(100), MinValueValidator(0)],
    )

    hauling_fuel_cost = models.IntegerField(
        verbose_name="Hauling fuel cost per m³",
        default=0,
        help_text="ISK per m³ that will be removed from the buy price ie. to cover jump freighet fuel costs. <b>Should not be used with price dencity modifier</b>",
    )

    price_dencity_modifier = models.BooleanField(
        verbose_name="Price density modifier",
        default=False,
        help_text="Should we modify buy prices for items with high volume and low value ie. T1 industrial hulls. <b>Should not be used with hauling fuel cost</b>",
    )

    compression_price_dencity_modifier = models.BooleanField(
        verbose_name="Price density modifier for compressable items",
        default=False,
        help_text="Should we apply price density calculations for items that can be compressed such as ore and ice. If set to False price density tax is not applied on any items that can be compressed.",
    )

    price_dencity_treshold = models.IntegerField(
        verbose_name="Price density threshold",
        default=0,
        null=True,
        help_text="At what ISK/m3 do we start to apply the low isk dencity tax. Tritanium is 500 ISK/m³ @ 5 ISK per unit price. PLEX is 14,5Trillion ISK/m³ @2.9M per unit price.",
    )

    price_dencity_tax = models.IntegerField(
        verbose_name="Price density tax",
        default=0,
        null=True,
        help_text="How much tax do we apply on the low isk density items.",
        validators=[MaxValueValidator(100), MinValueValidator(0)],
    )

    allow_all_items = models.BooleanField(
        default=True,
        help_text="If true all items are accepted to the buyback program. You can set extra taxes or disallow individual items from the program item section. If set to false you need to add each accepted item into the program item section. Blueprints are not included in all items.",
    )

    use_refined_value = models.BooleanField(
        verbose_name="Ore: Use refined value",
        default=False,
        help_text="Take refined value into account when calculating prices for ore, ice and moon goo",
    )

    use_compressed_value = models.BooleanField(
        verbose_name="Ore: Use compressed value",
        default=False,
        help_text="Take compressed value into account when calculating prices for ore, ice and moon goo",
    )

    use_raw_ore_value = models.BooleanField(
        verbose_name="Ore: Use raw value",
        default=True,
        help_text="Take raw ore value into account when calculating prices for ore, ice and moon goo",
    )

    allow_unpacked_items = models.BooleanField(
        verbose_name="Allow unpacked items",
        default=False,
        help_text="Do you want to allow unpacked items in this program such as assembled ship hulls?",
    )

    refining_rate = models.DecimalField(
        verbose_name="Refining rate",
        max_digits=5,
        decimal_places=2,
        default=0,
        null=True,
        help_text="Refining rate to be used if ore refined value is active",
        validators=[MaxValueValidator(100), MinValueValidator(0)],
    )

    blue_loot_npc_price = models.BooleanField(
        verbose_name="NPC price for: Sleeper Components",
        default=False,
        help_text="Use NPC price as value for blue loot",
    )

    red_loot_npc_price = models.BooleanField(
        verbose_name="NPC price for: Triglavian Survey Database",
        default=False,
        help_text="Use NPC price as value for red loot",
    )

    ope_npc_price = models.BooleanField(
        verbose_name="NPC price for: Overseer's Personal Effects",
        default=False,
        help_text="Use NPC price as value for OPEs",
    )

    bonds_npc_price = models.BooleanField(
        verbose_name="NPC price for: Bounty Encrypted Bonds",
        default=False,
        help_text="Use NPC price as value for SCC Encrypted Bond",
    )

    restricted_to_group = models.ManyToManyField(
        Group,
        blank=True,
        related_name="buybackprogram_require_groups",
        help_text="The group(s) that will be able to see this buyback program. If none is selected program is open for all.",
    )
    restricted_to_state = models.ManyToManyField(
        State,
        blank=True,
        related_name="buybackprogram_require_states",
        help_text="The state(s) that will be able to see this buyback program. If none is selected program is open for all.",
    )

    discord_dm_notification = models.BooleanField(
        verbose_name="Discord direct messages for new contracts",
        default=False,
        help_text="Check if you want to receive a direct message notification each time a new contract is created. <b>Requires aa-discordbot app or discordproxy app to work</b>",
    )

    discord_show_item_list = models.BooleanField(
        verbose_name="Show list of items on discord message",
        default=False,
        help_text="Determines if you want to show the contract items in the discord messages. This applies to both webhooks and direct messages.",
    )

    discord_channel_notification = models.CharField(
        verbose_name="Discord webhook for notifications",
        max_length=256,
        null=True,
        blank=True,
        help_text="Discord webhook to send contract notifications to.",
    )

    class Meta:
        default_permissions = ()

    def clean(self):
        super().clean()
        if (
            self.allow_all_items
            and not self.use_refined_value
            and not self.use_compressed_value
            and not self.use_raw_ore_value
        ):
            raise ValidationError(
                "All items are allowed but not a single pricing method for ores is selected. Please use at least one pricing method for ores if all items is allowed."
            )
        if self.price_dencity_modifier and not self.price_dencity_tax:
            raise ValidationError(
                "Price density is used but value for price density tax is missing"
            )
        if self.price_dencity_modifier and not self.price_dencity_treshold:
            raise ValidationError(
                "Price density is used but value for price density threshold is missing"
            )
        if self.use_refined_value and not self.refining_rate:
            raise ValidationError(
                "Refined value is used for ore pricing method but no refining rate is provided. Provide a refining rate to used with this pricing model."
            )


class ProgramItem(models.Model):
    """Items in the buyback program for a corp"""

    program = models.ForeignKey(
        Program,
        on_delete=models.deletion.CASCADE,
        help_text="What program do these items belong to",
    )
    item_type = models.ForeignKey(
        EveType,
        on_delete=models.deletion.CASCADE,
        help_text="Select item for special tax",
    )
    item_tax = models.IntegerField(
        verbose_name="Item tax adjustment",
        default=0,
        null=True,
        help_text="How much do you want to adjust the default tax on this item. Can be a positive or a negative value.",
        validators=[MaxValueValidator(100), MinValueValidator(-100)],
    )

    disallow_item = models.BooleanField(
        verbose_name="Disallow item in program",
        default=False,
        help_text="You can disallow an item from a buyback location. It will return 0 price if disallowed.",
    )

    class Meta:
        default_permissions = ()
        unique_together = ["program", "item_type"]


class ItemPrices(models.Model):
    eve_type = models.OneToOneField(
        EveType,
        on_delete=models.deletion.CASCADE,
        unique=True,
    )
    buy = models.BigIntegerField()
    sell = models.BigIntegerField()
    updated = models.DateTimeField()


class Contract(models.Model):
    assignee_id = models.IntegerField()
    availability = models.CharField(max_length=20)
    contract_id = models.IntegerField(unique=True)
    date_completed = models.DateTimeField(null=True)
    date_expired = models.DateTimeField(null=True)
    date_issued = models.DateTimeField()
    for_corporation = models.BooleanField()
    issuer_corporation_id = models.IntegerField()
    issuer_id = models.IntegerField()
    start_location_id = models.BigIntegerField(null=True)
    location_name = models.CharField(max_length=128, null=True)
    price = models.BigIntegerField()
    status = models.CharField(max_length=30)
    title = models.CharField(max_length=128)
    volume = models.BigIntegerField()
    no_tracking = models.BooleanField(default=False)

    def __str__(self) -> str:
        return str(self.contract_id)


class ContractItem(models.Model):
    contract = models.ForeignKey(
        Contract,
        on_delete=models.deletion.CASCADE,
        help_text="What contract do these items belong to",
    )

    eve_type = models.ForeignKey(
        EveType,
        on_delete=models.deletion.CASCADE,
        help_text="Item type information",
    )

    quantity = models.IntegerField()


class ContractNotification(models.Model):
    contract = models.ForeignKey(
        Contract,
        on_delete=models.deletion.CASCADE,
    )

    icon = models.CharField(
        max_length=64,
    )

    color = models.CharField(
        max_length=32,
    )

    message = models.CharField(
        max_length=1024,
    )


class Tracking(models.Model):
    program = models.ForeignKey(
        Program,
        null=True,
        on_delete=models.deletion.SET_NULL,
        related_name="+",
    )
    contract = models.ForeignKey(
        Contract,
        null=True,
        blank=True,
        on_delete=models.deletion.SET_NULL,
    )
    issuer_user = models.ForeignKey(
        User,
        on_delete=models.deletion.CASCADE,
        related_name="+",
    )
    value = models.BigIntegerField(null=False)
    taxes = models.BigIntegerField(null=False)
    hauling_cost = models.BigIntegerField(null=False)
    donation = models.BigIntegerField(null=True, blank=True)
    net_price = models.BigIntegerField(null=False)
    tracking_number = models.CharField(max_length=32)
    created_at = models.DateTimeField(null=True, blank=True)


class TrackingItem(models.Model):
    tracking = models.ForeignKey(
        Tracking,
        on_delete=models.deletion.CASCADE,
        help_text="What tracking do these items belong to",
    )

    eve_type = models.ForeignKey(
        EveType,
        on_delete=models.deletion.CASCADE,
        help_text="Item type information",
    )

    buy_value = models.BigIntegerField(null=False)

    quantity = models.IntegerField()


class UserSettings(models.Model):
    """
    User settings
    """

    user = models.ForeignKey(
        User,
        related_name="+",
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET(get_sentinel_user),
    )

    disable_notifications = models.BooleanField(
        default=False,
    )

    class Meta:
        """
        Meta definitions
        """

        default_permissions = ()
        verbose_name = _("User Settings")
        verbose_name_plural = _("User Settings")
