import * as THREE from 'three';
import {OrbitControls} from './OrbitControls.js';
const data=await fetch('./scene.json').then(r=>{if(!r.ok)throw Error('Scene unavailable');return r.json()});
const el=document.getElementById('viewport');
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor(0x121e27);renderer.shadowMap.enabled=true;
el.appendChild(renderer.domElement);document.getElementById('loading').remove();
const scene=new THREE.Scene();scene.fog=new THREE.Fog(0x121e27,12,25);
const camera=new THREE.PerspectiveCamera(42,1,.05,60);camera.up.set(0,0,1);
const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,0,.8);controls.enableDamping=true;controls.minDistance=2;controls.maxDistance=13;controls.maxPolarAngle=Math.PI/2-.02;
scene.add(new THREE.HemisphereLight(0xc6e3ff,0x52636b,2.1));const sun=new THREE.DirectionalLight(0xffffff,2.3);sun.position.set(-3,-4,8);sun.castShadow=true;sun.shadow.mapSize.set(1024,1024);scene.add(sun);
function box(x,y,z,pos,color){const m=new THREE.Mesh(new THREE.BoxGeometry(x,y,z),new THREE.MeshStandardMaterial({color,roughness:.72}));m.position.set(...pos);m.castShadow=true;m.receiveShadow=true;scene.add(m);return m;}
box(14,12,.04,[0,0,-.025],0x172731);
const grid=new THREE.GridHelper(14,28,0x344e5c,0x243c49);grid.rotation.x=Math.PI/2;grid.position.z=.003;scene.add(grid);
box(2.74,1.525,.055,[0,0,.7325],0x276d75);
for(const y of [-.754,.754])box(2.74,.015,.003,[0,y,.762],0xe7f0ee);
for(const x of [-1.36,1.36])box(.015,1.525,.003,[x,0,.762],0xe7f0ee);
box(2.74,.012,.003,[0,0,.762],0xe7f0ee);
for(const x of [-1.02,1.02])for(const y of [-.53,.53])box(.045,.045,.7,[x,y,.35],0x66818b);
const netMaterial=new THREE.MeshStandardMaterial({color:0x8eafb9,transparent:true,opacity:.4,side:THREE.DoubleSide,wireframe:true});
const net=new THREE.Mesh(new THREE.PlaneGeometry(1.525,.1525,32,5),netMaterial);net.rotation.set(Math.PI/2,Math.PI/2,0);net.position.set(0,0,.838);scene.add(net);
box(.014,1.58,.014,[0,0,.916],0xd4e3e6);for(const y of [-.8,.8])box(.02,.02,.18,[0,y,.825],0xa0bac5);
const edges=[[11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24],[23,25],[25,27],[24,26],[26,28],[27,31],[28,32]];
function sphere(radius,color){return new THREE.Mesh(new THREE.SphereGeometry(radius,12,8),new THREE.MeshStandardMaterial({color,roughness:.6}));}
function limb(a,b,r,mat){const d=new THREE.Vector3().subVectors(b,a);const m=new THREE.Mesh(new THREE.CylinderGeometry(r,r,1,8),mat);m.position.copy(a).add(b).multiplyScalar(.5);m.scale.y=d.length();m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());return m;}
const figures=[0x78c6ff,0xffaa75].map(color=>{const group=new THREE.Group();scene.add(group);const mat=new THREE.MeshStandardMaterial({color,roughness:.65});const bones=edges.map(()=>{const b=limb(new THREE.Vector3(),new THREE.Vector3(0,0,1),.035,mat);b.material=mat.clone();b.material.transparent=true;group.add(b);return b});const joints=Array.from({length:33},()=>{const s=sphere(.043,color);group.add(s);return s});const head=sphere(.115,color);group.add(head);return {group,bones,joints,head};});
const ball=sphere(.036,0xffffff);scene.add(ball);const ballGlow=new THREE.PointLight(0xd5ffb7,.35,1.3);ball.add(ballGlow);
const trailGeometry=new THREE.BufferGeometry();const trail=new THREE.Line(trailGeometry,new THREE.LineBasicMaterial({color:0xbbea92,transparent:true,opacity:.8}));scene.add(trail);
const presets={courtside:[4.4,-5.5,3.1],overhead:[.01,0,7.2],player1:[-5.8,-.5,2.6],player2:[5.8,-.5,2.6]};
function setView(name){camera.position.set(...presets[name]);controls.target.set(0,0,.8);controls.update();document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));controls.autoRotate=false;document.getElementById('orbit').classList.remove('active');}
setView('courtside');document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
document.getElementById('reset').onclick=()=>setView('courtside');document.getElementById('orbit').onclick=()=>{controls.autoRotate=!controls.autoRotate;controls.autoRotateSpeed=.8;document.getElementById('orbit').classList.toggle('active',controls.autoRotate)};
const video=document.getElementById('source'),slider=document.getElementById('timeline');slider.max=data.duration;
let time=0,playing=false,last=performance.now(),frameIndex=0;
const play=document.getElementById('play');play.onclick=()=>{playing=!playing;if(playing){if(time>=data.duration-.01){time=0;video.currentTime=0}video.play().catch(()=>{});}else video.pause();play.textContent=playing?'❚❚':'▶';play.setAttribute('aria-label',playing?'Pause replay':'Play replay');};
slider.oninput=()=>{time=Number(slider.value);video.currentTime=time;drawFrame(time)};
document.getElementById('speed').onchange=e=>video.playbackRate=Number(e.target.value);
function updateFigure(figure,person){figure.group.visible=!!person?.joints;if(!person?.joints)return;const points=person.joints.map(p=>new THREE.Vector3(...p));
figure.joints.forEach((mesh,i)=>{mesh.position.copy(points[i]);mesh.visible=[11,12,13,14,15,16,23,24,25,26,27,28,31,32].includes(i)});
figure.bones.forEach((mesh,i)=>{mesh.material.opacity=person.leg_pose_prior&&i>=8?.3:1;const [a,b]=edges[i];const delta=new THREE.Vector3().subVectors(points[b],points[a]);mesh.position.copy(points[a]).add(points[b]).multiplyScalar(.5);mesh.scale.y=Math.max(.001,delta.length());mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize())});
const face=points[0];figure.head.position.copy(face);figure.head.position.z+=.025;
}
function drawFrame(t){while(frameIndex<data.frames.length-1&&data.frames[frameIndex+1].time<=t)frameIndex++;while(frameIndex>0&&data.frames[frameIndex].time>t)frameIndex--;const f=data.frames[frameIndex];figures.forEach((figure,i)=>updateFigure(figure,f.players.find(p=>p.id===i)));ball.visible=!!f.ball?.position;if(ball.visible){ball.position.set(...f.ball.position);ball.material.color.setHex(f.ball.observed_2d?0xffffff:0xf3be55)}
const ps=data.frames.slice(Math.max(0,frameIndex-18),frameIndex+1).filter(f=>f.ball?.position).map(f=>new THREE.Vector3(...f.ball.position));trailGeometry.setFromPoints(ps);trail.visible=document.getElementById('trail').checked;document.getElementById('clock').textContent=`${t.toFixed(2)} / ${data.duration.toFixed(2)}`;slider.value=t;}
const resize=()=>{const w=el.clientWidth,h=el.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()};new ResizeObserver(resize).observe(el);resize();
const count=data.frames.length;document.getElementById('frameCount').textContent=count;document.getElementById('poseCoverage').textContent=(100*data.frames.reduce((n,f)=>n+f.players.filter(p=>p.joints).length,0)/(2*count)).toFixed(1)+'%';document.getElementById('fitError').textContent=data.report.ball.median_reprojection_error_px.toFixed(1)+' px';
function tick(now){const dt=Math.min(.1,(now-last)/1000);last=now;if(playing){time=video.paused?time+dt*Number(document.getElementById('speed').value):video.currentTime;if(time>=data.duration){time=data.duration;playing=false;video.pause();play.textContent='▶';play.setAttribute('aria-label','Play replay')}}drawFrame(time);controls.update(dt);renderer.render(scene,camera);requestAnimationFrame(tick)}requestAnimationFrame(tick);
window.addEventListener('error',e=>{console.error(e.message)});
