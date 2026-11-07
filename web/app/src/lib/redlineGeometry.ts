/** Drawing decoration only, independent of the compliance engine. */
export function revisionCloud(box: { x: number; y: number; w: number; h: number }, scallop: number): string {
  const { x, y, w, h } = box;
  const nx = Math.max(2, Math.ceil(w / scallop));
  const ny = Math.max(2, Math.ceil(h / scallop));
  const dx = w / nx, dy = h / ny;
  let path = `M ${x} ${y}`;
  for (let i = 0; i < nx; i++) path += ` a ${dx * .65} ${dx * .65} 0 0 1 ${dx} 0`;
  for (let i = 0; i < ny; i++) path += ` a ${dy * .65} ${dy * .65} 0 0 1 0 ${dy}`;
  for (let i = 0; i < nx; i++) path += ` a ${dx * .65} ${dx * .65} 0 0 1 ${-dx} 0`;
  for (let i = 0; i < ny; i++) path += ` a ${dy * .65} ${dy * .65} 0 0 1 0 ${-dy}`;
  return path + ' Z';
}
