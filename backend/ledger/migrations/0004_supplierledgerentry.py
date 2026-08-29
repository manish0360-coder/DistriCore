"""`supplier_ledger_entry` — the payables sibling of T-22 (`04` T-34, BR-005, D-PUR-3).

**Owned by `ledger`, not `purchasing`**, because BR-005 requires it on the same terms as the
customer ledger and `ledger` already owns immutability, the derived-balance rule and the
one-opening constraint.

The append-only trigger is **not** applied here. `customer_ledger_entry`'s Python-level
refusals live on the model and the queryset (`0002`), and this table carries the identical
pair; the database-level trigger is a `core.audit_log` measure that the customer ledger does
not have either. Symmetry with T-22 is the design, so nothing stronger is added on one side.
"""

import core.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0003_customerledgerentry_uq_cle_one_opening_per_customer'),
        ('purchasing', '0003_purchase_order'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SupplierLedgerEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('entry_date', models.DateField()),
                ('entry_type', models.CharField(choices=[('GOODS_RECEIPT', 'Goods receipt'), ('PAYMENT', 'Payment'), ('OPENING', 'Opening balance'), ('ADJUSTMENT', 'Adjustment'), ('DEBIT_NOTE', 'Debit note')], max_length=20)),
                ('amount', core.fields.MoneyField(decimal_places=2, max_digits=14)),
                ('source_document_type', models.CharField(blank=True, max_length=30)),
                ('source_document_id', models.BigIntegerField(blank=True, null=True)),
                ('narration', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supplier_ledger_entries', to=settings.AUTH_USER_MODEL)),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name='ledger_entries', to='purchasing.supplier')),
            ],
            options={
                'verbose_name': 'supplier ledger entry',
                'verbose_name_plural': 'supplier ledger entries',
                'db_table': 'supplier_ledger_entry',
                'ordering': ['supplier', 'entry_date', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='supplierledgerentry',
            index=models.Index(fields=['supplier', 'entry_date', 'id'], name='ix_sle_supplier_date'),
        ),
        migrations.AddIndex(
            model_name='supplierledgerentry',
            index=models.Index(fields=['source_document_type', 'source_document_id'], name='ix_sle_source'),
        ),
        migrations.AddIndex(
            model_name='supplierledgerentry',
            index=models.Index(fields=['entry_type', 'entry_date'], name='ix_sle_entry_type_date'),
        ),
        migrations.AddConstraint(
            model_name='supplierledgerentry',
            constraint=models.CheckConstraint(condition=models.Q(('amount', 0), _negated=True), name='ck_sle_amount_non_zero'),
        ),
        migrations.AddConstraint(
            model_name='supplierledgerentry',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('source_document_id__isnull', True), ('source_document_type', '')), models.Q(models.Q(('source_document_type', ''), _negated=True), ('source_document_id__isnull', False)), _connector='OR'), name='ck_sle_source_pair'),
        ),
        migrations.AddConstraint(
            model_name='supplierledgerentry',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('entry_type', 'GOODS_RECEIPT'), ('amount__gt', 0)), models.Q(('entry_type__in', ['PAYMENT', 'DEBIT_NOTE']), ('amount__lt', 0)), ('entry_type__in', ['OPENING', 'ADJUSTMENT']), _connector='OR'), name='ck_sle_sign'),
        ),
        migrations.AddConstraint(
            model_name='supplierledgerentry',
            constraint=models.UniqueConstraint(condition=models.Q(('entry_type', 'OPENING')), fields=('supplier',), name='uq_sle_one_opening_per_supplier'),
        ),
    ]
