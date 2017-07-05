# What is this?

Improvements to [WhiteNoise][0]:

  * Serve media as well as static files.
  * Save media with unique filenames, so they can be deduplicated and cached
    forever.
  * Store the original name for deduplicated files in the `UniqueFile` model.
  * Do not crash the ``collectstatic`` management command when a referenced
    file is not found or has an unknown scheme.
  * Add [django-pipeline][1] integration.
  * Add support for Django 1.6 via monkey patching.
  * Strip the `Vary` header for static file responses via middleware, to work
  	around an IE bug. This should come *before* `SessionMiddleware` in
  	`MIDDLEWARE_CLASSES`. See: http://stackoverflow.com/a/23410136

Settings:

  * `IXC_WHITENOISE_DEDUPE_EXTENSIONS` - Define short versions of long
    extensions in a dict, e.g. `{'.jpeg': '.jpg', '.yaml': '.yml'}`.
    Deduplicated files will use the short version.

  * `IXC_WHITENOISE_DEDUPE_PREFIX` - Deduplicated files will be saved into this
    directory. Their original path will be retained, but their filename
    will be replaced with a unique content hash.

Management commands:

  * `deduplicate_unique_storage` - Finds all file fields in all models that use
    `UniqueStorage` and re-saves them to deduplicate. The original files are not
    removed.

[0]: https://github.com/evansd/whitenoise/
[1]: https://github.com/jazzband/django-pipeline/
