/*
 * Thème : le bouton bascule clair/sombre et mémorise le choix
 * (localStorage["theme"], comme toute la flotte). Le script du <head> l'a déjà
 * appliqué avant le rendu.
 */
"use strict";
(function () {
    const racine = document.documentElement;
    const bouton = document.querySelector("[data-basculer-theme]");
    function afficher() {
        const sombre = racine.getAttribute("data-bs-theme") === "dark";
        if (bouton) {
            bouton.querySelector("i").className = sombre ? "bi bi-sun" : "bi bi-moon-stars";
            bouton.setAttribute("aria-pressed", sombre ? "true" : "false");
        }
    }
    afficher();
    if (bouton) {
        bouton.addEventListener("click", function () {
            const sombre = racine.getAttribute("data-bs-theme") !== "dark";
            racine.setAttribute("data-bs-theme", sombre ? "dark" : "light");
            racine.classList.toggle("dark-mode", sombre);
            try { localStorage.setItem("theme", sombre ? "dark" : "light"); } catch (e) { /* privé */ }
            afficher();
        });
    }
})();
