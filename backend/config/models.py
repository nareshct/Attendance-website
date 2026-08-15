import binascii
import os

from django.conf import settings
from django.db import models


class AuthToken(models.Model):
    """One row per *login*, not per user — unlike DRF's built-in
    rest_framework.authtoken.Token (a OneToOneField to user, so a whole
    account only ever has one live token). That shared-token design meant
    logging in on a second device silently handed back the same key the
    first device was already using, and logging out — or any single
    device's session getting invalidated — deleted that one shared row and
    signed every device out at once. AuthToken gives each login its own key
    so devices can't step on each other; see LoginView/LogoutView in
    config/views.py and AuthTokenAuthentication in config/authentication.py.
    """

    key = models.CharField(max_length=40, primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='auth_tokens', on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    @staticmethod
    def generate_key():
        return binascii.hexlify(os.urandom(20)).decode()

    def __str__(self):
        return f'{self.user}: {self.key[:8]}…'
