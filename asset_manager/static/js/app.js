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
const barcodeVideo = document.getElementById("barcodeVideo");
const assetCodeInput = document.getElementById("asset_code");

if (scanButton && barcodeVideo && assetCodeInput) {
    if (!("BarcodeDetector" in window) || !navigator.mediaDevices?.getUserMedia) {
        scanButton.disabled = true;
        scanButton.textContent = "Camera Scan Unavailable";
    } else {
        scanButton.addEventListener("click", async () => {
            let stream;
            try {
                const detector = new BarcodeDetector({ formats: ["code_128", "code_39", "qr_code"] });
                stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
                barcodeVideo.srcObject = stream;
                barcodeVideo.classList.remove("d-none");
                await barcodeVideo.play();

                const scanFrame = async () => {
                    const codes = await detector.detect(barcodeVideo);
                    if (codes.length > 0) {
                        assetCodeInput.value = codes[0].rawValue;
                        stream.getTracks().forEach((track) => track.stop());
                        barcodeVideo.classList.add("d-none");
                        barcodeVideo.srcObject = null;
                        assetCodeInput.form.requestSubmit();
                        return;
                    }
                    if (barcodeVideo.srcObject) {
                        requestAnimationFrame(scanFrame);
                    }
                };
                scanFrame();
            } catch (error) {
                if (stream) {
                    stream.getTracks().forEach((track) => track.stop());
                }
                barcodeVideo.classList.add("d-none");
                barcodeVideo.srcObject = null;
                scanButton.textContent = "Camera Scan Failed";
            }
        });
    }
}
