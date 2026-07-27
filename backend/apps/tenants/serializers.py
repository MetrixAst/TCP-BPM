from rest_framework import serializers
from .models import Tenant

class TenantSerializer(serializers.ModelSerializer):

    category = serializers.SerializerMethodField()
    def get_category(self, obj):
        return obj.category.title if obj.category else None

    number = serializers.SerializerMethodField()
    def get_number(self, obj):
        return obj.room.number if obj.room else None


    image = serializers.SerializerMethodField()
    def get_image(self, obj):
        return obj.get_image_url()

    class Meta:
        model = Tenant
        fields = '__all__'
