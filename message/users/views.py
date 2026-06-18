# users/views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from django.contrib.auth import get_user_model
from django.db.models import Q

from utils.api_response import success_response, error_response
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserAccountSerializer,
    LogoutSerializer,
)
from utils.cache import CacheService
from utils.cache_key import user_profile_key

User = get_user_model()

class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=UserRegistrationSerializer,
        responses={
            201: OpenApiResponse(
                description='Registration successful',
                examples=[
                    OpenApiExample('Success Response', value={'success': True, 'message': 'Registration successful'})
                ]
            ),
            400: OpenApiResponse(description='Bad Request - Validation errors')
        },
        tags=['Authentication'],
        summary='Register a new user',
        description='Create a new user account.'
    )
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            return success_response(
                message='Registration successful',
                status_code=status.HTTP_201_CREATED
            )
        
        return error_response(
            message='Registration failed',
            errors=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )

class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=UserLoginSerializer,
        responses={
            200: OpenApiResponse(
                description='Login successful',
                examples=[
                    OpenApiExample(
                        'Success Response',
                        value={
                            'success': True,
                            'message': 'Login successful',
                            'data': {
                                'access': 'eyJ0e...g',
                                'refresh': 'eyJ0e...g'
                            }
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description='Unauthorized - Invalid credentials')
        },
        tags=['Authentication'],
        summary='Login user',
        description='Authenticate using username or email along with password.'
    )
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            tokens = serializer.validated_data['tokens']
            return success_response(
                data=tokens,
                message='Login successful',
                status_code=status.HTTP_200_OK
            )
        
        return error_response(
            message='Login failed',
            errors=serializer.errors,
            status_code=status.HTTP_401_UNAUTHORIZED
        )

class TokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=TokenRefreshSerializer,
        responses={
            200: OpenApiResponse(
                description='Token refreshed successfully',
                examples=[
                    OpenApiExample(
                        'Success Response',
                        value={
                            'success': True,
                            'message': 'Token refreshed successfully',
                            'data': {
                                'access': 'eyJ0eXAi...g',
                                'refresh': 'eyJ0eXAi...g'
                            }
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description='Unauthorized - Invalid or expired refresh token')
        },
        tags=['Authentication'],
        summary='Refresh access token',
        description='Use a valid refresh token to obtain a new access token.'
    )
    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        
        if serializer.is_valid():
            return success_response(
                data={
                    'access': serializer.validated_data['access'],
                    'refresh': serializer.validated_data.get('refresh', request.data.get('refresh')),
                },
                message='Token refreshed successfully',
                status_code=status.HTTP_200_OK
            )
        
        return error_response(
            message='Token refresh failed',
            errors=serializer.errors,
            status_code=status.HTTP_401_UNAUTHORIZED
        )

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        request=LogoutSerializer,
        responses={
            200: OpenApiResponse(description='Logout successful'),
            400: OpenApiResponse(description='Bad Request - Invalid token')
        },
        tags=['Authentication'],
        summary='Logout user',
        description='Blacklist the refresh token to logout the user.'
    )
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return success_response(
                message='Logout successful',
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return error_response(
                message='Logout failed',
                errors={'detail': str(e)},
                status_code=status.HTTP_400_BAD_REQUEST
            )

class MeView(APIView):
    """
    Current User Profile Endpoint
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=UserAccountSerializer,
                description='User profile retrieved successfully'
            ),
            401: OpenApiResponse(description='Unauthorized')
        },
        tags=['User Profile'],
        summary='Get current user profile',
        description='Retrieve authenticated user profile.'
    )
    def get(self, request):
        cache_key = user_profile_key(request.user.id)
        cached_user = CacheService.get(cache_key)

        if cached_user:
            return success_response(
                data={'user': cached_user},
                status_code=status.HTTP_200_OK
            )

        user_data = UserAccountSerializer(request.user).data
        CacheService.set(cache_key, user_data, timeout=300)

        return success_response(
            data={'user': user_data},
            status_code=status.HTTP_200_OK
        )

class UpdateProfileView(APIView):
    """
    Update User Profile Endpoint
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=UserAccountSerializer,
        responses={
            200: OpenApiResponse(
                response=UserAccountSerializer,
                description='User profile updated successfully'
            ),
            400: OpenApiResponse(description='Bad Request - Validation errors'),
            401: OpenApiResponse(description='Unauthorized')
        },
        tags=['User Profile'],
        summary='Update current user profile',
        description='Update authenticated user profile information.'
    )
    def patch(self, request):
        serializer = UserAccountSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        
        if serializer.is_valid():
            user = serializer.save()
            cache_key = user_profile_key(request.user.id)
            CacheService.delete(cache_key)
            
            return success_response(
                data={'user': UserAccountSerializer(user).data},
                message='Profile updated successfully',
                status_code=status.HTTP_200_OK
            )
        
        return error_response(
            message='Profile update failed',
            errors=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )

class UserListView(APIView):
    """
    List of registered users so the current user can start a chat
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiResponse(response=UserAccountSerializer(many=True))},
        tags=['User Profile'],
        summary='Get all available users to chat with',
        description='Returns a list of all active registered users except the current user. Accepts an optional ?search= query parameter.'
    )
    def get(self, request):
        # Base query: Exclude current user AND only show active users
        users = User.objects.filter(is_active=True).exclude(id=request.user.id)
        
        # Search functionality (Look up by username or display_name)
        search_query = request.query_params.get('search', None)
        if search_query:
            users = users.filter(
                Q(username__icontains=search_query) | 
                Q(display_name__icontains=search_query)
            )
            
        # Order the results alphabetically
        users = users.order_by('username')
        
        user_data = UserAccountSerializer(users, many=True).data

        return success_response(
            data=user_data,
            status_code=status.HTTP_200_OK
        )