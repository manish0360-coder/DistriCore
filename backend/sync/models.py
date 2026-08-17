"""sync_operation — the server-side record of every operation a device sends (04 T-26).

**This table is the idempotency guarantee.** `01` §10.3's two non-negotiable metrics —
zero lost transactions, zero duplicates — are enforced by ``uq_sync_operation_client_uuid``
and by the rule that every device write is recorded here *before* the business operation
is attempted.
"""

from __future__ import annotations

from django.db import models


class SyncOperation(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        ACCEPTED = "ACCEPTED", "Accepted"
        DUPLICATE = "DUPLICATE", "Duplicate"
        DEFERRED = "DEFERRED", "Deferred"
        REJECTED = "REJECTED", "Rejected"

    class Type(models.TextChoices):
        """The V1 vocabulary (04 T-26, corrected 2026-08-16 — D-M9.1-1).

        ``DELIVERY_COMPLETE`` is the canonical spelling: `05` §11.2 is the wire contract
        and the shipped M8 client emits it. ``PAYMENT_CREATE``, ``CUSTOMER_CREATE`` and
        ``MEDIA_UPLOAD`` are named because the vocabulary is frozen, and are **not
        dispatchable** in M9.1 — an operation of an unknown or unimplemented type is
        REJECTED, never silently accepted.
        """

        DELIVERY_COMPLETE = "DELIVERY_COMPLETE", "Delivery completed"
        VISIT_CREATE = "VISIT_CREATE", "Visit recorded"

    #: **The idempotency key.** Unique by database constraint, not by service check: a
    #: concurrent double-submit defeats a check and not a constraint (I-6).
    client_uuid = models.UUIDField(unique=True)
    device_id = models.CharField(max_length=64)
    app_user = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="sync_operations"
    )
    operation_type = models.CharField(max_length=40)

    #: Device time. **Metadata — audit and display only.** It does not establish
    #: application order; the `operations` array does (PU-1…PU-3).
    client_created_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RECEIVED
    )
    result_entity_type = models.CharField(max_length=30, blank=True)
    result_entity_id = models.BigIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    error_detail = models.TextField(blank=True)

    #: **Retained only for REJECTED** — the BR-014 evidence. Accepting an operation and
    #: then keeping its body would store business data twice; refusing one and discarding
    #: the body would leave the owner nothing to look at.
    payload = models.JSONField(null=True, blank=True)
    retry_count = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "sync_operation"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "RECEIVED",
                        "ACCEPTED",
                        "DUPLICATE",
                        "DEFERRED",
                        "REJECTED",
                    ]
                ),
                name="ck_sync_operation_status",
            ),
            models.CheckConstraint(
                # A rejection with no reason is a rejection nobody can act on (BR-014).
                condition=~models.Q(status="REJECTED") | ~models.Q(error_code=""),
                name="ck_sync_operation_rejected",
            ),
        ]
        indexes = [
            models.Index(
                fields=["device_id", "client_created_at"],
                name="ix_sync_op_device_created",
            ),
            models.Index(
                fields=["status"],
                name="ix_sync_op_exceptions",
                condition=models.Q(status__in=["DEFERRED", "REJECTED"]),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.operation_type} {self.client_uuid} ({self.status})"
