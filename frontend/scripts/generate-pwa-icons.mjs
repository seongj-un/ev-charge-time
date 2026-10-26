// Development only. Regenerate from frontend with: node scripts/generate-pwa-icons.mjs
// sharp is already installed by Next.js; no additional dependencies are needed.
import { mkdir, readFile, writeFile } from "node:fs/promises";
import sharp from "sharp";

const root = new URL("../", import.meta.url);
const icons = await readFile(new URL("src/components/shell/icons.tsx", root), "utf8");
const css = await readFile(new URL("src/app/globals.css", root), "utf8");
const bolt = icons.match(/export const BoltIcon[\s\S]*?<path d="([^"]+)"/)?.[1];
const brand = css.match(/--color-brand:\s*(#[\da-f]+)/i)?.[1];
const canvas = css.match(/--color-canvas:\s*(#[\da-f]+)/i)?.[1];
if (!bolt || !brand || !canvas) throw new Error("BoltIcon path or theme colors missing");

await mkdir(new URL("public/icons/", root), { recursive: true });
for (const [file, size, scale] of [
  ["public/icons/icon-192.png", 192, 0.9],
  ["public/icons/icon-512.png", 512, 0.9],
  ["public/icons/icon-maskable-512.png", 512, 0.8],
  ["src/app/apple-icon.png", 180, 0.9],
  ["src/app/icon.png", 32, 0.9],
]) {
  // Center the path's bounds (x: 4.8–18.2, y: 2.5–21.5).
  // Maskable bounds fit inside a radius of 0.8 * hypot(6.7, 9.5) / 24
  // = 38.8% of the image, within the central 80%-diameter safe circle.
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24">
    <rect width="24" height="24" fill="${canvas}"/>
    <path d="${bolt}" fill="${brand}" transform="translate(12 12) scale(${scale}) translate(-11.5 -12)"/>
  </svg>`;
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  await writeFile(new URL(file, root), png);
  console.log(`${file}: ${size}x${size}`);
}
