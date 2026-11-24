// The header's hand-painted studio lot, drawn live on the canvas #art.
(() => {
'use strict';
/* ------------------------------------------------------------------ setup */
const W = 1820, H = 1024, FPS = 45, VARIANTS = 3;
const SEED = (+new URLSearchParams(location.search).get('seed')) || 1927; // ?seed=42 for another take
const cv = document.getElementById('art'), g = cv.getContext('2d');
const TAU = Math.PI * 2, PI = Math.PI;

function rng(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
let F = rng(SEED), P = rng(SEED + 7);          // F: paint strokes (stable)  P: pencil lines (boil)
const fr = (a,b) => a + (b-a)*F(), pr = (a,b) => a + (b-a)*P();
const lerp = (a,b,t) => a + (b-a)*t, clamp = (v,a,b) => Math.max(a, Math.min(b, v));
const hsl = (c,a=1,dl=0) => `hsla(${c[0]},${c[1]}%,${clamp(c[2]+dl,0,100)}%,${a})`;
const mix = (a,b,t) => [lerp(a[0],b[0],t), lerp(a[1],b[1],t), lerp(a[2],b[2],t)];
function ramp(stops,t){t=clamp(t,0,1)*(stops.length-1);const i=Math.min(stops.length-2,Math.floor(t));return mix(stops[i],stops[i+1],t-i);}
function mk(w,h){const c=document.createElement('canvas');c.width=w;c.height=h;return c;}

/* ----------------------------------------------------------------- shapes */
const R = (x,y,w,h) => [[x,y],[x+w,y],[x+w,y+h],[x,y+h]];
function E(cx,cy,rx,ry,a0=0,a1=TAU,n){n=n||Math.max(10,Math.ceil((rx+ry)/2.5));const full=a1-a0>=TAU-1e-6,p=[];for(let i=0;i<(full?n:n+1);i++){const a=a0+(a1-a0)*i/n;p.push([cx+Math.cos(a)*rx,cy+Math.sin(a)*ry]);}return p;}
function RR(x,y,w,h,r){const p=[],cs=[[x+w-r,y+r,-PI/2],[x+w-r,y+h-r,0],[x+r,y+h-r,PI/2],[x+r,y+r,PI]];for(const[cx,cy,a]of cs)for(let i=0;i<=4;i++){const t=a+i/4*PI/2;p.push([cx+Math.cos(t)*r,cy+Math.sin(t)*r]);}return p;}
function quad(x1,y1,x2,y2,w1,w2=w1){const a=Math.atan2(y2-y1,x2-x1)+PI/2,c=Math.cos(a),s=Math.sin(a);return[[x1+c*w1/2,y1+s*w1/2],[x2+c*w2/2,y2+s*w2/2],[x2-c*w2/2,y2-s*w2/2],[x1-c*w1/2,y1-s*w1/2]];}
function star(cx,cy,r,n=5,rot=-PI/2,inner=.45){const p=[];for(let i=0;i<n*2;i++){const a=rot+i*PI/n,rr=i%2?r*inner:r;p.push([cx+Math.cos(a)*rr,cy+Math.sin(a)*rr]);}return p;}
function trace(c,pts){c.beginPath();c.moveTo(pts[0][0],pts[0][1]);for(let i=1;i<pts.length;i++)c.lineTo(pts[i][0],pts[i][1]);c.closePath();}
function bbox(pts){let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;for(const p of pts){x0=Math.min(x0,p[0]);y0=Math.min(y0,p[1]);x1=Math.max(x1,p[0]);y1=Math.max(y1,p[1]);}return{x:x0,y:y0,w:x1-x0,h:y1-y0};}
function bez(p0,c1,c2,p3,t){const u=1-t,a=u*u*u,b=3*u*u*t,c=3*u*t*t,d=t*t*t;return[a*p0[0]+b*c1[0]+c*c2[0]+d*p3[0],a*p0[1]+b*c1[1]+c*c2[1]+d*p3[1]];}
function bezTan(p0,c1,c2,p3,t){const u=1-t;return Math.atan2(3*u*u*(c1[1]-p0[1])+6*u*t*(c2[1]-c1[1])+3*t*t*(p3[1]-c2[1]),3*u*u*(c1[0]-p0[0])+6*u*t*(c2[0]-c1[0])+3*t*t*(p3[0]-c2[0]));}

/* ------------------------------------------------- gouache + pencil tools */
// A surface = flat underpainting + many short semi-random strokes + impasto ridges + pencil outline.
function paint(c,pts,col,o={}){
  const b=bbox(pts),den=o.den||40,len=o.len||12,w=o.w||3.2,dir=o.dir??-0.5,wob=o.wob??0.55,jit=o.jit||[6,7,7],sh=o.shade||0,shx=o.shadeX||0;
  c.save();trace(c,pts);c.clip();
  c.fillStyle=hsl(col);c.fillRect(b.x-1,b.y-1,b.w+2,b.h+2);
  const n=Math.ceil(b.w*b.h/den)+6;c.lineCap='round';
  for(let i=0;i<n;i++){
    const x=b.x+F()*b.w,y=b.y+F()*b.h,a=dir+(F()-.5)*2*wob,l=len*(.5+F());
    const dx=Math.cos(a)*l/2,dy=Math.sin(a)*l/2;
    const dl=(F()-.5)*2*jit[2]+sh*(.5-(y-b.y)/(b.h||1))+shx*(.5-(x-b.x)/(b.w||1));
    c.strokeStyle=`hsla(${col[0]+(F()-.5)*2*jit[0]},${col[1]+(F()-.5)*2*jit[1]}%,${col[2]+dl}%,${.5+F()*.45})`;
    c.lineWidth=w*(.5+F());
    c.beginPath();c.moveTo(x-dx,y-dy);c.lineTo(x+dx,y+dy);c.stroke();
    if(F()<.22){ // impasto: a lit ridge and a little shadow beside the stroke
      c.lineWidth=.8;c.strokeStyle=`hsla(${col[0]},${col[1]*.6}%,${Math.min(96,col[2]+dl+15)}%,.5)`;
      c.beginPath();c.moveTo(x-dx-.8,y-dy-1);c.lineTo(x+dx-.8,y+dy-1);c.stroke();
      c.strokeStyle=`hsla(${col[0]},${col[1]}%,${Math.max(4,col[2]+dl-16)}%,.32)`;
      c.beginPath();c.moveTo(x-dx+.8,y-dy+1.2);c.lineTo(x+dx+.8,y+dy+1.2);c.stroke();
    }
  }
  c.restore();
  if(o.line!==false)pencil(c,pts,true,o.lw||1,o.la||.55);
}
function pencil(c,pts,closed=true,lw=1,alpha=.55){
  c.save();c.lineCap='round';c.lineJoin='round';
  const n=pts.length,m=closed?n:n-1;
  for(let pass=0;pass<2;pass++){
    c.beginPath();let first=true;
    for(let i=0;i<m;i++){
      const a=pts[i],b=pts[(i+1)%n],k=Math.max(1,Math.round(Math.hypot(b[0]-a[0],b[1]-a[1])/22));
      for(let j=0;j<k;j++){const t=j/k,x=lerp(a[0],b[0],t)+pr(-1.1,1.1),y=lerp(a[1],b[1],t)+pr(-1.1,1.1);if(first){c.moveTo(x,y);first=false;}else c.lineTo(x,y);}
      if(P()<.14){c.lineTo(b[0]+pr(-2.5,2.5),b[1]+pr(-2.5,2.5));c.moveTo(b[0]+pr(-1.5,1.5),b[1]+pr(-1.5,1.5));}
    }
    const e=closed?pts[0]:pts[n-1];c.lineTo(e[0]+pr(-1.1,1.1),e[1]+pr(-1.1,1.1));
    c.strokeStyle=`hsla(28,12%,${14+pr(0,8)}%,${alpha*(.55+P()*.45)})`;c.lineWidth=lw*(.6+P()*.7);c.stroke();
  }
  c.restore();
}
function hatch(c,pts,ang,gap,alpha=.25,lw=.8){
  const b=bbox(pts),cx=b.x+b.w/2,cy=b.y+b.h/2,r=Math.hypot(b.w,b.h)/2,ca=Math.cos(ang),sa=Math.sin(ang);
  c.save();trace(c,pts);c.clip();c.lineCap='round';
  for(let d=-r;d<r;d+=gap*(.7+F()*.6)){
    const ox=cx-sa*d,oy=cy+ca*d,l0=-r*(.6+F()*.4),l1=r*(.6+F()*.4);
    c.strokeStyle=`hsla(28,12%,16%,${alpha*(.5+F()*.5)})`;c.lineWidth=lw*(.6+F()*.8);
    c.beginPath();c.moveTo(ox+ca*l0+fr(-1,1),oy+sa*l0+fr(-1,1));c.lineTo(ox+ca*l1+fr(-1,1),oy+sa*l1+fr(-1,1));c.stroke();
  }
  c.restore();
}
// loose field of strokes whose colour depends on position (sky, ground)
function wash(c,x,y,w,h,n,colAt,o={}){
  c.save();c.beginPath();c.rect(x,y,w,h);c.clip();c.lineCap='round';
  for(let i=0;i<n;i++){
    const px=x+F()*w,py=y+F()*h,col=colAt((py-y)/h,(px-x)/w),a=(o.dir||0)+(F()-.5)*(o.wob??.4),l=(o.len||30)*(.5+F());
    const dx=Math.cos(a)*l/2,dy=Math.sin(a)*l/2;
    c.strokeStyle=`hsla(${col[0]+(F()-.5)*8},${col[1]+(F()-.5)*8}%,${col[2]+(F()-.5)*7}%,${.45+F()*.5})`;
    c.lineWidth=(o.w||6)*(.5+F());c.beginPath();c.moveTo(px-dx,py-dy);c.lineTo(px+dx,py+dy);c.stroke();
    if(F()<.18){c.lineWidth=.8;c.strokeStyle=`hsla(${col[0]},${col[1]*.6}%,${Math.min(96,col[2]+13)}%,.45)`;c.beginPath();c.moveTo(px-dx,py-dy-1.2);c.lineTo(px+dx,py+dy-1.2);c.stroke();}
  }
  c.restore();
}
function label(c,str,x,y,size,col,o={}){
  c.save();c.translate(x,y);c.rotate(o.rot||0);
  c.font=`${o.style||'bold'} ${size}px Georgia,"Times New Roman",serif`;c.textAlign=o.align||'center';c.textBaseline='middle';
  for(let i=0;i<3;i++){c.fillStyle=hsl(col,o.a||.5);c.fillText(str,fr(-.6,.6),fr(-.6,.6));}
  c.restore();
}
const limb=(c,x1,y1,x2,y2,w1,w2,col,o={})=>paint(c,quad(x1,y1,x2,y2,w1,w2),col,Object.assign({dir:Math.atan2(y2-y1,x2-x1),wob:.35,len:8,w:2.4,den:16},o));

/* ---------------------------------------------------------------- palette */
const C = {
  paper:[42,32,86], sky:[[205,16,66],[203,15,70],[200,13,74],[195,5,79],[50,8,81],[42,24,81],[36,36,80],[30,42,78]],
  ground:[[38,34,67],[35,32,61],[31,29,54],[27,26,46]],
  hillFar:[255,9,64], hillNear:[78,16,54], stucco:[40,30,76], stucco2:[32,26,69], terra:[14,36,48], teal:[178,20,40],
  wood:[28,34,42], woodL:[30,34,52], woodD:[24,30,28], brass:[40,42,55], brassL:[42,46,66], brassD:[34,36,40],
  robot:[34,36,57], robotL:[38,38,64], steel:[188,12,48], cream:[44,30,86], card:[47,52,80],
  cap:[352,34,35], capD:[352,34,26], mahog:[8,34,30], mahogD:[8,30,21], mahogL:[10,32,38],
  iron:[170,9,30], film:[28,10,15], leaf:[90,20,32], tin:[200,8,50]
};
const LIGHTS = [[222,146,154],[230,190,110],[122,182,170],[176,156,204],[228,156,116]]; // muted rose, mustard, teal, lavender, coral
function lightCol(ph,a=1){ph=((ph%5)+5)%5;const i=Math.floor(ph),f=ph-i,A=LIGHTS[i],B=LIGHTS[(i+1)%5];return`rgba(${lerp(A[0],B[0],f)|0},${lerp(A[1],B[1],f)|0},${lerp(A[2],B[2],f)|0},${a})`;}

/* ------------------------------------------------------- layout constants */
const RX = 400, BX = 520, PX = 640;                    // where the robot+desk, the magic box and the projector stand
const at = (c,ox,fn) => {c.save();c.translate(ox,0);fn(c);c.restore();};
const SCR = {x:1300,y:196,w:290,h:216};                // projection screen (global)
const WIN = {x:475,y:682,r:46};                         // magic box window (box-local)
const BULBS = [0,1,2,3,4].map(i=>[410+i*32.5,594]);
const HOP = {x:463,y:502,rx:64,ry:11};                 // hopper mouth (box-local)
const HOPG = [HOP.x+BX,506];
const STREAM = [[-60,430],[300,400],[820,350],HOPG];
const CARDPATH = [[282+RX,812],[372+RX,620],[HOPG[0]-110,400],HOPG];
const TAPE = [[578+BX,708],[1150,832],[1232,838],[638+PX,708]];
const REEL1 = {x:668,y:700,r:32}, REEL2 = {x:790,y:762,r:26}, LENSL = [730,728], LENS = [730+PX,728];
const KLIEG = [262,318], KLIEG2 = [1772,404], NECK = [173,690], SHOULDER = [226,726];

/* ================================================================ LAYERS */
/* ---- layer 1: sky, hills, the studio lot ---- */
function layerBackground(c){
  const sg=c.createLinearGradient(0,0,0,500);C.sky.forEach((s,i)=>sg.addColorStop(i/(C.sky.length-1),hsl(s)));
  c.fillStyle=sg;c.fillRect(0,0,W,500);
  wash(c,0,0,W,500,11500,t=>ramp(C.sky,t),{len:34,w:7,wob:.5});
  // low sun
  paint(c,E(1180,128,30,30),[44,52,85],{den:14,len:8,w:3,wob:3,line:false});
  c.save();c.lineCap='round';for(let i=0;i<70;i++){const a=fr(0,TAU),r=fr(34,58);c.strokeStyle=hsl([44,50,86],fr(.12,.4));c.lineWidth=fr(1.5,4);c.beginPath();c.arc(1180,128,r,a,a+fr(.15,.5));c.stroke();}c.restore();
  pencil(c,E(1180,128,30,30),true,.8,.3);
  cloud(c,150,110,1.15);cloud(c,430,70,.8);cloud(c,330,170,.55);cloud(c,800,120,1);cloud(c,1010,180,.6);cloud(c,1440,90,1.1);cloud(c,1690,150,.7);cloud(c,620,60,.5);
  // hills
  const far=[],near=[];
  for(let x=-10;x<=W+10;x+=18){far.push([x,424-30*Math.sin(x/130+1)-13*Math.sin(x/47)]);near.push([x,452-16*Math.sin(x/90+3)-7*Math.sin(x/31+1)]);}
  paint(c,far.concat([[W+10,490],[-10,490]]),C.hillFar,{dir:-.2,len:14,w:4,den:50,shade:10,la:.35});
  paint(c,near.concat([[W+10,490],[-10,490]]),C.hillNear,{dir:.15,len:12,w:4,den:45,shade:8,la:.4});

  barrelStage(c,0,'STAGE 7');gableStage(c,0,'STAGE 4');waterTower(c,0);
  facades(c,520);gableStage(c,818,'STAGE 2');gate(c,985);barrelStage(c,1512,'STAGE 5');
  palm(c,330,476,250,14);palm(c,536,480,205,-12);palm(c,8,480,150,10);
  palm(c,772,478,215,12);palm(c,1100,480,240,-14);palm(c,1486,480,190,10);palm(c,1640,478,120,-6);palm(c,1812,484,165,-10);
  pennants(c,[290,340],[408,266],16);pennants(c,[474,266],[836,272],30);
  pennants(c,[1140,272],[SCR.x-5,SCR.y-6],24);pennants(c,[SCR.x+SCR.w+5,SCR.y-6],[1668,264],12);
}
function barrelStage(c,ox,name){c.save();c.translate(ox,0);
  // Stage 7: barrel-roofed sound stage
  paint(c,E(153,336,140,74,PI,TAU).concat([[293,476],[13,476]]),C.stucco,{dir:PI/2,wob:.3,len:16,w:4.5,den:50,shade:10,shadeX:-8});
  const arcO=E(153,336,140,74,PI,TAU),arcI=E(153,340,128,62,PI,TAU).reverse();
  paint(c,arcO.concat(arcI),C.terra,{dir:0,wob:1.5,len:8,w:3,den:18});
  for(let i=1;i<8;i++)pencil(c,[[13+i*35,476],[13+i*35,336-Math.sqrt(Math.max(0,1-Math.pow((i*35-140)/140,2)))*62+6]],false,.6,.2);
  paint(c,R(104,386,98,90),C.teal,{dir:PI/2,wob:.2,len:14,w:3.5,den:30,shade:8});
  pencil(c,[[153,386],[153,476]],false,1,.5);hatch(c,R(104,386,98,90),PI/2,7,.14);
  label(c,name,153,362,19,[14,36,30],{a:.45});
  for(const x of[40,236]){paint(c,R(x,400,34,30),[200,14,44],{den:20,len:6,w:2.5});pencil(c,[[x+17,400],[x+17,430]],false,.7,.4);pencil(c,[[x,415],[x+34,415]],false,.7,.4);}
  hatch(c,R(13,440,280,36),.5,9,.1);

c.restore();}
function gableStage(c,ox,name){c.save();c.translate(ox,0);
  // Stage 4: gabled stage
  paint(c,R(300,376,186,100),C.stucco2,{dir:PI/2,wob:.3,len:14,w:4,den:45,shade:8});
  paint(c,[[290,378],[393,326],[496,378]],C.terra,{dir:.47,wob:.25,len:12,w:3.5,den:26});
  paint(c,R(352,410,60,66),[205,14,40],{dir:PI/2,wob:.2,len:12,w:3,den:26});
  label(c,name,382,394,12,[14,36,28],{a:.4});
  hatch(c,R(300,376,186,24),.6,6,.14);

c.restore();}
function waterTower(c,ox){c.save();c.translate(ox,0);
  // water tower
  for(const[x1,x2]of[[420,410],[462,472],[441,441]])limb(c,x1,330,x2,476,4.5,4.5,C.woodD);
  pencil(c,[[418,350],[466,400]],false,.9,.5);pencil(c,[[464,350],[414,400]],false,.9,.5);pencil(c,[[414,402],[470,458]],false,.9,.5);pencil(c,[[468,402],[412,458]],false,.9,.5);
  paint(c,R(408,262,66,72),[24,28,48],{dir:PI/2,wob:.12,len:18,w:3.5,den:22,shadeX:-16});
  for(const y of[278,300,322])pencil(c,[[408,y],[474,y]],false,1.2,.5);
  paint(c,[[400,264],[441,230],[482,264]],[14,26,36],{dir:.6,len:8,w:3,den:18});
  pencil(c,[[441,230],[441,216]],false,1,.6);

c.restore();}
function facades(c,ox){ // a little backlot street of false fronts
  c.save();c.translate(ox,0);
  for(const[x,w,h,col,name]of[[0,70,92,[30,28,66],'HOTEL'],[72,84,112,[16,30,56],'SALOON'],[158,66,84,[190,12,58],'BANK']]){
    paint(c,R(x,476-h,w,h),col,{dir:PI/2,wob:.2,len:12,w:3.5,den:30,shade:8});
    paint(c,R(x-3,476-h-8,w+6,10),C.woodD,{dir:0,len:8,w:2.5,den:12});
    label(c,name,x+w/2,476-h+16,9.5,[20,30,22],{a:.45});
    paint(c,R(x+w/2-9,446,18,30),C.woodD,{den:10,len:6,w:2});
    paint(c,R(x+8,476-h+28,14,16),[200,14,40],{den:8,len:5,w:2});paint(c,R(x+w-22,476-h+28,14,16),[200,14,40],{den:8,len:5,w:2});
    paint(c,[[x-4,434],[x+w+4,434],[x+w+8,443],[x-8,443]],C.terra,{dir:0,len:8,w:2.5,den:10});
  }
  c.restore();
}
function gate(c,ox){ // the studio gate
  c.save();c.translate(ox,0);
  for(const x of[-140,102]){paint(c,R(x,292,38,184),C.stucco,{dir:PI/2,wob:.25,len:14,w:4,den:30,shadeX:-10});paint(c,R(x-5,288,48,10),C.terra,{dir:0,len:8,w:2.5,den:10});hatch(c,R(x+24,298,14,178),-.8,5,.16);}
  paint(c,[[-70,258],[0,226],[70,258]],C.terra,{dir:.3,len:9,w:3,den:14});
  paint(c,star(0,246,7),[44,52,70],{den:5,len:4,w:1.6,lw:.7});
  paint(c,R(-160,256,320,38),C.cream,{dir:0,wob:.2,len:14,w:4,den:24,shade:6});
  pencil(c,R(-154,261,308,28),true,.8,.4);
  label(c,'VIDEOTAPE  PICTURES',0,276,19,[14,36,30],{a:.5});
  c.restore();
}
function cloud(c,x,y,s){
  const puffs=[[0,0,46,18],[-34,6,30,13],[36,7,34,13],[10,-12,28,15],[-12,10,52,11]];
  for(const[dx,dy,rx,ry]of puffs)paint(c,E(x+dx*s,y+dy*s,rx*s,ry*s),[40,26,89],{dir:0,wob:.6,len:12*s,w:4,den:36,shade:8,line:false});
  pencil(c,E(x,y-2*s,60*s,22*s,PI*1.05,PI*1.95),false,.7,.22);
}
function palm(c,x,by,h,lean){
  const tx=x+lean,ty=by-h,mx=x+lean*.3,my=by-h*.5;
  limb(c,x,by,mx,my,7,5.5,[28,22,40],{la:.4});limb(c,mx,my,tx,ty,5.5,4,[28,22,40],{la:.4});
  for(let i=0;i<9;i++)frond(c,tx,ty,-PI/2+(i-4)*.62+fr(-.15,.15),h*.3*fr(.8,1.15));
}
function frond(c,x,y,a,L){
  c.save();c.lineCap='round';let px=x,py=y;const n=9;
  for(let i=1;i<=n;i++){
    const t=i/n,nx=x+Math.cos(a)*L*t,ny=y+Math.sin(a)*L*t+L*.75*t*t,sa=Math.atan2(ny-py,nx-px);
    c.strokeStyle=hsl([90+fr(-10,10),20,28+fr(-6,6)],.9);c.lineWidth=2.2*(1-t)+.8;c.beginPath();c.moveTo(px,py);c.lineTo(nx,ny);c.stroke();
    for(const s of[-1,1]){const la=sa+s*1.1,ll=L*.22*(1-t*.6)*fr(.7,1.2);c.strokeStyle=hsl([88+fr(-12,12),22+fr(-6,6),34+fr(-8,8)],.85);c.lineWidth=fr(1,2.4);c.beginPath();c.moveTo(nx,ny);c.lineTo(nx+Math.cos(la)*ll,ny+Math.sin(la)*ll+ll*.3);c.stroke();}
    px=nx;py=ny;
  }
  c.restore();
}
function pennants(c,a,b,sag){
  const cols=[[352,34,52],[44,50,62],[178,22,48],[265,18,60],[20,44,58]],n=Math.round(Math.hypot(b[0]-a[0],b[1]-a[1])/15),line=[];
  for(let i=0;i<=n;i++){const t=i/n;line.push([lerp(a[0],b[0],t),lerp(a[1],b[1],t)+Math.sin(t*PI)*sag]);}
  pencil(c,line,false,.8,.6);
  for(let i=0;i<n;i++){const p=line[i],q=line[i+1];paint(c,[p,q,[(p[0]+q[0])/2+fr(-1,1),(p[1]+q[1])/2+13]],cols[i%5],{den:8,len:5,w:2,la:.4,lw:.7});}
}

/* ---- layer 2: the lot floor ---- */
function layerGround(c){
  const gg=c.createLinearGradient(0,470,0,H);C.ground.forEach((s,i)=>gg.addColorStop(i/3,hsl(s)));
  c.fillStyle=gg;c.fillRect(0,470,W,H-470);
  wash(c,0,470,W,H-470,11500,t=>ramp(C.ground,t),{len:30,w:6.5,wob:.3});
  wash(c,0,470,W,60,1100,()=>[40,30,70],{len:22,w:3,wob:.2});
  pencil(c,[[0,474],[W,472]],false,.8,.3);
  // faint cart tracks & floor marks
  for(let i=0;i<14;i++){const x=fr(-100,W+100);pencil(c,[[W/2+(x-W/2)*.3,480],[x,H]],false,.7,.12);}
  hatch(c,R(0,930,W,94),.08,10,.12);
}

/* ---- layer 3: things standing around the studio ---- */
function klieg(c,kx,ky,flip){
  c.save();if(flip){c.translate(kx,0);c.scale(-1,1);c.translate(-kx,0);}
  // klieg light on a tall stand
  hatch(c,E(kx+4,596,44,7),0,3,.25);
  limb(c,kx,ky+30,kx,592,5,5,C.iron);
  limb(c,kx,560,kx-30,596,3.5,3,C.iron);limb(c,kx,560,kx+32,596,3.5,3,C.iron);limb(c,kx,560,kx+4,600,3.5,3,C.iron);
  pencil(c,E(kx,ky,36,36,PI*.1,PI*.9),false,1.6,.7);
  paint(c,E(kx,ky,30,30),C.iron,{den:12,len:8,w:3,wob:3,shade:14});
  paint(c,E(kx-9,ky+8,21,23),[46,44,82],{den:10,len:6,w:2.5,wob:3});
  pencil(c,E(kx-9,ky+8,13,15),true,.7,.3);
  for(let i=0;i<4;i++)pencil(c,[[kx+10+i*4,ky-27+i*3],[kx+24+i*2,ky-12+i*5]],false,.9,.5);

  c.restore();
}
function layerStudio(c){
  // painted night-sky flat, far left
  hatch(c,E(156,650,150,8),0,3,.22);
  limb(c,52,500,20,648,5,4,C.woodD);limb(c,262,500,294,648,5,4,C.woodD);
  paint(c,R(46,488,222,152),[222,22,36],{dir:.2,len:14,w:4,den:30,shade:-8});
  paint(c,E(206,540,27,27),[46,40,84],{den:10,len:6,w:2.5,wob:3,line:false});
  paint(c,E(217,533,23,23),[222,22,36],{den:10,len:6,w:2.5,wob:3,line:false});
  [[80,520,6],[120,560,4],[150,512,5],[100,600,4],[176,592,6],[236,598,4],[66,572,3]].forEach(([x,y,r],i)=>paint(c,star(x,y,r,5,i),[46,44,80],{den:4,len:3,w:1.4,lw:.6,la:.35}));
  for(const[x,y,s]of[[110,622,1],[214,628,.8]])paint(c,E(x,y,44*s,10*s),[222,14,52],{dir:0,len:10,w:3,den:20,line:false});
  pencil(c,R(52,494,210,140),true,.7,.3);
  // pages that slipped out of the stream
  [[92,700,.3],[212,744,-.5],[330,690,.9],[150,812,-.2],[352,792,.5],[40,780,1.2],[268,838,-.9]].forEach(([x,y,a],i)=>{c.save();c.translate(x,y);c.rotate(a);paint(c,[[-15,-8],[15,-8],[19,8],[-19,8]],[44,28,87-i%2*4],{dir:0,len:8,w:3,den:14,la:.45,lw:.8});for(let k=0;k<3;k++)pencil(c,[[-11,-4+k*4],[9-(k%2)*8,-4+k*4]],false,.6,.3);c.restore();});
  at(c,290,c=>{
  // hand-crank camera on a tripod, far left
  hatch(c,E(64,570,40,7),0,3,.25);
  limb(c,62,500,36,568,4,3.5,C.wood);limb(c,62,500,64,574,4,3.5,C.wood);limb(c,62,500,90,568,4,3.5,C.wood);
  paint(c,E(50,452,13,13),C.iron,{den:8,len:5,w:2,wob:3});paint(c,E(76,452,13,13),C.iron,{den:8,len:5,w:2,wob:3});
  paint(c,R(38,462,50,38),C.wood,{dir:0,wob:.2,len:10,w:3,den:14,shade:12});
  paint(c,R(88,472,15,15),C.brassD,{den:8,len:5,w:2});paint(c,E(104,479.5,3.5,8),C.iron,{den:6,len:3,w:1.5});
  pencil(c,[[62,484],[72,494],[78,490]],false,1.2,.7);

  });
  at(c,RX,c=>{
  klieg(c,KLIEG[0],KLIEG[1]);
  // director's chair
  hatch(c,E(332,694,40,6),0,3,.22);
  limb(c,304,648,360,692,4,4,C.wood);limb(c,360,648,304,692,4,4,C.wood);
  limb(c,306,596,306,650,4,4,C.wood);limb(c,358,596,358,650,4,4,C.wood);
  paint(c,R(304,640,56,9),C.teal,{dir:0,len:8,w:2.5,den:12});
  paint(c,R(306,600,52,20),C.teal,{dir:0,len:8,w:2.5,den:12,shade:8});
  label(c,'DIRECTOR',332,610,7.5,C.cream,{a:.55});

  });
  klieg(c,KLIEG2[0],KLIEG2[1],true);

  // the picture screen on its poles
  const sl=SCR.x+4,sr=SCR.x+SCR.w-4,sb=SCR.y+SCR.h;
  hatch(c,E(SCR.x+SCR.w/2,590,SCR.w*.6,8),0,3,.2);
  limb(c,sl,SCR.y-2,sl,588,6,6,C.woodD);limb(c,sr,SCR.y-2,sr,588,6,6,C.woodD);
  pencil(c,[[sl,sb+18],[sl-36,586]],false,.8,.4);pencil(c,[[sr,sb+18],[sr+36,586]],false,.8,.4);
  paint(c,R(SCR.x-9,SCR.y-9,SCR.w+18,SCR.h+18),C.woodD,{dir:0,wob:.2,len:14,w:3.5,den:22,shade:8});
  paint(c,R(SCR.x,SCR.y,SCR.w,SCR.h),[44,22,86],{dir:.2,len:12,w:4,den:40});
}

/* ---- layer 4: the robot (body, baked), its desk ---- */
function layerRobot(c){
  hatch(c,E(190,962,190,14),0,3.5,.3);
  // stool + legs
  limb(c,122,850,112,952,5,4,C.woodD);limb(c,238,850,250,952,5,4,C.woodD);
  limb(c,152,846,150,934,20,18,C.steel,{shadeX:10});limb(c,206,846,210,934,20,18,C.steel,{shadeX:10});
  for(const y of[872,896])for(const x of[151,208])pencil(c,[[x-10,y],[x+10,y]],false,.8,.45);
  paint(c,RR(130,928,46,20,8),C.brassD,{den:12,len:7,w:2.5,shade:10});paint(c,RR(190,928,50,20,8),C.brassD,{den:12,len:7,w:2.5,shade:10});
  // far arm
  limb(c,122,724,99,770,17,15,C.steel);limb(c,99,770,150,795,15,13,C.steel);
  paint(c,E(99,770,9,9),C.brassD,{den:8,len:4,w:2,wob:3});
  // torso
  paint(c,RR(112,702,122,104,18),C.robot,{dir:PI/2,wob:.5,len:12,w:3.5,den:22,shade:14,shadeX:-10});
  hatch(c,RR(112,702,36,104,18),-.9,5,.2);
  paint(c,RR(140,722,64,46,6),[182,14,60],{den:14,len:7,w:2.5,shade:8});
  paint(c,E(158,745,11,11),C.cream,{den:8,len:4,w:2,wob:3});pencil(c,[[158,745],[164,738]],false,1.2,.8);
  [[182,736,[352,36,52]],[194,736,[44,52,60]],[182,750,[178,24,48]],[194,750,[30,10,30]]].forEach(([x,y,col])=>paint(c,E(x,y,4,4),col,{den:5,len:3,w:1.5,lw:.7}));
  for(const[x,y]of[[122,714],[224,714],[122,790],[224,790]])paint(c,E(x,y,2.6,2.6),C.brassD,{den:4,len:2,w:1,lw:.6});
  paint(c,E(226,726,13,13),C.brassD,{den:8,len:5,w:2,wob:3});
  // neck
  paint(c,R(160,680,26,24),C.steel,{dir:0,len:8,w:2,den:10});for(const y of[686,692,698])pencil(c,[[160,y],[186,y]],false,.8,.5);

  // desk
  limb(c,60,852,60,944,9,8,C.woodD);limb(c,326,852,326,944,9,8,C.woodD);
  paint(c,[[42,790],[346,790],[366,830],[22,830]],C.woodL,{dir:.05,wob:.2,len:22,w:4,den:28,shadeX:-8});
  paint(c,R(26,830,336,24),C.wood,{dir:0,wob:.15,len:20,w:4,den:24,shade:10});
  paint(c,R(34,854,14,112),C.wood,{dir:PI/2,wob:.15,len:14,w:3.5,den:16});paint(c,R(338,854,14,112),C.wood,{dir:PI/2,wob:.15,len:14,w:3.5,den:16});
  paint(c,E(194,842,5,5),C.brass,{den:5,len:3,w:1.5,lw:.7});
  hatch(c,R(26,854,336,16),.3,5,.22);
  // far hand resting on the desk, pile of screenplays, inkwell
  paint(c,E(152,796,10,7),C.brassD,{den:7,len:4,w:2,wob:3});
  for(let i=0;i<5;i++)paint(c,[[58+fr(-3,3),806-i*3],[116+fr(-3,3),806-i*3],[122,822-i*3],[52,822-i*3]],[44,28,86-i%2*4],{dir:0,len:10,w:3,den:16,lw:.7,la:.45});
  for(let i=0;i<4;i++)pencil(c,[[66,798+i*3.4],[108-(i%2)*14,798+i*3.4]],false,.7,.35);
  paint(c,RR(198,798,17,15,3),[215,20,26],{den:6,len:4,w:2});paint(c,R(203,794,7,5),C.brassD,{den:5,len:3,w:1.5,lw:.7});
}
// head lives in its own sprite so it can tilt
function drawHead(c){
  paint(c,RR(118,612,108,74,16),C.robotL,{dir:PI/2,wob:.6,len:11,w:3.5,den:20,shade:14,shadeX:-10});
  paint(c,E(119,650,7,11),C.brassD,{den:6,len:4,w:2});
  paint(c,RR(140,626,80,48,10),[44,28,76],{den:16,len:8,w:3,shade:6});
  paint(c,E(163,646,12.5,12.5),[30,10,18],{den:8,len:4,w:2,wob:3});paint(c,E(203,646,12.5,12.5),[30,10,18],{den:8,len:4,w:2,wob:3});
  paint(c,R(172,668,24,6),C.brassD,{den:6,len:3,w:1.5,lw:.7});for(let x=176;x<196;x+=4)pencil(c,[[x,668],[x,674]],false,.7,.6);
  for(const[x,y]of[[128,622],[128,676],[217,678]])paint(c,E(x,y,2.4,2.4),C.brassD,{den:4,len:2,w:1,lw:.6});
  // flat cap
  const crown=[[110,617],[113,600],[138,585],[178,580],[214,586],[230,600],[233,615]];
  paint(c,[[212,606],[252,612],[258,621],[224,621]],C.capD,{dir:.15,len:7,w:2.5,den:10});
  paint(c,crown,C.cap,{dir:-.3,wob:.7,len:9,w:3,den:14,shade:14});
  hatch(c,crown,.9,6,.2);hatch(c,crown,-.6,7,.16);
  paint(c,E(174,580,5,3),C.capD,{den:4,len:3,w:1.5,lw:.7});
}

/* ---- layer 5: the magic box ---- */
function layerBox(c){
  hatch(c,E(486,846,128,13),0,3.5,.32);
  paint(c,R(390,828,22,16),C.brassD,{den:8,len:5,w:2});paint(c,R(540,828,22,16),C.brassD,{den:8,len:5,w:2});
  // crank on the left side
  limb(c,382,712,360,712,6,6,C.brassD);limb(c,360,712,360,742,5,5,C.brassD);paint(c,E(360,746,6,6),C.woodD,{den:5,len:3,w:1.5,wob:3});
  // side, top, front
  paint(c,[[570,562],[590,548],[590,814],[570,830]],C.mahogD,{dir:PI/2,wob:.2,len:14,w:3.5,den:20});
  paint(c,[[380,560],[398,546],[590,546],[570,560]],C.mahogL,{dir:0,wob:.2,len:12,w:3,den:14});
  paint(c,RR(380,560,190,270,8),C.mahog,{dir:PI/2,wob:.22,len:18,w:4,den:24,shade:12,shadeX:-8});
  // brass trim
  paint(c,R(380,560,190,10),C.brass,{dir:0,len:10,w:3,den:12});paint(c,R(380,818,190,12),C.brass,{dir:0,len:10,w:3,den:12});
  paint(c,R(380,560,9,270),C.brass,{dir:PI/2,len:10,w:3,den:12});paint(c,R(561,560,9,270),C.brass,{dir:PI/2,len:10,w:3,den:12});
  for(const[x,y]of[[385,565],[565,565],[385,824],[565,824]])paint(c,E(x,y,2.4,2.4),C.brassD,{den:4,len:2,w:1,lw:.6});
  // bulbs, window ring, painted stars
  for(const[x,y]of BULBS){paint(c,E(x,y,10,10),C.brassD,{den:7,len:4,w:2,wob:3});paint(c,E(x,y,6.5,6.5),[45,20,72],{den:5,len:3,w:1.5,wob:3,lw:.7});}
  paint(c,E(WIN.x,WIN.y,WIN.r+13,WIN.r+13),C.brass,{den:12,len:8,w:3,wob:3,shade:16});
  paint(c,E(WIN.x,WIN.y,WIN.r,WIN.r),[240,20,17],{den:14,len:8,w:3,wob:3});
  for(let i=0;i<8;i++){const a=i*TAU/8+.2;paint(c,E(WIN.x+Math.cos(a)*(WIN.r+6.5),WIN.y+Math.sin(a)*(WIN.r+6.5),2.2,2.2),C.brassD,{den:4,len:2,w:1,lw:.5});}
  [[402,640,8],[549,634,7],[403,748,6],[548,742,8],[412,700,4],[540,690,4]].forEach(([x,y,r],i)=>paint(c,star(x,y,r,5,-PI/2+i),[44,52,64],{den:5,len:4,w:1.6,lw:.7,la:.45}));
  // controls + nameplate
  paint(c,E(416,792,13,13),C.cream,{den:8,len:5,w:2,wob:3});for(let i=0;i<7;i++){const a=PI+i*PI/6;pencil(c,[[416+Math.cos(a)*9,792+Math.sin(a)*9],[416+Math.cos(a)*12,792+Math.sin(a)*12]],false,.7,.6);}
  pencil(c,[[416,792],[423,784]],false,1.3,.85);
  paint(c,RR(444,780,100,24,4),C.brassL,{dir:0,len:9,w:2.5,den:12});
  label(c,'VIDEO MODEL',494,792.5,10,[8,34,22],{a:.55});
  // tape slot on the side
  paint(c,[[572,686],[588,676],[588,730],[572,740]],C.brass,{den:8,len:5,w:2});
  paint(c,[[576,696],[584,691],[584,721],[576,726]],[30,10,12],{den:6,len:4,w:2,lw:.7});
  // hopper
  paint(c,R(432,546,64,14),C.brassD,{dir:0,len:8,w:2.5,den:10});
  paint(c,[[HOP.x-HOP.rx,HOP.y],[HOP.x+HOP.rx,HOP.y],[498,552],[430,552]],C.brass,{dir:1.2,wob:.5,len:10,w:3,den:14,shadeX:-18});
  paint(c,E(HOP.x,HOP.y,HOP.rx,HOP.ry),[26,22,16],{dir:0,len:8,w:2.5,den:10});
  pencil(c,E(HOP.x,HOP.y,HOP.rx+1.5,HOP.ry+1.5),true,1.3,.6);
  hatch(c,[[470,514],[527,502],[498,552],[466,552]],1.1,4,.22);
}

/* ---- layer 6: projector (reels are animated), floor props ---- */
function layerProjector(c){
  hatch(c,E(718,974,84,11),0,3.5,.32);
  limb(c,716,828,664,972,7,5,C.wood);limb(c,716,828,718,978,7,5,C.wood);limb(c,716,828,778,972,7,5,C.wood);
  limb(c,694,762,REEL1.x,REEL1.y,8,7,C.iron);limb(c,752,776,REEL2.x,REEL2.y,8,7,C.iron);
  // lens barrel points up the lot, at the screen
  paint(c,quad(726,766,LENSL[0],LENSL[1]+4,26,22),C.brass,{dir:1.5,wob:.3,len:8,w:2.5,den:10,shadeX:-14});
  paint(c,E(LENSL[0],LENSL[1]+3,11,5),[46,40,84],{den:5,len:4,w:1.5,lw:.8});
  paint(c,RR(668,756,98,76,9),C.iron,{dir:PI/2,wob:.4,len:12,w:3.5,den:18,shade:14,shadeX:-10});
  hatch(c,RR(668,756,30,76,9),-.9,5,.22);
  paint(c,E(742,796,15,15),C.brassD,{den:8,len:5,w:2,wob:3,shade:10});paint(c,E(742,796,5,5),C.iron,{den:5,len:3,w:1.5,lw:.7});
  for(let i=0;i<4;i++)pencil(c,[[680,772+i*7],[712,772+i*7]],false,.9,.45);
  for(const[x,y]of[[675,763],[759,763],[675,825],[759,825]])paint(c,E(x,y,2.2,2.2),C.brassD,{den:4,len:2,w:1,lw:.6});
}
function layerProps(c){
  c.save();c.translate(RX,0);
  // megaphone
  hatch(c,E(446,948,56,7),0,3,.28);
  paint(c,[[404,912],[470,884],[478,944],[404,924]],[40,44,60],{dir:-.25,wob:.3,len:12,w:3,den:14,shade:14});
  paint(c,[[440,897],[450,893],[455,934],[445,931]],C.cap,{den:6,len:5,w:2,lw:.7});
  paint(c,E(474,914,8,30),[30,26,26],{den:8,len:6,w:2.5,dir:PI/2});
  paint(c,E(403,918,4,7),C.brassD,{den:5,len:3,w:1.5,lw:.7});
  c.restore();c.save();c.translate(BX,0);
  // film cans + a loose reel
  hatch(c,E(556,972,60,8),0,3,.28);
  const can=(x,y,rx,h)=>{paint(c,R(x-rx,y,rx*2,h).concat(E(x,y+h,rx,rx*.3,0,PI)),C.tin,{dir:0,len:10,w:3,den:14,shadeX:-16});paint(c,E(x,y,rx,rx*.3),[200,8,62],{dir:0,len:8,w:2.5,den:10});};
  can(552,944,40,16);can(546,922,36,15);
  label(c,'REEL 1',548,952,8,[30,10,24],{a:.5,style:''});
  paint(c,E(610,950,22,22),C.film,{den:10,len:6,w:2.5,wob:3});paint(c,E(610,950,13,13),C.tin,{den:8,len:5,w:2,wob:3});paint(c,E(610,950,4,4),C.film,{den:5,len:3,w:1.5,lw:.7});
  c.restore();
  // clapperboard leaning on the desk leg
  c.save();c.translate(98+RX,930);c.rotate(-.12);
  paint(c,R(-36,-22,72,50),[30,8,20],{dir:0,len:10,w:3,den:14});
  paint(c,R(-36,-36,72,12),C.cream,{dir:0,len:8,w:2.5,den:10});
  for(let i=0;i<5;i++)paint(c,[[-32+i*15,-36],[-24+i*15,-36],[-30+i*15,-24],[-38+i*15,-24]].map(p=>[clamp(p[0],-36,36),p[1]]),[30,8,20],{den:6,len:4,w:2,line:false});
  c.lineCap='round';for(let i=0;i<3;i++){c.strokeStyle=hsl(C.cream,.6);c.lineWidth=1.1;c.beginPath();c.moveTo(-30,-10+i*12+fr(-1,1));c.lineTo(30,-10+i*12+fr(-1,1));c.stroke();}
  label(c,'SCENE 1   TAKE 1',0,-4,6.5,C.cream,{a:.6,style:''});label(c,'VIDEOTAPE',0,9,7.5,C.cream,{a:.6});
  c.restore();
  // crates of scripts, bottom left
  hatch(c,E(166,962,130,9),0,3.5,.3);
  paint(c,R(60,872,122,88),C.wood,{dir:0,wob:.15,len:18,w:4,den:22,shade:10});
  for(const y of[900,930])pencil(c,[[60,y],[182,y]],false,.9,.45);pencil(c,R(66,878,110,76),true,.7,.3);
  label(c,'SCRIPTS',121,915,13,C.cream,{a:.5});
  paint(c,R(178,906,88,54),C.woodL,{dir:0,wob:.15,len:16,w:4,den:20,shade:10});pencil(c,[[178,932],[266,932]],false,.9,.45);
  label(c,'PROPS',222,920,10,[24,30,22],{a:.5});
  for(let i=0;i<5;i++)paint(c,[[78+fr(-3,3),862-i*3],[150+fr(-3,3),862-i*3],[156,874-i*3],[72,874-i*3]],[44,28,86-i%2*4],{dir:0,len:10,w:3,den:16,lw:.7,la:.45});
  // upright player piano for the accompaniment, right
  hatch(c,E(1666,902,126,11),0,3.5,.3);
  paint(c,R(1582,816,11,76),C.woodD,{dir:PI/2,len:10,w:3,den:12});paint(c,R(1739,816,11,76),C.woodD,{dir:PI/2,len:10,w:3,den:12});
  paint(c,R(1590,716,150,174),[14,32,24],{dir:PI/2,wob:.2,len:16,w:4,den:24,shade:10,shadeX:-8});
  paint(c,R(1582,706,166,12),[14,30,31],{dir:0,len:10,w:3,den:12});
  paint(c,R(1602,730,126,56),[14,32,29],{dir:PI/2,wob:.2,len:12,w:3,den:22});
  paint(c,R(1640,738,50,36),C.cream,{dir:0,len:8,w:2.5,den:14,la:.5});
  for(let i=0;i<4;i++)pencil(c,[[1645,746+i*7],[1685,746+i*7]],false,.6,.4);
  paint(c,[[1590,798],[1740,798],[1750,816],[1580,816]],[14,30,32],{dir:0,len:10,w:3,den:14});
  paint(c,R(1596,802,138,10),C.cream,{dir:PI/2,len:5,w:2,den:8});
  for(let i=1;i<23;i++)pencil(c,[[1596+i*6,802],[1596+i*6,812]],false,.6,.4);
  for(let i=0;i<22;i++)if(i%7!==2&&i%7!==6)paint(c,R(1600+i*6,802,3.6,6),[30,8,16],{den:4,len:3,w:1.5,line:false});
  paint(c,R(1610,832,110,44),[14,32,20],{dir:PI/2,wob:.2,len:12,w:3,den:22});
  paint(c,R(1650,884,9,6),C.brass,{den:4,len:3,w:1.5,lw:.7});paint(c,R(1672,884,9,6),C.brass,{den:4,len:3,w:1.5,lw:.7});
  limb(c,1665,894,1665,942,6,6,C.woodD);limb(c,1665,942,1644,954,4,4,C.woodD);limb(c,1665,942,1686,954,4,4,C.woodD);
  paint(c,E(1665,890,28,8),C.cap,{dir:0,len:8,w:2.5,den:10});
}

function drawScene(c){
  c.fillStyle=hsl(C.paper);c.fillRect(0,0,W,H);
  layerBackground(c);layerGround(c);layerStudio(c);at(c,RX,layerRobot);at(c,BX,layerBox);at(c,PX,layerProjector);layerProps(c);
}

/* ============================================================ PRE-RENDER */
// The same painting is made VARIANTS times: paint strokes identical, pencil lines re-drawn, so the linework "boils".
function variants(w,h,ox,oy,fn,seedOff=0){
  const out=[];
  for(let v=0;v<VARIANTS;v++){const cc=mk(w,h),c=cc.getContext('2d');F=rng(SEED+seedOff);P=rng(SEED+seedOff+7+v*101);c.translate(-ox,-oy);fn(c);out.push(cc);}
  return out;
}
const STATIC = variants(W,H,0,0,drawScene);
const HEAD = variants(200,150,90,565,drawHead,11);
const PAGE = [0,1,2].map(k=>variants(40,52,0,0,c=>{
  paint(c,R(4,4,32,44),[44,30,88-k*2],{dir:.2,len:9,w:3,den:14,la:.5,lw:.8});
  c.lineCap='round';
  for(let i=0;i<9;i++){const y=10+i*4.1,centered=(i+k)%4===1,x0=centered?15:8,x1=centered?25:fr(22,32);c.strokeStyle=hsl([30,12,24],fr(.35,.6));c.lineWidth=fr(.7,1.1);c.beginPath();c.moveTo(x0,y+fr(-.4,.4));c.lineTo(x1,y+fr(-.4,.4));c.stroke();}
},20+k));
const CARD = variants(40,30,0,0,c=>{
  paint(c,R(4,4,32,22),C.card,{dir:0,len:8,w:3,den:12,la:.55,lw:.8});
  c.lineCap='round';c.strokeStyle=hsl([178,30,34],.8);c.lineWidth=1.4;c.beginPath();c.moveTo(8,9);c.lineTo(11,11.5);c.lineTo(8,14);c.stroke();
  for(const[y,x1]of[[11.5,30],[16,26],[20.5,21]]){c.strokeStyle=hsl([30,12,24],.55);c.lineWidth=.9;c.beginPath();c.moveTo(y<12?14:8,y);c.lineTo(x1,y);c.stroke();}
},30);

// paper: grain to multiply over everything, plus tooth specks and a ragged unpainted margin
const GRAIN = (()=>{
  const cc=mk(W,H),c=cc.getContext('2d'),r=rng(SEED+900),im=c.createImageData(W,H),d=im.data;
  for(let i=0;i<W*H;i++){const n=226+r()*29-(r()<.04?18:0);d[i*4]=n;d[i*4+1]=n-2;d[i*4+2]=n-9;d[i*4+3]=255;}
  c.putImageData(im,0,0);c.lineCap='round';
  for(let i=0;i<2000;i++){const x=r()*W,y=r()*H,a=r()*TAU,l=4+r()*14;c.strokeStyle=`rgba(90,70,40,${.03+r()*.06})`;c.lineWidth=.6+r();c.beginPath();c.moveTo(x,y);c.quadraticCurveTo(x+Math.cos(a)*l*.5+r()*4-2,y+Math.sin(a)*l*.5+r()*4-2,x+Math.cos(a)*l,y+Math.sin(a)*l);c.stroke();}
  c.save();c.translate(W/2,H/2);c.scale(W/H,1);const vg=c.createRadialGradient(0,0,H*.38,0,0,H*.75);vg.addColorStop(0,'rgba(120,90,50,0)');vg.addColorStop(1,'rgba(120,90,50,.22)');c.fillStyle=vg;c.fillRect(-H/2,-H/2,H,H);c.restore();
  return cc;
})();
const FRAME = (()=>{
  const cc=mk(W,H),c=cc.getContext('2d'),r=rng(SEED+901);
  for(let i=0;i<7000;i++){c.fillStyle=`hsla(42,35%,90%,${.05+r()*.14})`;c.fillRect(r()*W,r()*H,1+r()*1.4,1+r()*1.4);}
  c.lineCap='round';c.fillStyle=hsl(C.paper);
  c.fillRect(0,0,W,9);c.fillRect(0,H-9,W,9);c.fillRect(0,0,9,H);c.fillRect(W-9,0,9,H);
  const edge=(x,y,dx,dy)=>{c.strokeStyle=`hsla(42,${28+r()*8}%,${84+r()*4}%,${.75+r()*.25})`;c.lineWidth=4+r()*7;const l=6+r()*r()*20;c.beginPath();c.moveTo(x-dx*4,y-dy*4);c.lineTo(x+dx*l+(r()-.5)*8,y+dy*l+(r()-.5)*8);c.stroke();};
  for(let i=0;i<1150;i++){edge(r()*W,0,0,1);edge(r()*W,H,0,-1);}
  for(let i=0;i<640;i++){edge(0,r()*H,1,0);edge(W,r()*H,-1,0);}
  return cc;
})();

/* ============================================================= ANIMATION */
let boil = 0, D = rng(1);
function seedDyn(k){F=rng(SEED*31+k*977+boil*13);P=rng(SEED*17+k*613+boil*29);}
const ease = t => t*t*(3-2*t);

function ik(S,T,u,f,flip){const dx=T[0]-S[0],dy=T[1]-S[1],d=Math.min(Math.hypot(dx,dy),u+f-.5),a=Math.atan2(dy,dx),b=Math.acos(clamp((u*u+d*d-f*f)/(2*u*d),-1,1)),e=a+flip*b;return[S[0]+Math.cos(e)*u,S[1]+Math.sin(e)*u];}
function glow(x,y,r,col0,col1){const gr=g.createRadialGradient(x,y,0,x,y,r);gr.addColorStop(0,col0);gr.addColorStop(1,col1);g.fillStyle=gr;g.fillRect(x-r,y-r,r*2,r*2);}

/* the silent film on the screen */
function drawFilm(t){
  const x=0,y=0,w=214,h=160,gy=y+126,fl=.9+D()*.1,jy=D()<.06?(D()-.5)*4:0;
  g.save();g.translate(SCR.x,SCR.y);g.scale(SCR.w/w,SCR.h/h);g.beginPath();g.rect(x,y,w,h);g.clip();g.translate(0,jy);
  const cyc=t%15;
  if(cyc<11){
    const sk=g.createLinearGradient(0,y,0,gy);sk.addColorStop(0,`hsl(40,22%,${70*fl}%)`);sk.addColorStop(1,`hsl(42,34%,${86*fl}%)`);g.fillStyle=sk;g.fillRect(x,y-4,w,h+8);
    // sun with turning rays
    g.fillStyle=`hsla(44,50%,${94*fl}%,.95)`;g.beginPath();g.arc(x+162,y+40,15,0,TAU);g.fill();
    g.strokeStyle='hsla(44,45%,94%,.6)';g.lineWidth=1.6;g.lineCap='round';
    for(let i=0;i<10;i++){const a=i*TAU/10+t*.25;g.beginPath();g.moveTo(x+162+Math.cos(a)*20,y+40+Math.sin(a)*20);g.lineTo(x+162+Math.cos(a)*(27+(i%2)*4),y+40+Math.sin(a)*(27+(i%2)*4));g.stroke();}
    // hills, telegraph poles, ground
    g.fillStyle='hsla(32,20%,52%,.9)';g.beginPath();g.moveTo(x,gy);for(let i=0;i<=w;i+=6)g.lineTo(x+i,gy-22-14*Math.sin(i/46+1)-6*Math.sin(i/17));g.lineTo(x+w,gy);g.fill();
    g.fillStyle='hsla(30,22%,38%,.95)';g.beginPath();g.moveTo(x,gy);for(let i=0;i<=w;i+=6)g.lineTo(x+i,gy-8-9*Math.sin(i/60+4));g.lineTo(x+w,gy);g.fill();
    g.strokeStyle='hsla(30,20%,20%,.8)';g.lineWidth=1.3;
    for(let i=0;i<4;i++){const px=x+20+i*62;g.beginPath();g.moveTo(px,gy);g.lineTo(px,gy-40);g.moveTo(px-6,gy-36);g.lineTo(px+6,gy-36);g.stroke();}
    g.lineWidth=.6;g.beginPath();g.moveTo(x,gy-34);for(let i=0;i<4;i++)g.quadraticCurveTo(x-11+i*62,gy-28,x+20+i*62,gy-36);g.lineTo(x+w,gy-30);g.stroke();
    g.fillStyle=`hsl(30,20%,${24*fl}%)`;g.fillRect(x,gy,w,h);
    g.strokeStyle='hsla(40,25%,70%,.6)';g.lineWidth=1;g.beginPath();g.moveTo(x,gy+3);g.lineTo(x+w,gy+3);g.stroke();
    for(let i=0;i<w;i+=9){g.beginPath();g.moveTo(x+i,gy+1);g.lineTo(x+i-2,gy+7);g.stroke();}
    // the little train
    const tx=x-90+((t*30)%(w+190)),bob=Math.sin(t*14)*.6,ink=`hsl(28,22%,${13*fl}%)`;
    g.fillStyle=ink;
    for(let k=0;k<6;k++){const a=(t*.9+k/6)%1;g.fillStyle=`hsla(40,20%,92%,${(1-a)*.75})`;g.beginPath();g.arc(tx+49-a*34,gy-36-a*30+Math.sin(k+a*5)*2,3+a*9,0,TAU);g.fill();}
    g.fillStyle=ink;
    g.fillRect(tx+22,gy-23+bob,34,15);g.fillRect(tx+6,gy-32+bob,18,24);g.fillRect(tx+46,gy-34+bob,6,12);g.fillRect(tx+34,gy-27+bob,6,5);
    g.beginPath();g.moveTo(tx+56,gy-8);g.lineTo(tx+66,gy);g.lineTo(tx+56,gy);g.fill();
    g.fillRect(tx-34,gy-25-bob,36,19);g.fillRect(tx-74,gy-25+bob,36,19);g.fillRect(tx-40,gy-10,48,2);
    g.fillStyle='hsla(42,34%,84%,.9)';g.fillRect(tx+10,gy-28+bob,9,8);for(const cx0 of[-68,-56,-28,-16])g.fillRect(tx+cx0,gy-21,7,7);
    for(const[wx,wr]of[[14,6],[34,5],[48,5],[-24,4.5],[-8,4.5],[-64,4.5],[-48,4.5]]){g.fillStyle=ink;g.beginPath();g.arc(tx+wx,gy+1,wr,0,TAU);g.fill();g.strokeStyle='hsla(42,30%,80%,.8)';g.lineWidth=1;const a=t*6+wx;g.beginPath();g.moveTo(tx+wx-Math.cos(a)*wr*.7,gy+1-Math.sin(a)*wr*.7);g.lineTo(tx+wx+Math.cos(a)*wr*.7,gy+1+Math.sin(a)*wr*.7);g.stroke();}
  }else{
    g.fillStyle=`hsl(30,14%,${15*fl}%)`;g.fillRect(x,y-4,w,h+8);
    g.strokeStyle='hsla(42,34%,84%,.85)';g.lineWidth=1.6;g.strokeRect(x+12,y+12,w-24,h-24);g.lineWidth=.7;g.strokeRect(x+17,y+17,w-34,h-34);
    g.fillStyle='hsla(42,34%,86%,.92)';g.textAlign='center';g.textBaseline='middle';
    g.font='bold 25px Georgia,"Times New Roman",serif';g.fillText('VIDEOTAPE',x+w/2+(D()-.5),y+h/2-14);
    g.font='italic 12.5px Georgia,"Times New Roman",serif';g.fillText('“ the tape is the app ”',x+w/2,y+h/2+16);
    g.beginPath();g.moveTo(x+w/2-34,y+h/2+38);g.lineTo(x+w/2+34,y+h/2+38);g.lineWidth=1;g.stroke();
  }
  // gouache grain on the picture, then scratches, dust and flicker
  seedDyn(60);g.lineCap='round';
  for(let i=0;i<70;i++){const px=x+F()*w,py=y+F()*h;g.strokeStyle=`hsla(${30+F()*14},25%,${F()<.5?86:30}%,${.05+F()*.09})`;g.lineWidth=1.5+F()*3;g.beginPath();g.moveTo(px,py);g.lineTo(px+(F()-.5)*14,py+(F()-.5)*6);g.stroke();}
  for(let i=0;i<2;i++)if(D()<.5){const sx=x+D()*w;g.strokeStyle=`hsla(42,30%,92%,${.15+D()*.3})`;g.lineWidth=.7;g.beginPath();g.moveTo(sx,y);g.lineTo(sx+(D()-.5)*4,y+h);g.stroke();}
  for(let i=0;i<5;i++){g.fillStyle=`hsla(30,20%,${D()<.5?12:92}%,${.3+D()*.4})`;g.fillRect(x+D()*w,y+D()*h,1+D()*2,1+D()*2);}
  const vg=g.createRadialGradient(x+w/2,y+h/2,h*.35,x+w/2,y+h/2,w*.72);vg.addColorStop(0,'rgba(30,20,10,0)');vg.addColorStop(1,'rgba(30,20,10,.5)');g.fillStyle=vg;g.fillRect(x,y-4,w,h+8);
  g.restore();
  seedDyn(61);pencil(g,R(SCR.x,SCR.y,SCR.w,SCR.h),true,1,.5);
  return fl;
}

function drawBeam(t,fl){
  const a=[SCR.x,SCR.y+SCR.h],b=[SCR.x+SCR.w,SCR.y+SCR.h];
  g.save();g.globalCompositeOperation='screen';
  const gr=g.createLinearGradient(LENS[0],LENS[1],SCR.x+SCR.w/2,a[1]);gr.addColorStop(0,`rgba(255,240,200,${.55*fl})`);gr.addColorStop(1,`rgba(255,240,200,${.13*fl})`);
  g.fillStyle=gr;g.beginPath();g.moveTo(LENS[0]-5,LENS[1]);g.lineTo(a[0],a[1]);g.lineTo(b[0],b[1]);g.lineTo(LENS[0]+5,LENS[1]);g.fill();
  seedDyn(62);g.lineCap='round';
  for(let i=0;i<9;i++){const u=F();g.strokeStyle=`rgba(255,244,214,${.05+F()*.1})`;g.lineWidth=.8+F()*1.6;g.beginPath();g.moveTo(LENS[0]+(F()-.5)*6,LENS[1]);g.lineTo(lerp(a[0],b[0],u),a[1]);g.stroke();}
  for(let i=0;i<16;i++){const u=((i*.618+t*(.02+i%3*.012))%1),v=.15+((i*.37+Math.sin(t*.4+i)*.04+1)%1)*.8,ex=lerp(a[0],b[0],u),px=lerp(LENS[0],ex,v),py=lerp(LENS[1],a[1],v);g.fillStyle=`rgba(255,246,220,${.25+.3*Math.sin(t*2+i*1.7)**2})`;g.fillRect(px,py,1.6,1.6);}
  glow(LENS[0],LENS[1]+2,26,`rgba(255,240,200,${.7*fl})`,'rgba(255,240,200,0)');
  glow(SCR.x+SCR.w/2,SCR.y+SCR.h/2,250,`rgba(255,236,196,${.14*fl})`,'rgba(255,236,196,0)');
  g.restore();
}

function drawBoxLights(t){
  const pulse=.78+.22*Math.sin(t*2.6),ph=t*.42;
  g.save();g.globalCompositeOperation='screen';
  glow(WIN.x,WIN.y,210,lightCol(ph,.26*pulse),lightCol(ph,0));
  glow(HOP.x,HOP.y-6,90,lightCol(ph+2,.4*pulse),lightCol(ph+2,0));
  glow(584,708,44,lightCol(ph+1,.5),lightCol(ph+1,0));
  g.restore();
  // the window: slow swirl of coloured light, painted as short arcs
  g.save();g.beginPath();g.arc(WIN.x,WIN.y,WIN.r-1,0,TAU);g.clip();g.globalCompositeOperation='screen';
  for(let k=0;k<3;k++){const a=t*.7+k*TAU/3;glow(WIN.x+Math.cos(a)*18,WIN.y+Math.sin(a)*18,44,lightCol(ph+k*1.7,.75*pulse),lightCol(ph+k*1.7,0));}
  g.lineCap='round';
  for(let k=0;k<34;k++){const rr=5+(k*37%41),a=k*2.4+t*(.7+(k%3)*.35)*(k%2?1:-1);g.strokeStyle=lightCol(ph+k*.31,.5+.3*Math.sin(k+t*2));g.lineWidth=1.6+(k%4);g.beginPath();g.arc(WIN.x,WIN.y,rr,a,a+.35+(k%5)*.08);g.stroke();}
  glow(WIN.x,WIN.y,16,`rgba(255,250,235,${.6*pulse})`,'rgba(255,250,235,0)');
  g.restore();
  g.save();g.strokeStyle='rgba(255,252,240,.35)';g.lineWidth=2.4;g.lineCap='round';g.beginPath();g.arc(WIN.x,WIN.y,WIN.r-7,PI*1.12,PI*1.42);g.stroke();g.restore();
  seedDyn(63);pencil(g,E(WIN.x,WIN.y,WIN.r,WIN.r),true,1,.45);
  // chasing bulbs
  BULBS.forEach(([x,y],i)=>{const v=clamp(1-(((t*3.2-i)%5+5)%5)/2.2,0,1);if(v<=0)return;g.save();g.globalCompositeOperation='screen';glow(x,y,22,lightCol(i+ph,.75*v),lightCol(i+ph,0));g.restore();g.fillStyle=lightCol(i+ph,.55+.4*v);g.beginPath();g.arc(x,y,5.5,0,TAU);g.fill();});
  // the dial twitches
  const da=-PI/2+Math.sin(t*1.7)*.9+Math.sin(t*9)*.08;g.strokeStyle='hsla(28,12%,14%,.85)';g.lineWidth=1.4;g.beginPath();g.moveTo(416,792);g.lineTo(416+Math.cos(da)*10,792+Math.sin(da)*10);g.stroke();
}

function sparkles(t){
  const r=rng(SEED+500);g.save();g.lineCap='round';
  for(let i=0;i<22;i++){
    const bx=i<15?360+r()*260:560+r()*300,by=i<15?470+r()*380:670+r()*180,per=1.6+r()*2.4,off=r(),p=(t/per+off)%1,s=Math.sin(p*PI)*(4+r()*6),a=t*.4+i;
    if(s<.6)continue;
    g.strokeStyle=i%3?`rgba(255,248,226,${.85*Math.sin(p*PI)})`:lightCol(i+t*.3,.9*Math.sin(p*PI));g.lineWidth=1.3;
    g.beginPath();for(let k=0;k<4;k++){const an=a+k*PI/2,l=k%2?s*.55:s;g.moveTo(bx,by-p*8);g.lineTo(bx+Math.cos(an)*l,by-p*8+Math.sin(an)*l);}g.stroke();
  }
  g.restore();
}

/* film tape: a ribbon along a bezier, sprocket holes and frames sliding along it */
function strip(B,wd,phase,k,N=30){
  const pts=[],len=[0];
  for(let i=0;i<=N;i++){pts.push(bez(B[0],B[1],B[2],B[3],i/N));if(i)len.push(len[i-1]+Math.hypot(pts[i][0]-pts[i-1][0],pts[i][1]-pts[i-1][1]));}
  const nrm=i=>{const a=pts[Math.max(0,i-1)],b=pts[Math.min(N,i+1)],an=Math.atan2(b[1]-a[1],b[0]-a[0]);return an;};
  const L=[],Rr=[];for(let i=0;i<=N;i++){const an=nrm(i)+PI/2;L.push([pts[i][0]+Math.cos(an)*wd/2,pts[i][1]+Math.sin(an)*wd/2]);Rr.push([pts[i][0]-Math.cos(an)*wd/2,pts[i][1]-Math.sin(an)*wd/2]);}
  g.fillStyle='hsla(28,12%,13%,.97)';trace(g,L.concat(Rr.slice().reverse()));g.fill();
  const total=len[N],step=11;let j=0,fi=Math.floor(phase/step);
  for(let s=step-(phase%step);s<total-2;s+=step,fi--){
    while(j<N-1&&len[j+1]<s)j++;
    const f=(s-len[j])/(len[j+1]-len[j]||1),px=lerp(pts[j][0],pts[j+1][0],f),py=lerp(pts[j][1],pts[j+1][1],f),an=nrm(j);
    g.save();g.translate(px,py);g.rotate(an);
    g.fillStyle=`hsla(${38+((fi%5)+5)%5*4},34%,${66+(((fi%3)+3)%3)*7}%,.8)`;g.fillRect(-4,-wd*.25,8,wd*.5);
    g.fillStyle='hsla(42,30%,86%,.8)';g.fillRect(-3.4,-wd*.44,1.8,1.8);g.fillRect(1.6,-wd*.44,1.8,1.8);g.fillRect(-3.4,wd*.44-1.8,1.8,1.8);g.fillRect(1.6,wd*.44-1.8,1.8,1.8);
    g.restore();
  }
  seedDyn(k);pencil(g,L,false,.9,.5);pencil(g,Rr,false,.9,.5);
}
function reel(o,ang,k){
  seedDyn(k);
  paint(g,E(o.x,o.y,o.r,o.r),C.film,{den:30,len:8,w:3,wob:3,dir:ang});
  g.save();g.translate(o.x,o.y);g.rotate(ang);
  g.strokeStyle=hsl(C.tin,.95);g.lineCap='round';g.lineWidth=o.r*.26;
  for(let i=0;i<3;i++){const a=i*TAU/3;g.beginPath();g.moveTo(0,0);g.lineTo(Math.cos(a)*o.r*.86,Math.sin(a)*o.r*.86);g.stroke();}
  g.lineWidth=3;g.beginPath();g.arc(0,0,o.r-1.5,0,TAU);g.stroke();
  g.fillStyle=hsl(C.brassD);g.beginPath();g.arc(0,0,o.r*.2,0,TAU);g.fill();
  g.strokeStyle='hsla(40,30%,84%,.5)';g.lineWidth=1;for(let i=0;i<3;i++){const a=i*TAU/3+.12;g.beginPath();g.moveTo(Math.cos(a)*6,Math.sin(a)*6);g.lineTo(Math.cos(a)*o.r*.8,Math.sin(a)*o.r*.8);g.stroke();}
  g.restore();
  pencil(g,E(o.x,o.y,o.r,o.r),true,1,.5);
}

/* the stream of screenplays */
const NPAGES = 78;
function drawStream(t){
  // pencil speed-lines along the current
  g.save();g.lineCap='round';g.setLineDash([30,44]);
  for(let k=-1;k<=1;k++){g.lineDashOffset=-t*95+k*17;g.strokeStyle=`hsla(28,12%,18%,${.16+.05*k})`;g.lineWidth=1;g.beginPath();g.moveTo(STREAM[0][0],STREAM[0][1]+k*44);g.bezierCurveTo(STREAM[1][0],STREAM[1][1]+k*40,STREAM[2][0],STREAM[2][1]+k*22,STREAM[3][0],STREAM[3][1]-4);g.stroke();}
  g.restore();
  const items=[];
  for(let i=0;i<NPAGES;i++){const lane=i%3-1,u=((t*.05+i/NPAGES+lane*.011+Math.sin(i*12.9)*.012)%1+1)%1;items.push([u,i,lane]);}
  items.sort((a,b)=>b[0]-a[0]);
  for(const[u,i,lane]of items){
    const p=bez(...STREAM,u),an=bezTan(...STREAM,u),conv=Math.pow(1-u,.8);
    const off=(lane*38+Math.sin(u*10+t*1.4+i*1.3)*10)*conv,x=p[0]+Math.cos(an+PI/2)*off,y=p[1]+Math.sin(an+PI/2)*off;
    const sc=lerp(1.15,.42,Math.pow(u,1.6)),al=u>.93?clamp((1-u)/.07,0,1):1;
    g.save();g.globalAlpha=al;g.translate(x,y);g.rotate(an*.6+Math.sin(t*1.6+i*2.1)*.38+(i%5-2)*.12);
    g.scale(sc,sc*(.72+.28*Math.cos(t*2.1+i*1.7)));
    g.drawImage(PAGE[i%3][(boil+i)%VARIANTS],-20,-26);g.restore();
  }
}

/* prompts: written on the desk, then they fly to the hopper */
const CYCLE = 2.5, WRITE = 1.75, FLY = 1.7;
const CARDPOLY = [[256,800],[308,800],[314,824],[250,824]];
function drawDeskCard(t){
  const cyc=t%CYCLE,prog=clamp(cyc/WRITE,0,1);
  let alpha=cyc<WRITE?clamp(cyc/.2,0,1):0;
  if(alpha>0){
    g.save();g.globalAlpha=alpha;seedDyn(70);
    paint(g,CARDPOLY,C.card,{dir:0,len:8,w:3,den:20,la:.55,lw:.9});
    g.lineCap='round';g.strokeStyle=hsl([178,30,34],.85);g.lineWidth=1.4;g.beginPath();g.moveTo(259,804);g.lineTo(262.5,806.5);g.lineTo(259,809);g.stroke();
    for(let li=0;li<3;li++){const f=clamp(prog*3-li,0,1);if(f<=0)break;const x0=li?260-li:266,x1=x0+(li===2?26:38)*f,y=806+li*6;g.strokeStyle='hsla(28,12%,18%,.7)';g.lineWidth=1;g.beginPath();g.moveTo(x0,y);for(let xx=x0+3;xx<=x1;xx+=3)g.lineTo(xx,y+Math.sin(xx*1.9+li)*1.1);g.stroke();}
    g.restore();
  }
  // where the pencil tip is
  if(cyc<WRITE){const li=Math.min(2,Math.floor(prog*3)),f=prog*3-li,x0=li?260-li:266;return[x0+(li===2?26:38)*f+Math.sin(t*31)*1.2,806+li*6+Math.sin(t*43)*1.3];}
  const back=ease((cyc-WRITE)/(CYCLE-WRITE));return[lerp(286,266,back),806+12*(1-back)-Math.sin(back*PI)*16];
}
function drawFlyingCards(t){
  const k0=Math.floor(t/CYCLE);
  for(let k=k0;k>=k0-1;k--){
    const fp=(t-k*CYCLE-WRITE)/FLY;if(k<0||fp<0||fp>1)continue;
    const u=ease(fp),p=bez(...CARDPATH,u),sc=lerp(1.5,.5,Math.pow(u,1.5)),al=u>.93?clamp((1-u)/.07,0,1):1;
    g.save();g.globalAlpha=al;g.translate(p[0],p[1]);g.rotate(Math.sin(fp*7+k)*.5*(1-u*.4)+u*.7);g.scale(sc,sc*(.75+.25*Math.cos(fp*9)));
    g.drawImage(CARD[(boil+k)%VARIANTS],-20,-15);g.restore();
    // tiny trailing pencil ticks
    g.save();g.strokeStyle='hsla(28,12%,18%,.3)';g.lineWidth=.9;g.lineCap='round';for(let j=1;j<4;j++){const q=bez(...CARDPATH,Math.max(0,u-j*.035));g.beginPath();g.moveTo(q[0]-3,q[1]+4+j);g.lineTo(q[0]+3,q[1]+7+j);g.stroke();}g.restore();
  }
}
function hopperFront(){ // re-lay the hopper's front lip so paper drops *into* it
  g.save();g.beginPath();const arc=E(HOP.x,HOP.y,HOP.rx,HOP.ry,0,PI);g.moveTo(arc[0][0],arc[0][1]);for(const p of arc)g.lineTo(p[0],p[1]);g.lineTo(428,566);g.lineTo(500,566);g.closePath();g.clip();
  g.drawImage(STATIC[boil],380+BX,490,170,80,380,490,170,80);g.restore();
}

function drawRobot(t,tip){
  const cyc=t%CYCLE,writing=cyc<WRITE;
  // head: tilts toward the page, glances up at the stream between prompts
  const tilt=.05+Math.sin(t*1.1)*.025+(writing?.03:-.09*Math.sin((cyc-WRITE)/(CYCLE-WRITE)*PI)),bobY=Math.sin(t*2.3)*1.1;
  g.save();g.translate(NECK[0],NECK[1]+bobY);g.rotate(tilt);g.translate(-NECK[0],-NECK[1]);
  g.drawImage(HEAD[boil],90,565);
  const blink=(t%4.3)<.13?.15:1;
  for(const ex of[163,203]){
    g.save();g.globalCompositeOperation='screen';glow(ex,646,20,'rgba(255,214,140,.55)','rgba(255,214,140,0)');g.restore();
    g.fillStyle='hsla(42,70%,74%,.95)';g.beginPath();g.ellipse(ex,646,8.5,8.5*blink,0,0,TAU);g.fill();
    g.fillStyle='hsla(30,20%,14%,.9)';g.beginPath();g.ellipse(ex+(writing?2.5:1.5),646+(writing?3:-3)*blink,3.2,3.2*blink,0,0,TAU);g.fill();
  }
  g.restore();
  // chest lamp
  const lv=.5+.5*Math.sin(t*5);g.save();g.globalCompositeOperation='screen';glow(194,750,12,`rgba(255,200,130,${.6*lv})`,'rgba(255,200,130,0)');g.restore();
  // writing arm (two-bone IK to the pencil tip)
  const hand=[tip[0]+7,tip[1]-11],el=ik(SHOULDER,hand,54,58,1);
  seedDyn(71);limb(g,SHOULDER[0],SHOULDER[1],el[0],el[1],18,16,C.steel,{den:22});
  seedDyn(72);limb(g,el[0],el[1],hand[0],hand[1],16,13,C.steel,{den:22});
  seedDyn(73);paint(g,E(el[0],el[1],9,9),C.brassD,{den:12,len:4,w:2,wob:3});
  seedDyn(74);limb(g,tip[0]+13,tip[1]-30,tip[0]+1.5,tip[1]-3,4.5,4,[44,58,56],{den:10,lw:.7});
  g.fillStyle='hsla(28,12%,14%,.9)';g.beginPath();g.moveTo(tip[0],tip[1]);g.lineTo(tip[0]+3.5,tip[1]-3.2);g.lineTo(tip[0]-.4,tip[1]-4.6);g.fill();
  seedDyn(75);paint(g,E(hand[0],hand[1],9,8),C.brassD,{den:12,len:4,w:2,wob:3});
  seedDyn(76);paint(g,E(SHOULDER[0],SHOULDER[1],12,12),C.brassD,{den:14,len:5,w:2,wob:3});
}

function kliegGlow(t){
  const[kx,ky]=KLIEG,fl=.85+.15*Math.sin(t*7.3)*Math.sin(t*3.1);
  g.save();g.globalCompositeOperation='screen';
  glow(kx-9,ky+8,60,`rgba(255,236,190,${.6*fl})`,'rgba(255,236,190,0)');
  const gr=g.createLinearGradient(kx-9,ky+8,170,640);gr.addColorStop(0,`rgba(255,236,190,${.2*fl})`);gr.addColorStop(1,'rgba(255,236,190,0)');
  g.fillStyle=gr;g.beginPath();g.moveTo(kx-26,ky+2);g.lineTo(60,640);g.lineTo(290,660);g.lineTo(kx+8,ky+26);g.fill();
  g.restore();
}

function drawNotes(t){ // the player piano: keys dip, notes drift up
  g.save();g.lineCap='round';
  for(let k=0;k<3;k++){const key=Math.floor(rng(SEED+Math.floor(t*3.5)*31+k)()*23);g.fillStyle='hsla(28,12%,16%,.4)';g.fillRect(1596+key*6+.8,803,4.6,8);}
  for(let i=0;i<5;i++){const p=(t*.2+i/5)%1,x=1650+Math.sin(p*6+i*2)*22+i*9,y=698-p*150,a=Math.sin(p*PI)*.65;g.strokeStyle=g.fillStyle=`hsla(28,12%,16%,${a})`;g.lineWidth=1.4;g.beginPath();g.ellipse(x,y,4.2,3.2,-.4,0,TAU);g.fill();g.beginPath();g.moveTo(x+3.8,y-1);g.lineTo(x+3.8,y-15);if(i%2)g.lineTo(x+9,y-11);g.stroke();}
  g.restore();
}

/* --------------------------------------------------------------- a frame */
function frame(t,n){
  boil=Math.floor(t*7)%VARIANTS;D=rng(SEED+n*7919);
  g.drawImage(STATIC[boil],0,0);
  at(g,RX,()=>kliegGlow(t));
  g.save();g.globalCompositeOperation='screen';const f2=.85+.15*Math.sin(t*6.1+2)*Math.sin(t*2.7);glow(KLIEG2[0]+9,KLIEG2[1]+8,64,`rgba(255,236,190,${.6*f2})`,'rgba(255,236,190,0)');g.restore();
  const fl=drawFilm(t);
  drawBeam(t,fl);
  at(g,BX,()=>drawBoxLights(t));
  strip(TAPE,15,t*46,80,46);
  at(g,PX,()=>{
    strip([[690,726],[696,738],[700,748],[704,760]],13,t*46,81);
    strip([[764,790],[778,800],[790,796],[794,786]],13,t*46,82);
    reel(REEL1,t*1.5,83);reel(REEL2,-t*1.9,84);
  });
  drawStream(t);
  drawFlyingCards(t);
  at(g,BX,()=>{
    hopperFront();
    g.save();g.globalCompositeOperation='screen';glow(HOP.x,HOP.y+2,54,lightCol(t*.42+2,.45+.2*Math.sin(t*2.6)),lightCol(t*.42+2,0));g.restore();
  });
  at(g,RX,()=>drawRobot(t,drawDeskCard(t)));
  at(g,BX,()=>sparkles(t));
  drawNotes(t);
  g.save();g.globalCompositeOperation='multiply';g.drawImage(GRAIN,0,0);g.restore();
  g.drawImage(FRAME,0,0);
}

/* ------------------------------------------------- ~45 fps, time-based loop */
const STEP = 1000/FPS;let last = 0, n = 0, t0 = null, seen = true;
new IntersectionObserver(([e]) => { seen = e.isIntersecting; }).observe(cv);   // rest while scrolled away
function tick(now){
  requestAnimationFrame(tick);
  if(!seen)return;
  if(t0===null){t0=now;last=now-STEP;}
  if(now-last<STEP-.5)return;
  last+=STEP;if(now-last>STEP*4)last=now;      // don't try to catch up after a hidden tab
  frame((now-t0)/1000+3,n++);
}
window.__frame = frame;                          // handy for stills: __frame(seconds, frameIndex)
if(matchMedia('(prefers-reduced-motion: reduce)').matches)frame(3.6,0);else requestAnimationFrame(tick);
})();
