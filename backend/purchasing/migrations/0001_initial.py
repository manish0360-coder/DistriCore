import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalogue', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=32, unique=True)),
                ('name', models.CharField(max_length=200)),
                ('contact_name', models.CharField(blank=True, max_length=200)),
                ('phone', models.CharField(max_length=20)),
                ('alt_phone', models.CharField(blank=True, max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('billing_address', models.TextField()),
                ('dispatch_address', models.TextField(blank=True)),
                ('gstin', models.CharField(blank=True, max_length=15)),
                ('state_code', models.CharField(blank=True, max_length=2)),
                ('payment_terms_days', models.SmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='suppliers_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'supplier',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ProductSupplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('supplier_sku', models.CharField(blank=True, max_length=64)),
                ('is_preferred', models.BooleanField(default=False)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='supplier_links', to='catalogue.product')),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='product_links', to='purchasing.supplier')),
            ],
            options={
                'db_table': 'product_supplier',
                'ordering': ['product', 'supplier'],
            },
        ),
        migrations.AddIndex(
            model_name='supplier',
            index=models.Index(fields=['name'], name='ix_supplier_name'),
        ),
        migrations.AddIndex(
            model_name='supplier',
            index=models.Index(fields=['phone'], name='ix_supplier_phone'),
        ),
        migrations.AddIndex(
            model_name='supplier',
            index=models.Index(fields=['updated_at'], name='ix_supplier_updated_at'),
        ),
        migrations.AddIndex(
            model_name='supplier',
            index=models.Index(condition=models.Q(('is_active', True)), fields=['is_active'], name='ix_supplier_active'),
        ),
        migrations.AddConstraint(
            model_name='supplier',
            constraint=models.CheckConstraint(condition=models.Q(('payment_terms_days__gte', 0)), name='ck_supplier_payment_terms'),
        ),
        migrations.AddIndex(
            model_name='productsupplier',
            index=models.Index(fields=['supplier'], name='ix_prodsup_supplier'),
        ),
        migrations.AddConstraint(
            model_name='productsupplier',
            constraint=models.UniqueConstraint(fields=('product', 'supplier'), name='uq_product_supplier'),
        ),
        migrations.AddConstraint(
            model_name='productsupplier',
            constraint=models.UniqueConstraint(condition=models.Q(('is_preferred', True)), fields=('product',), name='uq_product_supplier_one_preferred'),
        ),
    ]
