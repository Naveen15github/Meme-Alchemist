/** Slow-drifting colour blobs behind everything. Purely decorative. */
export default function Background() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute -left-32 -top-32 h-[32rem] w-[32rem] rounded-full bg-fuchsia-600/20 blur-[110px] animate-float" />
      <div
        className="absolute -right-40 top-1/4 h-[34rem] w-[34rem] rounded-full bg-violet-600/20 blur-[120px] animate-float"
        style={{ animationDelay: '-5s' }}
      />
      <div
        className="absolute bottom-[-14rem] left-1/3 h-[30rem] w-[30rem] rounded-full bg-amber-500/10 blur-[120px] animate-float"
        style={{ animationDelay: '-9s' }}
      />
      {/* Faint grid to give the dark field some texture. */}
      <div
        className="absolute inset-0 opacity-[0.16]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.06) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          maskImage: 'radial-gradient(ellipse at 50% 0%, black 30%, transparent 75%)',
          WebkitMaskImage: 'radial-gradient(ellipse at 50% 0%, black 30%, transparent 75%)',
        }}
      />
    </div>
  )
}
