// HeroScan.jsx — tilted website scan + framed brain analysis panel.

function ScanningSite({ children, tilt = 18, sweep = true }) {
  const T = window.TRIBE;
  const containerRef = React.useRef(null);
  const [scale, setScale] = React.useState(0.5);

  React.useEffect(() => {
    if (!containerRef.current) return;
    const updateScale = () => {
      const w = containerRef.current.offsetWidth;
      // The AirbnbSite is 1180px wide. We scale to fit the container.
      setScale(w / 1180);
    };
    updateScale();
    window.addEventListener('resize', updateScale);
    return () => window.removeEventListener('resize', updateScale);
  }, []);

  return (
    <div ref={containerRef} style={{ perspective: 3000, perspectiveOrigin: '50% 50%', width: '100%', display: 'flex', justifyContent: 'center' }}>
      <div style={{
        position: 'relative',
        transform: `rotateY(${-tilt}deg) rotateX(4deg)`,
        transformStyle: 'preserve-3d',
        width: '100%',
        maxWidth: 1180 * scale,
      }}>
        <div style={{
          position: 'relative', borderRadius: 16, overflow: 'hidden',
          boxShadow: '0 50px 100px -20px rgba(10,22,40,0.35), 0 10px 30px -10px rgba(10,22,40,0.2)',
          height: 900 * scale,
        }}>
          <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left' }}>
            {children}
          </div>

          {/* Scan sweep */}
          {sweep && (
            <div style={{
              position: 'absolute', left: 0, right: 0, top: 0, height: '10%',
              background: 'linear-gradient(180deg, transparent 0%, rgba(15,181,168,0.28) 40%, rgba(255,255,255,0.85) 50%, rgba(15,181,168,0.28) 60%, transparent 100%)',
              boxShadow: '0 0 36px 10px rgba(15,181,168,0.30)',
              mixBlendMode: 'screen',
              animation: 'tb-scan 3.6s cubic-bezier(.45,0,.55,1) infinite',
              pointerEvents: 'none',
            }}>
              <div style={{ position: 'absolute', left: 0, right: 0, bottom: '50%', height: 1, background: 'rgba(255,255,255,0.85)', boxShadow: '0 0 10px rgba(255,255,255,0.7)' }}/>
            </div>
          )}

          {/* ROI box — precisely surrounding the first row of cards on AirbnbSite (1180px wide) */}
          <div style={{
            position: 'absolute', 
            left: 28 * scale, 
            top: 196 * scale, 
            width: (1180 - 56) * scale, 
            height: 340 * scale,
            border: '1.5px solid rgba(15,181,168,0.9)',
            boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.25), 0 0 32px rgba(15,181,168,0.35)',
            borderRadius: 8 * scale,
            animation: 'tb-pulse 2.8s ease-in-out infinite',
            pointerEvents: 'none',
          }}>
            <div className="tb-corner tl"/><div className="tb-corner tr"/>
            <div className="tb-corner bl"/><div className="tb-corner br"/>
            <div style={{
              position: 'absolute', top: -22, left: 10,
              fontFamily: T.fMono, fontSize: 9.5, letterSpacing: '0.06em', color: T.tealDeep,
              background: 'rgba(246,247,249,0.95)', padding: '2px 8px', borderRadius: 3,
              boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
              border: '0.5px solid rgba(15,181,168,0.3)',
            }}>
              roi · primary fixation
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ScoreBar({ label, value, color, T }) {
  return (
    <div style={{ marginBottom: 7 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 3 }}>
        <span style={{ fontFamily: T.fMono, fontSize: 9.5, color: T.inkMute, letterSpacing: '0.03em' }}>{label}</span>
        <span style={{ fontFamily: T.fMono, fontSize: 9.5, color: color || T.ink, fontWeight: 500 }}>
          {value > 0 ? '+' : ''}{value.toFixed(2)}
        </span>
      </div>
      <div style={{ height: 3, background: 'rgba(10,22,40,0.07)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 2,
          width: `${Math.abs(value) * 100}%`,
          background: color || T.teal,
          transition: 'width 0.6s cubic-bezier(.2,.7,.3,1)',
        }}/>
      </div>
    </div>
  );
}

function HeroScan({ children, tilt = 18, brainSize = 210, brainRotX, brainRotY }) {
  const T = window.TRIBE;
  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 480 }}>

      {/* Background: large scanning site */}
      <div style={{ 
        position: 'relative', 
        zIndex: 2, 
        width: '100%', 
        height: '100%', 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center',
        padding: '0 40px'
      }}>
        <ScanningSite tilt={tilt}>{children}</ScanningSite>
      </div>

      {/* Signal paths: site ROI → brain panel (hidden in layered mode to keep it clean, or adjusted) */}
      <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 4, overflow: 'visible' }}>
        <defs>
          <linearGradient id="sig" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#0FB5A8" stopOpacity="0.7"/>
            <stop offset="100%" stopColor="#F9D84A" stopOpacity="0.6"/>
          </linearGradient>
        </defs>
        <path d="M 50% 45% Q 70% 30%, 82% 40%" stroke="url(#sig)" strokeWidth="1" fill="none" strokeDasharray="3 5" opacity="0.6"/>
      </svg>

      {/* Floating brain analysis panel */}
      <div style={{ 
        position: 'absolute', 
        top: '12%', 
        right: '-5%', 
        width: 320, 
        zIndex: 10,
        display: 'flex', 
        flexDirection: 'column' 
      }}>
        <div style={{
          borderRadius: 16, overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
          background: 'linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(244,247,251,0.85) 100%)',
          border: '0.5px solid rgba(10,22,40,0.12)',
          boxShadow: '0 4px 12px rgba(10,22,40,0.08), 0 30px 80px -20px rgba(10,80,100,0.25)',
          backdropFilter: 'blur(24px)',
        }}>

          {/* Panel header */}
          <div style={{
            padding: '12px 16px 11px',
            borderBottom: '0.5px solid rgba(10,22,40,0.08)',
            background: 'rgba(255,255,255,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div>
              <div style={{ fontFamily: T.fMono, fontSize: 9.5, color: T.tealDeep, letterSpacing: '0.05em' }}>
                section analysis
              </div>
              <div style={{ fontFamily: T.fUI, fontSize: 13, fontWeight: 600, color: T.ink, marginTop: 1, letterSpacing: '-0.01em' }}>
                Hero card #1
              </div>
            </div>
            <div style={{
              padding: '3px 8px', borderRadius: 4, fontFamily: T.fMono, fontSize: 9,
              background: 'rgba(15,181,168,0.12)', color: T.tealDeep, letterSpacing: '0.04em',
            }}>
              ● live
            </div>
          </div>

          {/* Brain canvas */}
          <div style={{
            display: 'flex', justifyContent: 'center', alignItems: 'center',
            padding: '12px 0 8px', minHeight: 200,
            background: 'radial-gradient(ellipse 70% 60% at 50% 50%, rgba(15,181,168,0.1), transparent 70%)',
          }}>
            <window.BrainCanvas width={brainSize} height={brainSize} initRotX={brainRotX} initRotY={brainRotY}/>
          </div>

          {/* Score bars */}
          <div style={{ padding: '10px 16px 8px', borderTop: '0.5px solid rgba(10,22,40,0.07)' }}>
            <ScoreBar label="attention"  value={0.71} color={T.tealDeep}   T={T}/>
            <ScoreBar label="curiosity"  value={0.58} color={T.teal}       T={T}/>
            <ScoreBar label="trust"      value={0.34} color={T.inkSoft}    T={T}/>
            <ScoreBar label="confusion"  value={-0.18} color="#C43A3A"     T={T}/>
          </div>

          {/* Recommendation */}
          <div style={{
            padding: '10px 16px 16px',
            borderTop: '0.5px solid rgba(10,22,40,0.07)',
            background: 'rgba(255,255,255,0.35)',
          }}>
            <div style={{ fontFamily: T.fMono, fontSize: 9.5, color: T.inkMute, letterSpacing: '0.05em', marginBottom: 6 }}>
              recommendation
            </div>
            <p style={{
              margin: 0, fontFamily: T.fUI, fontSize: 12, lineHeight: 1.5, color: T.inkSoft,
            }}>
              Frontal eye fields show strong fixation on the hero image.
            </p>
            <p style={{
              margin: '6px 0 0', fontFamily: T.fUI, fontSize: 12, lineHeight: 1.5, color: T.ink, fontWeight: 500,
            }}>
              Add a scarcity signal to reduce DLPFC confusion load by −0.12.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

window.HeroScan = HeroScan;
window.ScanningSite = ScanningSite;
