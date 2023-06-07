import hashlib
import logging
import posixpath
import re
import six

import django
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.functional import empty, LazyObject
from whitenoise.storage import \
    CompressedManifestStaticFilesStorage, MissingFileError
# HelpfulExceptionMixin was removed in Whitenoise 6.3.0
try:
    from whitenoise.storage import HelpfulExceptionMixin as HelpfulExceptionMixinIfAvailable
except ImportError:
    HelpfulExceptionMixinIfAvailable = object


logger = logging.getLogger(__name__)

DEDUPE_EXTENTIONS = {
    '.jpeg': '.jpg',
    '.yaml': '.yml',
}
DEDUPE_EXTENTIONS.update(
    getattr(settings, 'IXC_WHITENOISE_DEDUPE_EXTENTIONS', {}))

DEDUPE_PATH_PREFIX = getattr(
    settings, 'IXC_WHITENOISE_DEDUPE_PATH_PREFIX', 'dd')

HASH_LENGTH = getattr(
    settings, 'IXC_WHITENOISE_ORIGINAL_BASENAME_HASH_LENGTH', 7)

ORIGINAL_BASENAME = getattr(
    settings, 'IXC_WHITENOISE_ORIGINAL_BASENAME', False)


# Log a warning instead of raising an exception when a referenced file is
# not found. These are often in 3rd party packages and outside our control.
class HelpfulWarningMixin(HelpfulExceptionMixinIfAvailable):

    def make_helpful_exception(self, exception, name):
        exception = super(HelpfulWarningMixin, self) \
            .make_helpful_exception(exception, name)
        if isinstance(exception, MissingFileError):
            logger.warning('\n\nWARNING: %s' % exception)
            return False
        return exception


# Don't try to rewrite URLs with unknown schemes.
class RegexURLConverterMixin(object):

    def url_converter(self, name, hashed_files=None, template=None):
        # `hashed_files` parameter is only supported since Django 1.11
        # https://github.com/django/django/commit/53bffe8d03f01bd3214a5404998cb965fb28cd0b
        if django.VERSION[:2] >= (1, 11):
            if hashed_files is None:
                hashed_files = {}
            converter = super(RegexURLConverterMixin, self).url_converter(
                name, hashed_files=hashed_files, template=template)
        else:
            converter = super(RegexURLConverterMixin, self).url_converter(
                name, template=template)

        def custom_converter(matchobj):
            # Django did not name the groups until v3
            try:
                matches = matchobj.groupdict()
                matched = matches["matched"]
                url = matches["url"]
            except KeyError:
                matched, url = matchobj.groups()
            if re.match(r'(?i)([a-z]+://|//|#|data:)', url):
                return matched
            return converter(matchobj)

        return custom_converter


class UniqueMixin(object):
    """
    Save files with unique names so they can be deduplicated and cached forever.
    """

    def generate_content_hash(self, content):
        # Rewind content to ensure we generate a complete hash.
        content.seek(0)
        # Generate content hash.
        md5 = hashlib.md5()
        for chunk in content.chunks():
            # If content is a string, instead of bytes, encode with UTF-8 for
            # hashing to work. While we're assuming that the file has been
            # decoded with UTF-8, the only scenario in which we've encountered
            # this issue is when attachments for outgoing mail are being saved,
            # in which case Django's EmailMessage.attach() is guaranteed to
            # have decoded using UTF-8.
            if isinstance(chunk, six.text_type):
                chunk = chunk.encode()
            md5.update(chunk)
        return md5.hexdigest()

    def get_content_hash(self, name):
        """
        Return the content hash for the named file. Local storage classes should
        generate it. Remote storage classes should get it from metadata, if
        available (e.g. the Etag header from S3).
        """
        md5 = hashlib.md5()
        with self.open(name, 'rb') as content:
            for chunk in content.chunks():
                md5.update(chunk)
        content_hash = md5.hexdigest()
        return content_hash

    def get_unique_name(self, name, content_hash):
        """
        Determine the unique name for a given original name and content hash.
        """

        # Get path, name and extension.
        path, basename = posixpath.split(name)
        basename, ext = posixpath.splitext(basename)
        ext = DEDUPE_EXTENTIONS.get(ext.lower(), ext.lower())

        # Strip dedupe path prefix and unique hash suffix.
        path = re.sub(r'^%s/' % re.escape(DEDUPE_PATH_PREFIX), '', path)
        basename = re.sub(r'\.[0-9a-z]+$', '', basename)

        # Determine unique name. An abbreviated hash is sufficient when
        # combined with the original name. Otherwise use the full hash.
        if ORIGINAL_BASENAME:
            basename = '%s.%s' % (basename, content_hash[:HASH_LENGTH])
        else:
            basename = content_hash

        return posixpath.join(DEDUPE_PATH_PREFIX, path, basename + ext)

    def _save(self, name, content):
        """
        Save file with a content hash as its name and create a record of its
        original name.
        """
        from ixc_whitenoise.models import UniqueFile  # Avoid circular import

        # Get content hash.
        content_hash = self.generate_content_hash(content)

        # Get unique name.
        unique_name = self.get_unique_name(name, content_hash)

        # Create a record of the original name.
        if unique_name != name:
            UniqueFile.objects.create(name=unique_name, original_name=name)

        # Only save if file does not already exist, because existing files with
        # the same name must also have the same content.
        if not self.exists(unique_name):
            super(UniqueMixin, self)._save(unique_name, content)

        return unique_name

    def get_available_name(self, name, *args, **kwargs):
        """
        Disable name conflict resolution.
        """
        return name

    def original_name(self, name):
        """
        Return the latest original name for a file.
        """
        from ixc_whitenoise.models import UniqueFile  # Avoid circular import
        try:
            return UniqueFile.objects \
                .filter(name=name).latest('-pk').original_name
        except UniqueFile.DoesNotExist:
            return name


class CompressedManifestStaticFilesStorage(
        HelpfulWarningMixin,
        RegexURLConverterMixin,
        CompressedManifestStaticFilesStorage):

    # When collecting static files during deployment to global storage, there will be a
    # moment after files have been collected and the manifest written but before the
    # application has been restarted, where the wrong (new) manifest is used by the
    # wrong (old) app code. By appending a unique app code version to the manifest name,
    # both manifests can exist at the same time and be read by their respective app
    # versions.
    manifest_name = getattr(
        settings, 'IXC_WHITENOISE_MANIFEST_NAME', 'staticfiles.json'
    )

    # Do not raise `ValueError` when other files are directly added to the static root
    # directory (not via the `collectstatic` management command). For example, compiled
    # SCSS which is already compressed and given a unique filename.
    manifest_strict = False


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
