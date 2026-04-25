import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  motion,
  useMotionValue,
  useTransform,
  animate,
  cubicBezier,
} from 'framer-motion'
import './WhooshIntro.css'

// ============================================================================
// World coordinate system
// ============================================================================
// The world is a 6000×3000 plane. The viewport is the user's window — a moving
// "lens" looking onto this plane. Translate + scale on the world div moves the
// camera; CSS overflow:hidden on the viewport clips what's off-camera.
//
// At scale=1, one world pixel = one screen pixel. Zoom in by scaling up.

const WORLD_W = 6000
const WORLD_H = 3000

// Frame lives on the right side of the world. Its top-left corner is where
// the hand-drawn stroke lands.
const FRAME_W = 1600
const FRAME_H = 1000
const FRAME_X = 4000
const FRAME_Y = 1000
const FRAME_RX = 24

// Hand-drawn stroke: starts left-center, wobbles right, lands on frame top-left.
const STROKE_START_X = 600
const STROKE_START_Y = 1500
const STROKE_END_X = FRAME_X
const STROKE_END_Y = FRAME_Y

// Rounded-rect path drawn clockwise from top-left. Explicit coordinates so
// pathLength animation always starts at top-left regardless of browser.
const FRAME_PATH = [
  `M ${FRAME_X + FRAME_RX} ${FRAME_Y}`,
  `H ${FRAME_X + FRAME_W - FRAME_RX}`,
  `A ${FRAME_RX} ${FRAME_RX} 0 0 1 ${FRAME_X + FRAME_W} ${FRAME_Y + FRAME_RX}`,
  `V ${FRAME_Y + FRAME_H - FRAME_RX}`,
  `A ${FRAME_RX} ${FRAME_RX} 0 0 1 ${FRAME_X + FRAME_W - FRAME_RX} ${FRAME_Y + FRAME_H}`,
  `H ${FRAME_X + FRAME_RX}`,
  `A ${FRAME_RX} ${FRAME_RX} 0 0 1 ${FRAME_X} ${FRAME_Y + FRAME_H - FRAME_RX}`,
  `V ${FRAME_Y + FRAME_RX}`,
  `A ${FRAME_RX} ${FRAME_RX} 0 0 1 ${FRAME_X + FRAME_RX} ${FRAME_Y}`,
  'Z',
].join(' ')

// Stroke with two wobbles.
const STROKE_PATH = [
  `M ${STROKE_START_X} ${STROKE_START_Y}`,
  `C ${STROKE_START_X + 900} ${STROKE_START_Y - 380},`,
  ` ${STROKE_START_X + 1700} ${STROKE_START_Y + 320},`,
  ` ${STROKE_START_X + 2200} ${STROKE_START_Y - 100}`,
  `S ${STROKE_END_X - 600} ${STROKE_END_Y + 220},`,
  ` ${STROKE_END_X} ${STROKE_END_Y}`,
].join('')

// ============================================================================
// Timeline stops (progress 0..1)
// ============================================================================
// An 8s master timeline. Beats:
//   [0.000 – 0.050]  splotch drops onto canvas (scale 0 → 1 with overshoot)
//   [0.050 – 0.130]  HOLD — everything still, anticipation
//   [0.130 – 0.750]  THE CHASE — stroke grows, camera follows tip
//   [0.750 – 0.830]  camera pulls back, revealing space for the frame
//   [0.780 – 0.940]  frame perimeter draws clockwise (linear)
//   [0.820 – 0.940]  Airbnb screenshot fades in
//   [0.940 – 1.000]  hold on final composition
const T_SPLOTCH_END = 0.05
const T_CHASE_START = 0.13
const T_CHASE_END = 0.75
const T_PULLBACK_END = 0.83
const T_FRAME_START = 0.78
const T_FRAME_END = 0.94
const T_IMG_START = 0.82
const T_IMG_END = 0.94

// ============================================================================
// Easing
// ============================================================================
// Motion-design principles (design-motion-principles + impeccable skills):
//   - Ease out with exponential curves. No bounce, no elastic. They look dated.
//   - Match curve to purpose: expo = confident/decisive, quint = smooth, quart = refined.
const EXPO_OUT = cubicBezier(0.16, 1, 0.3, 1)       // confident (hero moments)
const QUINT_OUT = cubicBezier(0.22, 1, 0.36, 1)     // smooth (polish)
const QUART_OUT = cubicBezier(0.25, 1, 0.5, 1)      // refined (camera settles)
const EXPO_IN_OUT = cubicBezier(0.87, 0, 0.13, 1)   // explosive symmetric (the chase)

