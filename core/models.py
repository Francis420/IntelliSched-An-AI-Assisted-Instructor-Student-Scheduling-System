from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

# ---------- Custom User Manager ---------- 50 need to update templates to handle dynamic checks for username/instructorId
# This manager handles user creation and superuser creation with custom fields.
class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        if not username:
            raise ValueError("Users must have a username")

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('isActive', True)
        return self.create_user(username, email, password, **extra_fields)


# ---------- Role Model ----------
# This model defines roles that users can have, such as "deptHead", "instructor" or "student".
class Role(models.Model):
    name = models.CharField(max_length=20, unique=True)
    label = models.CharField(max_length=50) 

    def __str__(self):
        return self.label


# ---------- User Model ----------
# This model represents the user accounts in the system, including their roles and authentication details.
class User(AbstractBaseUser, PermissionsMixin):
    userId = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)

    firstName = models.CharField(max_length=50)
    lastName = models.CharField(max_length=50)
    middleInitial = models.CharField(max_length=1, blank=True, null=True)

    roles = models.ManyToManyField(Role, blank=True)

    isActive = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    createdAt = models.DateTimeField(auto_now_add=True)
    lastUpdated = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'firstName', 'lastName']
    
    def __str__(self):
        role_names = ", ".join([r.name for r in self.roles.all()])
        return f"{self.username} ({role_names})"

    def get_roles(self):
        return [role.name for role in self.roles.all()]


# ---------- Instructor Table ----------
# This model represents instructors in the system, including their ID, rank, designation, academic attainment and employment type.
class Instructor(models.Model):
    instructorId = models.CharField(primary_key=True, max_length=20)  # e.g., "2025-123456"
    rank = models.ForeignKey("instructors.InstructorRank", on_delete=models.SET_NULL, null=True, blank=True)
    designation = models.ForeignKey("instructors.InstructorDesignation", on_delete=models.SET_NULL, null=True, blank=True)
    academicAttainment = models.ForeignKey("instructors.InstructorAcademicAttainment", on_delete=models.SET_NULL, null=True, blank=True)
    employmentType = models.CharField(max_length=20, choices=[
        ('permanent', 'Permanent'),
        ('temporary', 'Temporary')
    ])
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    @property
    def activeWorkloadSource(self):
        return self.designation or self.rank
    
    @property
    def full_name(self):
        user = User.objects.filter(userlogin__instructor=self).first()
        if user:
            return f"{user.firstName} {user.lastName}"
        return self.instructorId

    def __str__(self):
        return self.instructorId


# ---------- Student Table ----------
# This model represents students in the system, identified by their student ID.
class Student(models.Model):
    studentId = models.CharField(primary_key=True, max_length=20)  # e.g., "2025-123456"
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.studentId


# ---------- UserLogin ----------
# This model tracks user logins, linking them to the User, Instructor or Student models.
class UserLogin(models.Model):
    loginId = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    instructor = models.ForeignKey(Instructor, on_delete=models.SET_NULL, null=True, blank=True)
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} login @ {self.createdAt}"
