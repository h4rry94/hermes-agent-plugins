/**
 * Open Config — status bar buttons, palette entries and a keybind that open
 * the Hermes home's config.yaml and .env in the OS default editor, not inside
 * Hermes.
 *
 * UI half of the unified open-config package. It needs no backend of its own:
 * the live (profile-aware) home comes from host.status().hermes_home, and the
 * resulting file:// URL goes to ctx.os.openExternal — Electron routes file:
 * URLs through shell.openPath, i.e. the OS file association, falling back to
 * reveal-in-folder.
 *
 * FILENAMES below is the one thing this file shares with the Python half
 * (../config_paths.py) and cannot import: a runtime plugin may only import
 * @hermes/plugin-sdk, react and react/jsx-runtime. Change the list in both.
 *
 * TypeScript source of truth; `pnpm build` compiles it to the plugin.js the
 * runtime loader executes (plain ESM, jsx() calls — the build refuses to emit
 * anything importing another module).
 */

import {
  cn,
  Codicon,
  type HermesDesktopPlugin,
  host,
  KEYBINDS_AREA,
  PALETTE_AREA,
  STATUSBAR_AREAS,
  type StatusbarItem,
  Tip
} from '@hermes/plugin-sdk'
import { Component, type ReactNode } from 'react'

const ID = 'open-config'

interface FileEntry {
  key: string
  file: string
  codicon: string
  label: string
  keywords: string[]
  /** Places the buttons side by side in the status bar. */
  order: number
}

// One entry per shortcut. Keep in step with FILENAMES in ../config_paths.py.
const FILES: FileEntry[] = [
  {
    key: 'config',
    file: 'config.yaml',
    codicon: 'gear',
    label: 'config',
    keywords: ['config', 'yaml', 'settings', 'edit', 'hermes'],
    order: 90
  },
  {
    key: 'env',
    file: '.env',
    codicon: 'key',
    label: '.env',
    keywords: ['env', 'dotenv', 'secrets', 'keys', 'api', 'hermes'],
    order: 91
  }
]

/**
 * Error blast wall for the buttons, mirroring the app's own ContribBoundary
 * (`contrib/react/boundary.tsx`, `variant="chip"`). Self-contained because a
 * runtime plugin may only import @hermes/plugin-sdk and react — the app's
 * boundary is not exported, and the data-contribution route these buttons need
 * for their right-click toggle bypasses the automatic one.
 */
class ButtonBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error) {
    console.error(`[${ID}] status bar button render failed`, error)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <Tip label={`${ID}: ${error.message}`}>
        <button
          className="inline-flex items-center gap-1 rounded px-1.5 text-[0.6875rem] text-destructive hover:bg-(--chrome-action-hover)"
          onClick={() => this.setState({ error: null })}
          type="button"
        >
          <Codicon name="warning" size="0.7rem" />
          {ID}
        </button>
      </Tip>
    )
  }
}

function fileUrl(hermesHome: string, filename: string): string {
  // Windows 'C:\Users\x\.hermes' and POSIX '/home/x/.hermes' both normalize
  // to a file:///-rooted URL. Encode only via URL so spaces etc. survive.
  const normalized = hermesHome.replace(/\\/g, '/').replace(/\/+$/, '')
  const prefix = normalized.startsWith('/') ? 'file://' : 'file:///'
  return new URL(`${prefix}${normalized}/${filename}`).toString()
}

// register() parks the opener here so the statusbar components (rendered long
// after register() returns) can trigger it.
let openFile: (filename: string) => void = () => {}

function FileButton({ codicon, file, label }: { codicon: string; file: string; label: string }) {
  return (
    <Tip label={`Open ${file} in your default editor`}>
      <button
        className={cn(
          'inline-flex h-full items-center gap-1 rounded-none px-1.5 text-[0.6875rem] transition-colors',
          'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
        )}
        onClick={() => openFile(file)}
        type="button"
      >
        <Codicon name={codicon} size="0.75rem" />
        <span>{label}</span>
      </button>
    </Tip>
  )
}

const plugin: HermesDesktopPlugin = {
  id: ID, // must match the folder name AND the backend plugin name
  name: 'Open Config',
  description: 'Status bar shortcuts that open config.yaml and .env in your default editor.',
  defaultEnabled: true,

  register(ctx) {
    openFile = async filename => {
      try {
        const status = await host.status()
        const home = status?.hermes_home
        if (!home) {
          throw new Error('gateway did not report hermes_home (is it running?)')
        }
        const ok = await ctx.os.openExternal(fileUrl(home, filename))
        if (!ok) {
          throw new Error('OS shell unavailable (older desktop build?)')
        }
      } catch (err) {
        host.notifyError(err, `Could not open ${filename}`)
      }
    }
    ctx.onDispose(() => {
      openFile = () => {}
    })

    ctx.registerMany([
      ...FILES.flatMap(entry => [
        {
          id: `palette-${entry.key}`,
          area: PALETTE_AREA,
          data: {
            id: `${ID}.open-${entry.key}`,
            action: `${ID}.open-${entry.key}`,
            label: `Config: Open ${entry.file}`,
            keywords: entry.keywords,
            run: () => openFile(entry.file)
          }
        },
        {
          id: `statusbar-${entry.key}`,
          area: STATUSBAR_AREAS.right,
          order: entry.order,
          // Contributed as `data` (a StatusbarItem), NOT a top-level `render`:
          // the app's useStatusbarContributions keeps only {id, render} from a
          // render contribution, so a `toggleLabel` there would be dropped and
          // the button could never be hidden from the bar's right-click menu.
          // `data.id` is what the hidden-ids store persists, so it must stay
          // stable across releases.
          data: {
            id: `${ID}:${entry.key}`,
            toggleLabel: `Open ${entry.file}`,
            // The data route also skips the app's ContribBoundary, so bring our
            // own — a throwing button must not take the status bar with it.
            render: () => (
              <ButtonBoundary>
                <FileButton codicon={entry.codicon} file={entry.file} label={entry.label} />
              </ButtonBoundary>
            )
          } satisfies StatusbarItem
        }
      ]),
      {
        id: 'keybind-config',
        area: KEYBINDS_AREA,
        data: {
          id: `${ID}.open-config`,
          category: 'view',
          defaults: ['mod+alt+c'],
          label: 'Open config.yaml',
          run: () => openFile('config.yaml')
        }
      }
    ])
  }
}

export default plugin
