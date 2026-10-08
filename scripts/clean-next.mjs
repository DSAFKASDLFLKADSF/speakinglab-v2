import { rmSync } from "node:fs";
import { join } from "node:path";

const nextDir = join(process.cwd(), ".next-dev");

try {
  rmSync(nextDir, { recursive: true, force: true });
  console.log("Removed .next-dev cache");
} catch (err) {
  console.warn("Could not remove .next-dev:", err.message);
}
