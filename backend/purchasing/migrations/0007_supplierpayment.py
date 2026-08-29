"""`supplier_payment` — money paid to a supplier (FR-PUR-012, D5 S4.3).

**`submission_id` is `NOT NULL UNIQUE`, and that pair is the whole of E3.**

`uq_supplier_payment_submission` is what makes accidental duplicate submission impossible
rather than merely unlikely. The service checks first so the common case gets a clean path,
but the *guarantee* is this index: two concurrent POSTs both pass the check, and only one
survives the insert.

It is `NOT NULL` — unlike `payment.client_uuid`, which had to be nullable because M3-era
callers predate it. This table has no history, so the protection is mandatory from the first
row. A nullable column could not enforce anything at the boundary, and the boundary is where
the ruling requires it enforced.

**No allocation table and no settled flag** (BD-1 Option A, frozen). Which goods receipts a
payment settles is derived through `ledger.walk` on every read.
"""

import core.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchasing', '0006_supplier_payment_number_sequence'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SupplierPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('submission_id', models.UUIDField(unique=True)),
                ('payment_number', models.CharField(max_length=32, unique=True)),
                ('amount', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('method', models.CharField(choices=[('CASH', 'Cash'), ('UPI', 'UPI'), ('BANK', 'Bank transfer'), ('CHEQUE', 'Cheque')], max_length=20)),
                ('reference_number', models.CharField(blank=True, max_length=100)),
                ('payment_date', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_reversed', models.BooleanField(default=False)),
                ('reversed_reason', models.TextField(blank=True)),
                ('reversed_at', models.DateTimeField(blank=True, null=True)),
                ('paid_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supplier_payments_made', to=settings.AUTH_USER_MODEL)),
                ('reversed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name='payments', to='purchasing.supplier')),
            ],
            options={
                'verbose_name': 'supplier payment',
                'verbose_name_plural': 'supplier payments',
                'db_table': 'supplier_payment',
                'ordering': ['-payment_date', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='supplierpayment',
            index=models.Index(fields=['supplier', '-payment_date'], name='ix_spay_supplier_date'),
        ),
        migrations.AddIndex(
            model_name='supplierpayment',
            index=models.Index(fields=['method', '-payment_date'], name='ix_spay_method_date'),
        ),
        migrations.AddIndex(
            model_name='supplierpayment',
            index=models.Index(fields=['paid_by'], name='ix_spay_paid_by'),
        ),
        migrations.AddConstraint(
            model_name='supplierpayment',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='ck_supplier_payment_amount'),
        ),
        migrations.AddConstraint(
            model_name='supplierpayment',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('is_reversed', True), _negated=True), models.Q(('reversed_reason', ''), _negated=True), _connector='OR'), name='ck_supplier_payment_reversed'),
        ),
        migrations.AddConstraint(
            model_name='supplierpayment',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('is_reversed', False), ('reversed_at__isnull', True)), models.Q(('is_reversed', True), ('reversed_at__isnull', False)), _connector='OR'), name='ck_supplier_payment_reversed_pair'),
        ),
    ]
