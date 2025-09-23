import { cn } from "@/lib/utils"

interface AppLogoProps {
  className?: string
}

export function AppLogo({ className }: AppLogoProps) {
  return (
    <div className={cn("flex flex-col items-center gap-1", className)}>
      <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary text-background">
        <div className="flex select-none items-center text-xl font-black leading-none">
          <span className="pr-1">A</span>
          <span className="-ml-3">N</span>
        </div>
      </div>
      <span className="text-sm font-semibold tracking-wide text-foreground">AI-Now</span>
    </div>
  )
}
