from datetime import datetime  # Flask application entry point that initializes the app, bootstraps the message bus, and defines routes for batch creation, order allocation and deallocation, and allocation views. Includes helper functions and endpoint handlers.
from flask import Flask, jsonify, request
from allocation.domain import commands
from allocation.service_layer.handlers import InvalidSku, InvalidDeallocation
from allocation import bootstrap, views

app = Flask(__name__)
bus = bootstrap.bootstrap()


def _get_json_field(data: dict, field: str, expected_type: type):
    """Extracts a field from a JSON-like dictionary, ensuring it exists and matches the expected type. Raises KeyError if the field is absent, and TypeError if the value is not of the specified type."""
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
    """Flask endpoint for POST /add_batch that extracts ref, sku, qty, and optional eta from JSON, validates required fields with _get_json_field and eta format, and dispatches a CreateBatch command. Returns HTTP 400 for validation errors or invalid eta, and HTTP 201 on successful batch creation."""
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
    """Flask endpoint for POST /allocate that extracts orderid, sku, and qty from JSON, validates them using _get_json_field, and dispatches an Allocate command via the message bus. Returns HTTP 400 on validation errors or invalid SKU, and HTTP 202 on successful allocation."""
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
    """Flask endpoint for POST /deallocate that parses JSON to extract orderid, sku, and qty, validates them using _get_json_field, and dispatches a Deallocate command via the message bus. Returns HTTP 400 on validation errors or invalid deallocation, and HTTP 202 on success."""
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
