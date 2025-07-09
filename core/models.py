from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

# ---------- Custom User Manager ----------
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

# ---------- Custom User Model ----------
class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('sysAdmin', 'System Admin'),
        ('deptHead', 'Department Head'),
        ('instructor', 'Instructor'),
        ('student', 'Student'),
    ]

    userId = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)

    firstName = models.CharField(max_length=50)
    lastName = models.CharField(max_length=50)
    middleInitial = models.CharField(max_length=1, blank=True, null=True)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    isActive = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # ✅ fixed
    is_superuser = models.BooleanField(default=False)  # ✅ fixed

    createdAt = models.DateTimeField(auto_now_add=True)
    lastUpdated = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'firstName', 'lastName', 'role']

    def __str__(self):
        return f"{self.username} ({self.role})"

# ---------- College ----------
class College(models.Model):
    collegeId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    acronym = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    isActive = models.BooleanField(default=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# ---------- Department ----------
class Department(models.Model):
    departmentId = models.AutoField(primary_key=True)
    college = models.ForeignKey(College, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    isActive = models.BooleanField(default=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
# ---------- Course ----------
class Course(models.Model):
    courseId = models.AutoField(primary_key=True)
    department = models.ForeignKey('Department', on_delete=models.CASCADE)
    courseName = models.CharField(max_length=150)
    acronym = models.CharField(max_length=50)
    isActive = models.BooleanField(default=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.courseName

# ---------- UserLogin ----------
class UserLogin(models.Model):
    loginId = models.AutoField(primary_key=True)
    user = models.ForeignKey('User', on_delete=models.CASCADE)
    instructor = models.ForeignKey('instructors.Instructor', on_delete=models.SET_NULL, null=True, blank=True)
    student = models.ForeignKey('students.Student', on_delete=models.SET_NULL, null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Login record for {self.user.username} at {self.createdAt}"