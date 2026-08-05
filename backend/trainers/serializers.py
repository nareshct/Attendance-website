from django.contrib.auth.models import User
from rest_framework import serializers

from courses.models import Course

from .models import Trainer, TrainerCourseRate


class TrainerCourseRateSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = TrainerCourseRate
        fields = ['id', 'trainer', 'course', 'course_name', 'rate_per_class']


class TrainerCourseRateInputSerializer(serializers.Serializer):
    """Used only nested inside TrainerSerializer.create() — no `trainer` yet."""

    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all())
    rate_per_class = serializers.DecimalField(max_digits=8, decimal_places=2)


class TrainerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})
    course_rates = TrainerCourseRateSerializer(many=True, read_only=True)
    rates = TrainerCourseRateInputSerializer(many=True, write_only=True, required=False)
    # Annotated on TrainerViewSet.get_queryset() — fall back to a live query for callers
    # that build a Trainer instance outside that queryset (e.g. serializer.save() in create()).
    active_student_count = serializers.SerializerMethodField()
    payout_pending = serializers.SerializerMethodField()

    class Meta:
        model = Trainer
        fields = [
            'id', 'trainer_id', 'name', 'phone_number', 'place', 'status', 'default_rate_per_class',
            'username', 'password', 'course_rates', 'rates', 'active_student_count', 'payout_pending',
        ]
        read_only_fields = ['trainer_id', 'status']

    def get_active_student_count(self, obj):
        if isinstance(getattr(obj, 'active_student_count', None), int):
            return obj.active_student_count
        return obj.enrollments.filter(status='ongoing').count()

    def get_payout_pending(self, obj):
        """Unpaid closed-cycle payouts only — deliberately excludes the live, still-open
        current cycle, since that amount isn't due yet (a cycle has to close before it
        becomes an actual Payout an admin can mark paid)."""
        from decimal import Decimal

        from django.db.models import Sum

        pending_closed = getattr(obj, 'pending_payout_amount', None)
        if pending_closed is None:
            pending_closed = obj.payouts.filter(paid_status='pending').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        return pending_closed

    def create(self, validated_data):
        username = validated_data.pop('username', None)
        password = validated_data.pop('password', None)
        rates = validated_data.pop('rates', [])

        if not username or not password:
            raise serializers.ValidationError(
                {'username': 'username and password are required to onboard a trainer.'}
            )
        if validated_data.get('default_rate_per_class') is None:
            raise serializers.ValidationError(
                {'default_rate_per_class': 'A default rate per class is required.'}
            )
        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError({'username': 'A user with this username already exists.'})

        user = User.objects.create_user(username=username, password=password)
        trainer = Trainer.objects.create(user=user, **validated_data)

        TrainerCourseRate.objects.bulk_create([
            TrainerCourseRate(trainer=trainer, course=r['course'], rate_per_class=r['rate_per_class'])
            for r in rates
        ])
        return trainer

    def update(self, instance, validated_data):
        validated_data.pop('username', None)
        validated_data.pop('password', None)
        validated_data.pop('rates', None)
        return super().update(instance, validated_data)
