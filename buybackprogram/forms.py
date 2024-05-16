from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.translation import gettext as _
from eveuniverse.models import EveMarketGroup, EveSolarSystem, EveType

from buybackprogram.models import Location, Owner, Program, UserSettings


class ProgramForm(forms.ModelForm):
    # specify the name of model to use
    class Meta:
        model = Program
        fields = "__all__"
        labels = {
            "price_dencity_modifier": "Price density modifier",
            "price_dencity_treshold": "Price density threshold",
            "price_dencity_tax": "Price density tax",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)

        super(ProgramForm, self).__init__(*args, **kwargs)
        self.fields["owner"].queryset = Owner.objects.filter(user=self.user)
        self.fields["location"].queryset = Location.objects.filter(
            owner__user=self.user
        )


class ProgramItemForm(forms.Form):
    item_type = forms.ModelChoiceField(
        queryset=EveType.objects.none(),
        label="Item type",
        help_text="Add the name of item which you want to determine an tax on. Once you start typing, we offer suggestions",
        empty_label=None,
    )
    item_tax = forms.IntegerField(
        label="Tax amount",
        initial=0,
        validators=[MaxValueValidator(100), MinValueValidator(-100)],
        help_text="Set an tax on the item. If program default tax is defined this tax will be added on top of the program tax. If program does not allow all items this tax is used to calculate the tax for the product.",
    )
    disallow_item = forms.BooleanField(
        label="Disallow item in this program",
        help_text="If you want to prevent any prices to be given for this item in this program you can check this box.",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        value = kwargs.pop("value", None)

        super(ProgramItemForm, self).__init__(*args, **kwargs)

        if value is not None:
            self.fields["item_type"].queryset = EveType.objects.filter(
                pk=value,
                published=True,
            ).exclude(eve_group__eve_category__id=9)


class ProgramMarketGroupForm(forms.Form):
    marketgroup = forms.ModelChoiceField(
        queryset=EveMarketGroup.objects.none(),
        label="Item type",
        help_text="Add the name of item which you want to determine an tax on. Once you start typing, we offer suggestions",
        empty_label=None,
    )
    item_tax = forms.IntegerField(
        label="Tax amount",
        initial=0,
        validators=[MaxValueValidator(100), MinValueValidator(-100)],
        help_text="Set an tax on the item. If program default tax is defined this tax will be added on top of the program tax. If program does not allow all items this tax is used to calculate the tax for the product.",
    )
    disallow_item = forms.BooleanField(
        label="Disallow item in this program",
        help_text="If you want to prevent any prices to be given for this item in this program you can check this box.",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        value = kwargs.pop("value", None)

        super(ProgramMarketGroupForm, self).__init__(*args, **kwargs)

        if value is not None:
            self.fields["marketgroup"].queryset = EveMarketGroup.objects.filter(
                pk=value,
            )


class LocationForm(forms.Form):
    eve_solar_system = forms.ModelChoiceField(
        queryset=EveSolarSystem.objects.none(),
        label="Solar system",
        help_text="Select solar system name. Start typing and we will give you suggestions.",
        empty_label=None,
    )
    name = forms.CharField(
        label="Structure/station name",
        help_text="A name or identification tag of the structure where the items should be contracted at. Does not need to match ingame name.",
        max_length=32,
    )

    structure_id = forms.CharField(
        required=False,
        label="Structure/station ID",
        help_text="The ingame ID for the structure you wish to accept the contracts at. <strong>If left empty the program statistics page will not track if the contract is actually made at the correct structure or not.</strong>",
    )

    def __init__(self, *args, **kwargs):
        value = kwargs.pop("value", None)
        self.user = kwargs.pop("user", None)

        super(LocationForm, self).__init__(*args, **kwargs)

        if value is not None:
            self.fields["eve_solar_system"].queryset = EveSolarSystem.objects.filter(
                pk=value,
            )


class CalculatorForm(forms.Form):
    items = forms.CharField(
        widget=forms.Textarea,
        label="Items",
        help_text="Copy and paste the item data from your inventory. Item types not in this buyback program will be ignored",
    )
    donation = forms.IntegerField(
        label="Donation %",
        initial=0,
        help_text="You can set a optional donation percentage on your contract",
        validators=[MaxValueValidator(100), MinValueValidator(0)],
    )
    additional_notes = forms.CharField(
        label="Additional Notes",
        help_text="You can set additional notes for your contract in here",
        required=False,  # Make sure it's not required
    )


class UserSettingsForm(forms.ModelForm):
    """
    User settings form
    """

    disable_notifications = forms.BooleanField(
        initial=False,
        required=False,
        label=_(
            "Disable notifications. "
            "(Auth and Discord, if a relevant module is installed)"
        ),
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """
        Meta definitions
        """

        model = UserSettings
        fields = ["disable_notifications"]
