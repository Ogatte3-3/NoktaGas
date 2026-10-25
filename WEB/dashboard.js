const API_GATEWAY_URL = "https://3hv82jpo9j.execute-api.eu-north-1.amazonaws.com/prod/cihazlar";

const DEVICE_REGIONS = [
    "Marmara",
    "Ege",
    "Akdeniz",
    "İç Anadolu",
    "Karadeniz",
    "Doğu Anadolu",
    "Güneydoğu Anadolu",
    "Diğer / Atanmamış"
];

const ALL_REGIONS = "Tümü";
let groupedDevices = {};
let activeRegion = ALL_REGIONS;

document.addEventListener("DOMContentLoaded", () => {
    const idToken = localStorage.getItem("idToken");
    const username = localStorage.getItem("username");

    if (!idToken || !username) {
        window.location.href = "index.html";
        return;
    }

    const welcomeMessage = document.getElementById("welcomeMessage");
    if (welcomeMessage) welcomeMessage.innerText = `Hoş geldiniz, ${username}`;

    document.getElementById("logoutBtn")?.addEventListener("click", () => {
        localStorage.clear();
        window.location.href = "index.html";
    });

    document.getElementById("refreshPageBtn")?.addEventListener("click", () => {
        window.location.reload();
    });

    const scrollTopBtn = document.getElementById("scrollTopBtn");
    if (scrollTopBtn) {
        window.addEventListener("scroll", () => {
            scrollTopBtn.classList.toggle("is-visible", window.scrollY > 320);
        });
        scrollTopBtn.addEventListener("click", () => {
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }

    document.getElementById("regionFilterButtons")?.addEventListener("click", event => {
        const button = event.target.closest("button[data-region]");
        if (!button) return;
        activeRegion = button.dataset.region;
        renderRegionNavigation();
        renderDeviceGrid();
    });

    fetchDevices(idToken, username);
});

function normalizeRegion(region) {
    return DEVICE_REGIONS.includes(region) ? region : "Diğer / Atanmamış";
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;"
    })[character]);
}

async function fetchDevices(idToken, username) {
    const grid = document.getElementById("deviceGrid");
    grid.innerHTML = "<div class='loading-state'>Veriler yükleniyor...</div>";

    try {
        const urlWithParams = `${API_GATEWAY_URL}?kullanici=${encodeURIComponent(username)}`;
        const response = await fetch(urlWithParams, {
            method: "GET",
            headers: {
                "Authorization": idToken,
                "Content-Type": "application/json"
            }
        });

        if (!response.ok) throw new Error(`Hata kodu: ${response.status}`);

        const data = await response.json();
        groupedDevices = data.reduce((devices, tank) => {
            const deviceId = tank.CihazSeriNo;
            if (!devices[deviceId]) devices[deviceId] = [];
            devices[deviceId].push(tank);
            return devices;
        }, {});

        renderRegionNavigation();
        renderDeviceGrid();
    } catch (error) {
        console.error("HATA DETAYI:", error);
        grid.innerHTML = `<div class="loading-state error-state">Veriler yüklenemedi. Detay: ${escapeHtml(error.message)}</div>`;
    }
}

function getDeviceRegion(tanks) {
    return normalizeRegion(tanks.find(tank => tank.Bolge)?.Bolge);
}

function renderRegionNavigation() {
    const navigation = document.getElementById("regionFilterButtons");
    if (!navigation) return;

    const deviceGroups = Object.values(groupedDevices);
    const regions = [ALL_REGIONS, ...DEVICE_REGIONS];
    navigation.innerHTML = regions.map(region => {
        const count = region === ALL_REGIONS
            ? deviceGroups.length
            : deviceGroups.filter(tanks => getDeviceRegion(tanks) === region).length;
        const active = region === activeRegion;
        return `
            <button class="region-filter-button${active ? " is-active" : ""}"
                    type="button"
                    data-region="${escapeHtml(region)}"
                    aria-pressed="${active}">
                <span>${escapeHtml(region)}</span>
                <span class="region-count">${count}</span>
            </button>
        `;
    }).join("");
}

