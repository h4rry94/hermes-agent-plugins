/**
 * Local type declarations for `@hermes/plugin-sdk`, the module the desktop
 * app injects into runtime plugins (apps/desktop/src/sdk/runtime.ts).
 *
 * The real SDK has no published .d.ts, so this file declares the slice these
 * plugins actually use, typed to match apps/desktop/src/sdk/index.ts and
 * src/contrib/plugin.ts in the hermes-agent source. Types only — nothing here
 * exists at runtime. Extend it as plugins reach for more of the SDK; if a
 * build of Hermes changes a signature, this file is where the drift shows up.
 */
declare module '@hermes/plugin-sdk' {
  import type { ComponentType, CSSProperties, ReactNode } from 'react'

  // ── Styling ────────────────────────────────────────────────────────────
  /** clsx/tailwind-merge combo used across the app. */
  export function cn(...classes: Array<string | false | null | undefined>): string

  // ── Components ────────────────────────────────────────────────────────
  export const Tip: ComponentType<{ label: ReactNode; children: ReactNode }>
  export const Codicon: ComponentType<{
    name: string
    size?: number | string
    className?: string
  }>
  /** THE app button (components/ui/button.tsx). Pick variant + size; never
   *  override its padding/size/chrome via className (DESIGN.md). */
  export const Button: ComponentType<{
    variant?: 'default' | 'destructive' | 'secondary' | 'outline' | 'ghost' | 'link' | 'text' | 'textStrong'
    size?:
      | 'default'
      | 'xs'
      | 'sm'
      | 'lg'
      | 'inline'
      | 'micro'
      | 'icon'
      | 'icon-xs'
      | 'icon-sm'
      | 'icon-lg'
      | 'icon-titlebar'
    onClick?: (event: unknown) => void
    disabled?: boolean
    type?: 'button' | 'submit'
    asChild?: boolean
    className?: string
    children?: ReactNode
    'aria-label'?: string
  }>
  /** Radix-based switch (components/ui/switch.tsx). */
  export const Switch: ComponentType<{
    checked?: boolean
    onCheckedChange?: (checked: boolean) => void
    disabled?: boolean
    size?: 'default' | 'xs'
    className?: string
    style?: CSSProperties
    'aria-label'?: string
  }>

  /** Text field with control chrome (components/ui/input.tsx). Sizes come
   *  from the shared controlVariants (xs/sm/default/lg). */
  export const Input: ComponentType<{
    value?: string
    onChange?: (event: { target: { value: string } }) => void
    placeholder?: string
    type?: string
    min?: number | string
    max?: number | string
    step?: number | string
    size?: 'xs' | 'sm' | 'default' | 'lg'
    disabled?: boolean
    className?: string
    'aria-label'?: string
  }>
  /** Multiline twin of Input (components/ui/textarea.tsx). */
  export const Textarea: ComponentType<{
    value?: string
    onChange?: (event: { target: { value: string } }) => void
    placeholder?: string
    rows?: number
    size?: 'xs' | 'sm' | 'default' | 'lg'
    disabled?: boolean
    className?: string
    'aria-label'?: string
  }>

  /** Grouped one-row toggle for small mutually-exclusive choices
   *  (components/ui/segmented-control.tsx) — the design system's tab/choice
   *  control. */
  export function SegmentedControl<T extends string>(props: {
    options: readonly { id: T; label: string }[]
    value: T
    onChange: (id: T) => void
    className?: string
    disabled?: boolean
  }): ReactNode

  /** Radix popover trio (components/ui/popover.tsx). */
  export const Popover: ComponentType<{
    children?: ReactNode
    open?: boolean
    onOpenChange?: (open: boolean) => void
  }>
  export const PopoverTrigger: ComponentType<{ asChild?: boolean; children?: ReactNode }>
  export const PopoverContent: ComponentType<{
    children?: ReactNode
    className?: string
    side?: 'top' | 'bottom' | 'left' | 'right'
    align?: 'start' | 'center' | 'end'
    sideOffset?: number
  }>

  // ── React Query (re-exported @tanstack/react-query singletons) ─────────
  export interface QueryResult<T> {
    data: T | undefined
    error: unknown
    isLoading: boolean
    refetch: () => void
  }
  export function useQuery<T>(options: {
    queryKey: readonly unknown[]
    queryFn: () => T | Promise<T>
    refetchInterval?: number | false
    refetchOnWindowFocus?: boolean
    retry?: boolean | number
    retryDelay?: number
    enabled?: boolean
    staleTime?: number
  }): QueryResult<T>

  export interface MutationResult<TVars> {
    mutate: (vars: TVars) => void
    isPending: boolean
  }
  export function useMutation<TData, TVars, TContext = unknown>(options: {
    mutationFn: (vars: TVars) => Promise<TData>
    onMutate?: (vars: TVars) => TContext | Promise<TContext>
    onError?: (error: unknown, vars: TVars, context: TContext | undefined) => void
    onSuccess?: (data: TData, vars: TVars, context: TContext | undefined) => void
    onSettled?: () => void
  }): MutationResult<TVars>

