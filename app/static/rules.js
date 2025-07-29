document.addEventListener('DOMContentLoaded', function() {
    // Attach event listeners to all suspend-rules-buttons
    const buttons = document.querySelectorAll('.suspend-rules-buttons button');

    buttons.forEach(function(button) {
        button.addEventListener('click', function() {
            const seconds = this.getAttribute('x-seconds');
            if (!seconds) {
                console.error('No x-seconds attribute found on button');
                return;
            }

            // Make API call to disable rules
            fetch(`/api/v1/disable-rules?seconds=${seconds}`)
                .then(response => {
                    if (response.ok) {
                        return response.json();
                    } else {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                })
                .then(data => {
                    console.log('Rules disabled successfully:', data);
                    // Refresh the page after successful response
                    window.location.reload();
                })
                .catch(error => {
                    console.error('Error disabling rules:', error);
                    alert('Error disabling rules. Please try again.');
                });
        });
    });
});