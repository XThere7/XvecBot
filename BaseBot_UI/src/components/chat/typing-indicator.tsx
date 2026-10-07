/** Three animated dots. Static when reduced motion is requested. */
export function TypingIndicator({ label = "Agent is typing" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-2"
    >
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent-400"
          style={{ animationDelay: `${index * 160}ms` }}
        />
      ))}
    </div>
  );
}