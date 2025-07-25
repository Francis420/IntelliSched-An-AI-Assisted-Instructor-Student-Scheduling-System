# Generated by Django 5.2.3 on 2025-07-23 01:49

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('instructors', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='instructorrank',
            options={'ordering': ['rankId']},
        ),
        migrations.RenameField(
            model_name='instructorrank',
            old_name='otherAssignmentHours',
            new_name='classAdviserHours',
        ),
        migrations.RemoveField(
            model_name='instructorrank',
            name='overloadBaccalaureate',
        ),
        migrations.RemoveField(
            model_name='instructorrank',
            name='overloadDoctoral',
        ),
        migrations.RemoveField(
            model_name='instructorrank',
            name='overloadMasters',
        ),
        migrations.RemoveField(
            model_name='instructorrank',
            name='totalHours',
        ),
    ]
