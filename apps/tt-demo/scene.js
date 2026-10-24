import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {createAvatar, poseAvatar} from './avatar.js';

export async function createScene(element, data, options = {}) {
  const response = await fetch('./avatar-high.json');
  if (!response.ok) throw new Error('Continuous avatar asset is unavailable');
  const asset = await response.json();
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: false});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setClearColor(0x0b161e);
  element.append(renderer.domElement);
  const scene = new THREE.Scene(); scene.fog = new THREE.Fog(0x0b161e, 12, 25);
  const camera = new THREE.PerspectiveCamera(43, 1, .025, 60); camera.up.set(0, 0, 1);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, .8); controls.enableDamping = true; controls.minDistance = .2; controls.maxDistance = 16; controls.maxPolarAngle = Math.PI / 2 - .015;
  controls.autoRotateSpeed = .45;
  scene.add(new THREE.HemisphereLight(0xb9e8ff, 0x203540, 2.5));
  const light = new THREE.DirectionalLight(0xe3f6ff, 2.5); light.position.set(-3, -4, 8); scene.add(light);
  const accent = new THREE.DirectionalLight(0x60c5d5, 1.7); accent.position.set(3, 2, 3); scene.add(accent);
  function box(size, position, color, opacity = 1) {
    const material = new THREE.MeshStandardMaterial({color, roughness: .7, transparent: opacity < 1, opacity});
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material); mesh.position.set(...position); scene.add(mesh); return mesh;
  }
  const tableHeight = Number.isFinite(data.table_height_m) ? data.table_height_m : Number.isFinite(data.table?.top_height_m) ? data.table.top_height_m : .76;
  const floorHeight = tableHeight - .76;
  box([15, 13, .025], [0, 0, floorHeight - .025], 0x0d1d26);
  const grid = new THREE.GridHelper(14, 40, 0x2a4a57, 0x17333f); grid.rotation.x = Math.PI / 2; grid.position.z = floorHeight + .001; scene.add(grid);
  box([2.74, 1.525, .04], [0, 0, tableHeight - .02], 0x153b49);
  for (const y of [-.754, .754]) box([2.74, .012, .003], [0, y, tableHeight + .001], 0x92bdc7);
  for (const x of [-1.363, 1.363]) box([.012, 1.525, .003], [x, 0, tableHeight + .001], 0x92bdc7);
  box([2.74, .009, .003], [0, 0, tableHeight + .002], 0x83aeb8);
  for (const x of [-1.02, 1.02]) for (const y of [-.53, .53]) box([.035, .035, .7], [x, y, tableHeight - .39], 0x2b4653);
  for (const y of [-.8, .8]) box([.015, .015, .18], [0, y, tableHeight + .075], 0x7999a4);
  box([.012, 1.6, .008], [0, 0, tableHeight + .1525], 0x9bc2cd);
  const net = new THREE.Mesh(new THREE.PlaneGeometry(1.525, .1525, 32, 5), new THREE.MeshBasicMaterial({color: 0x4a7f91, transparent: true, opacity: .35, wireframe: true, side: THREE.DoubleSide}));
  net.rotation.set(Math.PI / 2, Math.PI / 2, 0); net.position.set(0, 0, tableHeight + .07625); scene.add(net);
  const figures = [createAvatar(asset, 0x62e9e0, 0, scene), createAvatar(asset, 0x72b1ed, 1, scene)];
  figures.forEach((figure) => { figure.group.visible = false; });
  const ball = new THREE.Mesh(new THREE.SphereGeometry(.02, 18, 12), new THREE.MeshStandardMaterial({color: 0xffd09a, emissive: 0x7c4919, emissiveIntensity: .4})); scene.add(ball); ball.visible = false;
  const trail = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({color: 0xfbc58c, transparent: true, opacity: .75})); scene.add(trail);
  const ruler = new THREE.Group(); scene.add(ruler); ruler.visible = false;
  function line(a, b, color) { const result = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...a), new THREE.Vector3(...b)]), new THREE.LineBasicMaterial({color})); ruler.add(result); return result; }
  line([0, 0, 0], [0, 0, .16], 0xebb77f); line([-.08, 0, 0], [.08, 0, 0], 0x759ba6); line([-.08, 0, .16], [.08, 0, .16], 0xebb77f);
  const coneGeometry = new THREE.ConeGeometry(.16 * Math.tan(Math.PI / 6), .16, 24, 1, true);
  const cone = new THREE.Mesh(coneGeometry, new THREE.MeshBasicMaterial({color: 0x6be1d9, transparent: true, opacity: .1, side: THREE.DoubleSide, wireframe: true}));
  cone.rotation.x = Math.PI / 2; cone.position.z = .08; ruler.add(cone);
  let index = 0, destroyed = false;
  const frames = data.frames ?? [];
  function stamp(frame) { return Number(frame?.t ?? frame?.time ?? frame?.t_game_s ?? 0); }
  function players(frame) { return frame?.players ?? []; }
  function position(frame) { return frame?.ball?.position ?? frame?.ball?.pos_m ?? null; }
  function setView(name, point) {
    controls.autoRotate = name === 'orbit';
    const presets = {orbit: [4.2, -5.1, 3.1], side: [0, -5.8, 2.1], diagonal: [4.8, -3.8, 2.5], overhead: [.01, 0, 7.3], serve: [-2.8, -2.4, 1.95], edge: [2.25, -1.9, 1.2]};
    camera.fov = name === 'edge' || name === 'serve' ? 35 : 43;
    const source = (data.cameras ?? []).find((c) => c.id === name || c.role === name);
    if (source?.center && source?.R && options.trusted) {
      camera.position.set(...source.center); const forward = new THREE.Vector3(...source.R[2]); controls.target.copy(camera.position).add(forward);
    } else {
      camera.position.set(...(presets[name] ?? presets.orbit)); controls.target.set(name === 'edge' ? 1.2 : name === 'serve' ? -1.8 : 0, 0, name === 'serve' ? tableHeight + .25 : tableHeight);
    }
    camera.updateProjectionMatrix(); controls.update();
  }
  setView('diagonal');
  function draw(t, point) {
    if (destroyed || !frames.length) return;
    while (index < frames.length - 1 && stamp(frames[index + 1]) <= t) index++;
    while (index > 0 && stamp(frames[index]) > t) index--;
    const frame = frames[index], next = frames[Math.min(index + 1, frames.length - 1)];
    const span = stamp(next) - stamp(frame), alpha = span > 0 && span <= .15 ? Math.max(0, Math.min(1, (t - stamp(frame)) / span)) : 0;
    const stale = Math.abs(t - stamp(frame)) > .2;
    for (let id = 0; id < 2; id++) {
      // Only presentation pose is interpolated. Ball positions remain discrete
      // exported samples and are never derived from an avatar or paddle.
      const person = stale ? null : players(frame).find((p) => p.id === id || p.id === String(id) || p.id === (id ? 'B' : 'A'));
      const following = players(next).find((p) => p.id === id || p.id === String(id) || p.id === (id ? 'B' : 'A'));
      poseAvatar(figures[id], person, following, alpha);
    }
    const p = position(frame); ball.visible = !stale && Array.isArray(p) && p.length === 3 && p.every(Number.isFinite);
    if (ball.visible) ball.position.set(...p);
    const path = [];
    for (let i = Math.max(0, index - 14); i <= index; i++) {
      const value = position(frames[i]);
      if (!value || (i > 0 && stamp(frames[i]) - stamp(frames[i - 1]) > .06)) path.length = 0;
      if (Array.isArray(value) && value.length === 3 && value.every(Number.isFinite)) path.push(new THREE.Vector3(...value));
    }
    trail.geometry.dispose(); trail.geometry = new THREE.BufferGeometry().setFromPoints(path); trail.visible = !stale && path.length > 1;
    const release = point?.release_position_m ?? point?.measurement?.release_position_m ?? (options.synthetic && point?.height_m ? [-1.7, 0, 1.05] : null);
    ruler.visible = options.synthetic && Array.isArray(release) && release.length === 3;
    if (ruler.visible) ruler.position.set(...release);
    controls.update(); renderer.render(scene, camera);
  }
  function resize() { if (destroyed) return; const width = Math.max(1, element.clientWidth), height = Math.max(1, element.clientHeight); renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix(); }
  const observer = new ResizeObserver(resize); observer.observe(element); resize(); draw(0);
  function destroy() {
    destroyed = true; observer.disconnect(); controls.dispose();
    scene.traverse((object) => { object.geometry?.dispose(); if (Array.isArray(object.material)) object.material.forEach((m) => m.dispose()); else object.material?.dispose(); });
    renderer.dispose(); renderer.domElement.remove();
  }
  return {draw, setView, destroy};
}
