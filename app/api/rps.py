"""Mock RPS (core banking) write.

HITL BOUNDARY
Exactly one function here mutates the Customer record. Exactly one file in the codebase imports it (app/api/main.py). 
Within that file, exactly one handler calls it.

"""

from sqlalchemy.orm import Session

from app.models import ChangeType, Customer
from app.observability import get_logger

log = get_logger(__name__)


def commit_change(
    session: Session,
    customer_id: str,
    change_type: ChangeType,
    requested_value: dict,
) -> Customer:
    """Apply an approved change to the mock RPS Customer row.

    """
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise LookupError(f"Customer {customer_id!r} not found in mock RPS")

    if change_type == ChangeType.LEGAL_NAME:
        new_name = requested_value.get("new_name")
        if not new_name:
            raise ValueError(
                "requested_value missing 'new_name' for LEGAL_NAME change"
            )
        old_name = customer.name
        customer.name = new_name
        log.info(
            "rps_write",
            change_type=change_type.value,
            customer_id=customer_id,
            old_name=old_name,
            new_name=new_name,
        )
        return customer

    raise NotImplementedError(
        f"change_type {change_type.value} not yet supported in this prototype"
    )