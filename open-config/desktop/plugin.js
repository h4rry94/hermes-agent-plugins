// GENERATED from plugin.tsx by `pnpm build` - edit the .tsx, never this file.
import { jsx, jsxs } from "react/jsx-runtime";
import {
  cn,
  Codicon,
  host,
  KEYBINDS_AREA,
  PALETTE_AREA,
  STATUSBAR_AREAS,
  Tip
} from "@hermes/plugin-sdk";
import { Component } from "react";
const ID = "open-config";
const FILES = [
  {
    key: "config",
    file: "config.yaml",
    codicon: "gear",
    label: "config",
    keywords: ["config", "yaml", "settings", "edit", "hermes"],
    order: 90
  },
  {
    key: "env",
    file: ".env",
    codicon: "key",
    label: ".env",
    keywords: ["env", "dotenv", "secrets", "keys", "api", "hermes"],
    order: 91
  }
];
class ButtonBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error) {
    console.error(`[${ID}] status bar button render failed`, error);
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
function fileUrl(hermesHome, filename) {
  const normalized = hermesHome.replace(/\\/g, "/").replace(/\/+$/, "");
  const prefix = normalized.startsWith("/") ? "file://" : "file:///";
  return new URL(`${prefix}${normalized}/${filename}`).toString();
}
let openFile = () => {
};
function FileButton({ codicon, file, label }) {
  return /* @__PURE__ */ jsx(Tip, { label: `Open ${file} in your default editor`, children: /* @__PURE__ */ jsxs(
    "button",
    {
      className: cn(
        "inline-flex h-full items-center gap-1 rounded-none px-1.5 text-[0.6875rem] transition-colors",
        "text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground"
      ),
      onClick: () => openFile(file),
      type: "button",
      children: [
        /* @__PURE__ */ jsx(Codicon, { name: codicon, size: "0.75rem" }),
        /* @__PURE__ */ jsx("span", { children: label })
      ]
    }
  ) });
}
const plugin = {
  id: ID,
  // must match the folder name AND the backend plugin name
  name: "Open Config",
  description: "Status bar shortcuts that open config.yaml and .env in your default editor.",
  defaultEnabled: true,
  register(ctx) {
    openFile = async (filename) => {
      try {
        const status = await host.status();
        const home = status?.hermes_home;
        if (!home) {
          throw new Error("gateway did not report hermes_home (is it running?)");
        }
        const ok = await ctx.os.openExternal(fileUrl(home, filename));
        if (!ok) {
          throw new Error("OS shell unavailable (older desktop build?)");
        }
      } catch (err) {
        host.notifyError(err, `Could not open ${filename}`);
      }
    };
    ctx.onDispose(() => {
      openFile = () => {
      };
    });
    ctx.registerMany([
      ...FILES.flatMap((entry) => [
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
            render: () => /* @__PURE__ */ jsx(ButtonBoundary, { children: /* @__PURE__ */ jsx(FileButton, { codicon: entry.codicon, file: entry.file, label: entry.label }) })
          }
        }
      ]),
      {
        id: "keybind-config",
        area: KEYBINDS_AREA,
        data: {
          id: `${ID}.open-config`,
          category: "view",
          defaults: ["mod+alt+c"],
          label: "Open config.yaml",
          run: () => openFile("config.yaml")
        }
      }
    ]);
  }
};
var plugin_default = plugin;
export {
  plugin_default as default
};
