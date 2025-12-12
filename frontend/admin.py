from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'プロファイル'


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_is_material_manager')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'profile__is_material_manager')
    
    def get_is_material_manager(self, obj):
        return obj.profile.is_material_manager if hasattr(obj, 'profile') else False
    get_is_material_manager.short_description = '教材管理者'
    get_is_material_manager.boolean = True


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_material_manager', 'created_at')
    list_filter = ('is_material_manager', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
