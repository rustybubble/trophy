// Pure analysis functions shared by the local UI and Node verification.
// Events are estimates from reconstructed ball centres, never confirmed labels.
export const DEFAULTS=Object.freeze({names:['Blue','Orange'],negativePlayer:0,start:0,end:null,upToPlayhead:false,
  bandwidthCm:12,depthBins:3,widthBins:3,mode:'both',palette:'ember',sharedScale:true,opacity:.85,
  playerPerspective:true,minScore:.65,maxHeightCm:8,minVerticalSpeed:.35,minLongitudinalSpeed:.6,
  minSeparation:.18,maxGap:.06,includeOwnSide:false,confirmedOnly:false,showReplay:false});

export function lineFit(points,value){
  if(points.length<2)return null;
  const origin=points.reduce((s,p)=>s+p.time,0)/points.length;
  const mean=points.reduce((s,p)=>s+value(p),0)/points.length;
  let variance=0,covariance=0;
  for(const p of points){const dt=p.time-origin;variance+=dt*dt;covariance+=dt*(value(p)-mean)}
  if(variance<1e-12)return null;
  const slope=covariance/variance;
  return {slope,at:t=>mean+slope*(t-origin)};
}

export function estimateBounces(scene,settings={}){
  const cfg={...DEFAULTS,...settings},table=scene.table??{length:2.74,width:1.525,height:.76};
  const samples=scene.frames.filter(f=>Array.isArray(f.ball?.position)&&f.ball.position.length===3&&f.ball.position.every(Number.isFinite))
    .map(f=>({time:f.time,position:f.ball.position,score:f.ball.score??0,frame:f.frame_index}));
  const events=[];const contactHeight=table.height+.02;
  for(let i=1;i<samples.length-1;i++){
    const p=samples[i],z=p.position[2];
    if(z>samples[i-1].position[2]||z>samples[i+1].position[2]||
       (z===samples[i-1].position[2]&&z===samples[i+1].position[2]))continue;
    const pre=samples.filter(q=>q.time>=p.time-.100001&&q.time<=p.time);
    const post=samples.filter(q=>q.time>=p.time&&q.time<=p.time+.100001);
    if(pre.length<3||post.length<3)continue;
    const support=[...pre,...post.slice(1)];
    const gap=Math.max(...support.slice(1).map((q,j)=>q.time-support[j].time));
    if(gap>cfg.maxGap+1e-8)continue;
    const incoming=lineFit(pre,q=>q.position[2]),outgoing=lineFit(post,q=>q.position[2]);
    if(incoming.slope>-cfg.minVerticalSpeed||outgoing.slope<cfg.minVerticalSpeed)continue;
    const correction=(outgoing.at(p.time)-incoming.at(p.time))/(incoming.slope-outgoing.slope);
    if(!Number.isFinite(correction)||Math.abs(correction)>.04)continue;
    const time=p.time+correction,height=(incoming.at(time)+outgoing.at(time))/2;
    if(Math.abs(height-contactHeight)>cfg.maxHeightCm/100)continue;
    const nearby=support.filter(q=>Math.abs(q.time-time)<=.065);
    const fitX=lineFit(nearby,q=>q.position[0]),fitY=lineFit(nearby,q=>q.position[1]);
    if(!fitX||!fitY)continue;
    const x=fitX.at(time),y=fitY.at(time);
    if(Math.abs(x)>table.length/2+.02||Math.abs(y)>table.width/2+.02)continue;
    const vx=lineFit(pre,q=>q.position[0]).slope;
    let sourceSide=Math.abs(vx)>=cfg.minLongitudinalSpeed?-Math.sign(vx):null;
    const previous=events.at(-1),since=previous?.time??p.time-1.5;
    const serveContinuation=sourceSide!==null&&previous?.sourceSide===sourceSide&&previous?.kind==='own_side';
    const originSupported=sourceSide!==null&&samples.some(q=>q.time>=since&&q.time<time-.04&&q.position[0]*sourceSide>table.length*.4);
    // A net rebound or repeated table bounce is not a new player's shot. The
    // ball must have returned to that player's end (except a serve continuation).
    if(!originSupported&&!serveContinuation)sourceSide=null;
    const landingSide=Math.abs(x)>.025?Math.sign(x):0;
    const kind=sourceSide===null?'unassigned':landingSide===0?'near_net':landingSide===sourceSide?'own_side':'target';
    const shooter=sourceSide===null?null:sourceSide<0?cfg.negativePlayer:1-cfg.negativePlayer;
    const score=Math.min(...support.map(q=>q.score));
    const event={id:`bounce-${p.frame}`,frame_index:p.frame,time,x,y,height,score,shooter,sourceSide,kind,
      status:'estimated',included:true,method:'table-height vertical-velocity reversal',
      evidence:{incoming_vertical_m_s:incoming.slope,outgoing_vertical_m_s:outgoing.slope,
        incoming_longitudinal_m_s:vx,table_height_error_cm:Math.abs(height-contactHeight)*100,
        largest_support_gap_seconds:gap,shot_origin_supported:originSupported||serveContinuation,support_frames:support.map(q=>q.frame)}};
    const last=events.at(-1);
    if(last&&event.time-last.time<cfg.minSeparation){
      if(event.evidence.table_height_error_cm<last.evidence.table_height_error_cm)events[events.length-1]=event;
    }else events.push(event);
  }
  return events;
}

export function applyReviews(estimated,reviews={},manual=[]){
  return [...estimated.map(event=>({...event,...(reviews[event.id]??{}),id:event.id,evidence:event.evidence})),...manual]
    .sort((a,b)=>a.time-b.time);
}

