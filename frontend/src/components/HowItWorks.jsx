import { motion } from 'framer-motion'

const STEPS = [
  {
    icon: '📷',
    title: 'Drop a photo',
    body: 'Any JPEG or PNG. It goes straight to S3.',
    tint: 'from-fuchsia-500/20 to-fuchsia-500/5',
  },
  {
    icon: '👁️',
    title: 'AI looks at it',
    body: 'Rekognition names what it sees. Bedrock writes the joke.',
    tint: 'from-violet-500/20 to-violet-500/5',
  },
  {
    icon: '🔥',
    title: 'Meme comes out',
    body: 'Caption stamped on, ready to download and share.',
    tint: 'from-amber-500/20 to-amber-500/5',
  },
]

export default function HowItWorks() {
  return (
    <section aria-label="How it works" className="mx-auto mt-14 w-full max-w-4xl">
      <div className="grid gap-4 sm:grid-cols-3">
        {STEPS.map((step, index) => (
          <motion.div
            key={step.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 * index + 0.2, duration: 0.5, ease: 'easeOut' }}
            className={`glass relative overflow-hidden rounded-2xl bg-gradient-to-b ${step.tint} p-5`}
          >
            <div className="mb-3 flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/10 text-xl">
                {step.icon}
              </span>
              <span className="font-display text-xs tracking-widest text-white/40">
                STEP {index + 1}
              </span>
            </div>
            <h3 className="text-base font-semibold text-white">{step.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-400">{step.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
