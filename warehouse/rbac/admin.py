from django.contrib import admin
from .models import Role, Permission, UserRole
from .models import LoginLogs
from .models import WMSAdmin 

admin.site.register(Role)
admin.site.register(Permission)
admin.site.register(UserRole)
admin.site.register(LoginLogs)


@admin.register(WMSAdmin)
class WMSAdminAdmin(admin.ModelAdmin):

    list_display = (
        "admin_id",
        "username",
        "email",
        "role",
        "created_at"
    )

    search_fields = ("username", "email")