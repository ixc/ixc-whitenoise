import hashlib
import logging
import posixpath
import re

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.functional import empty, LazyObject
from whitenoise.storage import \
    CompressedManifestStaticFilesStorage, HelpfulExceptionMixin, \
    MissingFileError

from ixc_whitenoise import appsettings
from ixc_whitenoise.models import UniqueFile

logger = logging.getLogger(__name__)


# Log a warning instead of raising an exception when a referenced file is
# not found. These are often in 3rd party packages and outside our control.
class HelpfulWarningMixin(HelpfulExceptionMixin):

    def make_helpful_exception(self, exception, name):
        exception = super(HelpfulWarningMixin, self) \
            .make_helpful_exception(exception, name)
        if isinstance(exception, MissingFileError):
            logger.warning('\n\nWARNING: %s' % exception)
            return False
        return exception


# Don't try to rewrite URLs with unknown schemes.
class RegexURLConverterMixin(object):

    def url_converter(self, name, template=None):
        converter = super(RegexURLConverterMixin, self) \
            .url_converter(name, template)

        def custom_converter(matchobj):
            matched, url = matchobj.groups()
            if re.match(r'(?i)([a-z]+://|//|#|data:)', url):
                return matched
            return converter(matchobj)

        return custom_converter


class UniqueMixin(object):
    """
    Save files with unique names so they can be deduplicated and cached forever.
    """

    def _save(self, name, content):
        """
        Save file with a content hash as its name and create a record of its
        original name.
        """

        # Rewind content to ensure we generate a complete hash.
        content.seek(0)

        # Generate content hash.
        md5 = hashlib.md5()
        for chunk in content.chunks():
            md5.update(chunk)
        content_hash = md5.hexdigest()

        # Determine unique name.
        path, _ = posixpath.split(name)
        _, ext = posixpath.splitext(name)
        ext = appsettings.DEDUPE_EXTENTIONS.get(ext.lower(), ext.lower())
        unique_name = posixpath.join(path, content_hash + ext)

        # Abort without saving because existing files with the same name must
        # also have the same content.
        if self.exists(unique_name):
            return unique_name

        # Save and create a record of the original name.
        unique_name = super(UniqueMixin, self)._save(unique_name, content)
        if unique_name != name:
            UniqueFile.objects.create(name=unique_name, original_name=name)

        return unique_name

    def get_available_name(self, name):
        """
        Disable name conflict resolution.
        """
        return name

    def original_name(self, name):
        """
        Return the latest original name for a file.
        """
        try:
            return UniqueFile.objects \
                .filter(name=name).latest('-pk').original_name
        except UniqueFile.DoesNotExist:
            return name


class CompressedManifestStaticFilesStorage(
        HelpfulWarningMixin,
        RegexURLConverterMixin,
        CompressedManifestStaticFilesStorage):
    pass


class UniqueStorage(UniqueMixin, FileSystemStorage):
    pass


def unlazy_storage(storage):
    """
    If `storage` is lazy, return the wrapped storage object.
    """
    while isinstance(storage, LazyObject):
        if storage._wrapped is empty:
            storage._setup()
        storage = storage._wrapped
    return storage
