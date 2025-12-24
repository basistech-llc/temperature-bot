// Rooms menu popup functionality
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
});

