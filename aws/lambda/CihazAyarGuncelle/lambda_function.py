import json

import boto3


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("CihazMeta")

ALLOWED_REGIONS = {
    "Marmara",
    "Ege",
    "Akdeniz",
    "İç Anadolu",
    "Karadeniz",
    "Doğu Anadolu",
    "Güneydoğu Anadolu",
    "Dökme Gaz",
    "Dolum Tesisleri",
    "Diğer / Atanmamış",
}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Content-Type": "application/json",
}


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, ensure_ascii=False),
    }


def parse_integer(value, field_name, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} geçerli bir sayı olmalıdır.")

    if number < minimum or number > maximum:
        raise ValueError(f"{field_name} {minimum} ile {maximum} arasında olmalıdır.")
    return number


def lambda_handler(event, context):
    try:
        body = json.loads((event or {}).get("body") or "{}")
        device_id = str(body.get("cihazId") or "").strip()
        station_name = str(body.get("istasyonAdi") or "").strip()
        region = str(body.get("bolge") or "").strip()

        if not device_id:
            return response(400, {"error": "Cihaz kimliği eksik."})
        if not station_name:
            return response(400, {"error": "İstasyon adı boş bırakılamaz."})
        if len(station_name) > 120:
            return response(400, {"error": "İstasyon adı en fazla 120 karakter olabilir."})
        if region not in ALLOWED_REGIONS:
            return response(400, {"error": "Geçerli bir bölge seçilmelidir."})

        tank_capacities = {
            "depo1": parse_integer(body.get("depo1Hacim"), "Depo 1 hacmi", 1, 10_000_000),
            "depo2": parse_integer(body.get("depo2Hacim"), "Depo 2 hacmi", 1, 10_000_000),
        }
        critical_level = parse_integer(body.get("kritikSeviye"), "Kritik seviye", 0, 100)

        for tank_id, capacity in tank_capacities.items():
            table.update_item(
                Key={"CihazSeriNo": device_id, "DepoId": tank_id},
                UpdateExpression="SET IstasyonAdi = :name, DepoHacmi = :capacity, KritikSeviye = :critical, Bolge = :region",
                ExpressionAttributeValues={
                    ":name": station_name,
                    ":capacity": capacity,
                    ":critical": critical_level,
                    ":region": region,
                },
            )

        return response(200, {"message": "Ayarlar başarıyla kaydedildi.", "bolge": region})

    except ValueError as error:
        return response(400, {"error": str(error)})
    except json.JSONDecodeError:
        return response(400, {"error": "İstek gövdesi geçerli JSON olmalıdır."})
    except Exception as error:
        print(f"HATA OLUŞTU: {error}")
        return response(500, {"error": "Ayarlar kaydedilirken beklenmeyen bir hata oluştu."})
