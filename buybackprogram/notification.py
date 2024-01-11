"""
notifications helper
"""
import requests

from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import intcomma

from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger

from buybackprogram.app_settings import (
    aa_discordnotify_active,
    allianceauth_discordbot_active,
)

logger = get_extension_logger(__name__)


def send_aa_discordbot_notification(user, message):
    # If discordproxy app is not active we will check if aa-discordbot is active
    if allianceauth_discordbot_active():
        from aadiscordbot.tasks import send_message
        from discord import Embed

        contract = message["contract"]
        tracking = message["tracking"]

        embed = Embed(
            description=message["contract_items"],
            title=message["title"],
            color=message["color"],
        )

        embed.add_field(
            name="Date issued", value=str(contract.date_issued), inline=True
        )
        embed.add_field(
            name="Issued from", value=str(message["assigned_from"]), inline=True
        )
        embed.add_field(
            name="Issued to", value=str(message["assigned_to"]), inline=True
        )
        embed.add_field(name="Location", value=str(contract.location_name), inline=True)
        embed.add_field(
            name="Tracking #", value=str(tracking.tracking_number), inline=True
        )
        embed.add_field(
            name="Volume",
            value=str(intcomma(int(contract.volume))) + " m3",
            inline=True,
        )
        embed.add_field(
            name="Value", value=str(intcomma(int(contract.price))) + " ISK", inline=True
        )
        embed.add_field(name="Notes", value=str(message["notes"]), inline=False)

        send_message(user_pk=user, embed=embed)

        logger.debug("Sent discord DM to user %s" % user)
    else:
        logger.debug(
            "No discord notification modules active. Will not send user notifications"
        )


def send_aa_discordbot_channel_notification(channel_id, message):
    # If discordproxy app is not active we will check if aa-discordbot is active
    if allianceauth_discordbot_active():
        import aadiscordbot.tasks

        aadiscordbot.tasks.send_channel_message_by_discord_id.delay(
            channel_id, message, embed=True
        )

        logger.debug("Sent notification to channel %s" % channel_id)
    else:
        logger.debug(
            "No discord notification modules active. Will not send user notifications"
        )


# This will set a auth notification and send the user a direct notification on discord if requested for new contracts
def send_user_notification(user: User, level: str, message: dict) -> None:
    contract = message["contract"]
    tracking = message["tracking"]

    msg = (
        "Date issued: "
        + str(contract.date_issued)
        + "\n"
        + "Issued from: "
        + str(message["assigned_from"])
        + "\n"
        + "Location: "
        + str(contract.location_name)
        + "\n"
        + "Tracking #: "
        + str(tracking.tracking_number)
        + "\n"
        + "Price #: "
        + str(intcomma(int(contract.price)))
        + " ISK"
        + "\n"
    )
    notify(
        user=user,
        title=message["title"],
        level=level,
        message=msg,
    )

    if not aa_discordnotify_active():
        # Check if the discordproxy module is active. We will use it as our priority app for notifications
        try:
            from discordproxy.client import DiscordClient
            from discordproxy.discord_api_pb2 import Embed
            from discordproxy.exceptions import (
                DiscordProxyException,
                DiscordProxyGrpcError,
            )

            logger.debug("User has a active discord account")

            client = DiscordClient()

            contract = message["contract"]
            tracking = message["tracking"]

            fields = []

            fields.append(
                Embed.Field(
                    name="Date issued", value=str(contract.date_issued), inline=True
                )
            )
            fields.append(
                Embed.Field(
                    name="Issued from", value=str(message["assigned_from"]), inline=True
                )
            )
            fields.append(
                Embed.Field(
                    name="Issued to", value=str(message["assigned_to"]), inline=True
                )
            )
            fields.append(
                Embed.Field(
                    name="Location", value=str(contract.location_name), inline=True
                )
            )
            fields.append(
                Embed.Field(
                    name="Tracking #", value=str(tracking.tracking_number), inline=True
                )
            )
            fields.append(
                Embed.Field(
                    name="Volume",
                    value=str(intcomma(int(contract.volume))) + " m3",
                    inline=True,
                )
            )
            fields.append(
                Embed.Field(
                    name="Value",
                    value=str(intcomma(int(contract.price))) + " ISK",
                    inline=True,
                )
            )
            fields.append(
                Embed.Field(name="Notes", value=str(message["notes"]), inline=False)
            )

            embed = Embed(
                title=message["title"],
                color=message["color"],
                fields=fields,
                author=Embed.Author(name="AA Buyback Program"),
            )

            if user.discord.uid:
                try:
                    logger.debug(
                        "Sending notification for discord user %s" % user.discord.uid
                    )
                    client.create_direct_message(user_id=user.discord.uid, embed=embed)
                except DiscordProxyGrpcError:
                    logger.debug(
                        "Discordprox is installed but not running, failed to send message. Attempting to send via aa-discordbot instead."
                    )
                    send_aa_discordbot_notification(user.pk, message)

                except DiscordProxyException as ex:
                    logger.error(
                        "An error occured when trying to create a message: %s" % ex
                    )
            else:
                logger.error(
                    "User has no active discord accounts on AUTH, passing DM message."
                )

        except ModuleNotFoundError:
            send_aa_discordbot_notification(user.pk, message)
    else:
        logger.debug(
            "Aadiscordnotify is already active, passing notification sending to prevent multiple notifications"
        )


# This will send the contract notification to a selected webhook on discord
def send_message_to_discord_channel(
    webhook, message: dict, embed: bool = False
) -> None:
    logger.debug("Notifications: Starting to parse channel webhook notification")

    url = webhook  # webhook url, from here: https://i.imgur.com/f9XnAew.png

    # for all params, see https://discordapp.com/developers/docs/resources/webhook#execute-webhook
    data = {}

    # leave this out if you dont want an embed
    # for all params, see https://discordapp.com/developers/docs/resources/channel#embed-object

    contract = message["contract"]
    tracking = message["tracking"]

    data["embeds"] = [
        {
            "description": message["contract_items"],
            "title": message["title"],
            "color": message["color"],
            "fields": [
                {
                    "name": "Date issued",
                    "value": str(contract.date_issued),
                    "inline": True,
                },
                {
                    "name": "Issued from",
                    "value": str(message["assigned_from"]),
                    "inline": True,
                },
                {
                    "name": "Issued to",
                    "value": str(message["assigned_to"]),
                    "inline": True,
                },
                {
                    "name": "Location",
                    "value": str(contract.location_name),
                    "inline": True,
                },
                {
                    "name": "Tracking #",
                    "value": str(tracking.tracking_number),
                    "inline": True,
                },
                {
                    "name": "Volume",
                    "value": str(intcomma(int(contract.volume))) + " m3",
                    "inline": True,
                },
                {
                    "name": "Value",
                    "value": str(intcomma(int(contract.price))) + " ISK",
                    "inline": True,
                },
                {"name": "Notes", "value": str(message["notes"]), "inline": False},
            ],
        }
    ]

    result = requests.post(url, json=data)

    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        logger.error(err)
    else:
        logger.debug(
            "Payload delivered successfully, code {}.".format(result.status_code)
        )
