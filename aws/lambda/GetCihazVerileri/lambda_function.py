import json

import boto3


dynamodb = boto3.resource('dynamodb')
meta_table = dynamodb.Table('CihazMeta')
yetki_table = dynamodb.Table('KullaniciCihazYetki')

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,OPTIONS',
}


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps(body, default=str),
    }


def normalize_username(username):
    """DynamoDB kullanıcı anahtarlarını boşluk ve harf biçiminden bağımsız eşleştirir."""
    return str(username).strip().casefold()


def get_allowed_device_metadata(allowed_devices):
    """CihazMeta tablosunu sayfalayarak yalnızca yetkili cihazları döndürür."""
    allowed_device_set = {str(device) for device in allowed_devices}
    devices = []
    scan_kwargs = {}

    while True:
        scan_response = meta_table.scan(**scan_kwargs)
        devices.extend(
            item
            for item in scan_response.get('Items', [])
            if str(item.get('CihazSeriNo')) in allowed_device_set
        )

        last_key = scan_response.get('LastEvaluatedKey')
        if not last_key:
            break

        scan_kwargs['ExclusiveStartKey'] = last_key

    return devices


def lambda_handler(event, context):
    try:
        if event is None:
            return response(400, {'error': 'Event boş geldi'})

        query_params = event.get('queryStringParameters') or {}
        kullanici = query_params.get('kullanici')

        if not kullanici:
            return response(400, {'error': 'Kullanıcı bilgisi (kullanici) eksik'})

        normalized_username = normalize_username(kullanici)
        if not normalized_username:
            return response(400, {'error': 'Kullanıcı bilgisi (kullanici) eksik'})

        yetki_response = yetki_table.get_item(Key={'KullaniciAdi': normalized_username})
        item = yetki_response.get('Item')

        if not item:
            return response(200, [])

        allowed_devices = item.get('YetkiliCihazlar', [])
        if not allowed_devices:
            return response(200, [])

        devices = get_allowed_device_metadata(allowed_devices)
        return response(200, devices)

    except Exception as error:
        print(f'KRİTİK HATA: {error}')
        return response(500, {'error': str(error)})
