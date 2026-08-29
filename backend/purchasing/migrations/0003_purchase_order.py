from decimal import Decimal

import core.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0001_initial'),
        ('purchasing', '0002_purchase_order_number_sequence'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('po_number', models.CharField(max_length=32, unique=True)),
                ('status', models.CharField(choices=[('DRAFT', 'Draft'), ('ISSUED', 'Issued'), ('PARTIALLY_RECEIVED', 'Partially received'), ('RECEIVED', 'Received'), ('CLOSED', 'Closed'), ('CANCELLED', 'Cancelled')], default='DRAFT', max_length=20)),
                ('order_date', models.DateField()),
                ('expected_date', models.DateField(blank=True, null=True)),
                ('subtotal_amount', core.fields.MoneyField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('tax_amount', core.fields.MoneyField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('total_amount', core.fields.MoneyField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('notes', models.TextField(blank=True)),
                ('issued_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_reason', models.TextField(blank=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_orders_cancelled', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_orders_created', to=settings.AUTH_USER_MODEL)),
                ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_orders_issued', to=settings.AUTH_USER_MODEL)),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchase_orders', to='purchasing.supplier')),
            ],
            options={
                'db_table': 'purchase_order',
                'ordering': ['-order_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='PurchaseOrderLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('line_number', models.SmallIntegerField()),
                ('product_code', models.CharField(max_length=32)),
                ('product_name', models.CharField(max_length=200)),
                ('unit_name', models.CharField(max_length=20)),
                ('pack_size_snapshot', models.IntegerField()),
                ('quantity_ordered', core.fields.QuantityField(decimal_places=3, max_digits=14)),
                ('unit_cost', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('tax_rate_percent', core.fields.PercentField(decimal_places=2, max_digits=5)),
                ('taxable_amount', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('tax_amount', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('line_total', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchase_order_lines', to='catalogue.product')),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='purchasing.purchaseorder')),
            ],
            options={
                'db_table': 'purchase_order_line',
                'ordering': ['purchase_order', 'line_number'],
            },
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['supplier'], name='ix_po_supplier'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['status'], name='ix_po_status'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['order_date'], name='ix_po_order_date'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['updated_at'], name='ix_po_updated_at'),
        ),
        migrations.AddConstraint(
            model_name='purchaseorder',
            constraint=models.CheckConstraint(condition=models.Q(('subtotal_amount__gte', 0), ('tax_amount__gte', 0), ('total_amount__gte', 0)), name='ck_po_totals_non_negative'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderline',
            index=models.Index(fields=['product'], name='ix_po_line_product'),
        ),
        migrations.AddConstraint(
            model_name='purchaseorderline',
            constraint=models.UniqueConstraint(fields=('purchase_order', 'line_number'), name='uq_po_line_number'),
        ),
        migrations.AddConstraint(
            model_name='purchaseorderline',
            constraint=models.CheckConstraint(condition=models.Q(('quantity_ordered__gt', 0)), name='ck_po_line_quantity_positive'),
        ),
        migrations.AddConstraint(
            model_name='purchaseorderline',
            constraint=models.CheckConstraint(condition=models.Q(('unit_cost__gte', 0)), name='ck_po_line_unit_cost_non_negative'),
        ),
    ]
