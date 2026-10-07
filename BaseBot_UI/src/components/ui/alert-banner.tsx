import * as React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cn } from "@/lib/cn";

export type AlertTone = "info" | "warning" | "danger" | "success";

const TONE_CLASSES: Record<AlertTone, string> = {
  info: "border-info-500/30 bg-info-500/10 text-info-400",
  warning: "border-warning-500/30 bg-warning-500/10 text-warning-400",
  danger: "border-danger-500/30 bg-danger-500/10 text-danger-400",
  success: "border-success-500/30 bg-success-500/10 text-success-400",
};

const TONE_ICONS: Record<AlertTone, React.ElementType> = {
  info: Info,
  warning: AlertTriangle,
  danger: AlertCircle,
  success: CheckCircle2,
};

export type AlertBannerProps = {
  tone?: AlertTone;
  title?: string;
  icon?: React.ElementType;
  action?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
};

/** Inline, persistent messaging. Never transient — that is what toasts are for. */
export function AlertBanner({
  tone = "info",
  title,
  icon,
  action,
  className,
  children,
}: AlertBannerProps) {
  const Icon = icon ?? TONE_ICONS[tone];

  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-md border px-4 py-3",
        TONE_CLASSES[tone],
        className,
      )}
    >
      <Icon aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1 text-sm leading-5">
        {title && <p className="font-medium">{title}</p>}
        {children && (
          <div className={cn(title && "mt-1", "text-secondary")}>{children}</div>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}