import {sourcePoint, moveCorner} from './geometry.mjs';

const $=id=>document.getElementById(id), ns='http://www.w3.org/2000/svg';
let points=[],initial=[],width=1,height=1,ready=false,dragging=null,disabled=false,storageKey='';
function send(type,body={}){window.parent.postMessage({isStreamlitMessage:true,type,...body},'*');}
function frameHeight(){send('streamlit:setFrameHeight',{height:Math.ceil(document.body.getBoundingClientRect().height)+3});}
function publish(){
  try{sessionStorage.setItem(storageKey,JSON.stringify(points));}catch{}
  send('streamlit:setComponentValue',{value:points,dataType:'json'});
}
function draw(){
  const svg=$('surface');svg.replaceChildren();
  const radius=12*width/Math.max(1,svg.getBoundingClientRect().width);
  if(points.length>1){const polygon=document.createElementNS(ns,'polygon');polygon.setAttribute('points',points.map(p=>p.join(',')).join(' '));svg.append(polygon);}
  points.forEach((point,i)=>{
    const circle=document.createElementNS(ns,'circle');circle.setAttribute('cx',point[0]);circle.setAttribute('cy',point[1]);circle.setAttribute('r',radius);circle.dataset.index=i;
    circle.setAttribute('aria-label',`Corner ${'ABCD'[i]}; drag to adjust`);svg.append(circle);
    const text=document.createElementNS(ns,'text');text.setAttribute('x',point[0]);text.setAttribute('y',point[1]);text.setAttribute('font-size',radius*1.1);text.textContent='ABCD'[i];svg.append(text);
  });
  $('instruction').textContent=points.length<4?`Click corner ${'ABCD'[points.length]} on the table. Select the same physical corners in both views.`:initial.length?'Table detected automatically. Drag a marker only if the outline needs adjusting.':'All four corners selected. Drag a marker to adjust its position.';
  $('reset').textContent=initial.length?'Use automatic outline':'Reset corners';
  $('count').textContent=`${points.length} / 4 corners`;
  $('undo').disabled=$('reset').disabled=disabled||!points.length;
}
const pointFrom=e=>sourcePoint(e.clientX,e.clientY,$('surface').getBoundingClientRect(),width,height);
$('surface').addEventListener('pointerdown',e=>{
  if(disabled||!ready||e.button!==0)return;
  const target=e.target.dataset.index;
  if(target===undefined&&points.length===4)return;
  dragging=target===undefined?points.length:Number(target);
  $('surface').setPointerCapture(e.pointerId);
  points=moveCorner(points,dragging,pointFrom(e));draw();e.preventDefault();
});
$('surface').addEventListener('pointermove',e=>{if(dragging===null)return;points=moveCorner(points,dragging,pointFrom(e));draw();});
function endDrag(){if(dragging===null)return;dragging=null;publish();}
$('surface').addEventListener('pointerup',endDrag);
$('surface').addEventListener('pointercancel',endDrag);
$('undo').onclick=()=>{points=points.slice(0,-1);draw();publish();};
$('reset').onclick=()=>{points=initial.map(p=>[...p]);draw();publish();};
$('frame').onload=()=>{ready=true;draw();frameHeight();};
window.addEventListener('message',event=>{
  if(event.source!==window.parent||event.data?.type!=='streamlit:render')return;
  const args=event.data.args;disabled=event.data.disabled;initial=args.initial_points||[];
  if(storageKey!==args.key){
    storageKey=args.key;points=initial.map(p=>[...p]);
    try{const saved=JSON.parse(sessionStorage.getItem(storageKey));if(Array.isArray(saved)&&saved.length<=4)points=saved;}catch{}
    if(points.length)publish();
  }
  width=args.source_width;height=args.source_height;$('surface').setAttribute('viewBox',`0 0 ${width} ${height}`);
  if($('frame').getAttribute('src')!==args.image){ready=false;$('frame').src=args.image;}
  draw();frameHeight();
});
new ResizeObserver(()=>{draw();frameHeight();}).observe(document.body);
send('streamlit:componentReady',{apiVersion:1});
