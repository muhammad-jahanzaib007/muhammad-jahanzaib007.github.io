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

  // animated counters
  function animCount(el){const t=parseFloat(el.dataset.count),d=+(el.dataset.dec||0),s=el.dataset.suffix||'',dur=1300,t0=performance.now();
    (function st(n){const p=Math.min((n-t0)/dur,1),e=1-Math.pow(1-p,3);el.textContent=(t*e).toFixed(d)+s;if(p<1)requestAnimationFrame(st)})(t0)}
  const cio=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){animCount(e.target);cio.unobserve(e.target)}}),{threshold:.6});
  document.querySelectorAll('[data-count]').forEach(el=>cio.observe(el));

  // project-card spotlight
  if(!rm)document.querySelectorAll('.pcard').forEach(c=>{
    c.addEventListener('mousemove',e=>{const r=c.getBoundingClientRect();c.style.setProperty('--mx',(e.clientX-r.left)+'px');c.style.setProperty('--my',(e.clientY-r.top)+'px')});
  });

  // active nav highlight (home)
  const links=[...document.querySelectorAll('.navlinks a')].filter(a=>a.getAttribute('href')&&a.getAttribute('href').startsWith('#'));
  if(links.length){
    const map={};links.forEach(a=>{const id=a.getAttribute('href').slice(1);if(document.getElementById(id))map[id]=a});
    const sio=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){
      links.forEach(a=>a.classList.remove('active'));if(map[e.target.id])map[e.target.id].classList.add('active');
    }}),{rootMargin:'-45% 0px -50% 0px'});
    Object.keys(map).forEach(id=>sio.observe(document.getElementById(id)));
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
