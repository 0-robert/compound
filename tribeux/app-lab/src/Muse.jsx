import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './Muse.css'

// Bridge endpoint — the Python script at tribeux/app-lab/muse/bridge.py
// advertises this by default. Override via ?ws=… for demos on different hosts.
const DEFAULT_WS = 'ws://127.0.0.1:8787'

// Rolling buffer: 5 seconds of 256 Hz = 1280 samples per channel.
const BUFFER_SECONDS = 5
const SR = 256
const BUFFER_LEN = BUFFER_SECONDS * SR

// Muse 2 sample values are in microvolts, typically ±500µV on the scalp but
// much larger on motion / blink artefacts. The plot autoscales, but we cap
// the visible range so a single artefact doesn't flatten the whole trace.
const MAX_DISPLAY_UV = 200

// ---------------------------------------------------------------------------
// Ring buffer of fixed-length Float32Arrays. Write head wraps.
// ---------------------------------------------------------------------------
function makeBuffer() {
  return {
    data: Array.from({ length: 4 }, () => new Float32Array(BUFFER_LEN)),
    head: 0,    // next write index
    filled: 0,  // grows to BUFFER_LEN then stays
  }
}

function push(buf, sample) {
  for (let ch = 0; ch < 4; ch++) {
    buf.data[ch][buf.head] = sample[ch] ?? 0
  }
  buf.head = (buf.head + 1) % BUFFER_LEN
  if (buf.filled < BUFFER_LEN) buf.filled += 1
}

