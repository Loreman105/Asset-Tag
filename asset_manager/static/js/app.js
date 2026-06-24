const themeToggle = document.getElementById("themeToggle");
const root = document.documentElement;

if (localStorage.getItem("assetTheme") === "dark") {
    root.dataset.bsTheme = "dark";
}

if (themeToggle) {
    themeToggle.addEventListener("click", () => {
        const nextTheme = root.dataset.bsTheme === "dark" ? "light" : "dark";
        root.dataset.bsTheme = nextTheme;
        localStorage.setItem("assetTheme", nextTheme);
    });
}

const scanButton = document.getElementById("startBarcodeScan");
const stopScanButton = document.getElementById("stopBarcodeScan");
const barcodeVideo = document.getElementById("barcodeVideo");
const assetCodeInput = document.getElementById("asset_code");
const scannerStatus = document.getElementById("scannerStatus");
let activeBarcodeStream = null;

if (scanButton && barcodeVideo && assetCodeInput) {
    if (!("BarcodeDetector" in window) || !navigator.mediaDevices?.getUserMedia) {
        scanButton.disabled = true;
        scanButton.textContent = "Camera Scan Unavailable";
        if (scannerStatus) {
            scannerStatus.textContent = "This browser does not expose camera barcode scanning. Enter the tag manually.";
        }
    } else {
        scanButton.addEventListener("click", async () => {
            try {
                const detector = new BarcodeDetector({ formats: ["code_128", "code_39", "qr_code"] });
                activeBarcodeStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
                barcodeVideo.srcObject = activeBarcodeStream;
                barcodeVideo.classList.remove("d-none");
                stopScanButton?.classList.remove("d-none");
                scanButton.disabled = true;
                if (scannerStatus) {
                    scannerStatus.textContent = "Point the camera at the asset label.";
                }
                await barcodeVideo.play();

                const scanFrame = async () => {
                    const codes = await detector.detect(barcodeVideo);
                    if (codes.length > 0) {
                        assetCodeInput.value = codes[0].rawValue;
                        stopBarcodeScan();
                        assetCodeInput.form.requestSubmit();
                        return;
                    }
                    if (barcodeVideo.srcObject) {
                        requestAnimationFrame(scanFrame);
                    }
                };
                scanFrame();
            } catch (error) {
                stopBarcodeScan();
                scanButton.textContent = "Camera Scan Failed";
                scanButton.disabled = false;
                if (scannerStatus) {
                    scannerStatus.textContent = "Camera access failed. Check browser permissions or enter the tag manually.";
                }
            }
        });
    }
}

function stopBarcodeScan() {
    if (activeBarcodeStream) {
        activeBarcodeStream.getTracks().forEach((track) => track.stop());
        activeBarcodeStream = null;
    }
    if (barcodeVideo) {
        barcodeVideo.classList.add("d-none");
        barcodeVideo.srcObject = null;
    }
    stopScanButton?.classList.add("d-none");
    if (scanButton) {
        scanButton.disabled = false;
    }
}

stopScanButton?.addEventListener("click", () => {
    stopBarcodeScan();
    if (scannerStatus) {
        scannerStatus.textContent = "Scanner stopped.";
    }
});

const selectAllLabels = document.getElementById("selectAllLabels");
if (selectAllLabels) {
    selectAllLabels.addEventListener("change", () => {
        document.querySelectorAll(".label-check").forEach((checkbox) => {
            checkbox.checked = selectAllLabels.checked;
        });
    });
}