  export interface QueryClientLike {
    cancelQueries(filter: { queryKey: readonly unknown[] }): Promise<void>
    getQueryData<T>(key: readonly unknown[]): T | undefined
    setQueryData<T>(
      key: readonly unknown[],
      updater: T | ((current: T | undefined) => T | undefined)
    ): void
    invalidateQueries(filter: { queryKey: readonly unknown[] }): Promise<void>
  }
  export function useQueryClient(): QueryClientLike

  // ── Contribution areas ─────────────────────────────────────────────────
  /** Full page mounted in the workspace pane at `data.path`. */
  export const ROUTES_AREA: 'routes'
  /** Data row in the sidebar's top-left nav; pair with a ROUTES_AREA page. */
  export const SIDEBAR_NAV_AREA: 'sidebar.nav'
  export const PALETTE_AREA: string
  export const KEYBINDS_AREA: string
  export const STATUSBAR_AREAS: { left: 'statusBar.left'; right: 'statusBar.right' }

  /**
   * Declarative status bar item (app/shell/statusbar-controls.tsx).
   *
   * Contribute this as a contribution's `data`, not via a top-level `render`:
   * the app's `useStatusbarContributions` keeps only `{id, render}` from a
   * render contribution — every other field, `toggleLabel` included, is
   * dropped. The trade-off is that the data route skips the app's
   * ContribBoundary, so a data contribution should wrap its own render in an
   * error boundary.
   */
  export interface StatusbarItem {
    id: string
    /** Owns the slot when set: label/variant/onSelect are ignored. */
    render?: () => ReactNode
    label?: ReactNode
    detail?: ReactNode
    icon?: ReactNode
    className?: string
    disabled?: boolean
    hidden?: boolean
    menuAlign?: 'center' | 'end' | 'start'
    menuClassName?: string
    /** Popover body; the fn form receives a `close()`. */
    menuContent?: ((close: () => void) => ReactNode) | ReactNode
    onSelect?: (modifiers: { shiftKey: boolean }) => void
    title?: string
    to?: string
    variant?: 'action' | 'link' | 'menu' | 'text'
    /** Plain-text name in the bar's right-click show/hide menu. WITHOUT one the
     *  item is never listed there and always shows. Persisted against `id`. */
    toggleLabel?: string
    /** Listed but not switchable — for chrome that would strand the user. */
    lockedVisible?: boolean
  }
  /** Render-node slots in the titlebar (34px bar; keep contributions ~24px). */
  export const TITLEBAR_AREAS: { center: 'titleBar.center'; left: 'titleBar.left'; right: 'titleBar.right' }

  export interface RouteContribution {
    /** Absolute path, e.g. `/kanban`. One segment; no params. */
    path: string
  }
  export interface SidebarNavContribution {
    /** Codicon name, e.g. `'lightbulb'`. */
    codicon: string
    label: string
    /** Route to navigate to (usually a contributed page's path). */
    path: string
  }

  // ── Reactive state (nanostores-style atoms) ────────────────────────────
  export interface ReadableAtom<T> {
    get(): T
    subscribe(callback: (value: T) => void): () => void
  }
  /** React hook over a readable atom (re-render on change). */
  export function useValue<T>(atom: ReadableAtom<T>): T

  // ── Host door ──────────────────────────────────────────────────────────
  export const host: {
    /** Gateway status; `hermes_home` is the live (profile-aware) home dir. */
    status(): Promise<{ hermes_home?: string } & Record<string, unknown>>
    notifyError(error: unknown, title?: string): void
    navigate(path: string): void
    /** Read-only app state atoms (subset — extend as needed). */
    state: {
      /** Current main model slug, e.g. 'kimi-k2.7-code'. Empty until known. */
      model: ReadableAtom<string>
    }
  }

  // ── Plugin context (src/contrib/plugin.ts) ─────────────────────────────
  export interface PluginContribution {
    id: string
    area: string
    order?: number
    title?: string
    data?: unknown
    render?: () => ReactNode
  }
  export interface PluginRestOptions {
    method?: string
    body?: unknown
    timeoutMs?: number
  }
  export interface PluginContext {
    register(contribution: PluginContribution): void
    registerMany(contributions: PluginContribution[]): void
    /** Namespace-scoped REST: path is relative to /api/plugins/<plugin id>. */
    rest<T>(path: string, opts?: PluginRestOptions): Promise<T>
    /** WebSocket twin of `rest`; returns a disposer. */
    socket(path: string, onMessage: (data: unknown) => void): () => void
    os: {
      /** Resolves false when the capability is missing (older shells). */
      openExternal(url: string): Promise<boolean>
    }
    storage: {
      get<T>(key: string, fallback: T): T
      set(key: string, value: unknown): void
    }
    onDispose(fn: () => void): void
  }

  /** Shape of a runtime plugin's default export. */
  export interface HermesDesktopPlugin {
    /** Must match the desktop-plugins folder name AND the backend plugin name. */
    id: string
    name: string
    description?: string
    defaultEnabled?: boolean
    register(ctx: PluginContext): void
  }
}
