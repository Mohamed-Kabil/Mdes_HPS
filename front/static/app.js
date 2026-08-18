// Panneau lateral de detail (Comparaison / Releases) — vanilla JS, sans
// framework. Le contenu de chaque endpoint est deja present dans la page
// (blocs caches #detail-data-<endpoint>) : pas d'appel reseau, juste un
// deplacement de contenu dans le panneau + un jeu de classes CSS.

document.addEventListener("DOMContentLoaded", function () {
  var overlay = document.getElementById("panel-overlay");
  var panel = document.getElementById("detail-panel");
  var panelBody = document.getElementById("panel-body");
  var closeBtn = document.getElementById("panel-close");

  if (!overlay || !panel || !panelBody) {
    return;
  }

  function openPanel(sourceEl) {
    panelBody.innerHTML = sourceEl.innerHTML;
    overlay.classList.add("open");
    panel.classList.add("open");
  }

  function closePanel() {
    overlay.classList.remove("open");
    panel.classList.remove("open");
  }

  document.querySelectorAll("[data-detail-id]").forEach(function (trigger) {
    trigger.addEventListener("click", function (event) {
      var source = document.getElementById("detail-data-" + trigger.dataset.detailId);
      if (!source) {
        return; // pas de contenu pre-genere : on laisse la navigation normale se faire
      }
      event.preventDefault();
      openPanel(source);
    });
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", closePanel);
  }
  overlay.addEventListener("click", closePanel);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closePanel();
    }
  });
});

// Menu deroulant "Reseaux" — meme principe que le panneau de detail :
// pas de framework, juste un toggle de classe + fermeture au clic exterieur
// ou a Echap. Le declencheur est un <span role="button"> (ni <button> ni
// <a> : les deux heritent chacun d'un habillage d'accessibilite impose par
// le mode Contraste de Windows — bordure native pour <button>, soulignement
// force pour <a> non visite — qu'aucun CSS ne peut lever proprement). Un
// <span> n'active rien au clavier nativement, d'ou le gestionnaire keydown
// Entree/Espace ci-dessous, requis pour l'accessibilite avec role="button".
document.addEventListener("DOMContentLoaded", function () {
  var trigger = document.getElementById("networks-menu-trigger");
  var menuPanel = document.getElementById("networks-menu-panel");

  if (!trigger || !menuPanel) {
    return;
  }

  function closeMenu() {
    menuPanel.classList.remove("open");
  }

  function toggleMenu(event) {
    event.preventDefault();
    event.stopPropagation();
    menuPanel.classList.toggle("open");
  }

  trigger.addEventListener("click", toggleMenu);
  trigger.addEventListener("keydown", function (event) {
    if (event.key === "Enter" || event.key === " ") {
      toggleMenu(event);
    }
  });

  document.addEventListener("click", function (event) {
    if (!menuPanel.contains(event.target) && event.target !== trigger) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeMenu();
    }
  });
});

// Bouton "Lancer l'analyse" — navigation normale (pas d'AJAX), l'analyse
// est synchrone cote serveur et prend plusieurs secondes. Au clic : spinner
// + desactivation immediats ; la page reste affichee (avec le spinner)
// jusqu'a ce que le navigateur charge la page suivante (les resultats),
// qui remplace tout le document — donc rien a "annuler" manuellement.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".js-loading-btn").forEach(function (btn) {
    btn.addEventListener("click", function (event) {
      if (btn.classList.contains("is-loading")) {
        event.preventDefault();
        return;
      }
      btn.classList.add("is-loading");
      var loadingText = btn.dataset.loadingText || "Chargement...";
      btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span>' + loadingText;
    });
  });
});

// Accordeon (page Configuration) — chaque carte s'ouvre/se ferme
// independamment (pas de fermeture automatique des autres). Le corps est
// anime via max-height calcule ici en JS (scrollHeight), technique
// standard pour obtenir une transition CSS fluide quelle que soit la
// longueur du texte. En-tete = <div role="button">, pas <button>/<a> (voir
// commentaire sur .network-menu-trigger), donc clic + Entree/Espace geres
// explicitement pour l'accessibilite clavier.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".accordion-item").forEach(function (item) {
    var header = item.querySelector(".accordion-header");
    var body = item.querySelector(".accordion-body");
    if (!header || !body) {
      return;
    }

    function toggle(event) {
      event.preventDefault();
      var isOpen = item.classList.toggle("open");
      body.style.maxHeight = isOpen ? body.scrollHeight + "px" : null;
    }

    header.addEventListener("click", toggle);
    header.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        toggle(event);
      }
    });
  });
});
