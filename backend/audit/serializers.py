from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'actor_name', 'action', 'object_repr', 'detail', 'created_at']

    def get_actor_name(self, obj):
        if obj.actor is None:
            return 'System'
        trainer = getattr(obj.actor, 'trainer', None)
        return trainer.name if trainer else obj.actor.username
