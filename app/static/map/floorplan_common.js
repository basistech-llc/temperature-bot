/**
 * Shared floor plan data and helpers for map-readonly.html (view) and map-editable.html (annotator).
 * Coordinates are normalized 0.0–1.0; x,y = top-left corner, w,h = width and height.
 */
const FLOORPLAN_IMAGE = 'basistech_floorplan.png';

const regions = [
  { id: 'garage', label: 'GARAGE', x: 0.205, y: 0.290, w: 0.540, h: 0.400 },
  { id: 'broadway', label: 'Broadway', x: 0.845, y: 0.263, w: 0.120, h: 0.388 },
  { id: 'sunken_garden', label: 'Sunken Garden', x: 0.534, y: 0.169, w: 0.181, h: 0.122 },
  { id: 'media_room', label: 'Hickory', x: 0.174, y: 0.059, w: 0.069, h: 0.203 },
  { id: 'area_51', label: 'Area 51', x: 0.249, y: 0.058, w: 0.289, h: 0.208 },
  { id: 'dungeon', label: 'Dungeon', x: 0.149, y: 0.272, w: 0.058, h: 0.213 },
  { id: 'bamboo', label: 'Bamboo', x: 0.733, y: 0.037, w: 0.092, h: 0.137 },
  { id: 'greenhouse', label: 'Greenhouse', x: 0.532, y: 0.038, w: 0.206, h: 0.138 }
];

/**
 * Return the region under canvas coordinates (clientX, clientY), or null.
 * Also returns scaled mouse coordinates for drawing.
 */
function getRegionAt(canvas, regions, clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  const mouseX = (clientX - rect.left) * scaleX;
  const mouseY = (clientY - rect.top) * scaleY;
  for (const r of regions) {
    const px = r.x * canvas.width;
    const py = r.y * canvas.height;
    const pw = r.w * canvas.width;
    const ph = r.h * canvas.height;
    if (mouseX >= px && mouseX <= px + pw && mouseY >= py && mouseY <= py + ph) {
      return { region: r, mouseX, mouseY };
    }
  }
  return { region: null, mouseX, mouseY };
}

/**
 * Draw the floor plan image and all region boxes; highlight the region with id hoveredId.
 */
function drawRegions(ctx, img, regions, hoveredId) {
  const c = ctx.canvas;
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.drawImage(img, 0, 0);
  regions.forEach(function (r) {
    const px = r.x * c.width;
    const py = r.y * c.height;
    const pw = r.w * c.width;
    const ph = r.h * c.height;
    ctx.beginPath();
    ctx.rect(px, py, pw, ph);
    if (r.id === hoveredId) {
      ctx.fillStyle = 'rgba(0, 123, 255, 0.4)';
      ctx.strokeStyle = '#0056b3';
    } else {
      ctx.fillStyle = 'rgba(255, 0, 0, 0.15)';
      ctx.strokeStyle = 'red';
    }
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.stroke();
  });
}
