import posixpath

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.http import HttpResponseRedirect
from django.utils.functional import empty
from six.moves.urllib.parse import urlparse
from whitenoise.middleware import WhiteNoiseMiddleware

try:
    from whitenoise.string_utils import ensure_leading_trailing_slash  # >=4.0b1
except ImportError:
    from whitenoise.utils import ensure_leading_trailing_slash

from ixc_whitenoise.storage import UniqueMixin, unlazy_storage


class StripVaryHeaderMiddleware(object):

    def process_response(self, request, response):
        """
        Remove `Vary` header to work around an IE bug. See:
        http://stackoverflow.com/a/23410136
        """
        # FileResponse was added in Django 1.7.4. Do nothing when it is not
        # available.
        try:
            from django.http import FileResponse
        except ImportError:
            return response
        if isinstance(response, FileResponse):
            del response['vary']
        return response


# Serve media as well as static files.
# Redirect requests for deduplicated unique storage.
class WhiteNoiseMiddleware(WhiteNoiseMiddleware):

    # whitenoise 6 doesn't have config_attrs any more.
    try:
        config_attrs = WhiteNoiseMiddleware.config_attrs + ('media_prefix', )
    except AttributeError:
        pass
    media_prefix = None

    def __init__(self, *args, **kwargs):
        # This replaces the `config_attrs` which was removed in v6 (I think)
        if not hasattr(self, "config_attrs"):
            self.media_prefix = kwargs.pop(
                "media_prefix", urlparse(settings.MEDIA_URL or '').path
            )
        super(WhiteNoiseMiddleware, self).__init__(*args, **kwargs)
        # this doesn't work becaues it hasn't called configured_from_settings
        # - maybe it doesn't do that any more? If not, I wonder if trying to
        # maintain backward-compatible support is Too Hard
        self.media_prefix = ensure_leading_trailing_slash(self.media_prefix)
        self.media_root = settings.MEDIA_ROOT
        if self.media_root:
            self.add_files(self.media_root, prefix=self.media_prefix)

    # this doesn't happen any more in WN 6
    def check_settings(self, settings):
        raise NotImplementedError()
        super(WhiteNoiseMiddleware, self).check_settings(settings)
        if self.media_prefix == '/':
            media_url = getattr(settings, 'MEDIA_URL', '').rstrip('/')
            raise ImproperlyConfigured(
                'MEDIA_URL setting must include a path component, for '
                'example: MEDIA_URL = {0!r}'.format(media_url + '/media/')
            )

    # this doesn't happen any more in WN 6
    def configure_from_settings(self, settings):
        raise NotImplementedError()
        self.media_prefix = urlparse(settings.MEDIA_URL or '').path
        super(WhiteNoiseMiddleware, self).configure_from_settings(settings)
        self.media_prefix = ensure_leading_trailing_slash(self.media_prefix)
        self.media_root = settings.MEDIA_ROOT

    # Files with unique names are always immutable
    def immutable_file_test(self, path, url): # looks like this was never named is_immutable_file?

        if super(WhiteNoiseMiddleware, self).immutable_file_test(path, url):
            return True
        # `MEDIA_ROOT` and `MEDIA_URL` are used with the default storage class.
        # Only assume media is immutable if `UniqueMixin` is the default
        # storage class.
        storage = unlazy_storage(default_storage)
        if isinstance(storage, UniqueMixin) and \
                url.startswith(self.media_prefix):
            return True
        return False

    def process_response(self, request, response, *args, **kwargs):
        """
        Redirect requests for deduplicated unique storage.
        """
        from ixc_whitenoise.models import UniqueFile  # Avoid circular import
        if response.status_code == 404 and \
                request.path_info.startswith(self.media_prefix):
            original_name = request.path_info[len(self.media_prefix):]
            # There could be more than one `UniqueFile` object for a given
            # name. Redirect to the most recently deduplicated one.
            unique_file = UniqueFile.objects \
                .filter(original_name=original_name).last()
            if unique_file:
                response = HttpResponseRedirect(posixpath.join(
                    self.media_prefix,
                    unique_file.name,
                ))
        return response