export function filterEvents(events,settings,duration,playhead=duration){
  const end=Math.min(settings.end??duration,settings.upToPlayhead?playhead:duration);
  return events.filter(e=>e.included!==false&&e.status!=='ignored'&&e.time>=settings.start&&e.time<=end&&
    (e.status==='confirmed'||e.status==='manual'||e.score>=settings.minScore)&&
    (!settings.confirmedOnly||e.status==='confirmed'||e.status==='manual')&&
    (settings.includeOwnSide||e.kind==='target'||e.status==='manual')&&
    (e.shooter===0||e.shooter===1));
}

export function playerCoordinates(event,player,settings){
  const sourceSide=player===settings.negativePlayer?-1:1;
  const sign=settings.playerPerspective?-sourceSide:1;
  return {x:event.x*sign,y:event.y*sign};
}

export function zoneFor(event,player,settings,table){
  const sourceSide=player===settings.negativePlayer?-1:1;
  const x=-sourceSide*event.x,y=-sourceSide*event.y;
  const side=x>=0?'opponent':'own';
  const depth=Math.min(settings.depthBins-1,Math.max(0,Math.floor(Math.abs(x)/(table.length/2)*settings.depthBins)));
  const lane=Math.min(settings.widthBins-1,Math.max(0,Math.floor((table.width/2-y)/table.width*settings.widthBins)));
  const depthName=settings.depthBins===3?['short','middle','deep'][depth]:`depth ${depth+1}`;
  const laneName=settings.widthBins===3?['left','centre','right'][lane]:`lane ${lane+1}`;
  return {side,depth,lane,key:`${side}:${depth}:${lane}`,label:`${side==='opponent'?'Target':'Own side'} · ${depthName} · ${laneName}`};
}

export function summarize(events,player,settings,table){
  const chosen=events.filter(e=>e.shooter===player),zones=new Map();
  for(const e of chosen){const zone=zoneFor(e,player,settings,table);const row=zones.get(zone.key)??{...zone,count:0};row.count++;zones.set(zone.key,row)}
  const ordered=[...zones.values()].sort((a,b)=>b.count-a.count);
  return {count:chosen.length,estimated:chosen.filter(e=>e.status==='estimated').length,
    reviewed:chosen.filter(e=>e.status==='confirmed'||e.status==='manual').length,zones:ordered,
    topZones:ordered.filter(z=>z.count===ordered[0]?.count)};
}

export function densityGrid(events,player,settings,table,width=120,height=68){
  const values=new Float32Array(width*height),sigma=settings.bandwidthCm/100;
  const points=events.filter(e=>e.shooter===player).map(e=>playerCoordinates(e,player,settings));
  let max=0;
  for(let row=0;row<height;row++)for(let col=0;col<width;col++){
    const x=(col+.5)/width*table.length-table.length/2,y=table.width/2-(row+.5)/height*table.width;
    let sum=0;
    for(const p of points)sum+=Math.exp(-((x-p.x)**2+(y-p.y)**2)/(2*sigma*sigma));
    values[row*width+col]=sum;max=Math.max(max,sum);
  }
  return {values,max,width,height};
}

export function validatePreset(input,duration){
  if(input?.schema_version!==1||!input.settings||typeof input.settings!=='object')throw Error('Choose a Trophy placement preset (schema version 1).');
  const s={...DEFAULTS,...input.settings},number=(key,min,max)=>{if(!Number.isFinite(s[key])||s[key]<min||s[key]>max)throw Error(`Invalid ${key}`)};
  for(const [key,min,max] of [['negativePlayer',0,1],['bandwidthCm',4,35],['depthBins',1,8],['widthBins',1,6],['opacity',.2,1],['minScore',0,1],['maxHeightCm',2,20],['minVerticalSpeed',.1,2],['minLongitudinalSpeed',.1,3],['minSeparation',.1,.5],['maxGap',.02,.12]])number(key,min,max);
  for(const key of ['negativePlayer','depthBins','widthBins'])if(!Number.isInteger(s[key]))throw Error(`Invalid ${key}`);
  if(!['density','zones','both'].includes(s.mode)||!['ember','ocean','trophy'].includes(s.palette))throw Error('Unknown heatmap style');
  if(!Array.isArray(s.names)||s.names.length!==2||s.names.some(n=>typeof n!=='string'||!n.trim()||n.length>40))throw Error('Use two player names of 1–40 characters.');
  for(const key of ['upToPlayhead','sharedScale','playerPerspective','includeOwnSide','confirmedOnly','showReplay'])if(typeof s[key]!=='boolean')throw Error(`Invalid ${key}`);
  if(!Number.isFinite(s.start)||s.start<0)throw Error('Invalid start time');
  if(s.end!==null&&(!Number.isFinite(s.end)||s.end<s.start))throw Error('Invalid end time');
  s.start=Math.min(s.start,duration);s.end=Math.min(s.end??duration,duration);
  return s;
}

export function validateReview(event,duration,table){
  if(!event||typeof event!=='object')throw Error('Invalid contact review');
  for(const [key,min,max] of [['time',0,duration],['x',-table.length/2,table.length/2],['y',-table.width/2,table.width/2]])if(!Number.isFinite(event[key])||event[key]<min||event[key]>max)throw Error(`Invalid contact ${key}`);
  if(![0,1,null].includes(event.shooter)||!['estimated','confirmed','ignored','manual'].includes(event.status)||typeof event.included!=='boolean')throw Error('Invalid contact status or player');
  return event;
}
