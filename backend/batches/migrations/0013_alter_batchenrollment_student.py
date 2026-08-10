import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('batches', '0012_rename_guest_lead_info_fields'),
        ('students', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='batchenrollment',
            name='student',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='batch_enrollments',
                to='students.student',
            ),
        ),
    ]
