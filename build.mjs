/**
 * Compile every plugin's desktop/plugin.tsx to the desktop/plugin.js the
 * Hermes runtime loader actually executes.
 *
 * The output is written NEXT TO its source and committed, because
 * `hermes plugins install h4rry94/hermes-agent-plugins/<plugin>` copies that
 * one folder and nothing else - a build artifact staged anywhere above
 * <plugin>/ would simply not be installed. Committing it also means a machine
 * without node can still install the plugins as-is.
 *
 * Transform-only (no bundling): imports pass through untouched, which is
 * exactly the contract for runtime plugins - the desktop app injects
 * @hermes/plugin-sdk and react at load time. JSX compiles to jsx()/jsxs()
 * calls via the automatic runtime. Nothing else may be imported, so every
 * emitted file is checked against RUNTIME_IMPORTS below before it is kept.
 *
 *   npm run build          rebuild every plugin
 *   node build.mjs gpu-monitor
 *                          rebuild only the plugins named
 *
 * Rebuilding a clean checkout must leave `git status` clean; CI enforces that.
 */

import { build } from 'esbuild'
import { existsSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = dirname(fileURLToPath(import.meta.url))
const only = process.argv.slice(2)

/**
 * The only modules the desktop app injects into a runtime plugin. Anything
 * else resolves to nothing at load time and the plugin dies on import, so an
 * unexpected specifier is a build failure rather than a runtime surprise.
 */
const RUNTIME_IMPORTS = new Set(['@hermes/plugin-sdk', 'react', 'react/jsx-runtime'])

const BANNER = '// GENERATED from plugin.tsx by `npm run build` - edit the .tsx, never this file.'

/** Every `import`/`export ... from` specifier in an emitted ESM file. */
function importedModules(code) {
  const specifiers = new Set()
  // Side-effect imports: import "spec"
  for (const [, spec] of code.matchAll(/^import\s+["']([^"']+)["']/gm)) specifiers.add(spec)
  // Bound imports and re-exports: import ... from "spec" / export ... from "spec"
  for (const [, spec] of code.matchAll(/\bfrom\s*["']([^"']+)["']/g)) specifiers.add(spec)
  // Dynamic imports: import("spec")
  for (const [, spec] of code.matchAll(/\bimport\s*\(\s*["']([^"']+)["']\s*\)/g)) specifiers.add(spec)
  return specifiers
}

const entries = readdirSync(repo, { withFileTypes: true })
  .filter(d => d.isDirectory() && (!only.length || only.includes(d.name)))
  .map(d => join(repo, d.name, 'desktop', 'plugin.tsx'))
  .filter(existsSync)
  .map(entry => ({ entry, outfile: join(dirname(entry), 'plugin.js') }))

if (!entries.length) {
  console.error(
    only.length
      ? `no desktop/plugin.tsx found for: ${only.join(', ')}`
      : 'no */desktop/plugin.tsx files found'
  )
  process.exit(1)
}

let failed = false

for (const { entry, outfile } of entries) {
  const shown = relative(repo, outfile).replaceAll('\\', '/')

  // write: false - the emitted code is checked before it is allowed to
  // replace the committed artifact, so a rejected build cannot leave a
  // plugin.js on disk that no one asked for.
  const result = await build({
    entryPoints: [entry],
    write: false,
    bundle: false,
    format: 'esm',
    jsx: 'automatic',
    target: 'es2022',
    banner: { js: BANNER }
  })

  const code = result.outputFiles[0].text
  const stray = [...importedModules(code)].filter(spec => !RUNTIME_IMPORTS.has(spec))
  if (stray.length) {
    failed = true
    console.error(
      `${shown}: imports the desktop app does not inject: ${stray.join(', ')}` +
        "\n" +
        `  a runtime plugin may only import ${[...RUNTIME_IMPORTS].join(', ')}`
    )
    continue
  }

  writeFileSync(outfile, code)
  console.log('built', shown)
}

if (failed) process.exit(1)
