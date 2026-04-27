from rest_framework import serializers
from .models import Remnant, Invoice, InvoiceItem, Counterparty

class RemnantSerializer(serializers.ModelSerializer):

    class Meta:
        model = Remnant
        fields = '__all__'


class CounterpartySerializer(serializers.ModelSerializer):
    class Meta:
        model = Counterparty
        fields = [
            'id', 'id_1c', 'full_name', 'short_name', 'bin_number', 
            'iin', 'address', 'phone', 'email', 'is_supplier', 
            'is_customer', 'bank_accounts', 'contracts', 'synced_at'
        ]
        read_only_fields = ['id', 'id_1c', 'bin_number']

class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['id', 'name', 'quantity', 'price', 'total', 'vat_rate', 'vat_amount']

class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'counterparty', 'number', 'status', 'comment', 
            'Sum', 'Date', 'CounterpartyAccount', 'OrganizationAccount', 
            'Payment', 'items'
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        invoice = Invoice.objects.create(**validated_data)
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)
        return invoice

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                InvoiceItem.objects.create(invoice=instance, **item_data)
        return instance