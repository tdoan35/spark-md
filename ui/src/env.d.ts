interface SparkmdBridge {
  minimize: () => Promise<void>
  maximize: () => Promise<void>
  close: () => Promise<void>
  state: () => Promise<{ maximized: boolean; fullscreen: boolean }>
  onState: (fn: (s: { maximized: boolean; fullscreen: boolean }) => void) => () => void
}

interface Window {
  sparkmd?: SparkmdBridge
}
