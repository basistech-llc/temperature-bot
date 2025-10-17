// GitHub menu popup functionality
document.addEventListener('DOMContentLoaded', function() {
    const githubLink = document.getElementById('github-menu-link');
    const popup = document.getElementById('github-popup');

    if (githubLink && popup) {
        githubLink.addEventListener('click', function(e) {
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
            if (!githubLink.contains(e.target) && !popup.contains(e.target)) {
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
