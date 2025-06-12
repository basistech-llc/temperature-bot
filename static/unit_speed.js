console.log("unit_speed.js loaded");

async function setSpeed(unit, speed) {
  try {
    const response = await fetch('/api/v1/set_speed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ unit: unit, speed: speed })
    });

    const result = await response.json();
      console.log("Set speed: result=",result)
  } catch (e) {
    console.error('Failed to set speed:', e);
    alert('Error setting speed.');
  }
}



async function loadMapAndRenderGrid() {
  console.log("Running loadMapAndRenderGrid()");

  try {
    const res = await fetch('/api/v1/system_map');
    const systemMap = await res.json();
    console.log("Got system map:", systemMap);

    const speeds = [0, 1, 2, 3, 4];
    const table = document.createElement('table');
    table.className = 'pure-table pure-table-bordered';

    // Header row
    const headerRow = document.createElement('tr');
    headerRow.innerHTML = `<th>Unit</th>` + speeds.map(s => `<th>${s}</th>`).join('');
    table.appendChild(headerRow);

    // Rows
    for (const [unit, label] of Object.entries(systemMap)) {
      const row = document.createElement('tr');
      const labelCell = document.createElement('td');
      labelCell.textContent = label;
      row.appendChild(labelCell);

      speeds.forEach(speed => {
        const cell = document.createElement('td');
        const button = document.createElement('button');
        button.textContent = speed;
        button.className = 'pure-button';
        button.onclick = () => setSpeed(unit, speed);
        cell.appendChild(button);
        row.appendChild(cell);
      });

      table.appendChild(row);
    }

    document.getElementById('grid').appendChild(table);
  } catch (e) {
    console.error("Error in loadMapAndRenderGrid():", e);
  }
}

window.addEventListener('DOMContentLoaded', loadMapAndRenderGrid);
