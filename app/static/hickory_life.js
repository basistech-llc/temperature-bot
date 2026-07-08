// Hickory-only Conway's Game of Life easter egg.
(function(root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.HickoryLife = api;
        root.addEventListener('DOMContentLoaded', () => api.setupHickoryLifeEasterEgg());
    }
})(typeof window !== 'undefined' ? window : null, function() {
    const CORNER_SEQUENCE = ['top-left', 'top-right', 'bottom-left', 'bottom-right'];
    const CORNER_HIT_SIZE = 72;
    const CORNER_TIMEOUT_MS = 1400;
    const LIFE_INTERVAL_MS = 200;
    const LIFE_HISTORY_SIZE = 240;
    const LIFE_DENSITY = 0.34;
    const SKULL_SECONDS = 3;
    const STYLE_ID = 'hickory-life-style';
    const QUOTE_TEXT = 'I call heaven and earth to record this day against you, that I have set before you life and death, blessing and cursing: therefore choose life, that both thou and thy seed may live.';

    let activeOverlay = null;
    let lifeTimer = null;
    let lifeResizeHandler = null;
    let lifeSimulation = null;
    let skullTimer = null;

    function cornerForPoint(x, y, width, height, hitSize) {
        if (x < 0 || y < 0 || width <= 0 || height <= 0 || hitSize <= 0) {
            return null;
        }
        const left = x <= hitSize;
        const right = x >= width - hitSize;
        const top = y <= hitSize;
        const bottom = y >= height - hitSize;
        if (left && top) return 'top-left';
        if (right && top) return 'top-right';
        if (left && bottom) return 'bottom-left';
        if (right && bottom) return 'bottom-right';
        return null;
    }

    function createCornerSequenceRecognizer(options) {
        const sequence = options.sequence || CORNER_SEQUENCE;
        const timeoutMs = options.timeoutMs || CORNER_TIMEOUT_MS;
        const hitSize = options.hitSize || CORNER_HIT_SIZE;
        const onComplete = options.onComplete || function() {};
        let nextIndex = 0;
        let lastTime = null;

        function size() {
            if (options.getSize) return options.getSize();
            return { width: options.width, height: options.height };
        }

        function reset() {
            nextIndex = 0;
            lastTime = null;
        }

        function handlePoint(x, y, nowMs) {
            const currentTime = nowMs == null ? Date.now() : nowMs;
            if (lastTime != null && currentTime - lastTime > timeoutMs) {
                reset();
            }

            const bounds = size();
            const corner = cornerForPoint(
                x,
                y,
                bounds.width,
                bounds.height,
                hitSize,
            );
            if (!corner) {
                reset();
                return { corner: null, matched: false, completed: false };
            }

            if (corner === sequence[nextIndex]) {
                nextIndex += 1;
                lastTime = currentTime;
                if (nextIndex === sequence.length) {
                    reset();
                    onComplete();
                    return { corner, matched: true, completed: true };
                }
                return { corner, matched: true, completed: false };
            }

            if (corner === sequence[0]) {
                nextIndex = 1;
                lastTime = currentTime;
                return { corner, matched: true, completed: false };
            }

            reset();
            return { corner, matched: false, completed: false };
        }

        return { handlePoint, reset };
    }

    function createEmptyGrid(width, height) {
        const grid = [];
        for (let row = 0; row < height; row++) {
            grid.push(new Array(width).fill(0));
        }
        return grid;
    }

    function createRandomGrid(width, height, density, rng) {
        const random = rng || Math.random;
        const liveDensity = density == null ? LIFE_DENSITY : density;
        const grid = createEmptyGrid(width, height);
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                grid[y][x] = random() < liveDensity ? 1 : 0;
            }
        }
        return grid;
    }

    function countLiveNeighbors(grid, x, y, wrap) {
        const height = grid.length;
        const width = height ? grid[0].length : 0;
        if (!height || !width) return 0;
        let count = 0;
        for (let dy = -1; dy <= 1; dy++) {
            for (let dx = -1; dx <= 1; dx++) {
                if (dx === 0 && dy === 0) continue;
                let nx = x + dx;
                let ny = y + dy;
                if (wrap) {
                    nx = (nx + width) % width;
                    ny = (ny + height) % height;
                } else if (nx < 0 || ny < 0 || nx >= width || ny >= height) {
                    continue;
                }
                if (grid[ny][nx]) count += 1;
            }
        }
        return count;
    }

    function nextLifeGrid(grid, wrap) {
        const height = grid.length;
        const width = height ? grid[0].length : 0;
        const next = createEmptyGrid(width, height);
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const neighbors = countLiveNeighbors(grid, x, y, !!wrap);
                if (grid[y][x]) {
                    next[y][x] = neighbors === 2 || neighbors === 3 ? 1 : 0;
                } else {
                    next[y][x] = neighbors === 3 ? 1 : 0;
                }
            }
        }
        return next;
    }

    function aliveCount(grid) {
        let count = 0;
        grid.forEach(row => {
            row.forEach(cell => {
                if (cell) count += 1;
            });
        });
        return count;
    }

    function gridHash(grid) {
        return grid.map(row => row.map(cell => (cell ? '1' : '0')).join('')).join('/');
    }

    function rememberHash(simulation, hash, generation) {
        simulation.seen.set(hash, generation);
        simulation.hashQueue.push({ hash, generation });
        while (simulation.hashQueue.length > simulation.maxHistory) {
            const oldEntry = simulation.hashQueue.shift();
            if (simulation.seen.get(oldEntry.hash) === oldEntry.generation) {
                simulation.seen.delete(oldEntry.hash);
            }
        }
    }

    function makeLifeSimulation(grid, maxHistory) {
        const historySize = maxHistory || LIFE_HISTORY_SIZE;
        const hash = gridHash(grid);
        const simulation = {
            grid,
            generation: 0,
            lastHash: hash,
            seen: new Map(),
            hashQueue: [],
            maxHistory: historySize,
        };
        rememberHash(simulation, hash, 0);
        return simulation;
    }

    function advanceLifeSimulation(simulation, wrap) {
        const grid = nextLifeGrid(simulation.grid, !!wrap);
        const generation = simulation.generation + 1;
        const hash = gridHash(grid);
        const liveCells = aliveCount(grid);
        const repeatedAt = simulation.seen.get(hash);
        let resetReason = '';
        if (liveCells === 0) {
            resetReason = 'extinct';
        } else if (hash === simulation.lastHash) {
            resetReason = 'stable';
        } else if (repeatedAt !== undefined) {
            resetReason = 'cycle';
        }

        const nextSimulation = {
            grid,
            generation,
            lastHash: hash,
            seen: new Map(simulation.seen),
            hashQueue: simulation.hashQueue.slice(),
            maxHistory: simulation.maxHistory,
        };
        if (!resetReason) {
            rememberHash(nextSimulation, hash, generation);
        }
        return { simulation: nextSimulation, resetReason };
    }

    function ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
