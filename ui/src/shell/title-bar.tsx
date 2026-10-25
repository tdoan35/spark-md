import { useEffect, useRef, useState } from "react"
import { useNavigate, useLocation, useSearchParams } from "react-router"
import { ArrowLeft, ArrowRight, Menu, PanelLeft, Plus, Search, Moon, Sun, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { useApp } from "@/lib/app-context"
import { IconBtn, WindowControls } from "./window-controls"
import { useHistoryDepth } from "@/lib/ui-hooks"
import { useStudy } from "@/api/hooks"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export type ShellTab = { id: string; path: string; uid: string | null; label: string }

/** A study tab label from the worker (patient · timepoint). */
function StudyTabLabel({ uid }: { uid: string }) {
  const { data } = useStudy(uid)
  if (!data) return <span>Study</span>
  return (
    <span className="flex min-w-0 items-baseline gap-1.5">
      <span className="truncate font-medium">Patient {data.patient_id}</span>
      <span className="shrink-0 text-muted-foreground">· {data.timepoint}</span>
    </span>
  )
}

export function TitleBar({
  tabs, activeId, sidebarOpen, onToggleSidebar, onCloseTab,
}: {
  tabs: ShellTab[]
  activeId: string | null
  sidebarOpen: boolean
  onToggleSidebar: () => void
  onCloseTab: (id: string) => void
}) {
  const app = useApp()
  const navigate = useNavigate()
  const loc = useLocation()
  const [params] = useSearchParams()
  const { canBack, canForward } = useHistoryDepth()
  const stripRef = useRef<HTMLDivElement>(null)
  const [maximized, setMaximized] = useState(false)

  // Rounded shell: square the corners while maximized/fullscreen (no desktop notches).
  useEffect(() => {
    window.sparkmd?.state().then((s) => setMaximized(s.maximized || s.fullscreen)).catch(() => {})
    return window.sparkmd?.onState((s) => setMaximized(Boolean(s?.maximized || s?.fullscreen)))
  }, [])
  useEffect(() => {
    document.documentElement.classList.toggle("maximized", maximized)
  }, [maximized])
  useEffect(() => {
    stripRef.current?.querySelector<HTMLElement>(`[data-tab="${activeId}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" })
  }, [activeId, tabs.length])

  const close = (id: string) => {
    if (tabs.length === 1) {
      onCloseTab(id)
      return navigate("/")
    }
    const idx = tabs.findIndex((t) => t.id === id)
    const next = tabs[idx + 1] ?? tabs[idx - 1]
    if (id === activeId) navigate(next.path)
    onCloseTab(id)
  }

  return (
    <header className="drag fixed inset-x-0 top-0 z-50 flex h-(--titlebar-h) items-center rounded-t-(--win-radius) bg-sidebar">
      <div
        style={{ width: sidebarOpen ? "var(--sidebar-width)" : 172 }}
        className="flex h-full shrink-0 items-center gap-1 px-2 transition-[width] duration-200 ease-linear"
      >
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button aria-label="Application menu" className="no-drag grid size-7 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
              <Menu className="size-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-52">
            <DropdownMenuItem onSelect={() => navigate(`/?tab=${crypto.randomUUID()}`)}>Worklist</DropdownMenuItem>
            <DropdownMenuItem onSelect={app.openWorklistTab}>New study tab</DropdownMenuItem>
            <DropdownMenuItem onSelect={app.openSearch}>Search studies…</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => navigate("/inbox")}>EHR inbox</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => navigate("/activity")}>Agent activity</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => navigate("/system")}>System</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={app.toggleTheme}>Toggle theme</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <IconBtn label="Toggle sidebar" onClick={onToggleSidebar} active={sidebarOpen}>
          <PanelLeft className="size-4" />
        </IconBtn>
        <IconBtn label="Search studies" onClick={app.openSearch}>
          <Search className="size-4" />
        </IconBtn>
        <IconBtn label="Back" disabled={!canBack} onClick={() => navigate(-1)}>
          <ArrowLeft className="size-4" />
        </IconBtn>
        <IconBtn label="Forward" disabled={!canForward} onClick={() => navigate(1)}>
          <ArrowRight className="size-4" />
        </IconBtn>
      </div>

      <div className="flex h-full min-w-0 flex-1 items-center">
        {/* Size to the tabs, shrinking only on overflow so New tab follows the last tab. */}
        <div
          ref={stripRef}
          className="scrollbar-none flex h-full min-w-0 flex-initial items-center gap-1.5 overflow-x-auto px-1"
          role="tablist"
          aria-label="Open studies"
        >
          {tabs.map((t, i) => {
            const active = t.id === activeId
            return (
              <div
                key={t.id}
                role="tab"
                tabIndex={active ? 0 : -1}
                aria-selected={active}
                data-tab={t.id}
                onClick={() => navigate(t.path)}
                onAuxClick={(e) => {
                  if (e.button === 1) {
                    e.preventDefault()
                    close(t.id)
                  }
                }}
                onMouseDown={(e) => {
                  if (e.button === 1) e.preventDefault()
                }}
                onKeyDown={(e) => {
                  if (e.target !== e.currentTarget) return
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    navigate(t.path)
                  }
                  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                    const dir = e.key === "ArrowRight" ? 1 : -1
                    const nb = tabs[i + dir]
                    const el = nb ? stripRef.current?.querySelector<HTMLElement>(`[data-tab="${nb.id}"]`) : null
                    if (nb) {
                      navigate(nb.path)
                      el?.focus()
                    }
                  }
                }}
                className={cn(
                  "no-drag group flex h-8 min-w-[168px] max-w-52 shrink-0 cursor-default items-center gap-2 rounded-lg border px-3 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
                  active ? "border-border bg-background text-foreground" : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <span className="min-w-0 flex-1 truncate">{t.uid ? <StudyTabLabel uid={t.uid} /> : t.label}</span>
                <button
                  aria-label="Close tab"
                  onClick={(e) => {
                    e.stopPropagation()
                    close(t.id)
                  }}
                  className="grid size-5 shrink-0 place-items-center rounded opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="size-3" />
                </button>
              </div>
            )
          })}
        </div>
        <button
          aria-label="Open worklist in a new tab"
          title="New study"
          onClick={app.newTab}
          className="no-drag mr-1 grid size-7 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Plus className="size-4" />
        </button>
      </div>

      <div className="no-drag flex h-full shrink-0 items-center gap-1 px-2">
        <IconBtn label="Toggle theme" onClick={app.toggleTheme}>
          <Sun className="size-4 dark:hidden" />
          <Moon className="hidden size-4 dark:block" />
        </IconBtn>
        <WindowControls maximized={maximized} />
      </div>
      <span className="sr-only">
        {loc.pathname}
        {params.get("tab")}
      </span>
    </header>
  )
}
