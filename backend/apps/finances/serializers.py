from rest_framework import serializers

from .models import FinanceItem
from .enums import FinanceItemType

class FinanceItemSerializer(serializers.ModelSerializer):

    category = serializers.SerializerMethodField()
    def get_category(self, obj):
        return FinanceItemType.from_value(obj.category)[1]

    class Meta:
        model = FinanceItem
        fields = '__all__'