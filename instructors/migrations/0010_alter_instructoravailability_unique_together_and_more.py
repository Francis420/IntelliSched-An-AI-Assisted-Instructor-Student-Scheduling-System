# Generated by Django 5.2.3 on 2025-07-19 12:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_role_remove_user_role_user_roles'),
        ('instructors', '0009_alter_instructorexperience_unique_together_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='instructoravailability',
            unique_together={('instructor', 'dayOfWeek', 'startTime', 'endTime')},
        ),
        migrations.AddIndex(
            model_name='instructoravailability',
            index=models.Index(fields=['instructor', 'dayOfWeek'], name='instructors_instruc_aa99f4_idx'),
        ),
    ]
