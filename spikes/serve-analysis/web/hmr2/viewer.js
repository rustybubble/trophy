import * as THREE from './three.module.js';
import {OrbitControls} from './OrbitControls.js';

const $ = id => document.getElementById(id);
const status = $('status');
try {
  const metadata = await fetch('./scene.json').then(r => {if(!r.ok)throw Error('Scene unavailable');return r.json();});
  const [vertexBytes, faceBytes] = await Promise.all(['vertices.f32','faces.u32'].map(name => fetch(name).then(r => {if(!r.ok)throw Error(`${name} unavailable`);return r.arrayBuffer();})));
  const vertices = new Float32Array(vertexBytes), faces = new Uint32Array(faceBytes);
  const length = metadata.vertex_count*3;
  if(vertices.length!==metadata.frame_count*metadata.players*length)throw Error('Mesh frame count mismatch');
  const scene = new THREE.Scene();scene.background = new THREE.Color('#101b28');
  const renderer = new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;
  $('viewport').appendChild(renderer.domElement);
  const camera = new THREE.PerspectiveCamera(46,1,.02,100);camera.up.set(0,0,1);
  const controls = new OrbitControls(camera,renderer.domElement);controls.target.set(0,0,.9);controls.enableDamping=true;
  const ambient = new THREE.HemisphereLight(0xddefff,0x35404b,2.2);scene.add(ambient);
  const light = new THREE.DirectionalLight(0xffffff,2.4);light.position.set(2,-3,6);scene.add(light);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(16,12),new THREE.MeshStandardMaterial({color:0x192633,roughness:1,side:THREE.DoubleSide}));ground.position.z=-.012;scene.add(ground);
  const grid = new THREE.GridHelper(14,28,0x3a4d5d,0x263848);grid.rotation.x=Math.PI/2;grid.position.z=.002;scene.add(grid);
  function box(x,y,z,sx,sy,sz,color){const m=new THREE.Mesh(new THREE.BoxGeometry(sx,sy,sz),new THREE.MeshStandardMaterial({color,roughness:.75}));m.position.set(x,y,z);scene.add(m);return m;}
  box(0,0,.7325,2.74,1.525,.055,0x325d78);
  for(const x of [-1.05,1.05])for(const y of [-.55,.55])box(x,y,.36,.045,.045,.72,0x738798);
  const corners=[[-1.37,-.7625,.762],[1.37,-.7625,.762],[1.37,.7625,.762],[-1.37,.7625,.762],[-1.37,-.7625,.762]];
  scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(corners.map(p=>new THREE.Vector3(...p))),new THREE.LineBasicMaterial({color:0xe9f2f4})));
  scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-1.37,0,.763),new THREE.Vector3(1.37,0,.763)]),new THREE.LineBasicMaterial({color:0xd1e0e7})));
  const net=new THREE.Mesh(new THREE.BoxGeometry(.007,1.83,.1525),new THREE.MeshStandardMaterial({color:0xd7e0e3,transparent:true,opacity:.3}));net.position.z=.83625;scene.add(net);
  const colors=[0x62ccb6,0x8d9ff4];
  const meshes=colors.map(color=>{const geometry=new THREE.BufferGeometry();geometry.setIndex(new THREE.BufferAttribute(faces,1));geometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(length),3));const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color,roughness:.75,metalness:.02,side:THREE.DoubleSide}));mesh.frustumCulled=false;scene.add(mesh);return mesh;});
  const ball=new THREE.Mesh(new THREE.SphereGeometry(.02,16,12),new THREE.MeshStandardMaterial({color:0xffc778,emissive:0x8e3f00,emissiveIntensity:.2}));scene.add(ball);
  const trail=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0xf5cc85,transparent:true,opacity:.65}));scene.add(trail);
  const cvToWorld = p => new THREE.Vector3(-p[1],p[0],p[2]+.76);
  let view='orbit',time=metadata.start_time||0,playing=false,speed=.5,last=performance.now(),lastFrame=-1;
  function resetView(){camera.up.set(0,0,1);camera.fov=46;camera.position.set(4.8,-5.5,3.2);controls.target.set(0,0,.9);controls.enabled=true;camera.lookAt(controls.target);camera.updateProjectionMatrix();controls.update();}
  resetView();
  $('camera').onchange=()=>{view=$('camera').value;if(view==='orbit'){resetView();return;}controls.enabled=false;if(view==='top'){camera.position.set(.001,-.001,7);camera.up.set(0,1,0);camera.lookAt(0,0,0);camera.fov=46;}else{const c=metadata.geometry_report.cameras[Number(view)];const R=c.R;const forward=[R[2][0],R[2][1],R[2][2]],up=[-R[1][0],-R[1][1],-R[1][2]];camera.position.copy(cvToWorld(c.center));camera.up.set(-up[1],up[0],up[2]);camera.lookAt(camera.position.clone().add(new THREE.Vector3(-forward[1],forward[0],forward[2])));const size=(metadata.source_sizes||[[1920,1080],[1920,1080]])[Number(view)];camera.fov=2*Math.atan(size[1]/(2*c.K[1][1]))*180/Math.PI;}camera.updateProjectionMatrix();};
  const sources=[$('source0'),$('source1')];
  function syncSources(force=false){sources.forEach((video,i)=>{const target=Math.max(0,time+metadata.source_offsets_seconds[i]);if(video.readyState>=1&&(force||Math.abs(video.currentTime-target)>.05))video.currentTime=target;video.playbackRate=speed;if(playing&&video.paused)video.play().catch(()=>{});if(!playing&&!video.paused)video.pause();});}
  $('timeline').min=metadata.start_time||0;$('timeline').max=metadata.duration;
  $('timeline').oninput=()=>{time=Number($('timeline').value);syncSources(true);};
  $('speed').onchange=()=>{speed=Number($('speed').value);syncSources(true);};
  $('play').disabled=false;$('play').onclick=()=>{if(time>=metadata.duration)time=metadata.start_time||0;playing=!playing;$('play').textContent=playing?'Pause':'Play';syncSources(true);};
  $('offset').textContent=`${(metadata.source_offsets_seconds[1]*1000).toFixed(1)} ms`;
  const fitError=metadata.report.reprojection_after.median_px;$('error').textContent=fitError==null?'No visible joints':`${fitError.toFixed(1)} px median`;
  const valid=metadata.frames.filter(f=>f.ball.position).length;$('coverage').textContent=`${valid}/${metadata.frame_count} frames`;
  if (metadata.serve_events) {
    $('servePanel').hidden=false;
    $('serveSummary').textContent=`${metadata.serve_events.length} candidates in this replay. Candidates require source-video review; serve legality is not measured.`;
    $('serveReview').href=metadata.serve_review_url||'review/';
    for (const event of metadata.serve_events) {
      const button=document.createElement('button');
      button.textContent=`${event.time_seconds.toFixed(2)} s · ${event.player_id==='p0'?'Player 1':event.player_id==='p1'?'Player 2':'Player uncertain'} · ${event.event_status.replaceAll('_',' ')}`;
      button.onclick=()=>{playing=false;$('play').textContent='Play';time=THREE.MathUtils.clamp(event.time_seconds,metadata.start_time||0,metadata.duration);syncSources(true);};
      $('serveEvents').append(button);
    }
  }
  if (metadata.download_videos===false) for (const link of document.querySelectorAll('nav a')) if (['orbit.mp4','comparison.mp4'].includes(link.getAttribute('href'))) link.hidden=true;
  sources.forEach(video=>video.addEventListener('loadedmetadata',()=>syncSources(true)));
  status.textContent='Drag to orbit · shape and hidden motion estimated';
  function update(){const n=metadata.frame_count;let index=Math.min(n-1,Math.floor(time*metadata.fps));while(index>0&&metadata.frames[index].time>time)index--;while(index+1<n&&metadata.frames[index+1].time<=time)index++;const next=Math.min(n-1,index+1);const span=metadata.frames[next].time-metadata.frames[index].time;const alpha=span?THREE.MathUtils.clamp((time-metadata.frames[index].time)/span,0,1):0;meshes.forEach((mesh,p)=>{const data=mesh.geometry.attributes.position.array;const a=(index*2+p)*length,b=(next*2+p)*length;for(let k=0;k<length;k++)data[k]=vertices[a+k]*(1-alpha)+vertices[b+k]*alpha;mesh.geometry.attributes.position.needsUpdate=true;mesh.geometry.computeVertexNormals();});const frame=metadata.frames[index];ball.visible=!!frame.ball.position;if(ball.visible)ball.position.set(...frame.ball.position);if(index!==lastFrame){const points=[];for(let j=index;j>=Math.max(0,index-12);j--){const p=metadata.frames[j].ball.position;if(!p)break;points.unshift(new THREE.Vector3(...p));}trail.geometry.dispose();trail.geometry=new THREE.BufferGeometry().setFromPoints(points);lastFrame=index;}}
  new ResizeObserver(()=>{const w=$('viewport').clientWidth,h=$('viewport').clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}).observe($('viewport'));
  function tick(now){requestAnimationFrame(tick);const dt=Math.min(.1,(now-last)/1000);last=now;if(playing){time=Math.min(metadata.duration,time+dt*speed);if(time>=metadata.duration){playing=false;$('play').textContent='Play';}}$('timeline').value=time;$('clock').textContent=`${time.toFixed(2)} s`;update();syncSources();if(view==='orbit')controls.update();renderer.render(scene,camera);}
  requestAnimationFrame(tick);
}catch(error){status.textContent=`Reconstruction could not load: ${error.message}`;console.error(error);}
