from rest_framework import serializers

from .models import Batch, BatchEnrollment, BatchInstallment, BatchPayout, BatchSession


class BatchInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchInstallment
        fields = ['id', 'sequence', 'due_at_sessions', 'amount', 'paid_status', 'paid_date']
        read_only_fields = ['sequence', 'due_at_sessions', 'paid_status', 'paid_date']

    def validate_amount(self, value):
        # A discount/correction on what's still owed — once something's marked paid,
        # rewriting history goes through a withdraw refund instead (see BatchEnrollment
        # .refunded_amount), not a silent amount edit here.
        if self.instance and self.instance.paid_status != 'pending':
            raise serializers.ValidationError('Only a pending installment can have its amount changed.')
        return value


class BatchPayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchPayout
        fields = ['id', 'batch', 'recipient_name', 'amount', 'paid_status', 'paid_date', 'created_at']
        read_only_fields = ['paid_status', 'paid_date', 'created_at']


class BatchEnrollmentSerializer(serializers.ModelSerializer):
    # Every enrollment is linked to a registered Student — see BatchEnrollment.display_name
    # and batches.services.find_or_create_student, which resolves one at creation time.
    student_name = serializers.CharField(source='display_name', read_only=True)
    student_id_code = serializers.CharField(source='student.student_id', read_only=True)
    installments = BatchInstallmentSerializer(many=True, read_only=True)

    class Meta:
        model = BatchEnrollment
        fields = [
            'id', 'batch', 'student', 'student_name', 'student_id_code',
            'contact_email', 'occupation', 'lead_source',
            'joined_date', 'status', 'refunded_amount', 'refund_note', 'installments',
        ]
        read_only_fields = ['joined_date', 'status', 'refunded_amount', 'refund_note']

    def validate(self, data):
        # batch/student stay writable (required at creation) but can't be reassigned via
        # a later PATCH — moving someone to a different batch or swapping the linked
        # student isn't a supported edit.
        if self.instance:
            if 'batch' in data and data['batch'] != self.instance.batch:
                raise serializers.ValidationError({'batch': "Can't move this enrollment to a different batch."})
            if 'student' in data and data.get('student') != self.instance.student:
                raise serializers.ValidationError({'student': "Can't change the linked student directly."})
        return data


class BatchSessionSerializer(serializers.ModelSerializer):
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = BatchSession
        fields = [
            'id', 'batch', 'date', 'conducted_by_name', 'topic_covered', 'recording_link',
            'created_at', 'can_edit',
        ]
        read_only_fields = ['created_at']

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request is None:
            return True
        user = request.user
        return bool(user.is_staff or obj.created_by_id is None or obj.created_by_id == user.id)

    def validate(self, data):
        # 'batch' stays writable (required at creation, and the view already checks the
        # creator is allowed on it) but can't be reassigned via a later PATCH — moving a
        # session to a different batch, possibly one the editor isn't even assigned to,
        # isn't a supported edit. Mirrors BatchEnrollmentSerializer.validate() above.
        if self.instance and 'batch' in data and data['batch'] != self.instance.batch:
            raise serializers.ValidationError({'batch': "Can't move this session to a different batch."})
        return data


class BatchSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    payment_type_display = serializers.CharField(source='get_payment_type_display', read_only=True)
    enrolled_count = serializers.IntegerField(source='batch_enrollments.count', read_only=True)
    session_count = serializers.IntegerField(source='sessions.count', read_only=True)
    payouts = BatchPayoutSerializer(many=True, read_only=True)

    class Meta:
        model = Batch
        fields = [
            'id', 'name', 'course', 'course_name', 'trainer_names', 'description', 'total_classes',
            'fee_per_student', 'payment_type', 'payment_type_display', 'start_date',
            'class_time', 'class_days', 'meet_link', 'status', 'accepting_enrollments',
            'payouts', 'enrolled_count', 'session_count', 'created_at',
        ]
        read_only_fields = ['created_at']

    def validate(self, data):
        # Existing enrollments' installments are only ever built once, at signup time
        # (see services.create_batch_installments) — they're never recalculated, so
        # changing the fee or payment plan after people have already enrolled would
        # silently leave their installments mismatched with the batch's new numbers.
        if self.instance and self.instance.batch_enrollments.exists():
            locked_fields = ['fee_per_student', 'payment_type']
            changed = [f for f in locked_fields if f in data and data[f] != getattr(self.instance, f)]
            if changed:
                raise serializers.ValidationError(
                    f"Can't change {' or '.join(changed)} — this batch already has enrolled students, and "
                    'their existing installments would not be recalculated automatically.'
                )
        return data

    def validate_trainer_names(self, value):
        if not value:
            return value
        names = [n.strip() for n in value.split(',') if n.strip()]
        return ','.join(names)

    def validate_class_days(self, value):
        if not value:
            return value
        from enrollments.models import DAYS_OF_WEEK
        days = [d.strip().upper() for d in value.split(',') if d.strip()]
        invalid = [d for d in days if d not in DAYS_OF_WEEK]
        if invalid:
            raise serializers.ValidationError(f'Invalid day(s): {", ".join(invalid)}. Use {", ".join(DAYS_OF_WEEK)}.')
        return ','.join(d for d in DAYS_OF_WEEK if d in days)


class MyBatchSerializer(BatchSerializer):
    """Trainer-facing variant of BatchSerializer, used only by MyBatchesView.

    The base `payouts` field lists every payout on a batch — every co-trainer's agreed
    amount for co-taught batches — which would leak other trainers' pay to whoever's
    just viewing their own batches. Scoped here to the requesting trainer's own
    payout(s) on each batch, matching the case-insensitive name match
    BatchPayoutViewSet already uses to scope trainer access.
    """

    payouts = serializers.SerializerMethodField()

    def get_payouts(self, obj):
        trainer_name = self.context['request'].user.trainer.name.lower()
        # obj.payouts is prefetched by MyBatchesView.get_queryset() — filtering the
        # already-fetched list in Python avoids a query per batch.
        own_payouts = [p for p in obj.payouts.all() if p.recipient_name.lower() == trainer_name]
        return BatchPayoutSerializer(own_payouts, many=True).data
