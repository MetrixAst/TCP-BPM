from rest_framework import serializers
from .models import Remnant, Invoice

class RemnantSerializer(serializers.ModelSerializer):

    class Meta:
        model = Remnant
        fields = '__all__'


class InvoiceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Invoice
        fields = '__all__'