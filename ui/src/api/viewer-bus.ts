import type { ViewerCommand } from "./types"

type Listener = (cmd: ViewerCommand) => void

/** Transient viewer actions (show_nodule / compare_prior / reset_view / show_extras). Not cached state. */
class ViewerBus {
  private listeners = new Set<Listener>()
  private last: ViewerCommand | null = null
  emit(cmd: ViewerCommand) {
    this.last = cmd
    for (const l of this.listeners) l(cmd)
  }
  subscribe(l: Listener) {
    this.listeners.add(l)
    return () => {
      this.listeners.delete(l)
    }
  }
  /** For a view that mounts after the command arrived (e.g. switching tabs). */
  getLast() {
    return this.last
  }
  clear() {
    this.last = null
  }
}

export const viewerBus = new ViewerBus()
