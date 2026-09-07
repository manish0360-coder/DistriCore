"""manage.py seed_demo_data — Populate rich demo data for mobile app and web admin."""

from __future__ import annotations

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from identity.models import User, Role, UserRole
from customers.models import Zone, Customer
from catalogue.models import Product
from inventory.models import StockLocation, StockMovement, ReasonCode
from inventory.services import record_movement
from orders.models import SalesOrder, SalesOrderLine
from fulfilment.models import Delivery


class Command(BaseCommand):
    help = "Seed rich demo data: owner user, zones, customers, products, stock, orders, and deliveries."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding demo data...")

        # 1. Ensure Roles
        roles_dict = {}
        for code, name in [
            ("OWNER", "Owner"),
            ("SALESMAN", "Salesman"),
            ("DELIVERY", "Delivery"),
            ("RETAILER", "Retailer"),
        ]:
            r, _ = Role.objects.get_or_create(code=code, defaults={"name": name, "is_system": True})
            roles_dict[code] = r

        # 2. Ensure Admin / Owner user
        phone = "+917903324153"
        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={"full_name": "Local Owner", "language": "hi", "is_active": True},
        )
        user.set_password("Manish.0360")
        user.full_name = "Local Owner"
        user.is_active = True
        user.save()

        # Grant OWNER, SALESMAN, DELIVERY
        for code in ["OWNER", "SALESMAN", "DELIVERY"]:
            UserRole.objects.get_or_create(app_user=user, role=roles_dict[code])

        self.stdout.write(self.style.SUCCESS(f"User {user.phone} ready with roles."))

        # 3. Ensure Zones
        zone_central, _ = Zone.objects.get_or_create(
            name="Central Market Zone",
            defaults={"road_name": "Station Road", "pin_code": "800001", "city": "Patna", "assigned_user": user},
        )
        if zone_central.assigned_user != user:
            zone_central.assigned_user = user
            zone_central.save()

        zone_south, _ = Zone.objects.get_or_create(
            name="South Market Zone",
            defaults={"road_name": "Kankarbagh Main Road", "pin_code": "800020", "city": "Patna", "assigned_user": user},
        )
        if zone_south.assigned_user != user:
            zone_south.assigned_user = user
            zone_south.save()

        # 4. Ensure Customers
        customer_defs = [
            ("CUST-0001", "Gupta Kirana Store", "+919811100001", "Shop 4, Central Market, Patna", zone_central),
            ("CUST-0002", "Sharma General Store", "+919811100002", "Near Bus Stand, Station Road, Patna", zone_central),
            ("CUST-0003", "Verma Supermarket", "+919811100003", "12 Main Market, Gandhi Maidan, Patna", zone_central),
            ("CUST-0004", "Tiwari Provision Store", "+919811100004", "South Colony, Kankarbagh, Patna", zone_south),
            ("CUST-0005", "Rajesh Traders", "+919811100005", "Bypass Road, Patna", zone_south),
        ]
        customers = []
        for code, shop, cphone, addr, z in customer_defs:
            c, _ = Customer.objects.get_or_create(
                code=code,
                defaults={
                    "shop_name": shop,
                    "phone": cphone,
                    "billing_address": addr,
                    "zone": z,
                    "credit_limit_amount": Decimal("50000.00"),
                    "credit_days": 15,
                    "is_active": True,
                },
            )
            customers.append(c)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(customers)} customers."))

        # 5. Products
        product_defs = [
            ("P-0001", "Parle-G Biscuits 100g", Decimal("10.00"), Decimal("18.00"), "19053100", 24),
            ("P-0002", "Maggi 2-Minute Noodles 70g", Decimal("14.00"), Decimal("18.00"), "19023010", 12),
            ("P-0003", "Tata Salt 1kg", Decimal("28.00"), Decimal("0.00"), "25010010", 10),
            ("P-0004", "Fortune Sunlite Oil 1L", Decimal("145.00"), Decimal("5.00"), "15121910", 10),
            ("P-0005", "Colgate Strong Teeth 100g", Decimal("65.00"), Decimal("18.00"), "33061020", 12),
        ]
        products = []
        for code, name, price, tax, hsn, pack in product_defs:
            p, _ = Product.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "selling_price": price,
                    "tax_rate_percent": tax,
                    "hsn_code": hsn,
                    "pack_size": pack,
                    "is_active": True,
                },
            )
            products.append(p)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(products)} products."))

        # 6. Warehouse & Stock
        loc, _ = StockLocation.objects.get_or_create(code="MAIN", defaults={"name": "Main Warehouse", "is_default": True})
        for p in products:
            if not StockMovement.objects.filter(product=p, location=loc).exists():
                record_movement(
                    actor=user,
                    product=p,
                    quantity=Decimal("500"),
                    movement_type=StockMovement.Type.RECEIPT,
                    notes="Demo opening stock",
                    reason_code=ReasonCode.objects.get(code="OPENING"),
                )

        # 7. Orders & Deliveries
        today = timezone.now().date()
        for idx, (cust, prod, qty) in enumerate([
            (customers[0], products[0], Decimal("50")),
            (customers[1], products[1], Decimal("30")),
            (customers[2], products[3], Decimal("10")),
        ], start=1):
            order_num = f"SO-2026-DEMO{idx:02d}"
            tax_amt = (prod.selling_price * qty * prod.tax_rate_percent / Decimal("100")).quantize(Decimal("0.01"))
            line_tot = (prod.selling_price * qty + tax_amt).quantize(Decimal("0.01"))
            order, o_created = SalesOrder.objects.get_or_create(
                order_number=order_num,
                defaults={
                    "customer": cust,
                    "status": SalesOrder.Status.DISPATCHED,
                    "source": SalesOrder.Source.APP,
                    "order_date": today,
                    "expected_delivery_date": today,
                    "assigned_user": user,
                    "subtotal_amount": prod.selling_price * qty,
                    "discount_amount": Decimal("0.00"),
                    "tax_amount": tax_amt,
                    "total_amount": line_tot,
                },
            )
            if o_created:
                SalesOrderLine.objects.create(
                    sales_order=order,
                    line_number=1,
                    product=prod,
                    product_code=prod.code,
                    product_name=prod.name,
                    unit_name="Unit",
                    pack_size_snapshot=prod.pack_size,
                    quantity=qty,
                    unit_price=prod.selling_price,
                    tax_rate_percent=prod.tax_rate_percent,
                    taxable_amount=prod.selling_price * qty,
                    tax_amount=tax_amt,
                    line_total=line_tot,
                )

            Delivery.objects.get_or_create(
                sales_order=order,
                defaults={
                    "assigned_user": user,
                    "status": Delivery.Status.PENDING,
                    "dispatched_at": timezone.now(),
                },
            )

        self.stdout.write(self.style.SUCCESS("Seeded demo orders and dispatched deliveries!"))
