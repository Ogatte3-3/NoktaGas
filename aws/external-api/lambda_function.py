import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

META_TABLE_NAME = os.environ.get("META_TABLE", "CihazMeta")
ACCESS_TABLE_NAME = os.environ.get("ACCESS_TABLE", "HariciApiCihazYetki")
MAX_DEVICES = int(os.environ.get("MAX_DEVICES", "200"))
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "10"))

DYNAMODB = boto3.resource("dynamodb")
META_TABLE = DYNAMODB.Table(META_TABLE_NAME)
ACCESS_TABLE = DYNAMODB.Table(ACCESS_TABLE_NAME)

META_PROJECTION = (
    "CihazSeriNo, DepoId, IstasyonAdi, Bolge, DepoHacmi, "
    "SonDolulukOrani, KritikSeviye, SonGuncelleme"
)


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Unsupported JSON type: {type(value).__name__}")


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "private, max-age=60",
            "x-content-type-options": "nosniff",
        },
        "body": json.dumps(body, ensure_ascii=False, default=_json_default),
    }


def _client_id(event):
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    claims = authorizer.get("jwt", {}).get("claims", {})
    return claims.get("client_id") or claims.get("clientId")


def _allowed_serials(client_id):
    result = ACCESS_TABLE.query(
        KeyConditionExpression=Key("ClientId").eq(client_id),
        ProjectionExpression="CihazSeriNo",
        Limit=MAX_DEVICES,
    )
    return [item["CihazSeriNo"] for item in result.get("Items", [])]


def _is_allowed(client_id, serial_number):
    result = ACCESS_TABLE.get_item(
        Key={"ClientId": client_id, "CihazSeriNo": serial_number},
        ProjectionExpression="CihazSeriNo",
    )
    return "Item" in result


def _read_device(serial_number):
    result = META_TABLE.query(
        KeyConditionExpression=Key("CihazSeriNo").eq(serial_number),
        ProjectionExpression=META_PROJECTION,
    )
    tanks = result.get("Items", [])
    if not tanks:
        return None

    tanks.sort(key=lambda tank: tank.get("DepoId", ""))
    newest_update = max(
        (tank.get("SonGuncelleme", "") for tank in tanks),
        default="",
    )
    first = tanks[0]

    return {
        "serialNumber": serial_number,
        "stationName": first.get("IstasyonAdi"),
        "region": first.get("Bolge", "Diğer / Atanmamış"),
        "updatedAt": newest_update or None,
        "tanks": [
            {
                "tankId": tank.get("DepoId"),
                "capacityLiters": tank.get("DepoHacmi"),
                "fillPercent": tank.get("SonDolulukOrani"),
                "criticalLevelPercent": tank.get("KritikSeviye"),
                "updatedAt": tank.get("SonGuncelleme"),
            }
            for tank in tanks
        ],
    }


def _list_devices(client_id):
    serials = _allowed_serials(client_id)
    if not serials:
        return []

    devices = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(serials))) as executor:
        futures = {executor.submit(_read_device, serial): serial for serial in serials}
        for future in as_completed(futures):
            device = future.result()
            if device:
                devices.append(device)

    devices.sort(key=lambda device: device["serialNumber"])
    return devices


def lambda_handler(event, _context):
    client_id = _client_id(event)
    if not client_id:
        return _response(401, {"error": "unauthorized"})

    route_key = event.get("routeKey", "")

    try:
        if route_key == "GET /v1/devices":
            devices = _list_devices(client_id)
            return _response(
                200,
                {
                    "dataRefreshIntervalMinutes": 15,
                    "deviceCount": len(devices),
                    "maxDevices": MAX_DEVICES,
                    "devices": devices,
                },
            )

        if route_key == "GET /v1/devices/{deviceSerial}":
            serial_number = event.get("pathParameters", {}).get("deviceSerial")
            if not serial_number or not _is_allowed(client_id, serial_number):
                # 404 prevents callers from discovering serial numbers they cannot access.
                return _response(404, {"error": "device_not_found"})

            device = _read_device(serial_number)
            if not device:
                return _response(404, {"error": "device_not_found"})
            return _response(
                200,
                {
                    "dataRefreshIntervalMinutes": 15,
                    "device": device,
                },
            )

        return _response(404, {"error": "route_not_found"})
    except Exception:
        LOGGER.exception("External API request failed for client_id=%s", client_id)
        return _response(500, {"error": "internal_server_error"})
