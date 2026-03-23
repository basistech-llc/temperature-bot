// rules_master.js - Global master rules ON/OFF toggle behavior

(function () {
  const API_URL = "/api/v1/rules_master";

  /**
   * Update the visual state label next to the master toggle.
   * @param {boolean} enabled
   */
  function updateStateLabel(enabled) {
    const label = document.getElementById("rules-master-state-label");
    if (!label) return;
    label.textContent = enabled ? "On" : "Off";
    label.classList.toggle("rules-state-off", !enabled);
  }

  /**
   * Show or hide the Slack feedback banner.
   * @param {boolean} visible
   */
  function setBannerVisible(visible) {
    const banner = document.getElementById("rules-master-banner");
    if (!banner) return;
    if (visible) {
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
  }

  /**
   * Initialize the master rules toggle UI and wire it to the backend.
   */
  function initializeRulesMasterToggle() {
    const toggle = document.getElementById("rules-master-toggle");
    if (!toggle) {
      return;
    }

    // Fetch current master state
    fetch(API_URL, { method: "GET" })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load rules master state");
        }
        return response.json();
      })
      .then((data) => {
        const enabled = !!data.enabled;
        toggle.checked = enabled;
        updateStateLabel(enabled);
        // On initial load, only show banner if already off
        setBannerVisible(!enabled);
      })
      .catch((error) => {
        console.error("Error fetching rules master state:", error);
      });

    // Handle toggle changes
    let lastKnownEnabled = true;

    toggle.addEventListener("change", function () {
      const desiredEnabled = toggle.checked;
      const previous = lastKnownEnabled;

      // Optimistically update label
      updateStateLabel(desiredEnabled);

      // Disable control during request
      toggle.disabled = true;

      fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ enabled: desiredEnabled }),
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error("Failed to update rules master state");
          }
          return response.json();
        })
        .then((data) => {
          const confirmedEnabled = !!data.enabled;
          lastKnownEnabled = confirmedEnabled;
          toggle.checked = confirmedEnabled;
          updateStateLabel(confirmedEnabled);

          // When rules are turned off, show the Slack feedback banner.
          // When turned back on, hide it.
          setBannerVisible(!confirmedEnabled);
        })
        .catch((error) => {
          console.error("Error updating rules master state:", error);
          // Revert UI to previous state
          toggle.checked = previous;
          updateStateLabel(previous);
          alert(
            "Error updating the master rules switch. The previous setting has been restored."
          );
        })
        .finally(() => {
          toggle.disabled = false;
        });
    });

    // Banner close button
    const banner = document.getElementById("rules-master-banner");
    if (banner) {
      const closeBtn = banner.querySelector(".rules-master-banner-close");
      if (closeBtn) {
        closeBtn.addEventListener("click", function () {
          setBannerVisible(false);
        });
      }
    }
  }

  document.addEventListener("DOMContentLoaded", initializeRulesMasterToggle);
})();

