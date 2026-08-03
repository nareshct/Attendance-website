from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import DAYS_OF_WEEK, Enrollment, PaymentInstallment, PaymentPlan, SubstituteAssignment
from .services import create_payment_plan, find_schedule_conflict, total_amount_for_discount, upfront_payment_for


class SubstituteAssignmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='enrollment.student.name', read_only=True)
    course_name = serializers.CharField(source='enrollment.course.name', read_only=True)
    original_trainer_name = serializers.CharField(source='enrollment.trainer.name', read_only=True)
    substitute_trainer_name = serializers.CharField(source='substitute_trainer.name', read_only=True)

    class Meta:
        model = SubstituteAssignment
        fields = [
            'id', 'enrollment', 'student_name', 'course_name', 'original_trainer_name',
            'substitute_trainer', 'substitute_trainer_name', 'start_date', 'end_date', 'created_at',
        ]
        read_only_fields = ['created_at']


class PaymentInstallmentSerializer(serializers.ModelSerializer):
    # Whether the parent should be asked to pay this now — mirrors the milestone check
    # used for the dashboard's "installments due" alert (billing/services.py) and the
    # trainer payment gate (enrollments/services.py trainer_payment_gate), so the
    # admin-facing student profile can show the same due/not-due distinction.
    is_due = serializers.SerializerMethodField()

    class Meta:
        model = PaymentInstallment
        fields = ['id', 'sequence', 'due_at_classes', 'amount', 'paid_status', 'paid_date', 'is_due']

    def get_is_due(self, obj):
        return obj.due_at_classes is None or obj.plan.enrollment.classes_completed >= obj.due_at_classes - 1


class PaymentPlanSerializer(serializers.ModelSerializer):
    plan_type_display = serializers.CharField(source='get_plan_type_display', read_only=True)
    installments = PaymentInstallmentSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentPlan
        fields = [
            'id', 'plan_type', 'plan_type_display', 'total_amount', 'installments',
            'refunded_amount', 'refund_note',
        ]


