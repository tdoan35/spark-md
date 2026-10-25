import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

export function SliceColorToggle({ color, onChange }: { color: boolean; onChange: (color: boolean) => void }) {
  return (
    <ToggleGroup type="single" value={color ? "color" : "gray"} onValueChange={(v) => { if (v) onChange(v === "color") }} aria-label="CT slice colour" size="sm" spacing={0} className="absolute right-3 top-2.5 z-20 rounded-md border border-white/15 bg-black/70 p-0.5">
      <ToggleGroupItem value="gray" className="h-6 min-w-0 px-2 text-[11px] text-white/60 data-[state=on]:bg-white/20 data-[state=on]:text-white">Gray</ToggleGroupItem>
      <ToggleGroupItem value="color" className="h-6 min-w-0 px-2 text-[11px] text-white/60 data-[state=on]:bg-white/20 data-[state=on]:text-white">Color</ToggleGroupItem>
    </ToggleGroup>
  )
}
