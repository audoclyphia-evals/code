from sqlalchemy import text  # Module that defines view functions to query allocation read models, specifically for accessing allocation data by order ID using SQLAlchemy queries.
from allocation.service_layer import unit_of_work


def allocations(orderid: str, uow: unit_of_work.SqlAlchemyUnitOfWork):
    """Retrieves allocation details (SKU and batch reference) from the allocations_view table for a specified order ID. Executes a SQL text query within a SQLAlchemy unit of work and returns the results as a list of dictionaries."""
    with uow:
        results = uow.session.execute(
            text("SELECT sku, batchref FROM allocations_view WHERE orderid = :orderid"),
            dict(orderid=orderid),
        )
    return [dict(r) for r in results]
