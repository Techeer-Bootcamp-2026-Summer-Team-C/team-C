import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const galleryDir = dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(readFileSync(join(galleryDir, "capture-manifest.json"), "utf8"));
const scratch = mkdtempSync(join(tmpdir(), "edr-ui-gallery-"));

try {
  for (const route of manifest.routes) {
    const totalHeight = route.top + route.scrollH;
    const output = join(galleryDir, `${route.slug}.jpg`);
    const first = join(galleryDir, route.segments[0].file);
    let current = join(scratch, `${route.slug}-base.miff`);

    execFileSync("magick", [
      first,
      "-gravity", "north",
      "-background", "#08090d",
      "-extent", `${manifest.viewport.width}x${totalHeight}`,
      "-fill", "#17161c",
      "-draw", `rectangle 0,${manifest.viewport.height} ${route.left - 1},${totalHeight}`,
      current,
    ]);

    let coveredContentHeight = route.clientH;
    for (let index = 1; index < route.segments.length; index += 1) {
      const segment = route.segments[index];
      const scrollTop = Math.round(segment.scrollTop);
      const startWithinViewport = Math.max(0, coveredContentHeight - scrollTop);
      const visibleContentHeight = Math.min(route.clientH, route.scrollH - scrollTop);
      const uniqueHeight = Math.max(0, visibleContentHeight - startWithinViewport);
      if (uniqueHeight === 0) continue;

      const next = join(scratch, `${route.slug}-${index}.miff`);
      const cropTop = route.top + startWithinViewport;
      const destinationTop = route.top + coveredContentHeight;
      execFileSync("magick", [
        current,
        "(", join(galleryDir, segment.file),
        "-crop", `${route.width}x${uniqueHeight}+${route.left}+${cropTop}`,
        "+repage", ")",
        "-geometry", `+${route.left}+${destinationTop}`,
        "-composite",
        next,
      ]);
      current = next;
      coveredContentHeight += uniqueHeight;
    }

    execFileSync("magick", [current, "-strip", "-quality", "88", output]);
    process.stdout.write(`${route.slug}: ${manifest.viewport.width}x${totalHeight}\n`);
  }
} finally {
  rmSync(scratch, { force: true, recursive: true });
}
