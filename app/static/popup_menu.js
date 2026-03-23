// Popup menu functionality for Rooms and Deep Dive menus
document.addEventListener('DOMContentLoaded', function() {
    const roomsLink = document.getElementById('rooms-menu-link');
    const popup = document.getElementById('rooms-popup');

    if (roomsLink && popup) {
        roomsLink.addEventListener('click', function(e) {
            e.preventDefault();
            popup.classList.toggle('is-open');
        });

        // Close popup when clicking outside
        document.addEventListener('click', function(e) {
            if (!roomsLink.contains(e.target) && !popup.contains(e.target)) {
                popup.classList.remove('is-open');
            }
        });

        // Handle popup link clicks
        const popupLinks = popup.querySelectorAll('a');
        popupLinks.forEach(function(link) {
            link.addEventListener('click', function() {
                popup.classList.remove('is-open');
            });
        });
    }

    // Deep Dive menu popup functionality
    const deepDiveLink = document.getElementById('deep-dive-menu-link');
    const deepDivePopup = document.getElementById('deep-dive-popup');

    if (deepDiveLink && deepDivePopup) {
        deepDiveLink.addEventListener('click', function(e) {
            e.preventDefault();
            deepDivePopup.classList.toggle('is-open');
        });

        // Close popup when clicking outside
        document.addEventListener('click', function(e) {
            if (!deepDiveLink.contains(e.target) && !deepDivePopup.contains(e.target)) {
                deepDivePopup.classList.remove('is-open');
            }
        });

        // Handle popup link clicks
        const deepDivePopupLinks = deepDivePopup.querySelectorAll('a');
        deepDivePopupLinks.forEach(function(link) {
            link.addEventListener('click', function() {
                deepDivePopup.classList.remove('is-open');
            });
        });
    }
});