function renderDeviceGrid() {
    const grid = document.getElementById("deviceGrid");
    const visibleDevices = Object.entries(groupedDevices).filter(([, tanks]) => (
        activeRegion === ALL_REGIONS || getDeviceRegion(tanks) === activeRegion
    ));

    if (visibleDevices.length === 0) {
        const message = Object.keys(groupedDevices).length === 0
            ? "Hesabınıza tanımlı yetkili bir tank bulunamadı."
            : `${activeRegion} bölgesine atanmış cihaz bulunamadı.`;
        grid.innerHTML = `<div class="loading-state">${escapeHtml(message)}</div>`;
        return;
    }

    grid.innerHTML = visibleDevices.map(([deviceId, tanks]) => createDeviceCard(deviceId, tanks)).join("");

    grid.querySelectorAll(".device-card").forEach(card => {
        const openDetails = () => {
            const popupWidth = 1100;
            const popupHeight = 750;
            const left = (screen.width - popupWidth) / 2;
            const top = (screen.height - popupHeight) / 2;
            window.open(
                `detay.html?cihaz=${encodeURIComponent(card.dataset.deviceId)}`,
                "DetayPopUp",
                `width=${popupWidth},height=${popupHeight},left=${left},top=${top},resizable=yes,scrollbars=yes`
            );
        };
        card.addEventListener("click", openDetails);
        card.addEventListener("keydown", event => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                openDetails();
            }
        });
    });
}

function createDeviceCard(deviceId, tanks) {
    const criticalSource = tanks.find(tank => tank.KritikSeviye);
    const deviceCriticalLevel = criticalSource ? Number(criticalSource.KritikSeviye) : 20;
    const stationName = tanks[0].IstasyonAdi || `İstasyon: ${deviceId}`;
    const region = getDeviceRegion(tanks);

    let tanksHtml = tanks.map(tank => {
        const rawLevel = Number.parseFloat(tank.SonDolulukOrani || 0);
        const level = Number.isFinite(rawLevel) ? Math.min(100, Math.max(0, rawLevel)) : 0;
        const tankName = tank.DepoId || "Tanımsız Depo";
        const criticalLevel = tank.KritikSeviye ? Number(tank.KritikSeviye) : deviceCriticalLevel;
        const isInactive = level === 0;
        let statusClass = "status-normal";
        let backgroundClass = "bg-success";

        if (isInactive || level <= criticalLevel) {
            statusClass = isInactive ? "status-warning" : "status-danger";
            backgroundClass = isInactive ? "bg-warning" : "bg-danger";
        } else if (level <= criticalLevel + 20) {
            statusClass = "status-warning";
            backgroundClass = "bg-warning";
        }

        return `
            <div class="tank-section${isInactive ? " is-inactive" : ""}">
                <div class="tank-info-text">
                    <span>${escapeHtml(tankName)}</span>
                    <span class="status-badge ${statusClass}">${isInactive ? "PASİF / %0" : `%${level}`}</span>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill ${backgroundClass}" style="width: ${level}%;"></div>
                </div>
            </div>
        `;
    }).join("");

    if (tanks.length === 1) {
        tanksHtml += `
            <div class="tank-section is-inactive disconnected-tank">
                <div class="tank-info-text">
                    <span>Depo 2 (Bağlantı Yok)</span>
                    <span class="status-badge status-warning">PASİF</span>
                </div>
                <div class="progress-bar-bg"><div class="progress-bar-fill bg-warning" style="width: 0%;"></div></div>
            </div>
        `;
    }

    return `
        <article class="device-card" data-device-id="${escapeHtml(deviceId)}" role="button" tabindex="0"
                 aria-label="${escapeHtml(stationName)} cihaz detayını aç">
            <div class="critical-level-chip">Kritik eşik: %${deviceCriticalLevel}</div>
            <div class="card-header-area">
                <div>
                    <div class="device-name">${escapeHtml(stationName)}</div>
                    <div class="device-region">${escapeHtml(region)}</div>
                    <div class="device-id">Bağlı Depo Sayısı: ${tanks.length}</div>
                </div>
                <span class="card-open-indicator" aria-hidden="true">➔</span>
            </div>
            ${tanksHtml}
        </article>
    `;
}
