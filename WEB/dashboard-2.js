const API_GATEWAY_URL = "https://3hv82jpo9j.execute-api.eu-north-1.amazonaws.com/prod/cihazlar";

document.addEventListener("DOMContentLoaded", () => {
    // Auth kontrolü
    const idToken = localStorage.getItem('idToken');
    if (!idToken) {
        window.location.href = "index.html"; // Token yoksa login'e at
        return;
    }

    fetchDevices(idToken);
});

async function fetchDevices(idToken) {
    const grid = document.getElementById("deviceGrid"); // HTML'indeki kapsayıcı ID
    grid.innerHTML = "<div>Veriler yükleniyor...</div>";

    try {
        const username = localStorage.getItem('username');
const urlWithParams = `${API_GATEWAY_URL}?kullanici=${username}`;
const response = await fetch(urlWithParams, {
            method: 'GET',
            headers: { 
                'Authorization': idToken,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) throw new Error(`Hata kodu: ${response.status}`);

        const data = await response.json(); // AWS'den gelen veriyi al
        console.log("Gelen Veri:", data); // F12'de görebilirsin

        grid.innerHTML = ""; // Yükleniyor yazısını sil

        if (data.length === 0) {
            grid.innerHTML = "<div>Sistemde tanımlı tank verisi bulunamadı.</div>";
            return;
        }

        // Kartları oluştur
        data.forEach(device => {
            // Veritabanındaki "SonDolulukOrani" kısmını al, yoksa 0 say
            const level = parseFloat(device.SonDolulukOrani || 0);
            const statusClass = level < 20 ? 'bg-danger' : 'bg-success'; // 20'nin altı kırmızı
            const deviceName = device.DepoId || "Tanımsız Depo";

            grid.innerHTML += `
                <div class="device-card" style="border: 1px solid #333; padding: 15px; margin: 10px; border-radius: 8px;">
                    <h3>${deviceName}</h3>
                    <p>Seri No: ${device.CihazSeriNo}</p>
                    <div class="progress-container" style="background: #444; height: 20px; border-radius: 10px;">
                        <div class="progress-bar ${statusClass}" style="width: ${level}%; height: 100%; border-radius: 10px; transition: 0.5s;"></div>
                    </div>
                    <p>Doluluk: <strong>%${level}</strong></p>
                </div>
            `;
        });

    } catch (err) {
        console.error("KRİTİK HATA:", err);
        grid.innerHTML = `<div style="color:red;">Veriler yüklenemedi. Detay: ${err.message}</div>`;
    }
}