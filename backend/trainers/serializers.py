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

    class Meta:
        model = Trainer
        fields = [
            'id', 'trainer_id', 'name', 'phone_number', 'place', 'status', 'default_rate_per_class',
            'username', 'password', 'course_rates', 'rates',
        ]
        read_only_fields = ['trainer_id', 'status']

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
