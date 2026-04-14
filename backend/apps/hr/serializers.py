from rest_framework import serializers

from .models import CalendarItem
from .enums import CalendarItemType

class CalendarItemSerializer(serializers.ModelSerializer):

    category = serializers.SerializerMethodField()
    def get_category(self, obj):
        return CalendarItemType.from_value(obj.category)[1]
    
    user = serializers.SerializerMethodField()
    def get_user(self, obj):
        return obj.user.get_name
    

    title = serializers.SerializerMethodField()
    def get_title(self, obj):
        return f"{obj.title}, {obj.user.get_name}"
    

    class Meta:
        model = CalendarItem
        fields = ('id', 'user', 'title', 'start', 'end', 'category',)