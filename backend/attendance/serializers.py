from rest_framework import serializers

from enrollments.models import SubstituteAssignment
from enrollments.services import trainer_payment_gate

from .models import Attendance, AttendanceRequest


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='enrollment.student.name', read_only=True)
    course_name = serializers.CharField(source='enrollment.course.name', read_only=True)
    marked_by_name = serializers.CharField(source='marked_by.name', read_only=True)
    in_closed_cycle = serializers.SerializerMethodField()
    approved_via_request = serializers.SerializerMethodField()
    topic_covered = serializers.CharField(required=True, allow_blank=False)
    trainer_rate = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = [
            'id', 'enrollment', 'student_name', 'course_name', 'date', 'status',
            'topic_covered', 'marked_by', 'marked_by_name', 'in_closed_cycle', 'approved_via_request',
            'trainer_rate',
        ]
        read_only_fields = ['marked_by']

    def get_trainer_rate(self, obj):
        # What this specific class actually paid (or would pay) the trainer who marked
        # it — mirrors billing.services.trainer_totals_for_range()'s own per-row
        # resolution exactly: an enrollment-specific override first (see
        # Enrollment.trainer_rate_per_class), else the rate in effect on the class's own
        # date, else the trainer's live rate. Powers the rate column on the trainer's
        # My Earnings "last cycle classes" list.
        from billing.services import historical_rate

        if obj.enrollment.trainer_rate_per_class is not None:
            return obj.enrollment.trainer_rate_per_class
        rate = historical_rate(obj.marked_by, obj.enrollment.course_id, obj.date)
        if rate is None:
            rate = obj.marked_by.rate_for(obj.enrollment.course)
        return rate

    def get_in_closed_cycle(self, obj):
        # Annotated by the viewset's queryset for list/retrieve/update; only
        # missing right after a fresh create(), where a direct check is cheap.
        annotated = getattr(obj, 'in_closed_cycle', None)
        if annotated is not None:
            return annotated

        from billing.models import BillingCycle

        return BillingCycle.objects.filter(
            cycle_start__lte=obj.date, cycle_end__gte=obj.date
        ).exclude(status='open').exists()

    def get_approved_via_request(self, obj):
        return getattr(obj, 'approval_request', None) is not None

    def validate_enrollment(self, enrollment):
        if enrollment.status == 'withdrawn':
            raise serializers.ValidationError('This enrollment has been withdrawn — attendance can no longer be marked for it.')
        if enrollment.status == 'completed':
            raise serializers.ValidationError('This enrollment is already completed — attendance can no longer be marked for it.')

        request = self.context['request']
        if not request.user.is_staff:
            gate = trainer_payment_gate(enrollment)
            if gate == 'hidden':
                raise serializers.ValidationError('This student is not yet available — waiting on the first payment.')
            if gate == 'blocked':
                raise serializers.ValidationError(
                    'Attendance is paused for this student until the next installment is recorded as paid.'
                )
        return enrollment

    def validate(self, attrs):
        # Only relevant on create — an update never carries 'enrollment' from
        # a trainer (perform_update restricts them to topic_covered/date), and
        # get_queryset() already scopes which rows a trainer can reach for
        # update/delete to marked_by=themselves, so re-checking ownership here
        # would incorrectly reject a trainer editing their own past entry
        # after a substitute-coverage window has since ended.
        request = self.context['request']
        if self.instance is None and not request.user.is_staff:
            enrollment = attrs['enrollment']
            attendance_date = attrs.get('date')
            trainer = request.user.trainer

            is_owner = enrollment.trainer_id == trainer.id
            is_covering = attendance_date is not None and SubstituteAssignment.objects.filter(
                enrollment=enrollment, substitute_trainer=trainer,
                start_date__lte=attendance_date, end_date__gte=attendance_date,
            ).exists()
            if not is_owner and not is_covering:
                raise serializers.ValidationError('You can only mark attendance for your own students.')

        # A class only happens once — block a duplicate row for the same
        # enrollment+date (double-click, retry, etc.), on both create and update.
        enrollment = attrs.get('enrollment', getattr(self.instance, 'enrollment', None))
        attendance_date = attrs.get('date', getattr(self.instance, 'date', None))
        if enrollment is not None and attendance_date is not None:
            qs = Attendance.objects.filter(enrollment=enrollment, date=attendance_date)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError('Attendance for this class on this date has already been marked.')
        return attrs


class AttendanceRequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='enrollment.student.name', read_only=True)
    course_name = serializers.CharField(source='enrollment.course.name', read_only=True)
    trainer_name = serializers.CharField(source='requested_by.name', read_only=True)

    class Meta:
        model = AttendanceRequest
        fields = [
            'id', 'enrollment', 'student_name', 'course_name', 'date', 'topic_covered',
            'requested_by', 'trainer_name', 'status', 'created_at', 'reviewed_at',
        ]
        read_only_fields = ['requested_by', 'status', 'created_at', 'reviewed_at']
