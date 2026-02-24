import * as esbuild from "esbuild";
import { promises as fs } from "fs";
import path from "path";
import { sassPlugin } from "esbuild-sass-plugin";

const MODE_PROD = "prod";
const MODE_DEV = "dev";
const MODE_WATCH = "watch";

async function main(mode, outdir) {
  // Based on https://esbuild.github.io/getting-started/#build-scripts
  //
  // See https://esbuild.github.io/api/#simple-options for documentation on the
  // build options.
  const config = {
    // The top-level code that is evaluated when the script is loaded.
    // Keys determine output subdirectory structure within outdir.
    entryPoints: {
      "bookmarks/bookmarks": "./frontend/bookmarks/main.ts",
      "habits/habits": "./frontend/habits/main.ts",
      "jobs/jobs": "./frontend/jobs/main.ts",
      "llmweb/llmweb": "./frontend/llmweb/main.ts",
      "wikitidy/extension": "./frontend/wikitidy/ui.ts",
      "wikitidy/codemirror": "./frontend/wikitidy/codemirror.ts",
    },
    // Create a single JavaScript file with all dependencies inlined.
    bundle: true,
    minify: mode === MODE_PROD,
    outdir,
    // Generate a source map for debugging when not in prod mode.
    sourcemap: mode !== MODE_PROD,
    // According to caniuse.com, more than 98% of users have browsers that
    // support at least ES6.
    target: "es6",
    logLevel: "info",
    logLimit: 0,
    plugins: [sassPlugin()],
  };

  if (mode === MODE_WATCH) {
    const ctx = await esbuild.context(config);
    await ctx.watch();
  } else {
    await esbuild.build(config);
  }

  await copyWikipediaManifest(outdir);
}

async function copyWikipediaManifest(outdir) {
  const src = path.resolve("frontend", "wikitidy", "manifest.json");
  const dest = path.join(outdir, "wikitidy", "manifest.json");
  await fs.mkdir(path.dirname(dest), { recursive: true });
  await fs.copyFile(src, dest);
}

if (process.argv.length !== 3 && process.argv.length !== 4) {
  console.error("error: expected 1-2 command-line arguments");
  process.exit(1);
}

const mode = process.argv[2];
const outdir = process.argv[3] || "frontend/dist";
if (mode !== MODE_PROD && mode !== MODE_DEV && mode !== MODE_WATCH) {
  console.error(
    `error: expected mode to be one of: ${MODE_PROD}, ${MODE_DEV}, ${MODE_WATCH} (got '${mode}' instead)`,
  );
  process.exit(1);
}

await main(mode, outdir);
