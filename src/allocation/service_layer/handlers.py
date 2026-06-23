# pylint: disable=unused-argument  # Module defining command and event handlers for the allocation service layer, including functions for batch operations, order allocation, deallocation, and notifications, each accepting a command/event and a unit of work or publisher as parameters.
from __future__ import annotations
from dataclasses import asdict
from typing import List, Dict, Callable, Type, TYPE_CHECKING
from sqlalchemy import text
from allocation.domain import commands, events, model
from allocation.domain.model import OrderLine

if TYPE_CHECKING:
    from allocation.adapters import notifications
    from . import unit_of_work


class InvalidSku(Exception):
    pass


class InvalidDeallocation(Exception):
    """Exception raised to indicate an invalid deallocation operation, such as attempting to deallocate a line that isn't allocated or other domain rule violations during deallocation."""
    pass


def add_batch(
    cmd: commands.CreateBatch,
    uow: unit_of_work.AbstractUnitOfWork,
):
    with uow:
        product = uow.products.get(sku=cmd.sku)
        if product is None:
            product = model.Product(cmd.sku, batches=[])
            uow.products.add(product)
        product.batches.append(model.Batch(cmd.ref, cmd.sku, cmd.qty, cmd.eta))
        uow.commit()


def allocate(
    cmd: commands.Allocate,
    uow: unit_of_work.AbstractUnitOfWork,
):
    line = OrderLine(cmd.orderid, cmd.sku, cmd.qty)
    with uow:
        product = uow.products.get(sku=line.sku)
        if product is None:
            raise InvalidSku(f"Invalid sku {line.sku}")
        product.allocate(line)
        uow.commit()


def deallocate(
    """Processes the Deallocate command by creating an OrderLine, fetching the corresponding product via the unit of work, and invoking the domain model's deallocation method. Handles exceptions by converting ValueError to InvalidDeallocation and commits changes upon success."""
    cmd: commands.Deallocate,
    uow: unit_of_work.AbstractUnitOfWork,
):
    line = OrderLine(cmd.orderid, cmd.sku, cmd.qty)
    with uow:
        product = uow.products.get(sku=line.sku)
        if product is None:
            raise InvalidSku(f"Invalid sku {line.sku}")
        try:
            product.deallocate(line)
        except ValueError as e:
            raise InvalidDeallocation(str(e)) from e
        uow.commit()


def reallocate(
    event: events.Deallocated,
    uow: unit_of_work.AbstractUnitOfWork,
):
    allocate(commands.Allocate(**asdict(event)), uow=uow)


def change_batch_quantity(
    """Handles the ChangeBatchQuantity command by retrieving the product associated with the given batch reference, updating the batch quantity in the domain model, and committing the transaction. Raises ValueError if no product is found for the batch reference."""
    cmd: commands.ChangeBatchQuantity,
    uow: unit_of_work.AbstractUnitOfWork,
):
    with uow:
        product = uow.products.get_by_batchref(batchref=cmd.ref)
        if product is None:
            raise ValueError(f"No product found for batch ref '{cmd.ref}'")
        product.change_batch_quantity(ref=cmd.ref, qty=cmd.qty)
        uow.commit()


# pylint: disable=unused-argument


def send_out_of_stock_notification(
    event: events.OutOfStock,
    notifications: notifications.AbstractNotifications,
):
    notifications.send(
        "stock@made.com",
        f"Out of stock for {event.sku}",
    )


def publish_allocated_event(
    event: events.Allocated,
    publish: Callable,
):
    publish("line_allocated", event)


def add_allocation_to_read_model(
    """Responds to Allocated events by inserting a new allocation record into the read model (allocations_view) using the order ID, SKU, and batch reference from the event, and commits the transaction."""
    event: events.Allocated,
    uow: unit_of_work.SqlAlchemyUnitOfWork,
):
    with uow:
        uow.session.execute(
            text(
                "INSERT INTO allocations_view (orderid, sku, batchref) "
                "VALUES (:orderid, :sku, :batchref)"
            ),
            dict(orderid=event.orderid, sku=event.sku, batchref=event.batchref),
        )
        uow.commit()


def remove_allocation_from_read_model(
    """Responds to Deallocated events by deleting the corresponding allocation record from the read model (allocations_view) based on the order ID and SKU from the event, and commits the transaction."""
    event: events.Deallocated,
    uow: unit_of_work.SqlAlchemyUnitOfWork,
):
    with uow:
        uow.session.execute(
            text(
                "DELETE FROM allocations_view "
                "WHERE orderid = :orderid AND sku = :sku"
            ),
            dict(orderid=event.orderid, sku=event.sku),
        )
        uow.commit()


EVENT_HANDLERS = {
    events.Allocated: [publish_allocated_event, add_allocation_to_read_model],
    events.Deallocated: [remove_allocation_from_read_model, reallocate],
    events.OutOfStock: [send_out_of_stock_notification],
}  # type: Dict[Type[events.Event], List[Callable]]

COMMAND_HANDLERS = {
    commands.Allocate: allocate,
    commands.CreateBatch: add_batch,
    commands.ChangeBatchQuantity: change_batch_quantity,
    commands.Deallocate: deallocate,
}  # type: Dict[Type[commands.Command], Callable]
