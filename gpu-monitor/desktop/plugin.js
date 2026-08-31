// GENERATED from plugin.tsx by `pnpm build` - edit the .tsx, never this file.
import { jsx, jsxs } from "react/jsx-runtime";
import {
  cn,
  Codicon,
  STATUSBAR_AREAS,
  Tip,
  useQuery
} from "@hermes/plugin-sdk";
import { Component, useEffect, useState } from "react";
const ID = "gpu-monitor";
const DEFAULT_POLL_SECONDS = 2;
class ChipBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error) {
    console.error(`[${ID}] chip render failed`, error);
  }
  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return /* @__PURE__ */ jsx(Tip, { label: `${ID}: ${error.message}`, children: /* @__PURE__ */ jsxs(
      "button",
      {
        className: "inline-flex items-center gap-1 rounded px-1.5 text-[0.6875rem] text-destructive hover:bg-(--chrome-action-hover)",
        onClick: () => this.setState({ error: null }),
        type: "button",
        children: [
          /* @__PURE__ */ jsx(Codicon, { name: "warning", size: "0.7rem" }),
          ID
        ]
      }
    ) });
  }
}
let pluginCtx = null;
function gib(mib) {
  return (mib / 1024).toFixed(1);
}
function gpuLabel(gpu) {
  return `${gpu.util}% \xB7 ${gib(gpu.memUsed)}/${gib(gpu.memTotal)}G`;
}
function tipText(data, error) {
  if (error) {
    const message = error instanceof Error ? error.message : String(error);
    return `GPU monitor \u2014 backend unreachable (${message}). The gateway mounts /api/plugins/gpu-monitor at startup; restart the gateway if this persists.`;
  }
  if (!data) {
    return "GPU monitor \u2014 waiting for first sample\u2026";
  }
  if (!data.ok) {
    return `GPU monitor \u2014 ${data.error} \u2014 polling every ${data.pollSeconds}s`;
  }
  const stats = data.gpus.map((g) => `${g.name}: ${g.util}% util, ${g.memUsed}/${g.memTotal} MiB VRAM`).join(" \u2014 ");
  return `${stats} \u2014 polling every ${data.pollSeconds}s from config.yaml`;
}
function GpuChip() {
  const [pollSeconds, setPollSeconds] = useState(DEFAULT_POLL_SECONDS);
  const { data, error } = useQuery({
    queryKey: [ID, "stats"],
    queryFn: () => pluginCtx.rest("/stats"),
    refetchInterval: pollSeconds * 1e3,
    refetchOnWindowFocus: false,
    retry: false
  });
  useEffect(() => {
    if (data?.pollSeconds && data.pollSeconds !== pollSeconds) {
      setPollSeconds(data.pollSeconds);
    }
  }, [data?.pollSeconds, pollSeconds]);
  const gpus = data?.ok ? data.gpus : null;
  const hot = gpus?.some((g) => g.memUsed / g.memTotal > 0.92);
  return /* @__PURE__ */ jsx(Tip, { label: tipText(data, error), children: /* @__PURE__ */ jsxs(
    "span",
    {
      className: cn(
        "inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] tabular-nums",
        "text-(--ui-text-tertiary)"
      ),
      children: [
        /* @__PURE__ */ jsx("span", { "aria-hidden": true, children: "\u25A3" }),
        /* @__PURE__ */ jsx("span", { style: hot ? { color: "var(--ui-accent)" } : void 0, children: gpus ? gpus.map(gpuLabel).join(" | ") : "gpu \u2014" })
      ]
    }
  ) });
}
const plugin = {
  id: ID,
  // must match the folder name AND the backend plugin name
  name: "GPU Monitor",
  register(ctx) {
    pluginCtx = ctx;
    ctx.register({
      id: "chip",
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
        toggleLabel: "GPU",
        // The data route also skips the app's ContribBoundary, so bring our own
        // blast wall — a throwing chip must not take the status bar with it.
        render: () => /* @__PURE__ */ jsx(ChipBoundary, { children: /* @__PURE__ */ jsx(GpuChip, {}) })
      }
    });
  }
};
var plugin_default = plugin;
export {
  plugin_default as default
};
