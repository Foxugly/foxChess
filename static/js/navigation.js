/*
 * Navigation : sous 1024 px, le bouton menu ouvre et ferme le tiroir de la
 * topbar. Un lien choisi, Échap ou un clic hors de la topbar le referment.
 */
"use strict";
(function () {
    const topbar = document.querySelector("[data-topbar]");
    const bouton = document.querySelector("[data-ouvrir-nav]");
    if (!topbar || !bouton) { return; }

    function ouvrir(ouverte) {
        topbar.classList.toggle("topbar--ouverte", ouverte);
        bouton.setAttribute("aria-expanded", ouverte ? "true" : "false");
        bouton.querySelector("i").className = ouverte ? "bi bi-x-lg" : "bi bi-list";
    }

    bouton.addEventListener("click", function () {
        ouvrir(!topbar.classList.contains("topbar--ouverte"));
    });
    topbar.querySelectorAll(".topbar__nav .topbar__link").forEach(function (lien) {
        lien.addEventListener("click", function () { ouvrir(false); });
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { ouvrir(false); }
    });
    document.addEventListener("click", function (e) {
        if (!topbar.contains(e.target)) { ouvrir(false); }
    });
})();
