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
        return attrs
