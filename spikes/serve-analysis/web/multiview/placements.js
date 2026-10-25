import {DEFAULTS,estimateBounces,applyReviews,filterEvents,summarize,densityGrid,playerCoordinates,zoneFor,validatePreset,validateReview} from './placements-core.js?v=placements-5';

const PALETTES={ember:[[.12,[87,38,128]],[.4,[221,65,84]],[.72,[255,151,64]],[1,[255,238,149]]],
 ocean:[[.12,[29,65,150]],[.45,[30,157,209]],[.75,[67,221,205]],[1,[205,255,214]]],
 trophy:[[.12,[31,92,82]],[.45,[58,158,117]],[.75,[146,220,139]],[1,[243,248,182]]]};
const $=id=>document.getElementById(id);
const text=(element,value)=>element.textContent=String(value);
const download=(name,blob)=>{const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)};
const csvCell=v=>'"'+(typeof v==='string'&&/^[=+@\-\t\r]/.test(v)?"'":'')+String(v??'').replaceAll('"','""')+'"';
function colorAt(value,palette){const stops=PALETTES[palette];let a=stops[0],b=stops.at(-1);for(let i=1;i<stops.length;i++)if(value<=stops[i][0]){a=stops[i-1];b=stops[i];break}const t=Math.max(0,Math.min(1,(value-a[0])/(b[0]-a[0])));return a[1].map((v,j)=>Math.round(v+(b[1][j]-v)*t))}
function element(tag,textContent,cls){const e=document.createElement(tag);if(textContent!==undefined)e.textContent=textContent;if(cls)e.className=cls;return e}

