import { motion } from 'framer-motion'

export const STAGES = [
  { id: 'upload', label: 'Looking at your photo…', icon: '📷' },
  { id: 'caption', label: 'Cooking up a joke…', icon: '🧠' },
  { id: 'render', label: 'Stamping the meme…', icon: '🔥' },
]

/**
 * `activeIndex` is driven by real request milestones, not a fake timer:
 * 0 while the file is uploading to S3, 1 once /generate is in flight, and
 * 2 once that call has been running long enough to be in the render phase.
 */
export default function StageLoader({ activeIndex, preview }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass w-full rounded-3xl p-8"
      role="status"
      aria-live="polite"
    >
      {preview && (
        <div className="mx-auto mb-8 w-full max-w-xs overflow-hidden rounded-2xl">
          <motion.img
            src={preview}
            alt="Your upload, being processed"
            className="w-full object-cover"
            animate={{ opacity: [0.45, 0.85, 0.45] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
          />
        </div>
      )}

      <ul className="mx-auto flex max-w-sm flex-col gap-5">
        {STAGES.map((stage, index) => {
          const done = index < activeIndex
          const active = index === activeIndex
          return (
            <li key={stage.id} className="flex items-center gap-4">
              <div
                className={`grid h-11 w-11 shrink-0 place-items-center rounded-full text-lg transition-all duration-300
                  ${done ? 'bg-emerald-500/20 text-emerald-300' : ''}
                  ${active ? 'bg-fuchsia-500/20 text-fuchsia-200 ring-2 ring-fuchsia-400/60' : ''}
                  ${!done && !active ? 'bg-white/5 text-slate-600' : ''}`}
              >
                {done ? '✓' : stage.icon}
              </div>

              <div className="min-w-0 flex-1">
                <p
                  className={`text-sm font-medium transition-colors duration-300
                    ${active ? 'text-white' : done ? 'text-slate-400' : 'text-slate-600'}`}
                >
                  {stage.label}
                </p>
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/5">
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-fuchsia-400 to-violet-400"
                    initial={{ width: '0%' }}
                    animate={{ width: done ? '100%' : active ? ['10%', '80%'] : '0%' }}
                    transition={
                      active
                        ? { duration: 2.2, repeat: Infinity, repeatType: 'reverse', ease: 'easeInOut' }
                        : { duration: 0.4 }
                    }
                  />
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </motion.div>
  )
}
