# Generated by Django 5.2.3 on 2025-07-19 11:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_role_remove_user_role_user_roles'),
        ('instructors', '0007_instructorcredentials_instructors_instruc_05fda9_idx'),
        ('scheduling', '0012_alter_subject_defaultterm_alter_subject_name_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='instructorsubjectpreference',
            unique_together={('instructor', 'subject')},
        ),
        migrations.AddIndex(
            model_name='instructorsubjectpreference',
            index=models.Index(fields=['instructor', 'preferenceType'], name='instructors_instruc_fb7d84_idx'),
        ),
    ]