// ---------------------------------------------------------------------------
// Drawing — one canvas per channel, row layout.
// We re-read the ring buffer every RAF tick and redraw. A 1280-point line
// is cheap on modern GPUs; no need for webgl or offscreen canvas yet.
// ---------------------------------------------------------------------------
function drawChannel(ctx, buf, ch, w, h, color) {
  ctx.clearRect(0, 0, w, h)

  // baseline
  ctx.strokeStyle = 'rgba(0,0,0,0.06)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(0, h / 2)
  ctx.lineTo(w, h / 2)
  ctx.stroke()

  if (buf.filled < 2) return

  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  ctx.beginPath()

  const N = buf.filled
  const start = (buf.head - N + BUFFER_LEN) % BUFFER_LEN
  const series = buf.data[ch]
  const step = w / BUFFER_LEN

  for (let i = 0; i < N; i++) {
    const v = series[(start + i) % BUFFER_LEN]
    const clamped = Math.max(-MAX_DISPLAY_UV, Math.min(MAX_DISPLAY_UV, v))
    const y = h / 2 - (clamped / MAX_DISPLAY_UV) * (h / 2 - 4)
    const x = i * step
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.stroke()
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
const CH_NAMES = ['TP9', 'AF7', 'AF8', 'TP10']
const CH_COLORS = [
  'oklch(0.55 0.18 25)',   // red
  'oklch(0.55 0.15 85)',   // amber
  'oklch(0.55 0.15 150)',  // green
  'oklch(0.55 0.17 260)',  // blue
]

export default function Muse() {
  const [status, setStatus] = useState('idle')
  // status: 'idle' | 'connecting' | 'open' | 'streaming' | 'idle-stream' | 'error' | 'closed'
  const [meta, setMeta] = useState({ channels: CH_NAMES, sr: SR })
  const [sampleCount, setSampleCount] = useState(0)
  const [error, setError] = useState(null)
  const [latest, setLatest] = useState([0, 0, 0, 0])
  const wsRef = useRef(null)
  const bufRef = useRef(makeBuffer())
  const canvasRefs = useRef([null, null, null, null])

  const wsUrl = useMemo(() => {
    const params = new URLSearchParams(window.location.search)
    return params.get('ws') || DEFAULT_WS
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current) return
    setError(null)
    setStatus('connecting')
    let ws
    try {
      ws = new WebSocket(wsUrl)
    } catch (err) {
      setError(String(err))
      setStatus('error')
      return
    }
    wsRef.current = ws

    ws.onopen = () => setStatus('open')
    ws.onerror = () => {
      setError(`websocket error — is the bridge running at ${wsUrl}?`)
      setStatus('error')
    }
    ws.onclose = () => {
      wsRef.current = null
      setStatus(prev => (prev === 'error' ? 'error' : 'closed'))
    }
    ws.onmessage = ev => {
      let msg
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      if (msg.type === 'hello') {
        setMeta({ channels: msg.channels || CH_NAMES, sr: msg.sr || SR })
        setStatus('open')
      } else if (msg.type === 'eeg' && Array.isArray(msg.ch)) {
        push(bufRef.current, msg.ch)
        setSampleCount(c => c + 1)
        setStatus('streaming')
        setLatest(msg.ch.slice(0, 4))
      } else if (msg.type === 'idle') {
        setStatus('idle-stream')
      }
    }
  }, [wsUrl])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setStatus('closed')
  }, [])

  // Auto-connect on mount; disconnect on unmount.
  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  // Render loop — decoupled from WS rate so burst samples don't drop frames.
  useEffect(() => {
    let raf = 0
    const tick = () => {
      const buf = bufRef.current
      for (let ch = 0; ch < 4; ch++) {
        const canvas = canvasRefs.current[ch]
        if (!canvas) continue
        const rect = canvas.getBoundingClientRect()
        // Handle HiDPI. Only resize backing store when DPR-adjusted size changes,
        // to avoid clearing on every RAF.
        const dpr = window.devicePixelRatio || 1
        const targetW = Math.floor(rect.width * dpr)
        const targetH = Math.floor(rect.height * dpr)
        if (canvas.width !== targetW || canvas.height !== targetH) {
          canvas.width = targetW
          canvas.height = targetH
        }
        const ctx = canvas.getContext('2d')
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        drawChannel(ctx, buf, ch, rect.width, rect.height, CH_COLORS[ch])
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  const statusLabel = {
    idle: 'idle',
    connecting: 'connecting…',
    open: 'connected · waiting for samples',
    streaming: 'streaming',
    'idle-stream': 'bridge idle (no Muse data arriving)',
    error: 'error',
    closed: 'disconnected',
  }[status] || status

  return (
    <main className="page muse-page">
      <div className="muse-panel">
        <header className="muse-header">
          <div className="muse-title">
            <span className="muse-eyebrow">Live · Muse 2</span>
            <h1>Raw cortical feed</h1>
          </div>
          <div className={`muse-status muse-status--${status}`}>
            <span className="muse-status__dot" />
            <span className="muse-status__label">{statusLabel}</span>
          </div>
        </header>

        <div className="muse-meta">
          <div><span>Bridge</span><code>{wsUrl}</code></div>
          <div><span>Sample rate</span><code>{meta.sr} Hz</code></div>
          <div><span>Samples received</span><code>{sampleCount.toLocaleString()}</code></div>
        </div>

        {error && (
          <p className="muse-error">
            {error}
            <br />
            Start the bridge with <code>python tribeux/app-lab/muse/bridge.py</code>
            {' '}after <code>muselsl stream</code> is already running.
          </p>
        )}

        <div className="muse-channels">
          {CH_NAMES.map((name, i) => (
            <div className="muse-channel" key={name}>
              <div className="muse-channel__head">
                <span
                  className="muse-channel__swatch"
                  style={{ background: CH_COLORS[i] }}
                />
                <strong>{name}</strong>
                <span className="muse-channel__value">
                  {latest[i]?.toFixed(1)} µV
                </span>
              </div>
              <canvas
                ref={el => (canvasRefs.current[i] = el)}
                className="muse-channel__canvas"
                aria-label={`${name} EEG waveform`}
              />
            </div>
          ))}
        </div>

        <div className="muse-actions">
          {status === 'closed' || status === 'error' ? (
            <button type="button" className="muse-btn" onClick={connect}>
              Reconnect
            </button>
          ) : (
            <button type="button" className="muse-btn muse-btn--ghost" onClick={disconnect}>
              Disconnect
            </button>
          )}
        </div>
      </div>
    </main>
  )
}
