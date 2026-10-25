/** Local contact analysis using the exact same functions as the browser UI. */
import fs from 'node:fs';import path from 'node:path';
import {DEFAULTS,estimateBounces,applyReviews,filterEvents,summarize,validatePreset,validateReview} from '../web/multiview/placements-core.js';
const args=process.argv.slice(2),get=name=>{const i=args.indexOf(name);return i<0?null:args[i+1]};
const scenePath=get('--scene')??'artifacts/multiview/demo/scene.json',output=get('--output')??'artifacts/placements';
const scene=JSON.parse(fs.readFileSync(scenePath)),signature=scene.report?.source_hashes?.map(v=>v.video.sha256).join(':')??scene.title;
let settings={...DEFAULTS,names:[...DEFAULTS.names],end:scene.duration},reviews={},manual=[];
if(get('--preset')){
 const preset=JSON.parse(fs.readFileSync(get('--preset')));settings=validatePreset(preset,scene.duration);
 if(preset.scene_signature===signature){
  const ids=new Set(estimateBounces(scene,settings).map(e=>e.id));
  for(const [id,review]of Object.entries(preset.reviews??{}))if(ids.has(id))reviews[id]=validateReview(review,scene.duration,scene.table);
  manual=(preset.manual_events??[]).map(e=>({...validateReview(e,scene.duration,scene.table),status:'manual',kind:'manual'}));
 }
}
const contacts=applyReviews(estimateBounces(scene,settings),reviews,manual),included=filterEvents(contacts,settings,scene.duration),chosen=new Set(included.map(e=>e.id));
const report={schema_version:1,kind:'estimated table bounce placements',source_scene:path.resolve(scenePath),scene_signature:signature,
 independent_bounce_ground_truth_available:false,settings,contacts,included_contact_ids:[...chosen],summaries:[0,1].map(p=>summarize(included,p,settings,scene.table)),
 notes:['Counts are reconstructed candidate contacts, not verified match statistics.','Player attribution is inferred from incoming motion and origin evidence.','Own-side contacts and ambiguous origins are excluded by default.']};
fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,'analysis.json'),JSON.stringify(report,null,2));
const cell=v=>'"'+(typeof v==='string'&&/^[=+@\-\t\r]/.test(v)?"'":'')+String(v??'').replaceAll('"','""')+'"';
const csv=[['id','timestamp_seconds','player','player_id','x_m','y_m','review_status','contact_kind','detector_score','included_in_current_heatmap'].join(',')];
for(const e of contacts)csv.push([e.id,e.time,e.shooter===null?'Unassigned':settings.names[e.shooter],e.shooter,e.x,e.y,e.status,e.kind,e.score,chosen.has(e.id)].map(cell).join(','));
fs.writeFileSync(path.join(output,'contacts.csv'),csv.join('\n'));
console.log(JSON.stringify({included:included.length,players:report.summaries.map((s,i)=>({name:settings.names[i],contacts:s.count})),output:path.resolve(output)},null,2));
