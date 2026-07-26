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

function initializeBarcodeScanner({ input, scanButton, stopScanButton, video, status, unsupportedMessage }) {
    if (!input || !scanButton || !video) {
        return;
    }

    let activeBarcodeStream = null;
    const defaultButtonText = scanButton.textContent;

    const stopBarcodeScan = () => {
        if (activeBarcodeStream) {
            activeBarcodeStream.getTracks().forEach((track) => track.stop());
            activeBarcodeStream = null;
        }
        video.classList.add("d-none");
        video.srcObject = null;
        stopScanButton?.classList.add("d-none");
        scanButton.disabled = false;
        scanButton.textContent = defaultButtonText;
    };

    const updateStatus = (message) => {
        if (status) {
            status.textContent = message;
        }
    };

    if (!navigator.mediaDevices?.getUserMedia) {
        scanButton.disabled = true;
        scanButton.textContent = "Camera Scan Unavailable";
        updateStatus(unsupportedMessage || "This browser cannot access the camera. You can still enter the tag manually.");
        return;
    }

    scanButton.addEventListener("click", async () => {
        try {
            activeBarcodeStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
            video.srcObject = activeBarcodeStream;
            video.classList.remove("d-none");
            stopScanButton?.classList.remove("d-none");
            scanButton.disabled = true;
            scanButton.textContent = "Camera On";

            if ("BarcodeDetector" in window) {
                const detector = new BarcodeDetector({ formats: ["code_128", "code_39", "qr_code"] });
                updateStatus("Point the camera at the asset label.");
                await video.play();

                const scanFrame = async () => {
                    const codes = await detector.detect(video);
                    if (codes.length > 0) {
                        input.value = codes[0].rawValue;
                        stopBarcodeScan();
                        input.form?.requestSubmit();
                        return;
                    }
                    if (video.srcObject) {
                        requestAnimationFrame(scanFrame);
                    }
                };
                scanFrame();
            } else {
                await video.play();
                updateStatus("Camera is ready, but this browser does not support automatic barcode detection. Try a newer Chrome/Edge browser or use a hardware scanner.");
            }
        } catch (error) {
            stopBarcodeScan();
            scanButton.textContent = "Camera Scan Failed";
            scanButton.disabled = false;
            if (error?.name === "NotAllowedError") {
                updateStatus("Camera permission was denied. Allow camera access in the browser and try again.");
            } else if (error?.name === "NotFoundError") {
                updateStatus("No camera was found on this device. You can still enter the tag manually.");
            } else if (error?.message?.includes("secure")) {
                updateStatus("Camera access requires a secure connection (localhost or HTTPS). Please switch to a secure page and try again.");
            } else {
                updateStatus("Camera access failed. Check browser permissions or enter the tag manually.");
            }
        }
    });

    stopScanButton?.addEventListener("click", () => {
        stopBarcodeScan();
        updateStatus("Scanner stopped.");
    });

    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && input.value.trim()) {
            event.preventDefault();
            input.form?.requestSubmit();
        }
    });
}

[
    {
        input: document.getElementById("asset_code"),
        scanButton: document.getElementById("startBarcodeScan"),
        stopScanButton: document.getElementById("stopBarcodeScan"),
        video: document.getElementById("barcodeVideo"),
        status: document.getElementById("scannerStatus"),
        unsupportedMessage: "This browser does not expose camera barcode scanning. Enter the tag manually."
    },
    {
        input: document.getElementById("checkout_asset_code"),
        scanButton: document.getElementById("startCheckoutBarcodeScan"),
        stopScanButton: document.getElementById("stopCheckoutBarcodeScan"),
        video: document.getElementById("checkoutBarcodeVideo"),
        status: document.getElementById("checkoutScannerStatus"),
        unsupportedMessage: "Camera barcode scanning is unavailable for checkout. You can still enter the asset number manually."
    },
    {
        input: document.getElementById("checkin_asset_code"),
        scanButton: document.getElementById("startCheckinBarcodeScan"),
        stopScanButton: document.getElementById("stopCheckinBarcodeScan"),
        video: document.getElementById("checkinBarcodeVideo"),
        status: document.getElementById("checkinScannerStatus"),
        unsupportedMessage: "Camera barcode scanning is unavailable for check-in. You can still enter the asset number manually."
    }
].forEach((config) => initializeBarcodeScanner(config));

const selectAllLabels = document.getElementById("selectAllLabels");
if (selectAllLabels) {
    selectAllLabels.addEventListener("change", () => {
        document.querySelectorAll(".label-check").forEach((checkbox) => {
            checkbox.checked = selectAllLabels.checked;
        });
    });
}
