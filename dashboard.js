const API_GATEWAY_URL = "https://3hv82jpo9j.execute-api.eu-north-1.amazonaws.com/prod/cihazlar";

document.addEventListener("DOMContentLoaded", () => {
    const idToken = localStorage.getItem('idToken');
    const username = localStorage.getItem('username');

    if (!idToken || !username) {
        window.location.href = "index.html"; 
        return;
    }

    const welcomeMessage = document.getElementById("welcomeMessage");
    if (welcomeMessage) {
        welcomeMessage.innerText = `Hoş geldiniz, ${username}`;
    }

    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            localStorage.clear();
            window.location.href = "index.html";
        });
    }

    fetchDevices(idToken, username);
});

async function fetchDevices(idToken, username) {
    const grid = document.getElementById("deviceGrid");
    grid.innerHTML = "<div class='loading-state'>Veriler yükleniyor...</div>";

    try {
        const urlWithParams = `${API_GATEWAY_URL}?kullanici=${username}`;

        const response = await fetch(urlWithParams, {
            method: 'GET',
            headers: { 
                'Authorization': idToken,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) throw new Error(`Hata kodu: ${response.status}`);

        const data = await response.json(); 
        grid.innerHTML = ""; 

        if (data.length === 0) {
            grid.innerHTML = "<div class='loading-state'>Hesabınıza tanımlı yetkili bir tank bulunamadı.</div>";
            return;
        }

        // 1. Verileri "CihazSeriNo" bazında GRUPLA
        const groupedDevices = data.reduce((acc, currentTank) => {
            const cihazId = currentTank.CihazSeriNo;
            if (!acc[cihazId]) {
                acc[cihazId] = [];
            }
            acc[cihazId].push(currentTank);
            return acc;
        }, {});

        // 2. Gruplanmış cihazları TEK KART olarak bas
        Object.keys(groupedDevices).forEach(cihazSeriNo => {
            const tanks = groupedDevices[cihazSeriNo];
            let tanksHTML = "";
            const deviceCriticalLevel = tanks.find(tank => tank.KritikSeviye)?.KritikSeviye || 20;
            // Veritabanında özel isim varsa onu al, yoksa standart seri numarasını yaz
            const istasyonAdi = tanks[0].IstasyonAdi ? tanks[0].IstasyonAdi : `İstasyon: ${cihazSeriNo}`;

            // O cihaza ait depoları (barları) oluştur
            tanks.forEach(tank => {
                const level = parseFloat(tank.SonDolulukOrani || 0);
                const tankName = tank.DepoId || "Tanımsız Depo";
                const criticalLevel = tank.KritikSeviye ? parseFloat(tank.KritikSeviye) : parseFloat(deviceCriticalLevel);
                const isInactive = level === 0; 
                
                let statusClass = 'status-normal';
                let bgClass = 'bg-success';
                let opacityStyle = isInactive ? 'opacity: 0.5; filter: grayscale(100%);' : '';
                let badgeText = isInactive ? 'PASİF / %0' : `%${level}`;
                
                if (!isInactive) {
                    if (level <= criticalLevel) {
                        statusClass = 'status-danger';
                        bgClass = 'bg-danger';
                    } else if (level <= criticalLevel + 20) {
                        statusClass = 'status-warning';
                        bgClass = 'bg-warning';
                    }
                } else {
                    statusClass = 'status-warning';
                    bgClass = 'bg-warning';
                }

                tanksHTML += `
                    <div class="tank-section" style="${opacityStyle}">
                        <div class="tank-info-text">
                            <span>${tankName}</span>
                            <span class="status-badge ${statusClass}">${badgeText}</span>
                        </div>
                        <div class="progress-bar-bg">
                            <div class="progress-bar-fill ${bgClass}" style="width: ${level}%;"></div>
                        </div>
                    </div>
                `;
            });

            // 2. depo yoksa gri bir pasif depo barı ekle
            if (tanks.length === 1) {
                tanksHTML += `
                    <div class="tank-section" style="opacity: 0.4; filter: grayscale(100%); margin-top:15px;">
                        <div class="tank-info-text">
                            <span>Depo 2 (Bağlantı Yok)</span>
                            <span class="status-badge status-warning">PASİF</span>
                        </div>
                        <div class="progress-bar-bg">
                            <div class="progress-bar-fill bg-warning" style="width: 0%;"></div>
                        </div>
                    </div>
                `;
            }

            // ANA KARTI YAZDIR (Tek Cihaz = Tek Kart)
            grid.innerHTML += `
                
<div class="device-card" onclick="window.open('detay.html?cihaz=${cihazSeriNo}', 'DetayPopUp', 'width=1100,height=750,left=' + ((screen.width - 1100) / 2) + ',top=' + ((screen.height - 750) / 2) + ',resizable=yes,scrollbars=yes');">
                    <div class="critical-level-chip">Kritik eşik: %${deviceCriticalLevel}</div>
                    <div class="card-header-area">
                        <div>
                            <div class="device-name">${istasyonAdi}</div>
                            <div class="device-id">Bağlı Depo Sayısı: ${tanks.length}</div>
                        </div>
                        <span class="card-open-indicator">➔</span>
                    </div>
                    ${tanksHTML}
                </div>
            `;
        });

    } catch (err) {
        console.error("HATA DETAYI:", err);
        grid.innerHTML = `<div class='loading-state' style='color:#ef4444; border-color:#ef4444;'>Veriler yüklenemedi. Detay: ${err.message}</div>`;
    }
}