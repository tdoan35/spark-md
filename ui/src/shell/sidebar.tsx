import { NavLink } from "react-router"
import { ListChecks, Inbox, Activity, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { useWorklist } from "@/api/hooks"
import { useOutbox } from "@/api/hooks"
import { usePref } from "@/lib/prefs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

function Item({ to, icon: Icon, label, count, expanded }: { to: string; icon: typeof ListChecks; label: string; count?: number; expanded: boolean }) {
  const body = (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "relative flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] transition-colors",
          isActive ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium" : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground",
        )
      }
    >
      <Icon className="size-4 shrink-0" />
      {expanded && <span className="truncate">{label}</span>}
      {!!count && (
        <span className={cn("absolute right-2 rounded-full bg-muted px-1.5 text-[10px] tabular-nums text-muted-foreground", !expanded && "right-0.5 top-0.5 px-1")}>
          {count}
        </span>
      )}
    </NavLink>
  )
  if (expanded) return <li>{body}</li>
  return (
    <li>
      <Tooltip>
        <TooltipTrigger asChild>{body}</TooltipTrigger>
        <TooltipContent side="right">{label}</TooltipContent>
      </Tooltip>
    </li>
  )
}

export function Sidebar({ expanded }: { expanded: boolean }) {
  const { data: worklist } = useWorklist()
  const { data: outbox } = useOutbox()
  const [, setExpanded] = usePref("sparkmd-sidebar", true)
  const active = worklist?.filter((r) => r.status !== "approved").length ?? 0
  const unseen = outbox?.length ?? 0

  return (
    <aside
      style={{ "--sidebar-w": expanded ? "var(--sidebar-width)" : "48px" } as React.CSSProperties}
      className="fixed inset-y-0 left-0 z-30 flex w-(--sidebar-w) flex-col bg-sidebar pb-3 pt-[calc(var(--titlebar-h)+10px)] transition-[width] duration-200 ease-linear"
    >
      <div className={cn("mb-3 flex items-center gap-2 px-3", !expanded && "justify-center px-0")}>
        <img src="/brand/spark-md-icon.svg" alt="" className="size-7 shrink-0 rounded-lg" />
        {expanded && (
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold leading-tight">Spark MD</div>
            <div className="truncate text-[11px] leading-tight text-muted-foreground">Lung CT screening</div>
          </div>
        )}
      </div>
      <nav className="px-2">
        <ul className="flex flex-col gap-0.5">
          <Item to="/" icon={ListChecks} label="Worklist" count={active} expanded={expanded} />
          <Item to="/inbox" icon={Inbox} label="EHR inbox" count={unseen} expanded={expanded} />
          <Item to="/activity" icon={Activity} label="Agent activity" expanded={expanded} />
        </ul>
      </nav>
      <div className="mt-auto px-2">
        <button
          onClick={() => setExpanded((v) => !v)}
          className={cn("flex h-7 w-full items-center gap-1.5 rounded-md px-2 text-[11px] text-muted-foreground/70 hover:bg-sidebar-accent hover:text-foreground", !expanded && "justify-center px-0")}
        >
          <ChevronRight className={cn("size-3.5 transition-transform", expanded && "rotate-180")} />
          {expanded && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  )
}