// ============================================================================
// Hook: viewport size
// ============================================================================
function useViewportSize() {
  const [size, setSize] = useState(() => ({
    w: typeof window !== 'undefined' ? window.innerWidth : 1920,
    h: typeof window !== 'undefined' ? window.innerHeight : 1080,
  }))
  useEffect(() => {
    const onResize = () => setSize({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return size
}

// ============================================================================
// Hook: prefers-reduced-motion
// ============================================================================
// Accessibility: users who request reduced motion see a short cross-fade
// instead of the full cinematic sequence. No vestibular trigger.
function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  })
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = e => setReduced(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return reduced
}

// ============================================================================
// Main component
// ============================================================================
export default function WhooshIntro({ onComplete, duration = 8, frozen = null }) {
  const { w: vpW, h: vpH } = useViewportSize()
  const reducedMotion = usePrefersReducedMotion()
  const progress = useMotionValue(frozen ?? 0)
  const animationRef = useRef(null)
  const cancelledRef = useRef(false)
  const pathRef = useRef(null)
  // Mutable ref, not state — useTransform closures capture by reference so
  // this always reads the current length without triggering rerenders.
  const pathTotalLengthRef = useRef(0)

  // Effective duration: shorter for reduced-motion users (still gated on
  // pipeline readiness but no cinematic travel).
  const effectiveDuration = reducedMotion ? 0.6 : duration

  // Run the master timeline unless we're in frozen (debug) mode.
  useEffect(() => {
    cancelledRef.current = false
    if (frozen !== null) {
      progress.set(frozen)
      return () => {
        cancelledRef.current = true
      }
    }
    animationRef.current?.stop()
    // Reduced-motion users jump straight to 1 — we show the final composition
    // as a simple cross-fade instead of the full 8s cinematic.
    if (reducedMotion) {
      progress.set(1)
      const timeout = setTimeout(() => {
        if (cancelledRef.current) return
        onComplete?.()
      }, 600)
      return () => {
        cancelledRef.current = true
        clearTimeout(timeout)
      }
    }
    progress.set(0)
    animationRef.current = animate(progress, 1, {
      duration: effectiveDuration,
      ease: 'linear',
      onComplete: () => {
        if (cancelledRef.current) return
        onComplete?.()
      },
    })
    return () => {
      cancelledRef.current = true
      animationRef.current?.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frozen, duration, reducedMotion])

  // Measure the path's total length. useLayoutEffect so it's ready before
  // the first camera transform computation in paint. Stored in a ref so the
  // useTransform closure below reads it live — no rerender dependency.
  useLayoutEffect(() => {
    if (pathRef.current) {
      pathTotalLengthRef.current = pathRef.current.getTotalLength()
    }
  })

  // --------------------------------------------------------------------------
  // Stroke progress
  // --------------------------------------------------------------------------
  // What fraction of the path is drawn. Symmetric explosive easing gives the
  // "epic chase" rhythm: slow start, rapid middle, soft arrival.
  const strokeLen = useTransform(
    progress,
    [T_CHASE_START, T_CHASE_END],
    [0, 1],
    { ease: EXPO_IN_OUT }
  )

  // --------------------------------------------------------------------------
  // Camera scale
  // --------------------------------------------------------------------------
  // 1.8x resting near the splotch → 2.4x peak during the chase mid-section →
  // 0.9x reveal (full frame + small margin). Scale is driven by progress
  // (not strokeLen) so it leads/lags naturally.
  const cameraScale = useTransform(
    progress,
    [0.00, T_CHASE_START, 0.45, T_CHASE_END, T_PULLBACK_END, 1.00],
    [1.8, 2.0, 2.4, 1.8, 0.70, 0.70],
    { ease: [QUINT_OUT, EXPO_IN_OUT, EXPO_IN_OUT, EXPO_OUT, QUART_OUT] }
  )

  // --------------------------------------------------------------------------
  // Camera transform — computed in ONE place from progress + cameraScale
  // --------------------------------------------------------------------------
  // Why all in one: framer-motion's multi-source useTransform can be brittle
  // when chained through multiple derived values. Computing the final
  // translate/scale string in a single transform that reads `progress` and
  // `cameraScale` — then samples pathRef live inside the function — avoids
  // the chained-subscriber bug entirely. One source, one transform.
  //
  // This function runs on every frame (progress changes → motion emits);
  // getPointAtLength is cheap on a simple path.
  const frameCenterX = FRAME_X + FRAME_W / 2
  const frameCenterY = FRAME_Y + FRAME_H / 2

  const transform = useTransform(
    [progress, cameraScale],
    ([p, s]) => {
      // Stroke length with explosive in-out (matches strokeLen's mapping).
      const chasePhase = Math.max(0, Math.min(1, (p - T_CHASE_START) / (T_CHASE_END - T_CHASE_START)))
      const sL = EXPO_IN_OUT(chasePhase)

      // Sample path for tip position.
      let tx = STROKE_START_X
      let ty = STROKE_START_Y
      const el = pathRef.current
      const total = pathTotalLengthRef.current
      if (el && total) {
        const pt = el.getPointAtLength(sL * total)
        tx = pt.x
        ty = pt.y
      }

      // Pull-back blend: 0 follows tip, 1 snaps to frame center.
      const pullPhase = Math.max(0, Math.min(1, (p - T_CHASE_END) / (T_PULLBACK_END - T_CHASE_END)))
      const blend = EXPO_OUT(pullPhase)
      const cx = tx * (1 - blend) + frameCenterX * blend
      const cy = ty * (1 - blend) + frameCenterY * blend

      // Final translate to place (cx, cy) at viewport center.
      const dx = vpW / 2 - cx * s
      const dy = vpH / 2 - cy * s
      return `translate(${dx}px, ${dy}px) scale(${s})`
    }
  )

  // --------------------------------------------------------------------------
  // Splotch (the ink drop that starts it all)
  // --------------------------------------------------------------------------
  // Drops onto the canvas at the stroke's starting point. Decisive EXPO_OUT
  // (no bounce — design-motion-principles explicitly warns against it).
  // The splotch settles cleanly, then holds during the anticipation pause.
  const splotchScale = useTransform(
    progress,
    [0, T_SPLOTCH_END],
    [0, 1],
    { ease: EXPO_OUT }
  )
  // Splotch stays visible then gradually merges with the stroke.
  const splotchOpacity = useTransform(
    progress,
    [T_CHASE_START, T_CHASE_START + 0.08],
    [1, 0]
  )

  // --------------------------------------------------------------------------
  // Stroke + frame + image
  // --------------------------------------------------------------------------
  const strokeOpacity = useTransform(
    progress,
    [T_CHASE_END, T_PULLBACK_END],
    [1, 0]
  )
  const boxLen = useTransform(progress, [T_FRAME_START, T_FRAME_END], [0, 1])
  const imgOpacity = useTransform(
    progress,
    [T_IMG_START, T_IMG_END],
    [0, 1],
    { ease: QUINT_OUT }
  )

  return (
    <div className="whoosh-viewport">
      <motion.div
        className="whoosh-world"
        style={{
          width: WORLD_W,
          height: WORLD_H,
          transform,
          transformOrigin: '0 0',
        }}
      >
        {/* Airbnb screenshot — inside the world so it scales with the camera. */}
        <motion.img
          src="/airbnb-landing.png"
          alt=""
          loading="eager"
          className="whoosh-site-image"
          style={{
            left: FRAME_X,
            top: FRAME_Y,
            width: FRAME_W,
            height: FRAME_H,
            borderRadius: FRAME_RX,
            opacity: imgOpacity,
          }}
          onError={e => { e.currentTarget.style.visibility = 'hidden' }}
        />

        <svg
          className="whoosh-svg"
          width={WORLD_W}
          height={WORLD_H}
          viewBox={`0 0 ${WORLD_W} ${WORLD_H}`}
        >
          {/* Frame outline. Hairline regardless of zoom. */}
          <motion.path
            d={FRAME_PATH}
            fill="none"
            stroke="#1A1A1A"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
            style={{ pathLength: boxLen }}
          />

          {/* Ink splotch — the drop that starts it all. Rendered BEFORE the
              stroke so the stroke draws on top of it visually. */}
          <motion.circle
            cx={STROKE_START_X}
            cy={STROKE_START_Y}
            r={30}
            fill="#1A1A1A"
            style={{ scale: splotchScale, opacity: splotchOpacity, transformOrigin: `${STROKE_START_X}px ${STROKE_START_Y}px` }}
          />

          {/* Hand-drawn brush stroke. */}
          <motion.path
            ref={pathRef}
            d={STROKE_PATH}
            fill="none"
            stroke="#1A1A1A"
            strokeWidth="18"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ pathLength: strokeLen, opacity: strokeOpacity }}
          />
        </svg>
      </motion.div>
    </div>
  )
}
