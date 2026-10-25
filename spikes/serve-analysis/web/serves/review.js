import {TossReviewer} from './toss.js';
const $=id=>document.getElementById(id);
const labels={candidate:'Unreviewed',confirmed:'Confirmed',review_needed:'Needs review',rejected:'False detection'};
let session,events=[],selected=null,videos=[],storageKey,duration=1,tossReviewer;
const fmt=t=>`${Number(t).toFixed(3)} s`;
function current(){return Math.max(0,(videos[0]?.currentTime||0)-(session?.views[0]?.source_offset_seconds||0));}
function persist(){localStorage.setItem(storageKey,JSON.stringify(events));render();}
function seek(time){const t=Math.max(0,Math.min(duration,time));for(let i=0;i<videos.length;i++)videos[i].currentTime=Math.max(0,t+session.views[i].source_offset_seconds);$('timeline').value=t;updateClock();}
function pause(){videos.forEach(v=>v.pause());$('play').textContent='Play';}
function updateClock(){if(!session)return;const t=current();$('time').textContent=fmt(t);$('timeline').value=t;videos.forEach((v,i)=>{document.querySelector(`[data-clock="${i}"]`).textContent=fmt(v.currentTime);});}
function select(id){selected=events.find(e=>e.serve_id===id);pause();if(selected)seek(Math.max(0,selected.time_seconds-1.5));render();}
function review(status){if(!selected)return;selected.event_status=status;selected.reviewed_at=new Date().toISOString();selected.review_source='human';selected.revision=(selected.revision||1)+1;persist();}
function render(){
  $('count').textContent=events.length;$('events').replaceChildren();
  const filter=$('filter').value;const visible=events.filter(e=>filter==='all'||e.event_status===filter);
  for(const event of visible){const button=document.createElement('button');button.className=`event ${selected?.serve_id===event.serve_id?'selected':''}`;
    const row=document.createElement('span');row.className='row';const stamp=document.createElement('span');stamp.className='stamp';stamp.textContent=fmt(event.time_seconds);
    const state=document.createElement('span');state.className=`status ${event.event_status}`;state.textContent=labels[event.event_status]||event.event_status;row.append(stamp,state);
    const meta=document.createElement('span');meta.className='meta';meta.textContent=`${session.players[event.player_id]||'Player uncertain'} · ${event.supporting_views.length} view${event.supporting_views.length===1?'':'s'}`;button.append(row,meta);button.onclick=()=>select(event.serve_id);$('events').append(button);}
  if(!visible.length){const e=document.createElement('p');e.className='empty';e.textContent='No events in this filter. Add a missed serve from the timeline.';$('events').append(e);}
  $('edit').hidden=!selected;
  $('eventTitle').textContent=selected?`${session.players[selected.player_id]||'Player uncertain'} · ${fmt(selected.time_seconds)}`:'Choose a candidate';
  $('eventDetail').textContent=selected?`${labels[selected.event_status]||selected.event_status}. ${selected.supporting_views.join(' + ')||'Manually added'}. ${selected.score==null?'Manual event':`Model score ${selected.score.toFixed(3)} (uncalibrated)`}.`:'Select a candidate to inspect both source views.';
  $('player').value=selected?.player_id||'';
  tossReviewer?.render();
}
async function load(){
  const response=await fetch('serves.json');if(!response.ok)throw Error('Could not load serves.json');session=await response.json();
  if(session.demo_video){$('demoVideo').href=session.demo_video;$('demoVideo').hidden=false;}
  const fingerprint=session.views.map(v=>[v.video,v.source_size_bytes,v.source_mtime_ns]);storageKey=`trophy-serves-v1:${session.session_id}:${session.model.sha256}:${JSON.stringify(fingerprint)}`;
  let saved;try{saved=JSON.parse(localStorage.getItem(storageKey));}catch{}events=Array.isArray(saved)?saved:structuredClone(session.events);
  $('title').textContent=session.title;$('sync').textContent=`Camera timing: ${session.synchronization_status.replaceAll('_',' ')}. Inspect source timestamps when reviewing a close event.`;
  $('diagnostics').textContent=JSON.stringify({model:session.model,views:session.views,threshold:session.threshold,processing_seconds:session.processing_seconds,limitations:session.limitations},null,2);
  const unknown=document.createElement('option');unknown.value='';unknown.textContent='Uncertain';$('player').append(unknown);
  for(const [id,name]of Object.entries(session.players)){const option=document.createElement('option');option.value=id;option.textContent=name;$('player').append(option);}
  duration=Math.max(.01,Math.min(...session.views.map(v=>v.analyzed_until_seconds-v.source_offset_seconds)));$('timeline').max=duration;
  for(const [i,view]of session.views.entries()){
    const card=document.createElement('div');card.className='video-card';const video=document.createElement('video');video.src=view.review_url||`media/${i}`;video.preload='metadata';video.playsInline=true;video.muted=true;
    video.addEventListener('error',()=>{$('sync').textContent+=' This browser cannot decode one source; use the optional H.264 review-video export.';},{once:true});
    const viewport=document.createElement('div');viewport.className='video-viewport';
    const stage=document.createElement('div');stage.className='video-stage';stage.append(video);viewport.append(stage);
    if(video.requestVideoFrameCallback){const onFrame=(_now,meta)=>{video.presentedFramePTS=meta.mediaTime;video.requestVideoFrameCallback(onFrame);};video.requestVideoFrameCallback(onFrame);}
    const caption=document.createElement('div');caption.className='video-label';const title=document.createElement('strong');title.textContent=view.id;const clock=document.createElement('span');clock.dataset.clock=i;clock.textContent='0.000 s';
    const zoom=document.createElement('select');zoom.setAttribute('aria-label',`${view.id} crop`);
    for(const [value,label]of [['full','Full view'],['left','Left player'],['right','Right player']]){const option=document.createElement('option');option.value=value;option.textContent=label;zoom.append(option);}
    zoom.style.fontSize='10px';zoom.style.padding='2px';zoom.onchange=()=>{stage.style.transform=zoom.value==='full'?'none':'scale(2)';stage.style.transformOrigin=zoom.value==='left'?'25% 55%':'75% 55%';};
    caption.append(title,zoom,clock);card.append(viewport,caption);$('videos').append(card);videos.push(video);
  }
  tossReviewer=new TossReviewer({session,videos,getSelected:()=>selected,persist,pause,seek});
  await tossReviewer.load();
  $('timeline').oninput=e=>{pause();seek(Number(e.target.value));};
  $('play').onclick=async()=>{if(!videos[0].paused){pause();return;}for(let i=1;i<videos.length;i++)videos[i].currentTime=current()+session.views[i].source_offset_seconds;try{await Promise.all(videos.map(v=>v.play()));$('play').textContent='Pause';}catch(error){pause();$('sync').textContent=error.message;}};
  $('speed').onchange=()=>videos.forEach(v=>v.playbackRate=Number($('speed').value));
  $('backFrame').onclick=()=>{pause();seek(current()-1/60);};$('nextFrame').onclick=()=>{pause();seek(current()+1/60);};
  $('previous').onclick=()=>{const prior=events.filter(e=>e.time_seconds<(selected?.time_seconds??current())-.01).at(-1);if(prior)select(prior.serve_id);};
  $('next').onclick=()=>{const next=events.find(e=>e.time_seconds>(selected?.time_seconds??current())+.01);if(next)select(next.serve_id);};
  $('confirm').onclick=()=>review('confirmed');$('uncertain').onclick=()=>review('review_needed');$('reject').onclick=()=>review('rejected');
  $('player').onchange=()=>{if(selected){selected.player_id=$('player').value||null;selected.revision++;persist();}};
  $('setTime').onclick=()=>{if(selected){selected.time_seconds=current();selected.contact_interval_seconds=null;selected.contact_interval_status='human_adjusted';delete selected.toss_evidence;selected.revision++;events.sort((a,b)=>a.time_seconds-b.time_seconds);persist();}};
  $('add').onclick=()=>{const event={serve_id:`${session.session_id}/manual/${crypto.randomUUID()}`,time_seconds:current(),player_id:null,event_status:'review_needed',supporting_views:[],evidence:[],score:null,release_interval_seconds:null,measurement_status:'release_not_measured',fault_decision:null,review_source:'human',revision:1};events.push(event);events.sort((a,b)=>a.time_seconds-b.time_seconds);selected=event;persist();};
  $('filter').onchange=render;
  $('reset').onclick=()=>{pause();events=structuredClone(session.events);selected=events[0]||null;persist();if(selected)seek(Math.max(0,selected.time_seconds-1.5));};
  $('export').onclick=()=>{const data={...session,events,review_exported_at:new Date().toISOString()};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='reviewed-serves.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  videos[0].addEventListener('timeupdate',()=>{if(current()>=duration)pause();if(!videos[0].paused)for(let i=1;i<videos.length;i++){const target=current()+session.views[i].source_offset_seconds;if(Math.abs(videos[i].currentTime-target)>.1)videos[i].currentTime=target;}updateClock();});
  render();if(events.length)select(events[0].serve_id);
}
load().catch(error=>{$('error').hidden=false;$('error').textContent=`Serve review could not open: ${error.message}`;});
