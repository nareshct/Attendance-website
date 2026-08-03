from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsAdmin
from .throttling import LoginRateThrottle, PasswordResetRateThrottle


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        token, _ = Token.objects.get_or_create(user=user)
        is_trainer = hasattr(user, 'trainer')
        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'name': user.trainer.name if is_trainer else user.username,
            'is_staff': user.is_staff,
            'role': 'trainer' if is_trainer else 'admin',
        })


class LogoutView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.auth_token.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')

        if not current_password or not new_password:
            return Response(
                {'detail': 'current_password and new_password are required.'}, status=status.HTTP_400_BAD_REQUEST
            )
        if not request.user.check_password(current_password):
            return Response({'detail': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(new_password, user=request.user)
        except ValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """The logged-in user's own basic profile — mainly so a settings page can
    show/edit the email address a password-reset link would go to, without
    relying on the (possibly stale) copy cached in the frontend from login.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_trainer = hasattr(user, 'trainer')
        return Response({
            'username': user.username,
            'email': user.email,
            'name': user.trainer.name if is_trainer else user.username,
            'is_staff': user.is_staff,
            'role': 'trainer' if is_trainer else 'admin',
        })


class UpdateEmailView(APIView):
    """Lets a logged-in user set their own recovery email — this has to be
    done proactively, while still logged in, since it's exactly what a
    password-reset request needs and there's no other way to add it later.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        if not email:
            return Response({'detail': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_email(email)
        except ValidationError:
            return Response({'detail': 'Enter a valid email address.'}, status=status.HTTP_400_BAD_REQUEST)

        request.user.email = email
        request.user.save(update_fields=['email'])
        return Response({'email': request.user.email})


class PasswordResetRequestView(APIView):
    """Step 1 of "forgot password": emails a reset link if the username exists
    and has an email on file (see UpdateEmailView). Always responds the same
    way regardless of whether anything actually matched, so this endpoint
    can't be used to check which usernames exist.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    GENERIC_MESSAGE = 'If that account exists and has an email on file, a reset link has been sent to it.'

    def post(self, request):
        username = (request.data.get('username') or '').strip()
        User = get_user_model()
        user = User.objects.filter(username=username).first()

        if user is not None and user.email:
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = f'{settings.FRONTEND_URL}/reset-password/{uidb64}/{token}/'
            send_mail(
                subject='Apex Binary: Reset your password',
                message=(
                    f'A password reset was requested for the "{username}" account.\n\n'
                    f'Reset it here (this link expires in 3 days):\n{reset_url}\n\n'
                    "If you didn't request this, you can safely ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )

        return Response({'detail': self.GENERIC_MESSAGE})


class PasswordResetConfirmView(APIView):
    """Step 2 of "forgot password": exchanges the uid+token from the emailed
    link for a new password. The token is time-limited and single-use by
    design (django's default_token_generator invalidates it once the password
    it was issued for actually changes).
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        uidb64 = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')

        if not uidb64 or not token or not new_password:
            return Response(
                {'detail': 'uid, token, and new_password are required.'}, status=status.HTTP_400_BAD_REQUEST
            )

        User = get_user_model()
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'detail': 'This reset link is invalid.'}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response(
                {'detail': 'This reset link is invalid or has expired. Request a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SearchView(APIView):
    """Admin-facing: one search box across students, trainers, and clients —
    the three record types that otherwise each need their own list page to
    find someone on. Results are capped per category to keep it fast and
    dropdown-sized rather than a full results page.
    """

    permission_classes = [IsAdmin]
    RESULTS_PER_CATEGORY = 8

    def get(self, request):
        # Imported here, not at module level, purely to keep config — the
        # app auth/site-wide utilities live in — from taking a hard import
        # dependency on every domain app just for this one endpoint.
        from clients.models import Client
        from students.models import Student
        from trainers.models import Trainer

        query = (request.query_params.get('q') or '').strip()
        if len(query) < 2:
            return Response([])

        results = []
        for student in Student.objects.filter(
            Q(name__icontains=query) | Q(student_id__icontains=query)
        )[: self.RESULTS_PER_CATEGORY]:
            results.append({
                'type': 'student',
                'id': student.id,
                'label': student.name,
                'sublabel': f'{student.student_id} · {student.source_type}',
            })

        for trainer in Trainer.objects.filter(
            Q(name__icontains=query) | Q(trainer_id__icontains=query)
        )[: self.RESULTS_PER_CATEGORY]:
            results.append({
                'type': 'trainer',
                'id': trainer.id,
                'label': trainer.name,
                'sublabel': trainer.trainer_id,
            })

        for client in Client.objects.filter(company_name__icontains=query)[: self.RESULTS_PER_CATEGORY]:
            results.append({
                'type': 'client',
                'id': client.id,
                'label': client.company_name,
                'sublabel': client.contact_phone,
            })

        return Response(results)
