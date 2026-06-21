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
