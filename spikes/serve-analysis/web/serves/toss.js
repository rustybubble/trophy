import {decodeFrameAt} from './frame-proof.js';
const $=id=>document.getElementById(id);
const NS='http://www.w3.org/2000/svg';
const phases=[['last_on_hand','Last on hand'],['first_free','First free'],['apex_before','Before apex'],['apex','Apex'],['apex_after','After apex']];
const names={insufficient_evidence:'Insufficient evidence',criterion_satisfied:'Criterion satisfied',violation_supported:'Violation supported',borderline:'Borderline · review required',referee_judgment_required:'Referee judgment required'};
const statuses={violation_supported:'VIOLATION SUPPORTED',two_criteria_satisfied:'TWO CHECKS SATISFIED',needs_review:'NEEDS REVIEW'};
const fmt=t=>`${Number(t).toFixed(3)} s`;
function svgNode(tag,attrs={},text){const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;}
function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

export class TossReviewer{
  constructor({session,videos,getSelected,persist,pause,seek}){Object.assign(this,{session,videos,getSelected,persist,pause,seek});this.phase='last_on_hand';this.capturing=false;this.selectedID=null;this.layers=[];}
  async load(){
    try{const response=await fetch('api/toss-rules');if(!response.ok)throw Error('Toss evidence API unavailable. Start the updated review server.');this.info=await response.json();}
    catch(error){$('tossCalibration').textContent=error.message;$('measureToss').disabled=true;return;}
    const {rulebook,calibration}=this.info;
    $('heightRule').href=rulebook.law.url;$('angleRule').href=rulebook.ttr.url;
    const scope=calibration?.validation?.valid_session_time_range_seconds;
    $('tossCalibration').textContent=calibration?.fixture_only?'SYNTHETIC VERIFICATION ONLY · known generated geometry, not match footage.':calibration?.validation?.status==='validated'?'Metric camera validation is configured. Each toss must also pass frame, timing, and visibility checks.':`Calibration: unvalidated. Measurements are estimates; supported fault calls require validated camera geometry, timing, and error bounds.${scope?` Saved geometry interval: ${scope[0]}–${scope[1]} s.`:' No metric calibration is configured.'}`;
    for(const [i,video] of this.videos.entries()){
      const layer=svgNode('svg',{viewBox:'0 0 1000 562.5',class:'toss-overlay','aria-label':`${this.session.views[i].id} toss markers`});
      layer.addEventListener('click',e=>this.mark(i,e));video.parentElement.append(layer);this.layers.push(layer);
    }
    $('markToss').onclick=()=>{if(!this.getSelected())return;this.pause();this.capturing=!this.capturing;this.render();if(this.capturing)$('videos').scrollIntoView({block:'center',behavior:'smooth'});};
    $('clearToss').onclick=()=>{const event=this.getSelected();if(!event)return;delete event.toss_annotations;delete event.toss_evidence;this.capturing=false;this.persist();};
    for(const [id,key] of [['releaseVerified','release_bracket_confirmed'],['apexVerified','apex_bracket_confirmed'],['tossProfile','profile']])$(id).onchange=()=>{const event=this.getSelected();if(!event)return;const a=this.annotations(event);a[key]=$(id).type==='checkbox'?$(id).checked:$(id).value;event.toss_annotations=a;delete event.toss_evidence;this.persist();};
    $('measureToss').onclick=()=>this.measure();
    $('exportToss').onclick=()=>{const evidence=this.getSelected()?.toss_evidence;if(evidence)download(evidence,'toss-evidence.json');};
    $('exportTossImage').onclick=()=>this.exportImage();
  }
  annotations(event){const a=event.toss_annotations||event.toss_evidence?.annotations||{serve_id:event.serve_id,observations:{},profile:'ittf_ttr_30',release_bracket_confirmed:false,apex_bracket_confirmed:false};a.contact_time_seconds=event.time_seconds;return a;}
  mark(index,event){
    const selected=this.getSelected();if(!this.capturing||!selected)return;
    const video=this.videos[index];
    if(!video.paused||!video.videoWidth||!Number.isFinite(video.presentedFramePTS)||video.seeking){$('markHint').textContent='Pause on a decoded frame before marking. This browser must expose presented-frame timestamps.';return;}
    const rectangle=this.layers[index].getBoundingClientRect();
    const uv=[(event.clientX-rectangle.left)/rectangle.width,(event.clientY-rectangle.top)/rectangle.height];
    if(uv.some(v=>v<0||v>1))return;
    const a=this.annotations(selected);const viewID=this.session.views[index].id;
    const observation={view_id:viewID,uv_norm:uv,source_time_seconds:video.presentedFramePTS,
      image_size:[video.videoWidth,video.videoHeight],timing_source:'browser_presented_frame',observation_source:'human_marked_ball_center'};
    a.observations[this.phase]=[...(a.observations[this.phase]||[]).filter(o=>o.view_id!==viewID),observation];
    selected.toss_annotations=a;delete selected.toss_evidence;
    if(a.observations[this.phase].length===this.videos.length)this.capturing=false;
    this.persist();
  }
  async measure(){
    const event=this.getSelected();if(!event)return;
    $('measureToss').disabled=true;$('tossMessage').textContent='Computing source-linked toss evidence…';
    try{
      const response=await fetch('api/toss-measure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(this.annotations(event))});
      const result=await response.json();if(!response.ok)throw Error(result.error||'Measurement failed');
      event.toss_evidence=result;event.toss_annotations=result.annotations;this.persist();
      $('tossMessage').textContent='Evidence saved in this browser. Export the JSON to keep source frames, points, rules, and calibration identity.';
    }catch(error){$('tossMessage').textContent=error.message;}
    finally{$('measureToss').disabled=false;}
  }
  async exportImage(){
    const evidence=this.getSelected()?.toss_evidence;if(!evidence?.metrics)return;
    this.pause();const times=this.videos.map(v=>v.currentTime);$('exportTossImage').disabled=true;
    $('tossMessage').textContent='Decoding marked release and apex frames for the proof image…';
    try{
      const canvas=document.createElement('canvas');canvas.width=1920;canvas.height=3250;
      const c=canvas.getContext('2d');c.fillStyle='#0c1013';c.fillRect(0,0,canvas.width,canvas.height);
      c.fillStyle='#e9f0f2';c.font='bold 32px sans-serif';c.fillText('TROPHY · TOSS EVIDENCE · LAW 2.6.2',40,50);
      const status=evidence.calibration?.fixture_only?'SYNTHETIC VERIFICATION ONLY · NOT MATCH FOOTAGE':statuses[evidence.decision.status];
      c.fillStyle=evidence.decision.status==='violation_supported'?'#ffa99e':'#ffcf79';c.font='bold 25px sans-serif';c.fillText(status,40,90);
      const m=evidence.metrics;c.fillStyle='#e9f0f2';c.font='23px sans-serif';
      c.fillText(`Rise: ${(m.height_m*100).toFixed(2)} cm · angle: ${m.angle_degrees.toFixed(2)}° from calibrated vertical`,40,130);
      c.font='18px sans-serif';c.fillStyle='#9aacb6';
      c.fillText(`Height minimum: 16 cm · ${evidence.decision.profile==='ittf_ttr_30'?'TTR angle criterion: 30°':'Angle: referee interpretation'} · release-to-apex chord method`,40,164);
      c.fillText(`${evidence.evidence_id} · ${evidence.decision.scope} · profile: ${evidence.decision.profile}`,40,194);
      c.fillText(m.height_interval_m?`Height bounds: ${(m.height_interval_m[0]*100).toFixed(2)}–${(m.height_interval_m[1]*100).toFixed(2)} cm · angle bounds: ${m.angle_interval_degrees.map(v=>v.toFixed(2)).join('–')}°`:'No validated measurement error bounds; displayed values are estimates.',40,220);
      for(const [row,[phase,title]]of phases.entries())for(const [index,view]of this.session.views.entries()){
        const observation=evidence.annotations.observations[phase].find(o=>o.view_id===view.id);
        const stamp=await decodeFrameAt(this.videos[index],observation.source_time_seconds);
        if(Math.abs(stamp-observation.source_time_seconds)>.001)throw Error('Decoded frame does not match the recorded marker timestamp.');
        const x=40+index*950,y=250+row*580,w=900,h=506.25;
        c.fillStyle='#e9f0f2';c.font='20px sans-serif';c.fillText(`${view.id} · ${title.toUpperCase()} · source ${stamp.toFixed(6)} s`,x,y-15);
        c.drawImage(this.videos[index],x,y,w,h);
        const point=p=>[x+p[0]*w,y+p[1]*h];
        const overlay=evidence.overlays[view.id];
        if(overlay){
          for(const [target,color,dash]of [['apex','#ffcf79',[]],['vertical_at_apex','#9df1cb',[8,6]],['height_reference_16cm','#96c5ff',[]]]){
            c.beginPath();c.strokeStyle=color;c.lineWidth=3;c.setLineDash(dash);c.moveTo(...point(overlay.release));c.lineTo(...point(overlay[target]));c.stroke();
          }
          c.setLineDash([]);
        }
        c.beginPath();c.strokeStyle='#ffcf79';c.lineWidth=3;c.arc(...point(observation.uv_norm),12,0,2*Math.PI);c.stroke();
        c.fillStyle='#9aacb6';c.font='16px sans-serif';c.fillText('Circle: observed ball center. Lines: release/apex from different frames; blue segment = 16 cm.',x,y+h+25);
      }
      c.fillStyle='#9aacb6';c.font='18px sans-serif';
      c.fillText('ITTF Statutes 2026 p41, Law 2.6.2 · ITTF TTR guidance (8 Dec 2024). Full sources and calibration are in the evidence JSON.',40,3190);
      c.fillStyle='#ffcf79';c.fillText(evidence.decision.blockers.length?'INSUFFICIENT EVIDENCE: '+evidence.decision.blockers[0]:'Only these two criteria were evaluated. This image does not establish overall service legality.',40,3225);
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw Error('Could not encode proof image.');
      const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='toss-proof.png';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      $('tossMessage').textContent='Proof image exported with ten actual source frames. Keep the evidence JSON for full measurement bounds and provenance.';
    }catch(error){$('tossMessage').textContent=error.message;}
    finally{for(const [i,v]of this.videos.entries())v.currentTime=times[i];$('exportTossImage').disabled=false;}
  }
  render(){
    if(!this.info)return;
    const event=this.getSelected();if(this.selectedID!==event?.serve_id){this.selectedID=event?.serve_id;this.capturing=false;$('tossMessage').textContent='';}
    const annotations=event?this.annotations(event):{observations:{}};let result=event?.toss_evidence;
    if(result&&(result.calibration_sha256!==(this.info.calibration?.sha256||null)||result.rulebook.version!==this.info.rulebook.version)){
      result=null;$('tossMessage').textContent='Calibration or rule version changed. Recompute these checks from the saved marks.';
    }
    $('tossStatus').textContent=result?statuses[result.decision.status]:'NOT MEASURED';$('tossStatus').dataset.status=result?.decision.status||'';
    for(const [id,key] of [['releaseVerified','release_bracket_confirmed'],['apexVerified','apex_bracket_confirmed']])$(id).checked=Boolean(annotations[key]);
    $('tossProfile').value=annotations.profile||'ittf_ttr_30';
    $('angleRule').textContent=annotations.profile==='ittf_law_2_6_2'?'ITTF 2.6.2 · near vertically ↗':'ITTF TTR · maximum 30° ↗';
    $('angleRule').href=annotations.profile==='ittf_law_2_6_2'?this.info.rulebook.law.url:this.info.rulebook.ttr.url;
    $('tossPhases').replaceChildren();
    for(const [phase,title] of phases){
      const row=document.createElement('div');row.className='phase-row';
      const choose=document.createElement('button');choose.textContent=title;choose.className=phase===this.phase?'phase-active':'secondary';choose.onclick=()=>{this.phase=phase;this.capturing=false;this.render();};row.append(choose);
      for(const view of this.session.views){const observation=(annotations.observations[phase]||[]).find(o=>o.view_id===view.id);const button=document.createElement('button');button.className='phase-stamp secondary';button.textContent=observation?`${view.id}: ${fmt(observation.source_time_seconds)}`:`${view.id}: missing`;button.disabled=!observation;button.onclick=()=>{this.pause();this.seek(observation.source_time_seconds-view.source_offset_seconds);};row.append(button);}
      $('tossPhases').append(row);
    }
    $('markToss').textContent=this.capturing?'Cancel marking':`Mark ${phases.find(p=>p[0]===this.phase)[1].toLowerCase()} in both views`;
    $('markHint').textContent=this.capturing?'Click the ball center in each paused camera.':'';
    $('exportToss').disabled=!result;$('exportTossImage').disabled=!result?.metrics;$('measureToss').disabled=!event;
    for(const [index,prefix,scale,suffix] of [[0,'height',100,' cm'],[1,'angle',1,'°']]){
      const check=result?.decision.checks[index];
      const estimate=check?.estimate;$(prefix+'Value').textContent=Number.isFinite(estimate)?`${(estimate*scale).toFixed(1)}${suffix}`:`—${suffix}`;
      const interval=check?.interval;
      $(prefix+'Result').textContent=check?`${names[check.result]}${interval?` · ${(interval[0]*scale).toFixed(1)}–${(interval[1]*scale).toFixed(1)}${suffix}`:' · no validated error bound'}`:'Not measured';
      $(prefix+'Result').dataset.result=check?.result||'';
      $(prefix+'Explanation').textContent=check?.explanation||'';
    }
    $('tossBlockers').replaceChildren();for(const text of result?.decision.blockers||[]){const li=document.createElement('li');li.textContent=text;$('tossBlockers').append(li);}
    this.drawOverlays(annotations,result);this.drawDiagram(result);
  }
  drawOverlays(annotations,result){
    this.layers.forEach((layer,index)=>{
      layer.replaceChildren();layer.classList.toggle('marking',this.capturing);
      const view=this.session.views[index];const overlay=result?.overlays[view.id];
      const xy=p=>[p[0]*1000,p[1]*562.5];
      const line=(a,b,color,dash)=>{const [x1,y1]=xy(a),[x2,y2]=xy(b);layer.append(svgNode('line',{x1,y1,x2,y2,stroke:color,'stroke-width':2,'stroke-dasharray':dash||''}));};
      if(overlay){line(overlay.release,overlay.apex,'#ffcf79');line(overlay.release,overlay.vertical_at_apex,'#9df1cb','5 4');line(overlay.release,overlay.height_reference_16cm,'#96c5ff');
        for(const [key,label,color] of [['release','First-free anchor','#ffcf79'],['apex','Apex','#ffa99e'],['height_reference_16cm','16 cm above anchor','#96c5ff']]){const [cx,cy]=xy(overlay[key]);layer.append(svgNode('circle',{cx,cy,r:4,fill:color}));layer.append(svgNode('text',{x:cx+8,y:cy-8,fill:color,class:'overlay-text'},label));}
        layer.append(svgNode('text',{x:20,y:27,fill:'#ffcf79',class:'overlay-text'},`${result.decision.blockers.length?'ESTIMATE · ':''}Release → apex · different source frames`));
      }else{
        for(const [phase,title] of phases){const o=(annotations.observations[phase]||[]).find(o=>o.view_id===view.id);if(!o)continue;const [cx,cy]=xy(o.uv_norm);layer.append(svgNode('circle',{cx,cy,r:4,fill:phase==='apex'?'#ffa99e':'#ffcf79'}));layer.append(svgNode('text',{x:cx+7,y:cy-7,fill:'#ffcf79',class:'overlay-text'},`${title} · ${fmt(o.source_time_seconds)}`));}
      }
    });
  }
  drawDiagram(result){
    const panel=$('tossDiagram');panel.replaceChildren();panel.hidden=!result?.metrics;if(panel.hidden)return;
    const m=result.metrics;const svg=svgNode('svg',{viewBox:'0 0 480 240',role:'img','aria-label':'3D toss plane with vertical height and release-to-apex angle'});
    const scale=140/Math.max(.16,m.height_m,m.horizontal_displacement_m);
    const r=[85,190],a=[85+m.horizontal_displacement_m*scale,190-m.height_m*scale];
    svg.append(svgNode('line',{x1:r[0],y1:r[1],x2:r[0],y2:24,stroke:'#9df1cb','stroke-width':2,'stroke-dasharray':'5 5'}));
    svg.append(svgNode('line',{x1:r[0],y1:r[1],x2:a[0],y2:a[1],stroke:'#ffcf79','stroke-width':3}));
    svg.append(svgNode('line',{x1:r[0],y1:a[1],x2:a[0],y2:a[1],stroke:'#9aacb6','stroke-dasharray':'3 4'}));
    const y16=190-.16*scale;svg.append(svgNode('line',{x1:65,y1:y16,x2:105,y2:y16,stroke:'#96c5ff','stroke-width':3}));
    const theta=m.angle_degrees*Math.PI/180,rad=35;
    svg.append(svgNode('path',{d:`M 85 155 A 35 35 0 ${theta>Math.PI?1:0} 1 ${85+rad*Math.sin(theta)} ${190-rad*Math.cos(theta)}`,fill:'none',stroke:'#ffcf79','stroke-width':2}));
    for(const [p,label,color] of [[r,'Release anchor','#ffcf79'],[a,'Apex','#ffa99e']]){svg.append(svgNode('circle',{cx:p[0],cy:p[1],r:5,fill:color}));svg.append(svgNode('text',{x:p[0]+8,y:p[1]+18,fill:color},label));}
    svg.append(svgNode('text',{x:265,y:40,fill:'#e9f0f2'},`${(m.height_m*100).toFixed(1)} cm rise`));
    svg.append(svgNode('text',{x:265,y:68,fill:'#e9f0f2'},`${m.angle_degrees.toFixed(1)}° from vertical`));
    svg.append(svgNode('text',{x:265,y:97,fill:'#96c5ff'},'Blue tick = 16 cm'));
    svg.append(svgNode('text',{x:265,y:129,fill:'#9aacb6'},'Plane through the 3D toss'));
    svg.append(svgNode('text',{x:265,y:151,fill:'#9aacb6'},'and calibrated vertical'));
    svg.append(svgNode('text',{x:265,y:184,fill:result.decision.blockers.length?'#ffcf79':'#9df1cb'},result.decision.blockers.length?'UNVALIDATED / NEEDS REVIEW':'Conditional measurement bounds'));
    if(result.calibration?.fixture_only)svg.append(svgNode('text',{x:20,y:229,fill:'#ffcf79'},'SYNTHETIC VERIFICATION ONLY · NOT MATCH FOOTAGE'));
    panel.append(svg);
  }
}
