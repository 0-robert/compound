// AirbnbSite.jsx — static stylized mock of an Airbnb-like listings page.
// NOT a brand recreation: a generic travel-listings visual so the hero scan
// feels like a real site being analyzed. All strings are original.

function AirbnbSite({ scale = 1 }) {
  const cards = [
    { tag: 'Cabin · Hudson Valley',  photo: 'https://images.unsplash.com/photo-1510798831971-661eb04b3739?w=600&q=80', badge: 'Guest favourite' },
    { tag: 'Loft · Lisbon',          photo: 'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=600&q=80' },
    { tag: 'Cottage · Dartmoor',     photo: 'https://images.unsplash.com/photo-1464146072230-91cabc968266?w=600&q=80' },
    { tag: 'Villa · Mallorca',       photo: 'https://images.unsplash.com/photo-1613977257363-707ba9348227?w=600&q=80' },
    { tag: 'Studio · Kyoto',         photo: 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=600&q=80' },
    { tag: 'A-frame · Mt. Hood',     photo: 'https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=600&q=80' },
  ];
  return (
    <div style={{
      width: 1180, background: '#fff', borderRadius: 14, overflow: 'hidden',
      boxShadow: '0 1px 0 rgba(0,0,0,0.04)',
      fontFamily: window.TRIBE.fUI, color: '#222', transform: `scale(${scale})`, transformOrigin: 'top left',
    }}>
      {/* Top bar */}
      <div style={{
        display:'flex', alignItems:'center', justifyContent:'space-between',
        padding:'18px 32px', borderBottom:'1px solid #EBEBEB'
      }}>
        <div style={{display:'flex',alignItems:'center',gap:8,color:'#E31C5F',fontWeight:700,fontSize:18,letterSpacing:'-0.02em'}}>
          <div style={{width:22,height:22,borderRadius:'50%',background:'linear-gradient(135deg,#FF385C,#E31C5F)'}}/>
          staywander
        </div>
        <div style={{
          display:'flex', border:'1px solid #DDD', borderRadius:999, padding:'8px 8px 8px 20px',
          boxShadow:'0 1px 2px rgba(0,0,0,0.06)', fontSize:13, alignItems:'center', gap:16
        }}>
          <span style={{fontWeight:600}}>Anywhere</span>
          <span style={{width:1,height:18,background:'#EBEBEB'}}/>
          <span style={{fontWeight:600}}>Any week</span>
          <span style={{width:1,height:18,background:'#EBEBEB'}}/>
          <span style={{color:'#888'}}>Add guests</span>
          <div style={{width:28,height:28,borderRadius:'50%',background:'#FF385C',color:'#fff',display:'flex',alignItems:'center',justifyContent:'center',fontSize:12}}>⌕</div>
        </div>
        <div style={{display:'flex',gap:18,alignItems:'center',fontSize:13}}>
          <span>List your place</span>
          <div style={{padding:'6px 12px',border:'1px solid #DDD',borderRadius:999,display:'flex',gap:8,alignItems:'center'}}>
            <span style={{fontSize:10}}>☰</span>
            <div style={{width:22,height:22,borderRadius:'50%',background:'#717171'}}/>
          </div>
        </div>
      </div>

      {/* Category rail */}
      <div style={{display:'flex',gap:32,padding:'18px 32px',borderBottom:'1px solid #EBEBEB',overflow:'hidden'}}>
        {['Cabins','Beachfront','Lakefront','Design','Treehouses','Countryside','National parks','Castles','Tiny homes','OMG!','Amazing views','Creative spaces'].map((c,i)=>(
          <div key={i} style={{display:'flex',flexDirection:'column',alignItems:'center',gap:8,minWidth:58,
            color: i===0 ? '#222':'#717171', borderBottom: i===0?'2px solid #222':'2px solid transparent', paddingBottom:10}}>
            <div style={{width:24,height:24,background:'#E8E8E8',borderRadius:4}}/>
            <span style={{fontSize:11,fontWeight:i===0?600:400,whiteSpace:'nowrap'}}>{c}</span>
          </div>
        ))}
      </div>

      {/* Hero heading */}
      <div style={{padding:'28px 32px 10px',display:'flex',justifyContent:'space-between',alignItems:'end'}}>
        <div>
          <div style={{fontSize:28,fontWeight:600,letterSpacing:'-0.02em'}}>Over 1,200 stays</div>
          <div style={{fontSize:14,color:'#717171',marginTop:4}}>Trending getaways for Apr 28 – May 4</div>
        </div>
        <div style={{display:'flex',gap:10}}>
          {['Price','Type of place','Instant Book','More filters'].map((f,i)=>(
            <div key={i} style={{padding:'9px 16px',border:'1px solid #DDD',borderRadius:999,fontSize:12.5}}>{f}</div>
          ))}
        </div>
      </div>

      {/* Card grid */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:22,padding:'20px 32px 36px'}}>
        {cards.map((c,i)=>(
          <div key={i}>
            <div style={{
              aspectRatio:'1.1/1', borderRadius:14, overflow:'hidden', position:'relative',
              background: '#E8E8E8',
            }}>
              <img src={c.photo} alt={c.tag} style={{
                position:'absolute', inset:0, width:'100%', height:'100%',
                objectFit:'cover', display:'block',
              }}/>
              <div style={{position:'absolute',top:12,right:12,width:24,height:24,display:'flex',alignItems:'center',justifyContent:'center'}}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="rgba(0,0,0,0.25)" stroke="#fff" strokeWidth="2"><path d="M12 21s-7-4.5-7-10a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 5.5-7 10-7 10z"/></svg>
              </div>
              {c.badge && <div style={{position:'absolute',top:12,left:12,background:'#fff',padding:'4px 10px',borderRadius:4,fontSize:11,fontWeight:600}}>{c.badge}</div>}
            </div>
            <div style={{display:'flex',justifyContent:'space-between',marginTop:10,fontSize:13.5}}>
              <div style={{fontWeight:600}}>{c.tag}</div>
              <div>★ 4.9{i%2?2:0}</div>
            </div>
            <div style={{color:'#717171',fontSize:13,marginTop:2}}>{['1,245 kilometres away','2 nights · May 12–14','Stunning mountain views','Hosted by Elena','Near downtown','Entire home'][i]}</div>
            <div style={{marginTop:6,fontSize:13.5}}><b>${180 + i*37}</b> <span style={{color:'#717171'}}>night</span></div>
          </div>
        ))}
      </div>
    </div>
  );
}

window.AirbnbSite = AirbnbSite;
