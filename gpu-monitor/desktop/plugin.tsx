/**
 * GPU Monitor — nvidia-smi utilization % + used/total VRAM in
 * the status bar.
 *
 * UI half of the unified gpu-monitor package. Polls its Python backend
 * (~/.hermes/plugins/gpu-monitor/dashboard/plugin_api.py, mounted at
 * /api/plugins/gpu-monitor/stats) through React Query. The backend returns
 * the profile-scoped poll_seconds value from config.yaml with every sample;
 * polling pauses automatically while the window is in the background.
 *
 * TypeScript source of truth; `pnpm build` compiles it to the plugin.js
 * the runtime loader executes (plain ESM, jsx() calls, imports limited to
 * @hermes/plugin-sdk, react and react/jsx-runtime — the build refuses to
 * emit anything else).
 */

import {
  cn,
  Codicon,
  type HermesDesktopPlugin,
  type PluginContext,
  STATUSBAR_AREAS,
  type StatusbarItem,
  Tip,
  useQuery
} from '@hermes/plugin-sdk'
import { Component, type ReactNode, useEffect, useState } from 'react'

const ID = 'gpu-monitor'
const DEFAULT_POLL_SECONDS = 2

/**
 * Error blast wall for the chip, mirroring the app's own ContribBoundary
 * (`contrib/react/boundary.tsx`, `variant="chip"`). Self-contained because a
 * runtime plugin may only import @hermes/plugin-sdk and react — the app's
 * boundary is not exported, and the data-contribution route the chip needs for
 * its toggle bypasses the automatic one.
 */
class ChipBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error) {
    console.error(`[${ID}] chip render failed`, error)
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

interface Gpu {
  util: number | null // null when nvidia-smi reports [N/A] (MIG, some vGPU)
  memUsed: number // MiB
  memTotal: number // MiB
  name: string
}

type GpuStats = ({ ok: true; gpus: Gpu[] } | { ok: false; error: string }) & { pollSeconds: number }

let pluginCtx: PluginContext | null = null

function gib(mib: number): string {
  return (mib / 1024).toFixed(1)
}

function utilLabel(util: number | null): string {
  return util === null ? '—' : `${util}%`
}

function gpuLabel(gpu: Gpu): string {
  return `${utilLabel(gpu.util)} · ${gib(gpu.memUsed)}/${gib(gpu.memTotal)}G`
}

function tipText(data: GpuStats | undefined, error: unknown): string {
  if (error) {
    const message = error instanceof Error ? error.message : String(error)
    return (
      `GPU monitor — backend unreachable (${message}). ` +
      'The gateway mounts /api/plugins/gpu-monitor at startup; restart the gateway if this persists.'
    )
  }
  if (!data) {
    return 'GPU monitor — waiting for first sample…'
  }
  if (!data.ok) {
    return `GPU monitor — ${data.error} — polling every ${data.pollSeconds}s`
  }

  const stats = data.gpus
    .map(
      g =>
        `${g.name}: ${g.util === null ? 'utilization unavailable' : `${g.util}% util`}, ` +
        `${g.memUsed}/${g.memTotal} MiB VRAM`
    )
    .join(' — ')
  return `${stats} — polling every ${data.pollSeconds}s from config.yaml`
}

function GpuChip() {
  const [pollSeconds, setPollSeconds] = useState(DEFAULT_POLL_SECONDS)

  const { data, error } = useQuery<GpuStats>({
    queryKey: [ID, 'stats'],
    queryFn: () => pluginCtx!.rest('/stats'),
    refetchInterval: pollSeconds * 1000,
    refetchOnWindowFocus: false,
    retry: false
  })

  useEffect(() => {
    if (data?.pollSeconds && data.pollSeconds !== pollSeconds) {
      setPollSeconds(data.pollSeconds)
    }
  }, [data?.pollSeconds, pollSeconds])

  const gpus = data?.ok ? data.gpus : null
  // VRAM pressure gets the accent color so a nearly-full card is visible at
  // a glance without watching the numbers.
  const hot = gpus?.some(g => g.memUsed / g.memTotal > 0.92)

  return (
    <Tip label={tipText(data, error)}>
      <span
        className={cn(
          'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] tabular-nums',
          'text-(--ui-text-tertiary)'
        )}
      >
        <span aria-hidden>▣</span>
        <span style={hot ? { color: 'var(--ui-accent)' } : undefined}>
          {gpus ? gpus.map(gpuLabel).join(' | ') : 'gpu —'}
        </span>
      </span>
    </Tip>
  )
}

const plugin: HermesDesktopPlugin = {
  id: ID, // must match the folder name AND the backend plugin name
  name: 'GPU Monitor',
  register(ctx) {
    pluginCtx = ctx

    ctx.register({
      id: 'chip',
      area: STATUSBAR_AREAS.right,
      order: 115,
      // Contributed as `data` (a StatusbarItem), NOT a top-level `render`:
      // the app's useStatusbarContributions keeps only {id, render} from a
      // render contribution, so a `toggleLabel` there would be dropped and the
      // chip could never be hidden from the bar's right-click menu. The data
      // payload passes through whole. `data.id` is what the hidden-ids store
      // persists, so it must stay stable across releases.
      data: {
        id: `${ID}:chip`,
        toggleLabel: 'GPU',
        // The data route also skips the app's ContribBoundary, so bring our own
        // blast wall — a throwing chip must not take the status bar with it.
        render: () => (
          <ChipBoundary>
            <GpuChip />
          </ChipBoundary>
        )
      } satisfies StatusbarItem
    })
  }
}

export default plugin
