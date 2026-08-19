# users/models.py
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    # Core Authentication Fields
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=30, unique=True)
    
    # Profile & Chat Fields
    display_name = models.CharField(max_length=150, blank=True, help_text="The name shown to other chat users.")
    profile_picture = models.URLField(max_length=500, blank=True, default="")
    bio = models.CharField(max_length=255, blank=True, default="Hey there! I am using this chat app.")
    
    # Real-time state tracking fields
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)

    # Permission & Status Fields
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    class Meta:
        db_table = "user"   
        verbose_name = "User"
        verbose_name_plural = "Users"

    # Tell Django to use email for authentication
    USERNAME_FIELD = "email"
    
    # Required for the `createsuperuser` CLI command
    REQUIRED_FIELDS = ["username"]

    def save(self, *args, **kwargs):
        # Auto-fill display_name if the user leaves it blank
        if not self.display_name:
            self.display_name = self.username
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email