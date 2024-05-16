from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import F, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.html import format_html
from eveuniverse.models import EveMarketGroup, EveSolarSystem, EveType

from allianceauth.services.hooks import get_extension_logger

from buybackprogram.forms import UserSettingsForm
from buybackprogram.models import Faq, Program, UserSettings
from buybackprogram.utils import messages_plus

logger = get_extension_logger(__name__)


@login_required
@permission_required("buybackprogram.basic_access")
def index(request):
    user_groups = request.user.groups.all()

    logger.debug("User %s has groups: %s" % (request.user, user_groups))

    user_state = [request.user.profile.state]

    logger.debug("User %s state is : %s" % (request.user, user_state))

    try:
        user_settings = UserSettings.objects.get(user=request.user)
    except UserSettings.DoesNotExist:
        # create the default settings in the DB for the current user
        user_settings = UserSettings()
        user_settings.user = request.user
        user_settings.save()

        # get the user settings again
        user_settings = UserSettings.objects.get(user=request.user)

    program = (
        Program.objects.filter(
            Q(restricted_to_group__in=request.user.groups.all())
            | Q(restricted_to_group__isnull=True)
            | Q(owner__user=request.user)
        )
        .filter(
            Q(restricted_to_state=request.user.profile.state)
            | Q(restricted_to_state__isnull=True)
            | Q(owner__user=request.user)
        )
        .distinct()
    )

    context = {"programs": program}

    return render(request, "buybackprogram/index.html", context)


@login_required
@permission_required("buybackprogram.basic_access")
def faq(request):
    faq = Faq.objects.all()

    context = {
        "faqs": faq,
    }

    return render(request, "buybackprogram/faq.html", context)


@login_required
@permission_required("buybackprogram.manage_programs")
def item_autocomplete(request):
    items = EveType.objects.filter(published=True).exclude(
        eve_group__eve_category__id=9
    )

    q = request.GET.get("q", None)

    if q is not None:
        items = items.filter(name__icontains=q)

    items = items.annotate(
        value=F("id"),
        text=F("name"),
    ).values("value", "text")

    return JsonResponse(list(items), safe=False)


@login_required
@permission_required("buybackprogram.manage_programs")
def solarsystem_autocomplete(request):
    items = EveSolarSystem.objects.all()

    q = request.GET.get("q", None)

    if q is not None:
        items = items.filter(name__icontains=q)

    items = items.annotate(
        value=F("id"),
        text=F("name"),
    ).values("value", "text")

    return JsonResponse(list(items), safe=False)


@login_required
@permission_required("buybackprogram.manage_programs")
def marketgroup_autocomplete(request):
    items = EveMarketGroup.objects.all()

    q = request.GET.get("q", None)

    if q is not None:
        items = items.prefetch_related("parent_market_group").filter(name__icontains=q)

    items = items.annotate(
        value=F("id"),
        text=Concat(
            F("parent_market_group__parent_market_group__name"),
            Value(" -> "),
            F("parent_market_group__name"),
            Value(" -> "),
            F("name"),
        ),
    ).values("value", "text")

    print(items)

    return JsonResponse(list(items), safe=False)


@login_required
@permission_required("buybackprogram.basic_access")
def user_settings_edit(request):
    try:
        user_settings = UserSettings.objects.get(user=request.user)
    except UserSettings.DoesNotExist:
        # create the default settings in the DB for the current user
        user_settings = UserSettings()
        user_settings.user = request.user
        user_settings.save()

        # get the user settings again
        user_settings = UserSettings.objects.get(user=request.user)

    if request.method != "POST":
        user_settings_form = UserSettingsForm(instance=user_settings)
    else:
        user_settings_form = UserSettingsForm(request.POST, instance=user_settings)

        # check whether it's valid:
        if user_settings_form.is_valid():
            # user_settings.user = request.user
            user_settings.disable_notifications = user_settings_form.cleaned_data[
                "disable_notifications"
            ]
            user_settings.save()

            if user_settings.disable_notifications:
                messages_plus.success(
                    request,
                    format_html(
                        "Discord notifications <strong>disabled</strong>",
                    ),
                )
            else:
                messages_plus.success(
                    request,
                    format_html(
                        "Discord notifications <strong>enabled</strong>",
                    ),
                )

            return redirect("buybackprogram:index")

    context = {
        "form": user_settings_form,
    }

    return render(request, "buybackprogram/user_settings.html", context)
