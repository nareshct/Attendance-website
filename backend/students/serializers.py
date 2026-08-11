from rest_framework import serializers

from .models import Student


class StudentSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.company_name', read_only=True, default=None)

    class Meta:
        model = Student
        fields = [
            'id', 'student_id', 'name', 'grade', 'parent_name', 'place',
            'parent_phone_number', 'source_type', 'client', 'client_name', 'status', 'created_at',
        ]
        read_only_fields = ['student_id', 'status', 'created_at']

    def validate(self, attrs):
        source_type = attrs.get('source_type', getattr(self.instance, 'source_type', None))
        client = attrs.get('client', getattr(self.instance, 'client', None))
        if source_type == 'B2B' and not client:
            raise serializers.ValidationError({'client': 'A client is required for B2B students.'})

        if self.instance is not None:
            # billing/services.py reads student.source_type live (not a per-enrollment
            # snapshot) — flipping it, or swapping the linked client, while an
            # enrollment is actively being billed would change how already-running
            # classes get billed without reconciling the existing B2C PaymentPlan/
            # installments or B2B client rate. Same hard-block condition as
            # StudentViewSet.archive() — withdraw/complete first, same as archiving.
            changing_source_type = 'source_type' in attrs and attrs['source_type'] != self.instance.source_type
            changing_client = 'client' in attrs and attrs['client'] != self.instance.client
            if changing_source_type or changing_client:
                has_active_enrollment = (
                    self.instance.enrollments.filter(status='ongoing').exists()
                    or self.instance.batch_enrollments.filter(status='active').exists()
                )
                if has_active_enrollment:
                    raise serializers.ValidationError(
                        "This student has an ongoing enrollment or active batch — billing for it assumes "
                        "today's source type/client. Withdraw or complete it first before changing source type "
                        'or client.'
                    )
        return attrs
