"""`goods_receipt` and `goods_receipt_line` (`04` T-32, T-33 — D5 Stage 3).

**`goods_receipt_line.stock_movement_id` is `NOT NULL`, and that is the migration's point.**
It makes a received line with no stock movement unrepresentable at the schema level rather
than merely discouraged by a service (FR-PUR-007). Together with T-13's existing CHECK
forbidding half a source-document reference, the round trip
`stock_movement → goods_receipt → stock_movement` always resolves.

**No `updated_at` on the header**, deliberately: a posted receipt is immutable, and a column
that can never change would be a standing invitation to make it change.

Depends on `inventory` because of that `NOT NULL` FK, and on `0004` because
`grn_number` is `NOT NULL` from the first row and needs its sequence to exist first.
"""

from decimal import Decimal

import core.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0005_stock_movement_append_only'),
        ('purchasing', '0004_goods_receipt_number_sequence'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GoodsReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grn_number', models.CharField(max_length=32, unique=True)),
                ('receipt_date', models.DateField()),
                ('supplier_reference', models.CharField(blank=True, max_length=64)),
                ('subtotal_amount', core.fields.MoneyField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('tax_amount', core.fields.MoneyField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('total_amount', core.fields.MoneyField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name='goods_receipts', to='purchasing.purchaseorder')),
                ('received_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='goods_receipts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'goods receipt',
                'verbose_name_plural': 'goods receipts',
                'db_table': 'goods_receipt',
                'ordering': ['-receipt_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='GoodsReceiptLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity_received', core.fields.QuantityField(decimal_places=3, max_digits=14)),
                ('unit_cost', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('tax_rate_percent', core.fields.PercentField(decimal_places=2, max_digits=5)),
                ('taxable_amount', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('tax_amount', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('line_total', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('goods_receipt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='purchasing.goodsreceipt')),
                ('purchase_order_line', models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name='receipt_lines', to='purchasing.purchaseorderline')),
                ('stock_movement', models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name='goods_receipt_lines', to='inventory.stockmovement')),
            ],
            options={
                'verbose_name': 'goods receipt line',
                'verbose_name_plural': 'goods receipt lines',
                'db_table': 'goods_receipt_line',
                'ordering': ['goods_receipt', 'purchase_order_line'],
            },
        ),
        migrations.AddIndex(
            model_name='goodsreceipt',
            index=models.Index(fields=['purchase_order'], name='ix_grn_purchase_order'),
        ),
        migrations.AddIndex(
            model_name='goodsreceipt',
            index=models.Index(fields=['receipt_date'], name='ix_grn_receipt_date'),
        ),
        migrations.AddConstraint(
            model_name='goodsreceipt',
            constraint=models.CheckConstraint(condition=models.Q(('subtotal_amount__gte', 0), ('tax_amount__gte', 0), ('total_amount__gte', 0)), name='ck_grn_totals_non_negative'),
        ),
        migrations.AddIndex(
            model_name='goodsreceiptline',
            index=models.Index(fields=['purchase_order_line'], name='ix_grn_line_po_line'),
        ),
        migrations.AddConstraint(
            model_name='goodsreceiptline',
            constraint=models.UniqueConstraint(fields=('goods_receipt', 'purchase_order_line'), name='uq_grn_line'),
        ),
        migrations.AddConstraint(
            model_name='goodsreceiptline',
            constraint=models.CheckConstraint(condition=models.Q(('quantity_received__gt', 0)), name='ck_grn_line_quantity_positive'),
        ),
    ]
