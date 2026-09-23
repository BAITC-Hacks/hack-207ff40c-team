export function ProductLogo({ className = "", onClick }: { className?: string; onClick?: () => void }) {
  const clickable = typeof onClick === 'function';

  return (
    <div
      className={`${className} flex items-center gap-2 ${clickable ? 'cursor-pointer hover:opacity-90 focus:opacity-90 outline-none' : ''}`}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(event) => {
        if (clickable && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          onClick?.();
        }
      }}
    >
      <img src="/station-mark.svg" alt="" className="h-8 w-8 sm:h-9 sm:w-9" />
      <span className="text-lg font-semibold tracking-tight">Meeting Station</span>
    </div>
  );
}
