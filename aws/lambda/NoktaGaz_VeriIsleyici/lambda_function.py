import json
import boto3
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo

dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses', region_name='eu-north-1')

meta_table = dynamodb.Table('CihazMeta')
log_table = dynamodb.Table('CihazGeciciLog')

# Türkiye saati (UTC+03:00)
TURKEY_TZ = ZoneInfo('Europe/Istanbul')

# Gönderici her zaman yetkili/doğrulanmış adres olmalı
DEFAULT_ADMIN_MAIL = "tekinoguzhana@gmail.com"
SENDER_IDENTITY = f"NoktaGAZ LPG Ölçüm Sistemi <{DEFAULT_ADMIN_MAIL}>"


def lambda_handler(event, context):
    try:
        # 1. CİHAZ ID AYIKLAMA
        cihaz_id = event.get('cihaz_id')
        if not cihaz_id:
            cihaz_id = "NoktaGaz-00001"

        # Bütün zaman alanlarını aynı Türkiye saati üzerinden üret.
        now_tr = datetime.now(TURKEY_TZ)
        timestamp = event.get('timestamp', int(now_tr.timestamp() * 1000))
        current_time = now_tr.isoformat()

        # DynamoDB TTL Unix zamanı saniye cinsinden olmalıdır. Unix zamanı saat
        # diliminden bağımsızdır; now_tr üzerinden hesaplanarak 7 gün eklenir.
        silinme_zamani = int(now_tr.timestamp()) + 604800

        print(f"====== TELEMETRİ İŞLEME BAŞLADI (Cihaz: {cihaz_id}) ======")
        print(f"Gelen Event İçeriği: {json.dumps(event, default=str)}")

        # 2. Döngü: Gelen paketteki tüm depoları sırayla yakalar
        for key, value in event.items():
            if key.endswith('_yuzde'):
                depo_id = key.replace('_yuzde', '')
                print(f"\n▶️ [{depo_id}] için süreç başladı. Gelen Değer: {value}")

                try:
                    anlik_yuzde = Decimal(str(value))

                    # CihazMeta'dan deponun mevcut durumunu çek
                    meta_response = meta_table.get_item(Key={'CihazSeriNo': cihaz_id, 'DepoId': depo_id})
                    eski_meta = meta_response.get('Item', {})

                    istasyon_adi = eski_meta.get('IstasyonAdi', cihaz_id)

                    # --- ÇOKLU MAİL AYIKLAMA MANTIĞI ---
                    raw_mail_data = eski_meta.get('YetkiliMail', DEFAULT_ADMIN_MAIL)
                    hedef_mailler = []

                    # Eğer DB'den Liste olarak gelirse
                    if isinstance(raw_mail_data, list):
                        hedef_mailler = raw_mail_data
                    # Eğer DB'den virgülle ayrılmış Metin (String) olarak gelirse
                    elif isinstance(raw_mail_data, str):
                        hedef_mailler = [m.strip() for m in raw_mail_data.split(',') if m.strip()]

                    # Güvenlik kontrolü: Liste boş kalırsa ana admine at
                    if not hedef_mailler:
                        hedef_mailler = [DEFAULT_ADMIN_MAIL]
                    # -----------------------------------

                    eski_oran = eski_meta.get('SonDolulukOrani', anlik_yuzde)
                    eski_is_filling = eski_meta.get('IsFilling', False)
                    eski_fill_start = eski_meta.get('FillStartPercent', anlik_yuzde)
                    kritik_seviye = eski_meta.get('KritikSeviye', Decimal('20'))
                    alarm_gonderildi = eski_meta.get('AlarmGonderildi', False)

                    yeni_is_filling = eski_is_filling
                    yeni_fill_start = eski_fill_start
                    yeni_alarm_durumu = alarm_gonderildi

                    # Eski kayıtlar için bilinen en iyi başlangıç değeri SonGuncelleme'dir.
                    # Bundan sonra yalnızca doluluk yüzdesi gerçekten değişirse ilerletilir.
                    son_seviye_degisimi = eski_meta.get(
                        'SonSeviyeDegisimi',
                        eski_meta.get('SonGuncelleme', current_time)
                    )
                    if not eski_meta or anlik_yuzde != eski_oran:
                        son_seviye_degisimi = current_time

                    # --- Dolum Algoritmaları ---
                    if anlik_yuzde > eski_oran:
                        if not eski_is_filling:
                            yeni_is_filling = True
                            yeni_fill_start = eski_oran
                            print(f"   [{depo_id}] 📈 Dolum başladı tetiklendi. Başlangıç: %{yeni_fill_start}")
                    elif anlik_yuzde < eski_oran:
                        if eski_is_filling:
                            dolum_miktari = eski_oran - eski_fill_start
                            if dolum_miktari > 0:
                                print(f"   [{depo_id}] 📉 Dolum bitti. Fark: %{dolum_miktari} | Log yazılıyor...")
                                log_table.put_item(
                                    Item={
                                        'CihazSeriNo': cihaz_id,
                                        'DepoId#ZamanDamgasi': f"{depo_id}#DOLUM#{timestamp}",
                                        'LogTipi': 'DOLUM_OZETI',
                                        'IslemTipi': 'DOLUM_OZETI',
                                        'BaslangicYuzdesi': yeni_fill_start,
                                        'BitisYuzdesi': eski_oran,
                                        'Fark': dolum_miktari,
                                        'Tarih': current_time,
                                        'SilinmeZamani': silinme_zamani
                                    }
                                )
                            yeni_is_filling = False

                    # --- Akıllı SES HTML Alarm Algoritması ---
                    if anlik_yuzde <= kritik_seviye:
                        if not alarm_gonderildi:
                            try:
                                print(f"   [{depo_id}] 🚨 Kritik sınır aşıldı (%{anlik_yuzde} <= %{kritik_seviye}). SES Mail atılıyor. Hedefler: {hedef_mailler}")
                                html_body = f"""
                                <html>
                                <head>
                                    <style>
                                        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; margin: 0; padding: 20px; background-color: #f9f9f9; }}
                                        .container {{ max-width: 600px; background: #ffffff; border-radius: 8px; padding: 30px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-top: 6px solid #d9534f; }}
                                        .header {{ font-size: 22px; font-weight: bold; color: #d9534f; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 1px; }}
                                        .alert-box {{ background-color: #fdf7f7; border-left: 4px solid #d9534f; padding: 15px; margin-bottom: 25px; border-radius: 4px; }}
                                        .meta-table {{ width: 100%; border-collapse: collapse; margin-bottom: 25px; }}
                                        .meta-table td {{ padding: 10px; border-bottom: 1px solid #eee; }}
                                        .meta-table td.label {{ font-weight: bold; color: #666; width: 40%; }}
                                        .footer {{ font-size: 12px; color: #999; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px; line-height: 1.5; }}
                                    </style>
                                </head>
                                <body>
                                    <div class="container">
                                        <div class="header">⚠️ KRİTİK SEVİYE UYARISI</div>
                                        <div class="alert-box">
                                            <strong>Sayın Yetkili,</strong><br>
                                            Sistemimize bağlı bir depoda kritik seviye sınırı aşılmıştır. Lütfen aşağıdaki verileri kontrol edip dolum operasyonunu planlayınız.
                                        </div>
                                        <table class="meta-table">
                                            <tr><td class="label">İstasyon Adı:</td><td><strong>{istasyon_adi}</strong> <span style="font-size: 11px; color: #999;">({cihaz_id})</span></td></tr>
                                            <tr><td class="label">Depo Tanımı:</td><td>{depo_id.upper()}</td></tr>
                                            <tr><td class="label">Kritik Eşik Seviyesi:</td><td>%{kritik_seviye}</td></tr>
                                            <tr><td class="label" style="color: #d9534f;">Ölçülen Anlık Seviye:</td><td style="font-weight: bold; color: #d9534f;">%{anlik_yuzde}</td></tr>
                                        </table>
                                        <p>Bu e-posta NoktaGAZ IoT altyapısı tarafından otomatik olarak üretilmiştir. Lütfen yanıtlamayınız.</p>
                                        <div class="footer">
                                            <strong>NoktaGAZ Otomasyon ve LPG Ölçüm Sistemleri</strong><br>
                                            Bulut Veri Entegrasyon Servisi • Kesintisiz Takip
                                        </div>
                                    </div>
                                </body>
                                </html>
                                """

                                ses_client.send_email(
                                    Source=SENDER_IDENTITY,
                                    Destination={'ToAddresses': hedef_mailler},
                                    Message={
                                        'Subject': {'Data': f"🚨 Kritik Eşik: {istasyon_adi} - {depo_id.upper()}"},
                                        'Body': {'Html': {'Data': html_body}}
                                    }
                                )
                                yeni_alarm_durumu = True
                                print(f"   [{depo_id}] ✅ SES Mail {hedef_mailler} adreslerine başarılı gönderildi.")
                            except Exception as mail_err:
                                print(f"   [{depo_id}] ❌ SES Mail hatası ({hedef_mailler}): {str(mail_err)}")
                    else:
                        yeni_alarm_durumu = False

                    # --- Veritabanı Kayıt İşlemleri ---

                    eski_meta['CihazSeriNo'] = cihaz_id
                    eski_meta['DepoId'] = depo_id
                    eski_meta['SonDolulukOrani'] = anlik_yuzde
                    eski_meta['SonIletisim'] = current_time
                    eski_meta['SonSeviyeDegisimi'] = son_seviye_degisimi
                    # Geriye uyumluluk: mevcut ekran ve entegrasyonlar bu alanı kullanıyor.
                    eski_meta['SonGuncelleme'] = current_time
                    eski_meta['IsFilling'] = yeni_is_filling
                    eski_meta['FillStartPercent'] = yeni_fill_start
                    eski_meta['KritikSeviye'] = kritik_seviye
                    eski_meta['AlarmGonderildi'] = yeni_alarm_durumu

                    # Eğer JSON'dan ilk defa okunduysa, varsayılan DB kaydında da String formatında görünsün
                    if 'YetkiliMail' not in eski_meta:
                        eski_meta['YetkiliMail'] = DEFAULT_ADMIN_MAIL

                    meta_table.put_item(Item=eski_meta)
                    print(f"   [{depo_id}] ✅ CihazMeta tablosu başarıyla güncellendi.")

                    # 2. Geçici Log Tablosuna Yaz
                    log_table.put_item(
                        Item={
                            'CihazSeriNo': cihaz_id,
                            'DepoId#ZamanDamgasi': f"{depo_id}#{timestamp}",
                            'LogTipi': 'TELEMETRI',
                            'IslemTipi': 'TELEMETRI',
                            'DolulukOrani': anlik_yuzde,
                            'Tarih': current_time,
                            'SilinmeZamani': silinme_zamani
                        }
                    )
                    print(f"   [{depo_id}] ✅ CihazGeciciLog tablosu başarıyla güncellendi.")
                    print(f"🏁 [{depo_id}] işlemi sorunsuz TAMAMLANDI.")

                except Exception as depo_err:
                    print(f"❌ HATA: [{depo_id}] işlenirken döngü içi hata oluştu: {str(depo_err)}")

        print("\n====== TELEMETRİ İŞLEME SÜRECİ BİTTİ ======")
        return {'statusCode': 200, 'body': json.dumps('İşlem akışı tamamlandı.')}

    except Exception as e:
        print(f"🚨 GLOBAL LAMBDA HATASI: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps(f"Global hata: {str(e)}")}
