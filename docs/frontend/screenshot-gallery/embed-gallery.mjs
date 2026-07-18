import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const galleryDir = dirname(fileURLToPath(import.meta.url));
const htmlPath = join(galleryDir, "..", "full-page-screenshot-review.html");
const source = readFileSync(htmlPath, "utf8");
const embedded = source.replace(
  /src="\.\/screenshot-gallery\/([^"]+\.jpg)"/g,
  (_, filename) => {
    const base64 = readFileSync(join(galleryDir, filename)).toString("base64");
    return `src="data:image/jpeg;base64,${base64}"`;
  },
);

writeFileSync(htmlPath, embedded);
process.stdout.write(`Embedded ${embedded.match(/data:image\/jpeg;base64,/g)?.length ?? 0} screenshots.\n`);
