// PipelineStages.jsx — simulated analysis pipeline (sentence case).

const PIPELINE = [
  { id:'tribev2',  label:'Tribe v2 inference',      sub:'brain-activation estimation from DOM + pixels',  ms:1400 },
  { id:'destrieux',label:'Destrieux atlas mapping', sub:'parcel-level emotion and feeling decoding',      ms:1100 },
  { id:'perturb',  label:'Perturbation maps',       sub:'region occlusion · saliency recovery',           ms:1300 },
  { id:'llm',      label:'LLM synthesis',           sub:'grounded critique from activation maps',         ms:1500 },
  { id:'regen',    label:'Image-gen delta',         sub:'counter-factual redesign · double OOD',          ms:1800 },
  { id:'reinfer',  label:'Tribe v2 re-inference',   sub:'delta site back through the brain model',        ms:1200 },
  { id:'rank',     label:'Ranking',                 sub:'composite UX score · Δ attention · Δ affect',    ms:900  },
];

function PipelineStages({ url, onDone, compact = false }) {
  const [active, setActive] = React.useState(0);
  const [progress, setProgress] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    let i = 0;
    const run = () => {
      if (cancelled) return;
      if (i >= PIPELINE.length) { onDone && onDone(); return; }
      setActive(i);
      setProgress(0);
      const dur = PIPELINE[i].ms;
      const start = performance.now();
      const tick = () => {
        if (cancelled) return;
        const p = Math.min(1, (performance.now() - start) / dur);
        setProgress(p);
        if (p < 1) requestAnimationFrame(tick);
        else { i += 1; run(); }
      };
      requestAnimationFrame(tick);
    };
    run();
    return () => { cancelled = true; };
  }, []);

  return (
    <div style={{
      width:'100%', display:'flex', flexDirection:'column', gap:compact ? 6 : 8,
      fontFamily: window.TRIBE.fUI,
    }}>
      <div style={{
        display:'flex', justifyContent:'space-between', alignItems:'baseline',
        marginBottom:6, fontFamily:window.TRIBE.fMono, fontSize:10.5, letterSpacing:'0.04em',
        color: window.TRIBE.inkMute,
      }}>
        <span>analyzing · <span style={{color:window.TRIBE.ink}}>{url}</span></span>
        <span>{active+1} / {PIPELINE.length}</span>
      </div>
      {PIPELINE.map((s, i) => {
        const state = i < active ? 'done' : i === active ? 'run' : 'wait';
        const p = i < active ? 1 : i === active ? progress : 0;
        return (
          <div key={s.id} style={{
            display:'grid', gridTemplateColumns:'18px 1fr auto', gap:12, alignItems:'center',
            padding:'10px 14px', borderRadius:10,
            background: state === 'run' ? 'rgba(255,255,255,0.55)' : 'transparent',
            border: state === 'run' ? '0.5px solid rgba(255,255,255,0.7)' : '0.5px solid transparent',
            boxShadow: state === 'run' ? 'inset 0 1px 0 rgba(255,255,255,0.9), 0 6px 20px -8px rgba(10,22,40,0.15)' : 'none',
            opacity: state === 'wait' ? 0.4 : 1,
            transition:'all .3s cubic-bezier(.2,.7,.3,1)',
          }}>
            {/* indicator */}
            <div style={{position:'relative',width:14,height:14}}>
              {state === 'done' ? (
                <svg width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="6.5" fill={window.TRIBE.teal}/><path d="M4 7.2l2 2 4-4.4" stroke="#fff" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
              ) : state === 'run' ? (
                <>
                  <div style={{position:'absolute',inset:0,borderRadius:'50%',border:`1.5px solid ${window.TRIBE.hair}`}}/>
                  <svg width="14" height="14" viewBox="0 0 14 14" style={{position:'absolute',inset:0,transform:'rotate(-90deg)'}}>
                    <circle cx="7" cy="7" r="5.6" fill="none" stroke={window.TRIBE.teal} strokeWidth="1.5" strokeDasharray={`${p*35.2} 35.2`} strokeLinecap="round"/>
                  </svg>
                </>
              ) : (
                <div style={{position:'absolute',inset:0,borderRadius:'50%',border:`1px dashed ${window.TRIBE.hairStrong}`}}/>
              )}
            </div>
            <div>
              <div style={{fontSize:13.5, fontWeight:500, color: window.TRIBE.ink, letterSpacing:'-0.005em'}}>{s.label}</div>
              <div style={{fontSize:11.5, color: window.TRIBE.inkMute, marginTop:1}}>{s.sub}</div>
            </div>
            <div style={{fontFamily:window.TRIBE.fMono,fontSize:10,color: state==='run' ? window.TRIBE.tealDeep : window.TRIBE.inkMute, letterSpacing:'0.02em'}}>
              {state==='done' ? 'ok' : state==='run' ? `${Math.round(p*100)}%` : '—'}
            </div>
          </div>
        );
      })}
    </div>
  );
}

window.PipelineStages = PipelineStages;
