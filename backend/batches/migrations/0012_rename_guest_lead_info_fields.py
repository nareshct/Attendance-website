from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('batches', '0011_remove_batchenrollment_unique_guest_enrollment_per_batch_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='batchenrollment',
            old_name='guest_email',
            new_name='contact_email',
        ),
        migrations.RenameField(
            model_name='batchenrollment',
            old_name='guest_occupation',
            new_name='occupation',
        ),
        migrations.RenameField(
            model_name='batchenrollment',
            old_name='guest_source',
            new_name='lead_source',
        ),
    ]
