# users/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class UserLoginSerializer(serializers.Serializer):
    login = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        login_val = attrs.get('login')
        password = attrs.get('password')

        # Allow login with either email or username
        user = User.objects.filter(
            Q(email=login_val) | Q(username=login_val)
        ).first()

        if user and user.check_password(password):
            if not user.is_active:
                raise serializers.ValidationError("This account is inactive.")

            refresh = RefreshToken.for_user(user)
            
            # Return tokens and basic user data in one payload
            return {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email
                }
            }
            
        raise serializers.ValidationError("Invalid credentials")

class UserAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'display_name', 
            'profile_picture', 'bio', 'is_online', 
            'last_seen', 'created_at'
        )
        read_only_fields = ('id', 'email', 'created_at', 'is_online', 'last_seen')

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

class TokenRefreshCustomSerializer(TokenRefreshSerializer):
    pass