# NoktaGaz Harici Cihaz API Rehberi

Bu API, firmanıza atanmış en fazla 200 cihazın en son ölçüm bilgilerini salt okunur olarak sunar. Cihazlar normal çalışma koşullarında yaklaşık **15 dakikada bir** veri gönderir. API daha sık çağrılsa bile yeni bir cihaz ölçümü oluşmayabilir; her zaman `updatedAt` alanını kontrol edin.

## Erişim bilgileri

- API adresi: `https://ouujtyqbj8.execute-api.eu-north-1.amazonaws.com`
- Token adresi: `https://eu-north-1m0xhethbh.auth.eu-north-1.amazoncognito.com/oauth2/token`
- OAuth kapsamı: `noktagaz-external-api/devices.read`
- Token geçerlilik süresi: 60 dakika
- İstemci kimliği: NoktaGaz tarafından güvenli kanaldan paylaşılır.
- İstemci parolası: NoktaGaz tarafından güvenli kanaldan paylaşılır; kaynak koda eklenmemelidir.

## 1. Erişim tokenı alma

```bash
curl --request POST "https://eu-north-1m0xhethbh.auth.eu-north-1.amazoncognito.com/oauth2/token" \
  --user "CLIENT_ID:CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=noktagaz-external-api/devices.read"
```

Yanıttaki `access_token` değerini süresi dolana kadar önbelleğe alın. Her API isteğinde yeniden token almayın.
Bu bilgiler yalnızca sunucu tarafında kullanılmalıdır; `CLIENT_SECRET` tarayıcı veya mobil uygulama içine gömülmemelidir.

## 2. Atanmış cihazları listeleme

```bash
curl "https://ouujtyqbj8.execute-api.eu-north-1.amazonaws.com/v1/devices" \
  --header "Authorization: Bearer ACCESS_TOKEN"
```

Örnek yanıt:

```json
{
  "dataRefreshIntervalMinutes": 15,
  "deviceCount": 1,
  "maxDevices": 200,
  "devices": [
    {
      "serialNumber": "NoktaGaz-0002",
      "stationName": "Örnek İstasyon",
      "region": "Marmara",
      "updatedAt": "2026-11-05T12:30:00+03:00",
      "tanks": [
        {
          "tankId": "depo1",
          "capacityLiters": 10000,
          "fillPercent": 56,
          "criticalLevelPercent": 30,
          "updatedAt": "2026-11-05T12:30:00+03:00"
        }
      ]
    }
  ]
}
```

## 3. Tek cihazı getirme

```bash
curl "https://ouujtyqbj8.execute-api.eu-north-1.amazonaws.com/v1/devices/NoktaGaz-0002" \
  --header "Authorization: Bearer ACCESS_TOKEN"
```

Firma hesabına atanmamış veya bulunmayan cihazlar için `404 device_not_found` döner.

## Alanlar ve kullanım notları

- `fillPercent`: Deponun son alınan doluluk yüzdesidir.
- `capacityLiters`: Depo kapasitesidir.
- `criticalLevelPercent`: Kritik seviye eşiğidir.
- `updatedAt`: İlgili verinin cihazdan en son alındığı zamandır. Güncellik kontrolünde bu alan esas alınmalıdır.
- `region`: Yedi coğrafi bölgeden biri, `Dökme Gaz`, `Dolum Tesisleri` veya `Diğer / Atanmamış` olabilir.
- Ölçüm aralığı yaklaşık 15 dakika olduğundan API'nin 15 dakikadan daha sık sorgulanması önerilmez.
- Tüm zaman değerleri ISO 8601 biçimindedir ve saat dilimi içerir.

## Hata kodları

- `401`: Token eksik, geçersiz veya süresi dolmuş.
- `403`: Token gerekli OAuth kapsamına sahip değil.
- `404`: Cihaz bulunamadı veya firmaya atanmamış.
- `429`: İstek limiti aşıldı; artan bekleme süreleriyle tekrar deneyin.
- `500`: Geçici sunucu hatası; daha sonra tekrar deneyin.
