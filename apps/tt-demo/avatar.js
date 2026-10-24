import * as THREE from 'three';

const Y=new THREE.Vector3(0,1,0),Z=new THREE.Vector3(0,0,1);
const vector=p=>new THREE.Vector3(...p);
const midpoint=(a,b)=>a.clone().add(b).multiplyScalar(.5);

// One closed, indexed surface, smoothly bound across the entire skeleton.
// Bones are independent world-space controls driven by reconstructed landmarks.
export function createAvatar(asset,color,id,scene){
  const group=new THREE.Group();scene.add(group);
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(asset.positions.flat(),3));
  geometry.setAttribute('normal',new THREE.Float32BufferAttribute(asset.normals.flat(),3));
  geometry.setAttribute('skinIndex',new THREE.Uint16BufferAttribute(asset.skin_indices.flat(),4));
  geometry.setAttribute('skinWeight',new THREE.Float32BufferAttribute(asset.skin_weights.flat(),4));
  geometry.setIndex(asset.faces.flat());
  const accent=new THREE.Color(color);
  const material=new THREE.MeshStandardMaterial({color:0x10242e,roughness:.58,metalness:.08,side:THREE.DoubleSide});
  // Rest-surface coordinates travel through GPU skinning with the mesh. The
  // orderly shader grid stays attached to the continuous surface; no floating
  // wireframe shell and no change to raw observed landmarks are introduced.
  material.onBeforeCompile=shader=>{
    shader.uniforms.trophyAccent={value:accent};
    shader.vertexShader=shader.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vTrophyRest;\nvarying vec3 vTrophyNormal;');
    shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvTrophyRest=position; vTrophyNormal=normal;');
    shader.fragmentShader=shader.fragmentShader.replace('#include <common>', '#include <common>\nuniform vec3 trophyAccent;\nvarying vec3 vTrophyRest;\nvarying vec3 vTrophyNormal;');
    shader.fragmentShader=shader.fragmentShader.replace('#include <color_fragment>', `#include <color_fragment>
      vec3 gridCoordinate=vTrophyRest / 0.075;
      vec3 gridDistance=abs(fract(gridCoordinate-0.5)-0.5)/max(fwidth(gridCoordinate),vec3(0.0001));
      vec3 gridLine=1.0-smoothstep(vec3(0.45),vec3(1.15),gridDistance);
      vec3 gridWeight=pow(abs(normalize(vTrophyNormal)),vec3(6.0));
      gridWeight/=max(dot(gridWeight,vec3(1.0)),0.0001);
      float surfaceLine=dot(vec3(max(gridLine.y,gridLine.z),max(gridLine.x,gridLine.z),max(gridLine.x,gridLine.y)),gridWeight);
      diffuseColor.rgb=mix(diffuseColor.rgb,trophyAccent*0.72,surfaceLine*0.86);
    `);
  };
  material.customProgramCacheKey=()=> 'trophy-skinned-surface-grid-v1';
  const body=new THREE.SkinnedMesh(geometry,material);body.castShadow=true;body.receiveShadow=true;body.frustumCulled=false;group.add(body);
  const lengths=[];
  const bones=asset.bones.map(([a,b])=>{const bone=new THREE.Bone(),start=vector(a),direction=vector(b).sub(start);lengths.push(direction.length());bone.position.copy(start);bone.quaternion.setFromUnitVectors(Y,direction.normalize());body.add(bone);return bone});
  body.updateMatrixWorld(true);body.bind(new THREE.Skeleton(bones));body.normalizeSkinWeights();
  const racket=new THREE.Group();group.add(racket);
  const prop=(geometry,color)=>{const m=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color,roughness:.6}));m.castShadow=true;racket.add(m);return m};
  const handle=prop(new THREE.CylinderGeometry(.014,.017,.105,12),0xb48b59);handle.rotation.x=Math.PI/2;handle.position.z=.042;
  const blade=prop(new THREE.CylinderGeometry(.076,.076,.009,32),id===0?0xdf465c:0x22252a);blade.scale.z=1.15;blade.position.z=.17;
  const back=prop(new THREE.CircleGeometry(.074,32),id===0?0x25272d:0xd84d55);back.rotation.x=Math.PI/2;back.position.set(0,.005,.17);
  return {group,body,bones,lengths,racket};
}

function endpoints(q){
  const hips=midpoint(q[23],q[24]),shoulders=midpoint(q[11],q[12]);
  const up=shoulders.clone().sub(hips).normalize(),side=q[12].clone().sub(q[11]).normalize();
  const front=new THREE.Vector3().crossVectors(side,up).normalize();
  const head=q[0].clone().addScaledVector(front,-.08).addScaledVector(up,.035);
  const delta=head.clone().sub(shoulders),neckLength=THREE.MathUtils.clamp(delta.length(),.20,.27);
  head.copy(shoulders).addScaledVector(delta.normalize(),neckLength);
  const pairs=[[hips,shoulders],[shoulders,head],[head.clone().addScaledVector(up,-.13),head.clone().addScaledVector(up,.13)]];
  for(const [s,e,w] of [[11,13,15],[12,14,16]])pairs.push([q[s],q[e]],[q[e],q[w]],[q[w],q[w].clone().addScaledVector(q[w].clone().sub(q[e]).normalize(),.095)]);
  for(const [h,k,a,t] of [[23,25,27,31],[24,26,28,32]])pairs.push([q[h],q[k]],[q[k],q[a]],[q[a],q[t]]);
  return pairs;
}

export function poseAvatar(figure,person,next=null,alpha=0){
  figure.group.visible=!!person?.joints;if(!person?.joints)return;
  const current=person.render_joints??person.joints;
  const following=next?.joints?(next.render_joints??next.joints):null;
  const q=current.map((p,i)=>{const a=vector(p);return following?a.lerp(vector(following[i]),alpha):a});
  endpoints(q).forEach(([a,b],i)=>{const d=b.clone().sub(a),length=d.length(),bone=figure.bones[i];bone.position.copy(a);bone.quaternion.setFromUnitVectors(Y,d.normalize());bone.scale.set(1,length/figure.lengths[i],1)});
  const direction=q[16].clone().sub(q[14]).normalize();figure.racket.position.copy(q[16]);figure.racket.quaternion.setFromUnitVectors(Z,direction);
}