export function initPlacements(scene,{onSeek,onOverlay}={}){
  const table=scene.table,duration=scene.duration,signature=scene.report?.source_hashes?.map(v=>v.video.sha256).join(':')??scene.title;
  const storageKey='trophy-placement-v1:'+signature;
  let settings={...DEFAULTS,names:[...DEFAULTS.names],end:duration},reviews={},manual=[],playhead=0,estimated=[],all=[],filtered=[],lastCutoff=-1;
  const pngUrls=[null,null],pngGenerations=[0,0];
  let stored=null;try{stored=JSON.parse(localStorage.getItem(storageKey));if(stored){settings=validatePreset(stored,duration);reviews=validReviews(stored.reviews);manual=validManual(stored.manual_events)}}catch{stored=null}
  const detectorKeys=new Set(['negativePlayer','maxHeightCm','minVerticalSpeed','minLongitudinalSpeed','minSeparation','maxGap']);
  const ids={name0:'placementName0',name1:'placementName1',negativePlayer:'placementEnds',start:'placementStart',end:'placementEnd',
    upToPlayhead:'placementPlayhead',bandwidthCm:'placementBlur',depthBins:'placementDepth',widthBins:'placementWidth',mode:'placementMode',palette:'placementPalette',
    sharedScale:'placementScale',opacity:'placementOpacity',playerPerspective:'placementPerspective',minScore:'placementScore',maxHeightCm:'placementHeight',
    minVerticalSpeed:'placementVertical',minLongitudinalSpeed:'placementLongitudinal',minSeparation:'placementSeparation',maxGap:'placementGap',
    includeOwnSide:'placementOwn',confirmedOnly:'placementConfirmed',showReplay:'placementReplay'};

  function validReviews(value){const result={};if(!value||typeof value!=='object'||Array.isArray(value))return result;for(const [id,event]of Object.entries(value)){if(!/^bounce-\d+$/.test(id))continue;try{result[id]=validateReview(event,duration,table)}catch{}}return result}
  function validManual(value){if(!Array.isArray(value))return [];return value.slice(0,1000).flatMap(e=>{try{validateReview(e,duration,table);if(typeof e.id!=='string'||!e.id.startsWith('manual-'))return [];return [{...e,status:'manual',kind:'manual'}]}catch{return []}})}
  function persist(){try{localStorage.setItem(storageKey,JSON.stringify(preset()));text($('placementSaveState'),'Saved on this browser')}catch{text($('placementSaveState'),'Browser storage unavailable — export a preset to save')}}
  function preset(){return {schema_version:1,scene_signature:signature,settings,reviews,manual_events:manual}}
  function announce(message,error=false){text($('placementNotice'),message);$('placementNotice').classList.toggle('error',error)}
  function writeControls(){for(const [key,id]of Object.entries(ids)){const e=$(id),value=key==='name0'?settings.names[0]:key==='name1'?settings.names[1]:settings[key];if(e.type==='checkbox')e.checked=value;else if(key==='sharedScale')e.value=value?'shared':'individual';else if(key==='playerPerspective')e.value=value?'player':'fixed';else e.value=(key==='start'||key==='end')?Number(Number(value).toFixed(3)):value}for(const id of ['placementStart','placementEnd','manualTime'])$(id).max=duration.toFixed(3);labels()}
  function labels(){text($('placementBlurValue'),settings.bandwidthCm+' cm');text($('placementScoreValue'),Number(settings.minScore).toFixed(2));text($('placementOpacityValue'),Math.round(settings.opacity*100)+'%');text($('placementTitle0'),settings.names[0]+'’s placements');text($('placementTitle1'),settings.names[1]+'’s placements');const options=$('placementEnds').options;options[0].text=settings.names[0]+' at −X end';options[1].text=settings.names[1]+' at −X end';$('manualPlayer').options[0].text=settings.names[0];$('manualPlayer').options[1].text=settings.names[1]}
  for(const [key,id]of Object.entries(ids))$(id).addEventListener(['range','number','text'].includes($(id).type)?'input':'change',()=>{
    const control=$(id);let value=control.type==='checkbox'?control.checked:control.value;
    if(key.startsWith('name')){if(!value.trim())return;settings.names[Number(key.at(-1))]=value.slice(0,40)}
    else if(key==='sharedScale')settings[key]=value==='shared';else if(key==='playerPerspective')settings[key]=value==='player';
    else if(['negativePlayer','start','end','bandwidthCm','depthBins','widthBins','opacity','minScore','maxHeightCm','minVerticalSpeed','minLongitudinalSpeed','minSeparation','maxGap'].includes(key)){value=Number(value);if(!Number.isFinite(value))return;const trial={...settings,[key]:value};try{validatePreset({schema_version:1,settings:trial},duration)}catch{return}settings[key]=value}
    else settings[key]=value;
    if(detectorKeys.has(key))estimated=estimateBounces(scene,settings);
    labels();refresh();reviewTable();persist();
  });

  function refresh(){all=applyReviews(estimated,reviews,manual);filtered=filterEvents(all,settings,duration,playhead);
    const density=[0,1].map(p=>densityGrid(filtered,p,settings,table));const common=Math.max(...density.map(d=>d.max));
    for(const pid of [0,1]){const summary=summarize(filtered,pid,settings,table);text($('placementCount'+pid),summary.count);text($('placementCountLabel'+pid),summary.count===1?'included contact':'included contacts');
      text($('placementReview'+pid),`${summary.estimated} estimated · ${summary.reviewed} reviewed / manual`);
      text($('placementTop'+pid),summary.topZones.length===1?summary.topZones[0].label:summary.topZones.length>1?`${summary.topZones.length} zones tied`: 'No contacts in this range');
      text($('placementTopShare'+pid),summary.topZones.length===1?`${summary.topZones[0].count} of ${summary.count} (${Math.round(100*summary.topZones[0].count/summary.count)}%)`:'');
      drawCourt($('placementCanvas'+pid),pid,density[pid],settings.sharedScale?common:density[pid].max,summary);
      const list=$('placementZones'+pid);list.replaceChildren();for(const z of summary.zones.slice(0,4)){const row=element('div',undefined,'zone-row');row.append(element('span',z.label),element('strong',`${z.count} · ${Math.round(100*z.count/summary.count)}%`));list.append(row)}
      if(!summary.zones.length)list.append(element('p','Adjust the range, review contacts, or add a missed contact.','empty-hint'));
    }
    const hiddenOwn=all.filter(e=>e.kind==='own_side'&&e.included!==false).length,unassigned=all.filter(e=>e.shooter===null).length;
    text($('placementSummary'),`${filtered.length} included · ${all.length} candidate contacts · ${unassigned} unassigned${!settings.includeOwnSide?` · ${hiddenOwn} own-side contacts excluded`:''}`);
    document.querySelector('.heat-gradient').style.background='linear-gradient(90deg,'+PALETTES[settings.palette].map(([,rgb])=>'rgb('+rgb.join(',')+')').join(',')+')';
    text($('placementScaleLabel'),settings.sharedScale?'Shared density scale: compare both players directly.':'Each map uses its own peak: compare patterns, not intensity between players.');
    text($('placementSampleNote'),filtered.length<20?'Small sample: these contacts describe this clip, not a reliable long-term tendency.':'Counts reflect only the included, reconstructed contacts in the selected range.');
    onOverlay?.(settings.showReplay?filtered:[]);
  }

  function drawCourt(canvas,pid,density,maximum,summary){
    const ctx=canvas.getContext('2d'),W=900,H=610;canvas.width=W;canvas.height=H;
    ctx.fillStyle='#101d25';ctx.fillRect(0,0,W,H);
    const left=64,top=82,w=772,h=w*table.width/table.length;
    const toPixel=event=>{const p=playerCoordinates(event,pid,settings);return [left+(p.x/table.length+.5)*w,top+(.5-p.y/table.width)*h]};
    ctx.fillStyle='#214c54';ctx.fillRect(left,top,w,h);
    if(settings.mode!=='zones'&&maximum>0){const off=document.createElement('canvas');off.width=density.width;off.height=density.height;const oc=off.getContext('2d'),im=oc.createImageData(off.width,off.height);
      density.values.forEach((v,i)=>{const t=v/maximum;if(t<.015)return;const rgb=colorAt(t,settings.palette);im.data.set([...rgb,Math.round(255*settings.opacity*Math.min(1,t*2.5))],i*4)});oc.putImageData(im,0,0);ctx.imageSmoothingEnabled=true;ctx.drawImage(off,left,top,w,h)}
    if(settings.mode!=='density'){
      const counts=new Map();for(const e of filtered.filter(e=>e.shooter===pid)){const p=playerCoordinates(e,pid,settings),col=Math.min(settings.depthBins*2-1,Math.max(0,Math.floor((p.x/table.length+.5)*settings.depthBins*2))),row=Math.min(settings.widthBins-1,Math.max(0,Math.floor((.5-p.y/table.width)*settings.widthBins)));const key=col+':'+row;counts.set(key,(counts.get(key)??0)+1)}
      const cw=w/(settings.depthBins*2),ch=h/settings.widthBins;ctx.lineWidth=1;ctx.strokeStyle='#d3ebe540';
      for(let c=1;c<settings.depthBins*2;c++){ctx.beginPath();ctx.moveTo(left+c*cw,top);ctx.lineTo(left+c*cw,top+h);ctx.stroke()}
      for(let r=1;r<settings.widthBins;r++){ctx.beginPath();ctx.moveTo(left,top+r*ch);ctx.lineTo(left+w,top+r*ch);ctx.stroke()}
      ctx.font='600 22px -apple-system, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
      for(const [key,n]of counts){const [c,r]=key.split(':').map(Number);ctx.fillStyle='#08131cbb';ctx.fillRect(left+c*cw+cw/2-22,top+r*ch+ch/2-18,44,36);ctx.fillStyle='#f0f7f3';ctx.fillText(n,left+c*cw+cw/2,top+r*ch+ch/2)}
    }
    ctx.strokeStyle='#e6f0e9';ctx.lineWidth=3;ctx.strokeRect(left,top,w,h);ctx.beginPath();ctx.moveTo(left,top+h/2);ctx.lineTo(left+w,top+h/2);ctx.lineWidth=1.5;ctx.stroke();ctx.beginPath();ctx.moveTo(left+w/2,top-12);ctx.lineTo(left+w/2,top+h+12);ctx.lineWidth=4;ctx.stroke();
    for(const e of filtered.filter(e=>e.shooter===pid)){const [x,y]=toPixel(e);ctx.beginPath();ctx.arc(x,y,7,0,Math.PI*2);ctx.fillStyle=e.status==='estimated'?'#0d1723':'#f0f8f1';ctx.fill();ctx.lineWidth=2;ctx.strokeStyle='#f6f7ed';ctx.stroke()}
    ctx.font='500 19px -apple-system, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle='#bfd4d7';
    const side=pid===settings.negativePlayer?-1:1,ownLeft=settings.playerPerspective||side<0;
    ctx.fillText(ownLeft?'OWN SIDE':'TARGET SIDE',left+w/4,top-32);ctx.fillText(ownLeft?'TARGET SIDE':'OWN SIDE',left+w*3/4,top-32);
    ctx.font='16px -apple-system, sans-serif';ctx.fillStyle='#9db7be';ctx.fillText(`${settings.names[pid]} · ${summary.count} contacts · ${settings.playerPerspective?'player perspective':'fixed court'}`,W/2,H-62);ctx.fillText(settings.mode==='zones'?'Numbers = contacts per zone':`Density · ${settings.bandwidthCm} cm bandwidth · ${settings.sharedScale?'shared':'individual'} scale`,W/2,H-34);
    if(!summary.count){ctx.fillStyle='#07111bb5';ctx.fillRect(left,top,w,h);ctx.fillStyle='#d6e7e5';ctx.font='24px -apple-system, sans-serif';ctx.fillText('No included contacts',left+w/2,top+h/2)}
    const generation=++pngGenerations[pid];
    canvas.toBlob(blob=>{if(!blob||generation!==pngGenerations[pid])return;const previous=pngUrls[pid];pngUrls[pid]=URL.createObjectURL(blob);const link=$('placementPng'+pid);link.href=pngUrls[pid];link.download=`trophy-${settings.names[pid].replace(/[^a-z0-9_-]/gi,'-')}-placements.png`;link.removeAttribute('aria-disabled');link.textContent='Download PNG';if(previous)setTimeout(()=>URL.revokeObjectURL(previous),30000)},'image/png');
    canvas.setAttribute('aria-label',`${settings.names[pid]} placement heatmap, ${summary.count} included contacts${summary.topZones.length===1?', most common '+summary.topZones[0].label:''}`);
  }

  function reviewTable(){const tbody=$('placementRows');tbody.replaceChildren();
    for(const event of all){const row=element('tr');row.dataset.contactId=event.id;tbody.append(row);const included=filterEvents([event],settings,duration,playhead).length>0;row.classList.toggle('excluded',!included);
      const td=()=>{const cell=element('td');row.append(cell);return cell};
      const check=element('input');check.type='checkbox';check.checked=event.included!==false;check.setAttribute('aria-label',`Include contact at ${event.time.toFixed(3)} seconds`);check.onchange=()=>patch(event,{included:check.checked});td().append(check);
      const seek=element('button',event.time.toFixed(3)+' s','contact-seek');seek.onclick=()=>onSeek?.(event.time);td().append(seek);
      const player=element('select');player.setAttribute('aria-label',`Player for contact ${event.id}`);for(const [v,n]of [['','Unassigned'],['0',settings.names[0]],['1',settings.names[1]]]){const option=element('option',n);option.value=v;player.append(option)}player.value=event.shooter===null?'':String(event.shooter);player.onchange=()=>{const shooter=player.value===''?null:Number(player.value);patch(event,{shooter,kind:classify(event.x,shooter)})};td().append(player);
      for(const axis of ['x','y']){const input=element('input');input.type='number';input.step='0.1';input.value=(event[axis]*100).toFixed(1);input.min=String(-(axis==='x'?table.length:table.width)*50);input.max=String((axis==='x'?table.length:table.width)*50);input.setAttribute('aria-label',`${axis.toUpperCase()} centimetres for contact ${event.id}`);input.onchange=()=>{const value=Number(input.value)/100;try{validateReview({...event,[axis]:value},duration,table);patch(event,{[axis]:value,kind:classify(axis==='x'?value:event.x,event.shooter)})}catch(e){announce(e.message,true);input.value=(event[axis]*100).toFixed(1)}};td().append(input)}
      const status=element('select');status.setAttribute('aria-label',`Review status for contact ${event.id}`);for(const [v,n]of [['estimated','Estimated'],['confirmed','Reviewed'],['ignored','Ignore'],...(event.status==='manual'?[['manual','Manual']]:[])]){const o=element('option',n);o.value=v;status.append(o)}status.value=event.status;status.onchange=()=>patch(event,{status:status.value});td().append(status);
      const note=element('span',event.kind.replaceAll('_',' '),'contact-kind');note.title=event.evidence?`Vertical speed ${event.evidence.incoming_vertical_m_s.toFixed(2)} → ${event.evidence.outgoing_vertical_m_s.toFixed(2)} m/s; fitted height error ${event.evidence.table_height_error_cm.toFixed(1)} cm. Player attribution is inferred.`:'Added manually';td().append(note);td().append(element('span',event.score===null?'—':event.score.toFixed(2)));
      const actions=td();if(event.id.startsWith('manual-')){const remove=element('button','Remove');remove.setAttribute('aria-label',`Remove manual contact ${event.id}`);remove.onclick=()=>{manual=manual.filter(e=>e.id!==event.id);refresh();reviewTable();persist();announce('Manual contact removed.')};actions.append(remove)}
    }
  }
  function classify(x,shooter){if(shooter===null)return 'unassigned';const source=shooter===settings.negativePlayer?-1:1;return Math.abs(x)<.025?'near_net':Math.sign(x)===source?'own_side':'target'}
  function patch(event,changes){if(event.id.startsWith('manual-'))manual=manual.map(e=>e.id===event.id?{...e,...changes}:e);else reviews[event.id]={time:event.time,x:event.x,y:event.y,shooter:event.shooter,status:event.status,included:event.included,kind:event.kind,...(reviews[event.id]??{}),...changes};refresh();reviewTable();persist();announce('Contact updated. Use its time button to check the recording.')}

  // PNGs use prepared native download links, preserving the user's click gesture.

  $('placementExportCsv').onclick=()=>{const cols=['id','timestamp_seconds','player','player_id','x_m','y_m','review_status','contact_kind','detector_score','included_in_current_heatmap'];const lines=[cols.join(',')];for(const e of all)lines.push([e.id,e.time,e.shooter===null?'Unassigned':settings.names[e.shooter],e.shooter,e.x,e.y,e.status,e.kind,e.score,filtered.some(p=>p.id===e.id)].map(csvCell).join(','));download('trophy-placement-contacts.csv',new Blob([lines.join('\n')],{type:'text/csv'}))};
  $('placementExportPreset').onclick=()=>download('trophy-placement-preset.json',new Blob([JSON.stringify(preset(),null,2)],{type:'application/json'}));
  $('placementImport').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>1_000_000)throw Error('Preset must be smaller than 1 MB.');const value=JSON.parse(await file.text());settings=validatePreset(value,duration);const same=value.scene_signature===signature;if(same){reviews=validReviews(value.reviews);manual=validManual(value.manual_events)}estimated=estimateBounces(scene,settings);writeControls();refresh();reviewTable();persist();announce(same?'Preset and contact reviews restored.':'Visual settings imported. Reviews from a different rally were not applied.')}catch(e){announce(e.message,true)}event.target.value=''};
  $('placementReset').onclick=()=>{settings={...DEFAULTS,names:[...DEFAULTS.names],end:duration};estimated=estimateBounces(scene,settings);writeControls();refresh();reviewTable();persist();announce('Settings reset. Your contact reviews are retained.')};
  $('manualAdd').onclick=()=>{try{const time=Number($('manualTime').value),x=Number($('manualX').value)/100,y=Number($('manualY').value)/100,shooter=Number($('manualPlayer').value);const contact={id:'manual-'+crypto.randomUUID(),time,x,y,shooter,sourceSide:shooter===settings.negativePlayer?-1:1,status:'manual',kind:'manual',included:true,score:null,height:table.height+.02,method:'user-added contact'};validateReview(contact,duration,table);manual.push(contact);refresh();reviewTable();persist();announce('Manual contact added.')}catch(e){announce(e.message,true)}};
  $('manualUseTime').onclick=()=>{$('manualTime').value=playhead.toFixed(3)};
  estimated=estimateBounces(scene,settings);writeControls();refresh();reviewTable();
  if(stored)announce('Your saved settings and contact reviews were restored.');
  return {updateTime(t){playhead=t;if(settings.upToPlayhead&&Math.abs(t-lastCutoff)>.08){lastCutoff=t;refresh();const ids=new Set(filtered.map(e=>e.id));for(const row of $('placementRows').rows)row.classList.toggle('excluded',!ids.has(row.dataset.contactId))}},
    exportAnalysis(){return {schema_version:1,settings,contacts:all,included:filtered.map(e=>e.id),summaries:[0,1].map(p=>summarize(filtered,p,settings,table))}}};
}
