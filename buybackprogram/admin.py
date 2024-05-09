from django.contrib import admin

from .models import Contract, Faq, Location, Owner, Program

# Register your models here.


class ProgramAdmin(admin.ModelAdmin):
    model = Program

    list_display = (
        "owner",
        "_location",
        "is_corporation",
        "hauling_fuel_cost",
        "tax",
        "refining_rate",
        "price_dencity_modifier",
        "allow_all_items",
        "use_refined_value",
        "use_compressed_value",
        "use_raw_ore_value",
        "allow_unpacked_items",
    )

    @classmethod
    def _location(cls, obj):
        names = [x.name for x in obj.location.all().order_by("name")]

        if names:
            return ", ".join(names)
        else:
            return None

    _location.short_description = "Location"
    _location.admin_order_field = "location__name"


class FaqAdmin(admin.ModelAdmin):
    model = Program

    list_display = (
        "header",
        "body",
    )


admin.site.register(Program, ProgramAdmin)

admin.site.register(Owner)

admin.site.register(Contract)

admin.site.register(Location)

admin.site.register(Faq, FaqAdmin)
