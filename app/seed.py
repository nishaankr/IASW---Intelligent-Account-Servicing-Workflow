"""Database seed script

Creates the schema (drop + recreate so it's safe to re-run during dev) and populates the mock-RPS table with a handful of customers.

Run with:
    python -m app.seed

A real system would not use a seed script, we are using this to instantialize ur Db and fill details
"""

from datetime import datetime

from app.db import Base, SessionLocal, engine
from app.models import Customer
from app.observability import configure_logging, get_logger


_SEED_CUSTOMERS = [
    Customer(
        customer_id="C001",
        name="Priya Sharma",
        date_of_birth=datetime(1995, 3, 14),
        email="priya.sharma@example.com",
        phone="+91-9876543210",
        address="42 MG Road, Bangalore, KA 560001, India",
    ),
    Customer(
        customer_id="C002",
        name="Rahul Verma",
        date_of_birth=datetime(1989, 7, 22),
        email="rahul.verma@example.com",
        phone="+91-9123456780",
        address="11 Park Street, Kolkata, WB 700016, India",
    ),
    Customer(
        customer_id="C003",
        name="Ananya Iyer",
        date_of_birth=datetime(1992, 11, 5),
        email="ananya.iyer@example.com",
        phone="+91-9988776655",
        address="7 Marine Drive, Mumbai, MH 400002, India",
    ),
    Customer(
        customer_id="C004",
        name="Pooja Singh",
        date_of_birth=datetime(1998, 9, 2),
        email="pooja.rawat@example.com",
        phone="+91-9123456780",
        address="19 Park Street, Kolkata, WB 700018, India",
    ),
]


def reset_schema() -> None:
    #Drop every table the ORM knows about, then recreate from scratch.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_customers() -> None:
    #Insert the  mock-RPS customers.
    with SessionLocal() as session:
        session.add_all(_SEED_CUSTOMERS)
        session.commit()


def main() -> None:
    configure_logging()
    log = get_logger(__name__)

    log.info("seed_start")
    reset_schema()
    log.info("schema_reset", tables=sorted(Base.metadata.tables.keys()))
    seed_customers()
    log.info("seed_complete", customers=[c.customer_id for c in _SEED_CUSTOMERS])


if __name__ == "__main__":
    main()