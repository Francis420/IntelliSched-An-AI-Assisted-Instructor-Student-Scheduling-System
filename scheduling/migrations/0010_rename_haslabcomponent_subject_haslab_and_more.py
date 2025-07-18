# Generated by Django 5.2.3 on 2025-07-19 10:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0009_alter_semester_term'),
    ]

    operations = [
        migrations.RenameField(
            model_name='subject',
            old_name='hasLabComponent',
            new_name='hasLab',
        ),
        migrations.RemoveField(
            model_name='subject',
            name='labDeliveryMode',
        ),
        migrations.RemoveField(
            model_name='subject',
            name='preferredDeliveryMode',
        ),
        migrations.RemoveField(
            model_name='subject',
            name='requiredLabRoomType',
        ),
        migrations.RemoveField(
            model_name='subject',
            name='requiredRoomType',
        ),
        migrations.AddField(
            model_name='subject',
            name='isPriorityForRooms',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='subject',
            name='yearLevel',
            field=models.IntegerField(choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4')]),
        ),
    ]
