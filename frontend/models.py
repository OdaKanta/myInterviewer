from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """ユーザープロファイル"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_material_manager = models.BooleanField(default=False, verbose_name="教材管理者")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "ユーザープロファイル"
        verbose_name_plural = "ユーザープロファイル"
    
    def __str__(self):
        return f"{self.user.username} - {'教材管理者' if self.is_material_manager else '一般ユーザー'}"


# ユーザー作成時に自動でプロファイルを作成
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        UserProfile.objects.create(user=instance)
