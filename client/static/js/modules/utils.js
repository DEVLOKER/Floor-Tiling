// Convert hex string to [r, g, b] array
export function hexToRgbArray(color) {
  if (!color.startsWith("#") || color.length != 7)
    throw new Error(`${color} must be a hex color`);

  return [
    parseInt(color.slice(1, 3), 16),
    parseInt(color.slice(3, 5), 16),
    parseInt(color.slice(5, 7), 16),
  ];
}