.hickory-life-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(5, 5, 5, 0.86);
  color: #f8f3df;
}
.hickory-life-dialog {
  width: min(92vw, 760px);
  box-sizing: border-box;
  padding: clamp(1.2rem, 4vw, 2.2rem);
  border: 2px solid #d6c27a;
  border-radius: 8px;
  background: #17120d;
  box-shadow: 0 16px 42px rgba(0, 0, 0, 0.55);
  text-align: center;
}
.hickory-life-quote {
  margin: 0 0 1.4rem;
  font-family: "UnifrakturCook", "Old English Text MT", "Cloister Black", fantasy, serif;
  font-size: clamp(1.65rem, 4.5vw, 3.5rem);
  line-height: 1.18;
}
.hickory-life-reference {
  margin: 0 0 1.6rem;
  color: #d6c27a;
  font: 700 clamp(0.9rem, 2vw, 1.15rem) Georgia, serif;
}
.hickory-life-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.8rem;
  justify-content: center;
}
.hickory-life-choice {
  min-width: min(100%, 14rem);
  min-height: 3.4rem;
  border: 2px solid transparent;
  border-radius: 8px;
  padding: 0 1rem;
  font: 700 1.05rem sans-serif;
  cursor: pointer;
}
.hickory-life-choice:focus {
  outline: 3px solid #f7d35e;
  outline-offset: 2px;
}
.hickory-life-choice-yes {
  background: #2e7d32;
  color: white;
}
.hickory-life-choice-no {
  background: #2b2b2b;
  color: white;
  border-color: #777;
}
.hickory-life-canvas {
  width: 100vw;
  height: 100vh;
  display: block;
  background: #020302;
}
.hickory-life-skull {
  font: 700 clamp(7rem, 28vw, 18rem) serif;
  line-height: 1;
  color: #f5f5f5;
  text-shadow: 0 0 28px rgba(255, 255, 255, 0.24);
}
@media (max-width: 560px) {
  .hickory-life-actions {
    flex-direction: column;
  }
  .hickory-life-choice {
    width: 100%;
  }
}
`;
        document.head.appendChild(style);
    }

    function clearOverlay() {
        if (lifeTimer) {
            clearInterval(lifeTimer);
            lifeTimer = null;
        }
        if (lifeResizeHandler) {
            window.removeEventListener('resize', lifeResizeHandler);
            lifeResizeHandler = null;
        }
        if (skullTimer) {
            clearTimeout(skullTimer);
            skullTimer = null;
        }
        lifeSimulation = null;
        if (activeOverlay) {
            activeOverlay.remove();
            activeOverlay = null;
        }
    }

    function buildOverlay(className) {
        clearOverlay();
        ensureStyle();
        const overlay = document.createElement('div');
        overlay.className = `hickory-life-overlay ${className || ''}`.trim();
        document.body.appendChild(overlay);
        activeOverlay = overlay;
        return overlay;
    }

    function showChoiceDialog() {
        const overlay = buildOverlay('hickory-life-choice-overlay');
        const dialog = document.createElement('div');
        dialog.className = 'hickory-life-dialog';
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');

        const quote = document.createElement('p');
        quote.className = 'hickory-life-quote';
        quote.textContent = QUOTE_TEXT;

        const reference = document.createElement('p');
        reference.className = 'hickory-life-reference';
        reference.textContent = 'Deuteronomy 30:19 (KJV)';

        const actions = document.createElement('div');
        actions.className = 'hickory-life-actions';

        const yesButton = document.createElement('button');
        yesButton.type = 'button';
        yesButton.className = 'hickory-life-choice hickory-life-choice-yes';
        yesButton.textContent = 'Choose life';
        yesButton.addEventListener('click', event => {
            event.stopPropagation();
            startLifeOverlay();
        });

        const noButton = document.createElement('button');
        noButton.type = 'button';
        noButton.className = 'hickory-life-choice hickory-life-choice-no';
        noButton.textContent = 'Do not choose life';
        noButton.addEventListener('click', event => {
            event.stopPropagation();
            showSkullOverlay();
        });

        actions.append(yesButton, noButton);
        dialog.append(quote, reference, actions);
        overlay.appendChild(dialog);
        yesButton.focus();
    }

    function canvasGridSize() {
        const width = window.innerWidth;
        const height = window.innerHeight;
        const cellSize = Math.max(7, Math.floor(Math.min(width, height) / 58));
        return {
            columns: Math.max(24, Math.floor(width / cellSize)),
            rows: Math.max(18, Math.floor(height / cellSize)),
        };
    }

    function randomLifeSimulation() {
        const size = canvasGridSize();
        let grid = createRandomGrid(size.columns, size.rows, LIFE_DENSITY);
        if (aliveCount(grid) === 0) {
            grid = createRandomGrid(size.columns, size.rows, 0.5);
        }
        return makeLifeSimulation(grid, LIFE_HISTORY_SIZE);
    }

    function renderLife(canvas, simulation) {
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const width = window.innerWidth;
        const height = window.innerHeight;
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.fillStyle = '#020302';
        ctx.fillRect(0, 0, width, height);

        const rows = simulation.grid.length;
        const columns = rows ? simulation.grid[0].length : 0;
        const cellWidth = width / columns;
        const cellHeight = height / rows;

        ctx.fillStyle = '#69d16f';
        for (let y = 0; y < rows; y++) {
            for (let x = 0; x < columns; x++) {
                if (!simulation.grid[y][x]) continue;
                ctx.fillRect(
                    Math.floor(x * cellWidth),
                    Math.floor(y * cellHeight),
                    Math.ceil(cellWidth),
                    Math.ceil(cellHeight),
                );
            }
        }
    }

    function startLifeOverlay() {
        const overlay = buildOverlay('hickory-life-runner');
        const canvas = document.createElement('canvas');
        canvas.className = 'hickory-life-canvas';
        overlay.appendChild(canvas);

        function resetSimulation() {
            lifeSimulation = randomLifeSimulation();
            renderLife(canvas, lifeSimulation);
        }

        function tick() {
            const result = advanceLifeSimulation(lifeSimulation, false);
            lifeSimulation = result.resetReason ? randomLifeSimulation() : result.simulation;
            renderLife(canvas, lifeSimulation);
        }

        overlay.addEventListener('pointerdown', event => {
            event.preventDefault();
            clearOverlay();
        });
        lifeResizeHandler = resetSimulation;
        window.addEventListener('resize', lifeResizeHandler);
        resetSimulation();
        lifeTimer = setInterval(tick, LIFE_INTERVAL_MS);
    }

    function showSkullOverlay() {
        const overlay = buildOverlay('hickory-life-skull-overlay');
        const skull = document.createElement('div');
        skull.className = 'hickory-life-skull';
        skull.textContent = '\u2620';
        overlay.appendChild(skull);
        skullTimer = setTimeout(clearOverlay, SKULL_SECONDS * 1000);
    }

    function setupHickoryLifeEasterEgg() {
        if (typeof document === 'undefined') return;
        if (!document.body) return;
        if (document.body.dataset.hickoryLifeReady === '1') return;
        document.body.dataset.hickoryLifeReady = '1';

        const recognizer = createCornerSequenceRecognizer({
            getSize: () => ({ width: window.innerWidth, height: window.innerHeight }),
            hitSize: CORNER_HIT_SIZE,
            timeoutMs: CORNER_TIMEOUT_MS,
            onComplete: showChoiceDialog,
        });

        document.addEventListener('pointerdown', event => {
            if (activeOverlay) return;
            const result = recognizer.handlePoint(event.clientX, event.clientY, Date.now());
            if (result.matched) {
                event.preventDefault();
                event.stopPropagation();
            }
        }, true);
    }

    return {
        aliveCount,
        advanceLifeSimulation,
        cornerForPoint,
        createCornerSequenceRecognizer,
        createEmptyGrid,
        createRandomGrid,
        gridHash,
        makeLifeSimulation,
        nextLifeGrid,
        setupHickoryLifeEasterEgg,
    };
});
