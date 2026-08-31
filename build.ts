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
 *   pnpm build             rebuild every plugin
 *   node build.ts gpu-monitor
 *                          rebuild only the plugins named
 *
 * Run directly by node, which strips the types at load. That keeps the build
 * dependency-free while `pnpm check` still type-checks this file - so
 * `erasableSyntaxOnly` is set in tsconfig.json: syntax node cannot strip
 * (enums, namespaces, parameter properties) has to fail at check time rather
 * than when someone runs the build.
 *
 * Rebuilding a clean checkout must leave `git status` clean; CI enforces that.
 */

import { build } from 'esbuild'
import { existsSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = dirname(fileURLToPath(import.meta.url))
const only = process.argv.slice(2)

/**
 * The only modules the desktop app injects into a runtime plugin. Anything
 * else resolves to nothing at load time and the plugin dies on import, so an
 * unexpected specifier is a build failure rather than a runtime surprise.
 */
const RUNTIME_IMPORTS: ReadonlySet<string> = new Set([
  '@hermes/plugin-sdk',
  'react',
  'react/jsx-runtime'
])

const BANNER = '// GENERATED from plugin.tsx by `pnpm build` - edit the .tsx, never this file.'

interface Target {
  /** Absolute path to the plugin.tsx source. */
  entry: string
  /** Absolute path to the plugin.js the runtime loads, beside the source. */
  outfile: string
  /** Repo-relative, forward-slashed - what a human sees in build output. */
  shown: string
}

/** Every module specifier an emitted ESM file imports or re-exports. */
function importedModules(code: string): Set<string> {
  const specifiers = new Set<string>()
  // Side-effect imports: import "spec"
  for (const [, spec] of code.matchAll(/^import\s+["']([^"']+)["']/gm)) specifiers.add(spec)
  // Bound imports and re-exports: import ... from "spec" / export ... from "spec"
  for (const [, spec] of code.matchAll(/\bfrom\s*["']([^"']+)["']/g)) specifiers.add(spec)
  // Dynamic imports: import("spec")
  for (const [, spec] of code.matchAll(/\bimport\s*\(\s*["']([^"']+)["']\s*\)/g)) specifiers.add(spec)
  return specifiers
}

const targets: Target[] = readdirSync(repo, { withFileTypes: true })
  .filter(d => d.isDirectory() && (only.length === 0 || only.includes(d.name)))
  .map(d => join(repo, d.name, 'desktop', 'plugin.tsx'))
  .filter(existsSync)
  .map(entry => {
    const outfile = join(dirname(entry), 'plugin.js')
    const shown = relative(repo, outfile).split(sep).join('/')
    return { entry, outfile, shown }
  })

if (targets.length === 0) {
  console.error(
    only.length > 0
      ? `no desktop/plugin.tsx found for: ${only.join(', ')}`
      : 'no */desktop/plugin.tsx files found'
  )
  process.exit(1)
}

let failed = false

for (const { entry, outfile, shown } of targets) {
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

  const emitted = result.outputFiles?.[0]
  if (!emitted) {
    failed = true
    console.error(`${shown}: esbuild produced no output`)
    continue
  }

  const stray = [...importedModules(emitted.text)].filter(spec => !RUNTIME_IMPORTS.has(spec))
  if (stray.length > 0) {
    failed = true
    console.error(`${shown}: imports the desktop app does not inject: ${stray.join(', ')}`)
    console.error(`  a runtime plugin may only import ${[...RUNTIME_IMPORTS].join(', ')}`)
    continue
  }

  writeFileSync(outfile, emitted.text)
  console.log('built', shown)
}

if (failed) process.exit(1)
