from django.db import models


class UniqueFile(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(db_index=True, max_length=500)
    original_name = models.CharField(db_index=True, max_length=500)

    class Meta:
        ordering = ('-pk', )

    def __unicode__(self):
        return '%s -> %s' % (self.original_name, self.name)
