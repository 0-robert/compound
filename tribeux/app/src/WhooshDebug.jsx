import { useState } from 'react'
import WhooshIntro from './WhooshIntro'

// Debug page — lets us scrub the whoosh animation manually with a slider.
export default function WhooshDebug() {
  const [p, setP] = useState(0.35)
  return (
    <>
      <div
        style={{
          position: 'fixed',
          top: 12,
          left: 12,
          zIndex: 9999,
          background: '#fff',
          padding: 10,
          borderRadius: 8,
          boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        <label style={{ fontSize: 12, color: '#333' }}>
          progress: {p.toFixed(2)}
        </label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={p}
          onChange={e => setP(parseFloat(e.target.value))}
          style={{ display: 'block', width: 320, marginTop: 6 }}
        />
      </div>
      <WhooshIntro frozen={p} onComplete={() => {}} />
    </>
  )
}
