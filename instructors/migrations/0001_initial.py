# Generated by Django 5.2.3 on 2025-07-23 01:18

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_initial'),
        ('scheduling', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='InstructorDesignation',
            fields=[
                ('designationId', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255, unique=True)),
                ('instructionHours', models.IntegerField(default=0)),
                ('researchHours', models.IntegerField(default=0)),
                ('extensionHours', models.IntegerField(default=0)),
                ('productionHours', models.IntegerField(default=0)),
                ('consultationHours', models.IntegerField(default=0)),
                ('adminSupervisionHours', models.IntegerField(default=0)),
                ('otherAssignmentHours', models.IntegerField(default=0)),
                ('overloadDoctoral', models.IntegerField(default=6)),
                ('overloadMasters', models.IntegerField(default=6)),
                ('overloadBaccalaureate', models.IntegerField(default=6)),
                ('totalHours', models.IntegerField(default=40)),
            ],
        ),
        migrations.CreateModel(
            name='InstructorAbsence',
            fields=[
                ('absenceId', models.AutoField(primary_key=True, serialize=False)),
                ('reportType', models.CharField(choices=[('auto-detected', 'Auto Detected'), ('manual', 'Manual')], max_length=20)),
                ('reason', models.TextField(blank=True, null=True)),
                ('dateMissed', models.DateField()),
                ('reportedAt', models.DateTimeField(auto_now_add=True)),
                ('instructor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.instructor')),
                ('schedule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='scheduling.schedule')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='scheduling.subject')),
            ],
        ),
        migrations.CreateModel(
            name='InstructorRank',
            fields=[
                ('rankId', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255, unique=True)),
                ('instructionHours', models.IntegerField(default=0)),
                ('researchHours', models.IntegerField(default=0)),
                ('extensionHours', models.IntegerField(default=0)),
                ('productionHours', models.IntegerField(default=0)),
                ('consultationHours', models.IntegerField(default=0)),
                ('otherAssignmentHours', models.IntegerField(default=0)),
                ('overloadDoctoral', models.IntegerField(default=9)),
                ('overloadMasters', models.IntegerField(default=6)),
                ('overloadBaccalaureate', models.IntegerField(default=6)),
                ('totalHours', models.IntegerField(default=40)),
            ],
            options={
                'ordering': ['name'],
                'indexes': [models.Index(fields=['name'], name='instructors_name_ef585f_idx')],
            },
        ),
        migrations.CreateModel(
            name='InstructorAvailability',
            fields=[
                ('availabilityId', models.AutoField(primary_key=True, serialize=False)),
                ('dayOfWeek', models.CharField(choices=[('Monday', 'Monday'), ('Tuesday', 'Tuesday'), ('Wednesday', 'Wednesday'), ('Thursday', 'Thursday'), ('Friday', 'Friday'), ('Saturday', 'Saturday'), ('Sunday', 'Sunday')], max_length=10)),
                ('startTime', models.TimeField()),
                ('endTime', models.TimeField()),
                ('createdAt', models.DateTimeField(auto_now_add=True)),
                ('updatedAt', models.DateTimeField(auto_now=True)),
                ('instructor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.instructor')),
            ],
            options={
                'ordering': ['instructor', 'dayOfWeek', 'startTime'],
                'indexes': [models.Index(fields=['instructor', 'dayOfWeek'], name='instructors_instruc_aa99f4_idx')],
                'unique_together': {('instructor', 'dayOfWeek', 'startTime', 'endTime')},
            },
        ),
        migrations.CreateModel(
            name='InstructorCredentials',
            fields=[
                ('credentialId', models.AutoField(primary_key=True, serialize=False)),
                ('type', models.CharField(choices=[('Certification', 'Certification'), ('Workshop', 'Workshop'), ('Training', 'Training'), ('License', 'License')], max_length=30)),
                ('title', models.CharField(max_length=100)),
                ('description', models.TextField()),
                ('issuer', models.CharField(max_length=100)),
                ('isVerified', models.BooleanField(default=False)),
                ('documentUrl', models.CharField(blank=True, max_length=255, null=True)),
                ('dateEarned', models.DateField()),
                ('createdAt', models.DateTimeField(auto_now_add=True)),
                ('updatedAt', models.DateTimeField(auto_now=True)),
                ('instructor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.instructor')),
                ('relatedSubjects', models.ManyToManyField(blank=True, to='scheduling.subject')),
            ],
            options={
                'ordering': ['-dateEarned'],
                'indexes': [models.Index(fields=['instructor', 'isVerified'], name='instructors_instruc_05fda9_idx')],
            },
        ),
        migrations.CreateModel(
            name='InstructorExperience',
            fields=[
                ('experienceId', models.AutoField(primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=100)),
                ('organization', models.CharField(max_length=100)),
                ('startDate', models.DateField()),
                ('endDate', models.DateField(blank=True, null=True)),
                ('description', models.TextField()),
                ('experienceType', models.CharField(choices=[('Work Experience', 'Work Experience'), ('Academic Position', 'Academic Position'), ('Research Role', 'Research Role')], max_length=30)),
                ('isVerified', models.BooleanField(default=False)),
                ('createdAt', models.DateTimeField(auto_now_add=True)),
                ('updatedAt', models.DateTimeField(auto_now=True)),
                ('instructor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.instructor')),
                ('relatedSubjects', models.ManyToManyField(blank=True, to='scheduling.subject')),
            ],
            options={
                'indexes': [models.Index(fields=['instructor', 'isVerified'], name='instructors_instruc_9d96bd_idx')],
                'unique_together': {('instructor', 'title', 'organization', 'startDate')},
            },
        ),
        migrations.CreateModel(
            name='InstructorSubjectPreference',
            fields=[
                ('preferenceId', models.AutoField(primary_key=True, serialize=False)),
                ('preferenceType', models.CharField(choices=[('Prefer', 'Prefer'), ('Neutral', 'Neutral'), ('Avoid', 'Avoid')], max_length=20)),
                ('reason', models.TextField(blank=True, null=True)),
                ('createdAt', models.DateTimeField(auto_now_add=True)),
                ('updatedAt', models.DateTimeField(auto_now=True)),
                ('instructor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.instructor')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='scheduling.subject')),
            ],
            options={
                'ordering': ['instructor', 'subject'],
                'indexes': [models.Index(fields=['instructor', 'preferenceType'], name='instructors_instruc_fb7d84_idx')],
                'unique_together': {('instructor', 'subject')},
            },
        ),
        migrations.CreateModel(
            name='TeachingHistory',
            fields=[
                ('teachingId', models.AutoField(primary_key=True, serialize=False)),
                ('timesTaught', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
                ('createdAt', models.DateTimeField(auto_now_add=True)),
                ('updatedAt', models.DateTimeField(auto_now=True)),
                ('instructor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='teachingHistory', to='core.instructor')),
                ('semester', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='scheduling.semester')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='scheduling.subject')),
            ],
            options={
                'indexes': [models.Index(fields=['instructor', 'subject', 'semester'], name='instructors_instruc_5944de_idx')],
                'unique_together': {('instructor', 'subject', 'semester')},
            },
        ),
    ]
