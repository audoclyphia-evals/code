import logging  # Defines SQLAlchemy ORM metadata and table schemas for the allocation system, including order_lines, batches, allocations, and allocations_view tables. Provides the start_mappers function to configure ORM mappers and includes an event listener for model.Product load events.
from sqlalchemy import (
    Table,
    MetaData,
    Column,
    Integer,
    String,
    Date,
    ForeignKey,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import mapper, relationship, class_mapper
import sqlalchemy.exc

from allocation.domain import model

logger = logging.getLogger(__name__)

metadata = MetaData()

order_lines = Table(
    "order_lines",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("sku", String(255)),
    Column("qty", Integer, nullable=False),
    Column("orderid", String(255)),
)

products = Table(
    "products",
    metadata,
    Column("sku", String(255), primary_key=True),
    Column("version_number", Integer, nullable=False, server_default="0"),
)

batches = Table(
    "batches",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("reference", String(255)),
    Column("sku", ForeignKey("products.sku")),
    Column("_purchased_quantity", Integer, nullable=False),
    Column("eta", Date, nullable=True),
)

allocations = Table(
    "allocations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("orderline_id", ForeignKey("order_lines.id")),
    Column("batch_id", ForeignKey("batches.id")),
)

allocations_view = Table(
    "allocations_view",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("orderid", String(255)),
    Column("sku", String(255)),
    Column("batchref", String(255)),
    UniqueConstraint("orderid", "sku", name="uq_allocations_view_orderid_sku"),
)


def start_mappers():
    """Configures SQLAlchemy ORM mappers for domain model classes: OrderLine, Batch, and Product. It first checks if mappers are already started to prevent duplication, then sets up mappers with relationships, such as linking Batch to OrderLine through allocations and Product to Batch."""
    try:
        class_mapper(model.Product)
        logger.info("Mappers already started, skipping")
        return
    except sqlalchemy.exc.NoInspectionAvailable:
        pass

    logger.info("Starting mappers")
    lines_mapper = mapper(model.OrderLine, order_lines)
    batches_mapper = mapper(
        model.Batch,
        batches,
        properties={
            "_allocations": relationship(
                lines_mapper,
                secondary=allocations,
                collection_class=set,
            )
        },
    )
    mapper(
        model.Product,
        products,
        properties={"batches": relationship(batches_mapper)},
    )


@event.listens_for(model.Product, "load")
def receive_load(product, _):
    product.events = []
