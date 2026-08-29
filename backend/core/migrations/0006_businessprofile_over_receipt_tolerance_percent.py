"""The over-receipt tolerance (`04` T-05, D-PUR-4 / BD-2).

**Default `0.00`, and the default is the decision.** An unconfigured system refuses every
over-receipt, which is the safest commercial position and the one that relaxes later without
another migration. Existing rows — there is exactly one, the singleton — take the default, so
no data migration is needed and no behaviour changes until an owner sets a figure.

The CHECK mirrors `ck_business_profile_discount`: a percentage that can be 200 or -5 is not a
percentage.
"""

from decimal import Decimal

import core.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_alter_auditlog_action'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessprofile',
            name='over_receipt_tolerance_percent',
            field=core.fields.PercentField(decimal_places=2, default=Decimal('0.00'), max_digits=5),
        ),
        migrations.AddConstraint(
            model_name='businessprofile',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('over_receipt_tolerance_percent__gte', 0),
                    ('over_receipt_tolerance_percent__lte', 100),
                ),
                name='ck_business_profile_over_receipt_tolerance',
            ),
        ),
    ]
