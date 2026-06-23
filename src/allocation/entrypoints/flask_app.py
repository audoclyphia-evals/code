from datetime import datetime
from flask import Flask, jsonify, request
from allocation.domain import commands
from allocation.service_layer.handlers import InvalidSku, InvalidDeallocation
from allocation import bootstrap, views

app = Flask(__name__)
bus = bootstrap.bootstrap()


def _get_json_field(data: dict, field: str, expected_type: type):
    """Return field value or raise ValueError with a clear message."""
    if field not in data:
        raise KeyError(field)
    value = data[field]
    if not isinstance(value, expected_type):
        raise TypeError(
            f"Field '{field}' must be {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )
    return value


@app.route("/add_batch", methods=["POST"])
def add_batch():
    data = request.get_json(silent=True) or {}
    try:
        ref = _get_json_field(data, "ref", str)
        sku = _get_json_field(data, "sku", str)
        qty = _get_json_field(data, "qty", int)
        eta = data.get("eta")
        if eta is not None:
            eta = datetime.fromisoformat(eta).date()
    except (KeyError, TypeError) as e:
        return {"message": str(e)}, 400
    except ValueError as e:
        return {"message": f"Invalid eta format: {e}"}, 400

    cmd = commands.CreateBatch(ref, sku, qty, eta)
    bus.handle(cmd)
    return "OK", 201


@app.route("/allocate", methods=["POST"])
def allocate_endpoint():
    data = request.get_json(silent=True) or {}
    try:
        orderid = _get_json_field(data, "orderid", str)
        sku = _get_json_field(data, "sku", str)
        qty = _get_json_field(data, "qty", int)
    except (KeyError, TypeError) as e:
        return {"message": str(e)}, 400

    try:
        cmd = commands.Allocate(orderid, sku, qty)
        bus.handle(cmd)
    except InvalidSku as e:
        return {"message": str(e)}, 400

    return "OK", 202


@app.route("/deallocate", methods=["POST"])
def deallocate_endpoint():
    data = request.get_json(silent=True) or {}
    try:
        orderid = _get_json_field(data, "orderid", str)
        sku = _get_json_field(data, "sku", str)
        qty = _get_json_field(data, "qty", int)
    except (KeyError, TypeError) as e:
        return {"message": str(e)}, 400

    try:
        cmd = commands.Deallocate(orderid, sku, qty)
        bus.handle(cmd)
    except (InvalidSku, InvalidDeallocation) as e:
        return {"message": str(e)}, 400

    return "OK", 202


@app.route("/allocations/<orderid>", methods=["GET"])
def allocations_view_endpoint(orderid):
    result = views.allocations(orderid, bus.uow)
    if not result:
        return "not found", 404
    return jsonify(result), 200