class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    course_name = serializers.CharField(source='course.name', read_only=True)
    trainer_name = serializers.CharField(source='trainer.name', read_only=True)

    # Write-only, B2C-only payment plan input — see create(). Never serialized back out
    # of this endpoint (MyStudentsView reuses this serializer for trainers, who shouldn't
    # see billing data — see PaymentPlanSerializer usage in students/views.py instead).
    # The total course fee and upfront (first) installment are never taken from the
    # client as raw amounts — only a discount percentage is, and the actual rupee
    # figures are always computed server-side from the course rate. See
    # total_amount_for_discount() / upfront_payment_for().
    payment_type = serializers.ChoiceField(choices=PaymentPlan.PLAN_CHOICES, write_only=True, required=False)
    # Percentage discount off the course's standard price (rate_per_class x total_classes),
    # capped at 15 — the most this business ever discounts a B2C course fee.
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, write_only=True, required=False, default=Decimal('0.00'),
        min_value=Decimal('0'), max_value=Decimal('15'),
    )

    class Meta:
        model = Enrollment
        fields = [
            'id', 'student', 'student_name', 'course', 'course_name', 'trainer', 'trainer_name',
            'batch_number', 'classes_completed', 'classes_total', 'start_date', 'status',
            'class_time', 'class_days', 'payment_type', 'discount_percent',
        ]
        read_only_fields = ['batch_number', 'classes_completed', 'status', 'start_date']
        extra_kwargs = {
            'class_time': {'required': True, 'allow_null': False},
            'class_days': {'required': True},
        }

    def validate_class_days(self, value):
        days = [d.strip().upper() for d in value.split(',') if d.strip()]
        if not days:
            raise serializers.ValidationError('Select at least one class day.')
        invalid = [d for d in days if d not in DAYS_OF_WEEK]
        if invalid:
            raise serializers.ValidationError(f'Invalid day(s): {", ".join(invalid)}. Use {", ".join(DAYS_OF_WEEK)}.')
        return ','.join(d for d in DAYS_OF_WEEK if d in days)

    def validate(self, attrs):
        trainer = attrs.get('trainer') or getattr(self.instance, 'trainer', None)
        course = attrs.get('course') or getattr(self.instance, 'course', None)
        if trainer and course and not trainer.has_rate_for(course):
            raise serializers.ValidationError(
                f'{trainer.name} has no rate set for {course.name} — set a default rate or add a course override first.'
            )

        # Block double-booking a trainer at the same day/time — the same check already
        # applied to Transfer and Substitute (see EnrollmentViewSet), just also enforced
        # here so a brand-new enrollment or a schedule edit can't create the clash in the
        # first place.
        class_time = attrs.get('class_time') or getattr(self.instance, 'class_time', None)
        class_days = attrs.get('class_days') or getattr(self.instance, 'class_days', None)
        if trainer and class_time and class_days:
            conflict = find_schedule_conflict(
                trainer, class_time, class_days,
                exclude_enrollment_id=self.instance.id if self.instance else None,
            )
            if conflict is not None:
                raise serializers.ValidationError(
                    f'{trainer.name} already has a class at that time — {conflict.student.name} '
                    f'({conflict.course.name}). Choose a different time or trainer.'
                )

        # The batch count can be edited after creation (e.g. correcting a typo, or
        # extending a batch), but never below classes already taught — that would make
        # classes_completed exceed classes_total, which the attendance-marking checks
        # (see attendance/views.py) treat as "enrollment complete."
        if self.instance is not None and 'classes_total' in attrs and attrs['classes_total'] < self.instance.classes_completed:
            raise serializers.ValidationError(
                f'Batch count can\'t be less than the {self.instance.classes_completed} classes already completed.'
            )

        # Earnings/invoices are calculated by grouping live Attendance rows by
        # enrollment.course, not a rate snapshotted per-session — so changing the course
        # after any class has already been taught would retroactively re-bill those past
        # sessions at the new course's rate. Only allow it before the enrollment starts.
        if (
            self.instance is not None
            and 'course' in attrs
            and attrs['course'] != self.instance.course
            and self.instance.classes_completed > 0
        ):
            raise serializers.ValidationError(
                'This enrollment already has classes recorded, so its course can no longer be changed.'
            )

        student = attrs.get('student') or getattr(self.instance, 'student', None)
        payment_type = attrs.get('payment_type')
        # Payment plan fields are only meaningful — and only required — when creating a
        # new B2C enrollment. An update (e.g. editing class_time) shouldn't have to
        # resend them just because the student happens to be B2C.
        if self.instance is None and student and student.source_type == 'B2C':
            if not payment_type:
                raise serializers.ValidationError('B2C enrollments require: payment_type.')
            if not course:
                raise serializers.ValidationError('Select a course to set up the payment plan.')
            if not course.rate_per_class:
                raise serializers.ValidationError(
                    f'{course.name} has no B2C rate set — set one on the Courses page first.'
                )

            classes_total = attrs.get('classes_total') or course.total_classes
            discount_percent = attrs.get('discount_percent') or Decimal('0.00')
            total_amount = total_amount_for_discount(course, classes_total, discount_percent)

            upfront = upfront_payment_for(payment_type, total_amount, classes_total)
            if upfront > total_amount:
                raise serializers.ValidationError(
                    f'This plan requires ₹{upfront} upfront (before class 1), which is more than the '
                    f'discounted total course fee of ₹{total_amount}.'
                )
        elif payment_type and (student is None or student.source_type != 'B2C'):
            raise serializers.ValidationError('Payment plan fields are only valid for B2C students.')

        return attrs

    def create(self, validated_data):
        payment_type = validated_data.pop('payment_type', None)
        discount_percent = validated_data.pop('discount_percent', None) or Decimal('0.00')

        if not validated_data.get('classes_total'):
            validated_data['classes_total'] = validated_data['course'].total_classes

        existing = Enrollment.objects.filter(
            student=validated_data['student'], course=validated_data['course']
        ).count()
        validated_data['batch_number'] = existing + 1
        validated_data['start_date'] = timezone.localdate()

        enrollment = super().create(validated_data)

        if payment_type:
            total_amount = total_amount_for_discount(enrollment.course, enrollment.classes_total, discount_percent)
            create_payment_plan(enrollment, payment_type, total_amount)

        return enrollment

    def update(self, instance, validated_data):
        new_course = validated_data.get('course')
        if new_course and new_course != instance.course:
            validated_data.setdefault('classes_total', new_course.total_classes)
        return super().update(instance, validated_data)
