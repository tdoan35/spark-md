import { type ReactNode } from "react"
import { cn } from "@/lib/utils"

export function WindowControls({ maximized }: { maximized: boolean }) {
  const api = window.sparkmd
  if (!api) return null
  return (
    <div className="no-drag flex h-full items-center">
      <button aria-label="Minimize" className="grid h-8 w-11 place-items-center text-muted-foreground hover:bg-muted hover:text-foreground" onClick={() => api.minimize()}>
        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 5h6" stroke="currentColor" strokeWidth="1.2" /></svg>
      </button>
      <button aria-label={maximized ? "Restore" : "Maximize"} className="grid h-8 w-11 place-items-center text-muted-foreground hover:bg-muted hover:text-foreground" onClick={() => api.maximize()}>
        {maximized ? (
          <svg width="10" height="10" viewBox="0 0 10 10"><rect x="1.5" y="1.5" width="5" height="5" fill="none" stroke="currentColor" strokeWidth="1.2" /><path d="M3.5 6.5v2h5v-5h-2" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
        ) : (
          <svg width="10" height="10" viewBox="0 0 10 10"><rect x="2" y="2" width="6" height="6" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
        )}
      </button>
      <button aria-label="Close" className="grid h-8 w-11 place-items-center text-muted-foreground hover:bg-alert hover:text-white" onClick={() => api.close()}>
        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2.5 2.5l5 5M7.5 2.5l-5 5" stroke="currentColor" strokeWidth="1.2" /></svg>
      </button>
    </div>
  )
}

export function IconBtn({ label, onClick, children, active, disabled }: { label: string; onClick?: () => void; children: ReactNode; active?: boolean; disabled?: boolean }) {
  return (
    <button
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "no-drag grid size-7 place-items-center rounded-md text-muted-foreground transition-colors",
        "hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-40",
        active && "bg-muted text-foreground",
      )}
    >
      {children}
    </button>
  )
}
