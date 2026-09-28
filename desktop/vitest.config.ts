import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svelte()],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    // material-color-utilities uses extensionless ESM imports that Node's
    // resolver rejects; run it through Vite's pipeline instead.
    server: { deps: { inline: [/@material\/material-color-utilities/] } },
  },
});
