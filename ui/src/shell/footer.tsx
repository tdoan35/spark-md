import { Link, useLocation } from "react-router"
import { ShieldCheck, Server } from "lucide-react"
import { cn } from "@/lib/utils"

export function Footer() {
  const { pathname } = useLocation()
  return (
    <footer className="fixed inset-x-0 bottom-0 z-40 flex h-(--footer-h) items-center justify-between rounded-b-(--win-radius) bg-sidebar px-4 text-[11px] text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <ShieldCheck className="size-3.5 text-ok" />
        Research demo, not for clinical use
      </span>
      <span className="flex items-center gap-3">
        <span className="text-muted-foreground/80">Local only · Air-gapped</span>
        <Link
          to="/system"
          aria-current={pathname === "/system" ? "page" : undefined}
          className={cn("flex items-center gap-1.5 rounded px-1 py-0.5 hover:text-foreground", pathname === "/system" ? "text-foreground" : "text-muted-foreground")}
        >
          <Server className="size-3.5" />
          System
        </Link>
      </span>
    </footer>
  )
}
