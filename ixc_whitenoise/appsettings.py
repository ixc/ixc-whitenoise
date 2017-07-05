from django.conf import settings

DEDUPE_EXTENTIONS = {
    '.jpeg': '.jpg',
    '.yaml': '.yml',
}
DEDUPE_EXTENTIONS.update(
    getattr(settings, 'IXC_WHITENOISE_DEDUPE_EXTENTIONS', {}))

DEDUPE_PREFIX = getattr(settings, 'IXC_WHITENOISE_DEDUPE_PREFIX', 'dd')
