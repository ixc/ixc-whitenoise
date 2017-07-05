from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.http import FileResponse
from django.utils.functional import empty
from django.utils.six.moves.urllib.parse import urlparse
from whitenoise.middleware import WhiteNoiseMiddleware
from whitenoise.utils import ensure_leading_trailing_slash

from ixc_whitenoise import appsettings
from ixc_whitenoise.storage import UniqueStorage


class StripVaryHeaderMiddleware(object):

    def process_response(self, request, response):
        """
        Remove `Vary` header to work around an IE bug. See:
        http://stackoverflow.com/a/23410136
        """
        if isinstance(response, FileResponse):
            del response['vary']
        return response


# Serve regular and dedupe media as well as static files.
class WhiteNoiseMiddleware(WhiteNoiseMiddleware):

    config_attrs = WhiteNoiseMiddleware.config_attrs + (
        'dedupe_prefix',
        'media_prefix',
    )
    dedupe_prefix = None
    media_prefix = None

    def __init__(self, *args, **kwargs):
        super(WhiteNoiseMiddleware, self).__init__(*args, **kwargs)
        if self.dedupe_root:
            self.add_files(self.dedupe_root, prefix=self.dedupe_prefix)
        if self.media_root:
            self.add_files(self.media_root, prefix=self.media_prefix)

    def check_settings(self, settings):
        super(WhiteNoiseMiddleware, self).check_settings(settings)
        if self.dedupe_prefix == '/':
            dedupe_url = getattr(settings, 'DEDUPE_URL', '').rstrip('/')
            raise ImproperlyConfigured(
                'DEDUPE_URL setting must include a path component, for '
                'example: DEDUPE_URL = {0!r}'.format(dedupe_url + '/dd/')
            )
        if self.media_prefix == '/':
            media_url = getattr(settings, 'MEDIA_URL', '').rstrip('/')
            raise ImproperlyConfigured(
                'MEDIA_URL setting must include a path component, for '
                'example: MEDIA_URL = {0!r}'.format(media_url + '/media/')
            )

    def configure_from_settings(self, settings):
        # Prefixes.
        self.dedupe_prefix = urlparse(appsettings.DEDUPE_URL or '').path
        self.media_prefix = urlparse(settings.MEDIA_URL or '').path

        super(WhiteNoiseMiddleware, self).configure_from_settings(settings)

        # Dedupe media.
        self.dedupe_prefix = ensure_leading_trailing_slash(self.dedupe_prefix)
        self.dedupe_root = appsettings.DEDUPE_ROOT

        # Media.
        self.media_prefix = ensure_leading_trailing_slash(self.media_prefix)
        self.media_root = settings.MEDIA_ROOT

    def is_immutable_file(self, path, url):
        if super(WhiteNoiseMiddleware, self).is_immutable_file(path, url):
            return True
        if self.dedupe_prefix and url.startswith(self.dedupe_prefix):
            return True
        return False
