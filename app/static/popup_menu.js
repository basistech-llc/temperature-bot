// Popup menu functionality for Rooms and Admin menus
document.addEventListener('DOMContentLoaded', function() {
    const roomsLink = document.getElementById('rooms-menu-link');
    const popup = document.getElementById('rooms-popup');

    if (roomsLink && popup) {
        roomsLink.addEventListener('click', function(e) {
            e.preventDefault();
            // Toggle popup visibility
            if (popup.style.display === 'block') {
                popup.style.display = 'none';
            } else {
                popup.style.display = 'block';
            }
        });

        // Close popup when clicking outside
        document.addEventListener('click', function(e) {
            if (!roomsLink.contains(e.target) && !popup.contains(e.target)) {
                popup.style.display = 'none';
            }
        });

        // Handle popup link clicks
        const popupLinks = popup.querySelectorAll('a');
        popupLinks.forEach(function(link) {
            link.addEventListener('click', function() {
                popup.style.display = 'none';
            });
        });
    }

    // Admin menu popup functionality
    const adminLink = document.getElementById('admin-menu-link');
    const adminPopup = document.getElementById('admin-popup');

    if (adminLink && adminPopup) {
        adminLink.addEventListener('click', function(e) {
            e.preventDefault();
            // Toggle popup visibility
            if (adminPopup.style.display === 'block') {
                adminPopup.style.display = 'none';
            } else {
                adminPopup.style.display = 'block';
            }
        });

        // Close popup when clicking outside
        document.addEventListener('click', function(e) {
            if (!adminLink.contains(e.target) && !adminPopup.contains(e.target)) {
                adminPopup.style.display = 'none';
            }
        });

        // Handle popup link clicks
        const adminPopupLinks = adminPopup.querySelectorAll('a');
        adminPopupLinks.forEach(function(link) {
            link.addEventListener('click', function() {
                adminPopup.style.display = 'none';
            });
        });
    }
});

