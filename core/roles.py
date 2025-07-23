from core.models import Role

#managing roles in the system; run this script to seed roles:
# from core.roles import seed_roles
# seed_roles()

def seed_roles():
    roles = [
        ('deptHead', 'Department Head'),
        ('instructor', 'Instructor'),
        ('student', 'Student'),
    ]

    for name, label in roles:
        role, created = Role.objects.get_or_create(name=name, defaults={'label': label})
        if created:
            print(f"✓ Created role: {name} ({label})")
        else:
            print(f"- Role already exists: {name}")
