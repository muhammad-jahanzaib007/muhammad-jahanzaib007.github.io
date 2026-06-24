/* ===== shared interactions ===== */
(function(){
  const rm=matchMedia('(prefers-reduced-motion:reduce)').matches;

  // scroll progress
  const prog=document.getElementById('prog');
  if(prog)addEventListener('scroll',()=>{const h=document.documentElement;prog.style.width=(h.scrollTop/(h.scrollHeight-h.clientHeight)*100)+'%'},{passive:true});

  // cursor glow
  const glow=document.getElementById('glow');
  if(glow&&!rm)addEventListener('mousemove',e=>{glow.style.left=e.clientX+'px';glow.style.top=e.clientY+'px'});

  // reveal on scroll
  const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.1});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));

  // smooth-scroll for in-page anchors with fixed-nav offset (reliable both directions)
  const NAV_OFFSET=88;
  document.querySelectorAll('a[href^="#"]').forEach(a=>{
    a.addEventListener('click',e=>{
      const id=a.getAttribute('href').slice(1);
      if(!id)return;
      const el=document.getElementById(id);
      if(!el)return;
      e.preventDefault();
      const top=el.getBoundingClientRect().top+window.scrollY-NAV_OFFSET;
      window.scrollTo({top:Math.max(0,top),behavior:'smooth'});
      history.replaceState(null,'','#'+id);
    });
  });

  // animated counters
  function animCount(el){const t=parseFloat(el.dataset.count),d=+(el.dataset.dec||0),s=el.dataset.suffix||'',dur=1300,t0=performance.now();
    (function st(n){const p=Math.min((n-t0)/dur,1),e=1-Math.pow(1-p,3);el.textContent=(t*e).toFixed(d)+s;if(p<1)requestAnimationFrame(st)})(t0)}
  const cio=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){animCount(e.target);cio.unobserve(e.target)}}),{threshold:.6});
  document.querySelectorAll('[data-count]').forEach(el=>cio.observe(el));

  // project-card spotlight
  if(!rm)document.querySelectorAll('.pcard').forEach(c=>{
    c.addEventListener('mousemove',e=>{const r=c.getBoundingClientRect();c.style.setProperty('--mx',(e.clientX-r.left)+'px');c.style.setProperty('--my',(e.clientY-r.top)+'px')});
  });

  // active nav highlight (home) — scroll-position based for reliability
  const links=[...document.querySelectorAll('.navlinks a')].filter(a=>(a.getAttribute('href')||'').startsWith('#'));
  if(links.length){
    const secs=links.map(a=>({a,el:document.getElementById(a.getAttribute('href').slice(1))})).filter(s=>s.el);
    let active=null;
    function setActive(){
      const y=scrollY+140;
      let cur=null;
      for(const s of secs){ if(s.el.offsetTop<=y) cur=s; }
      if(cur===active) return;
      active=cur;
      links.forEach(a=>a.classList.remove('active'));
      if(cur) cur.a.classList.add('active');
    }
    addEventListener('scroll',setActive,{passive:true});
    addEventListener('resize',setActive);
    setActive();
  }

  // lightbox (any <figure> with an <img>)
  const lb=document.getElementById('lb');
  if(lb){
    const lbImg=lb.querySelector('img'),lbCap=lb.querySelector('.cap');
    document.querySelectorAll('figure').forEach(f=>{
      const img=f.querySelector('img');if(!img)return;
      f.addEventListener('click',()=>{const cap=f.querySelector('figcaption');
        lbImg.src=img.src;lbImg.alt=img.alt;lbCap.textContent=cap?cap.textContent:'';lb.classList.add('open')});
    });
    const close=()=>lb.classList.remove('open');
    lb.addEventListener('click',close);
    addEventListener('keydown',e=>{if(e.key==='Escape')close()});
  }

  // toast
  const toast=document.getElementById('toast');let tt;
  function showToast(m){if(!toast)return;toast.textContent=m;toast.classList.add('show');clearTimeout(tt);tt=setTimeout(()=>toast.classList.remove('show'),2800)}

  // copy email
  const ce=document.getElementById('copyEmail');
  if(ce)ce.addEventListener('click',()=>{const em=ce.dataset.email;
    navigator.clipboard.writeText(em).then(()=>showToast('Email copied: '+em)).catch(()=>showToast(em));});

  // contact form (Formspree)
  const cf=document.getElementById('cform');
  if(cf)cf.addEventListener('submit',e=>{
    e.preventDefault();
    if(cf.action.includes('FORMSPREE_ID')){showToast('Contact form not configured yet — use the email above for now.');return;}
    const btn=cf.querySelector('button');btn.disabled=true;btn.textContent='Sending…';
    fetch(cf.action,{method:'POST',body:new FormData(cf),headers:{Accept:'application/json'}})
      .then(r=>{if(r.ok){cf.reset();showToast('Message sent — thanks! I’ll reply within 24h.')}else throw 0})
      .catch(()=>showToast('Something went wrong — please email me directly.'))
      .finally(()=>{btn.disabled=false;btn.textContent='Send message'});
  });

  // image blur-up
  document.querySelectorAll('.figgrid figure img, .pcard .thumb img').forEach(img=>{
    if(img.complete&&img.naturalWidth)img.classList.add('loaded');
    else{img.addEventListener('load',()=>img.classList.add('loaded'));img.addEventListener('error',()=>img.classList.add('loaded'))}
  });

  // hero particle constellation
  const cv2=document.getElementById('hp');
  if(cv2&&!rm){
    const ctx=cv2.getContext('2d');let w,h,pts=[],mouse={x:-999,y:-999},raf;
    function size(){const r=cv2.getBoundingClientRect();w=cv2.width=r.width*devicePixelRatio;h=cv2.height=r.height*devicePixelRatio;
      const n=Math.min(64,Math.floor(r.width/20));pts=Array.from({length:n},()=>({x:Math.random()*w,y:Math.random()*h,vx:(Math.random()-.5)*.25*devicePixelRatio,vy:(Math.random()-.5)*.25*devicePixelRatio}))}
    size();addEventListener('resize',size);
    cv2.parentElement.addEventListener('mousemove',e=>{const r=cv2.getBoundingClientRect();mouse.x=(e.clientX-r.left)*devicePixelRatio;mouse.y=(e.clientY-r.top)*devicePixelRatio});
    cv2.parentElement.addEventListener('mouseleave',()=>{mouse.x=mouse.y=-999});
    const LINK=110*devicePixelRatio;
    function draw(){
      ctx.clearRect(0,0,w,h);
      for(const p of pts){p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>w)p.vx*=-1;if(p.y<0||p.y>h)p.vy*=-1;
        const dx=p.x-mouse.x,dy=p.y-mouse.y,dm=Math.hypot(dx,dy);
        if(dm<140*devicePixelRatio&&dm>0){p.x+=dx/dm*.6;p.y+=dy/dm*.6}
        ctx.beginPath();ctx.arc(p.x,p.y,1.6*devicePixelRatio,0,7);ctx.fillStyle='rgba(52,211,153,.55)';ctx.fill()}
      for(let i=0;i<pts.length;i++)for(let j=i+1;j<pts.length;j++){
        const a=pts[i],b=pts[j],d=Math.hypot(a.x-b.x,a.y-b.y);
        if(d<LINK){ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);
          ctx.strokeStyle='rgba(120,160,255,'+(0.16*(1-d/LINK))+')';ctx.lineWidth=devicePixelRatio;ctx.stroke()}}
      raf=requestAnimationFrame(draw)}
    draw();
  }

  // CV button — graceful fallback if PDF missing
  const cv=document.getElementById('cvbtn');
  if(cv)cv.addEventListener('click',e=>{
    e.preventDefault();
    fetch(cv.href,{method:'HEAD'}).then(r=>{
      if(r.ok)window.open(cv.href,'_blank','noopener');
      else showToast('CV PDF not added yet — drop it in /assets to enable download.');
    }).catch(()=>showToast('CV PDF not added yet — drop it in /assets to enable download.'));
  });
})();
