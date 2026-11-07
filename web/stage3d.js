// 3D の舞台: 地面の盤面（5 m／25 m の二重グリッド）、敷地の台、光、包絡の殻。
// 見え方だけを受け持つ。座標・距離・判定の値はここで作らない（engine/ の結果を描くだけ）。
import * as THREE from './vendor/three/three.module.js';

export const STAGE = {
  bg: 0x0b0f14,          // 空（画面の地）
  ground: [0.071, 0.090, 0.110],
  minor: [0.125, 0.155, 0.185],
  major: [0.200, 0.250, 0.300],
  pad: [0.115, 0.150, 0.185],
  edge: 0x5fd0ff,        // 敷地の縁（HUD の線色）
};

// 舞台を用意する。主画面と取込タブの小さい 3D の両方で使う
export function setupStage(scene, renderer) {
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  scene.background = new THREE.Color(STAGE.bg);
  scene.fog = new THREE.Fog(STAGE.bg, 280, 760);
  scene.add(new THREE.HemisphereLight(0xd8e6f5, 0x1a2028, 1.25));
  const sun = new THREE.DirectionalLight(0xfff4e6, 1.9); sun.position.set(-70, -40, 140); scene.add(sun);
  const fill = new THREE.DirectionalLight(0x9fc4ff, 0.55); fill.position.set(90, 120, 60); scene.add(fill);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(1600, 1600), groundMaterial());
  ground.position.z = -0.03; ground.renderOrder = -2; scene.add(ground);
  return { ground };
}

// グリッドは画面上の線幅が一定になるよう fwidth で描く（遠くでちらつかない）
function groundMaterial() {
  return new THREE.ShaderMaterial({
    toneMapped: false, depthWrite: true,
    uniforms: {
      base: { value: new THREE.Vector3(...STAGE.ground) },
      minorC: { value: new THREE.Vector3(...STAGE.minor) },
      majorC: { value: new THREE.Vector3(...STAGE.major) },
      sky: { value: new THREE.Color(STAGE.bg) },
    },
    vertexShader: `varying vec3 vW; varying float vD;
      void main(){ vec4 w = modelMatrix * vec4(position,1.0); vW = w.xyz; vec4 v = viewMatrix * w; vD = -v.z; gl_Position = projectionMatrix * v; }`,
    fragmentShader: `uniform vec3 base, minorC, majorC, sky; varying vec3 vW; varying float vD;
      float line(vec2 p, float s, float wpx){ vec2 q = p / s; vec2 g = abs(fract(q - 0.5) - 0.5) / fwidth(q); return 1.0 - clamp(min(g.x, g.y) - (wpx - 1.0), 0.0, 1.0); }
      void main(){
        vec3 c = base;
        c = mix(c, minorC, line(vW.xy, 5.0, 1.0) * 0.85);
        c = mix(c, majorC, line(vW.xy, 25.0, 1.4));
        float f = smoothstep(300.0, 720.0, vD);
        gl_FragColor = vec4(mix(c, sky, f), 1.0);
      }`,
  });
}

// 敷地の台: 構内（柵の内側）を一段明るい盤にし、縁と四隅の鍵形を描く
export function sitePad(fence) {
  const g = new THREE.Group();
  const { x = 0, y = 0, w = 135, h = 125 } = fence || {};
  const pad = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(...STAGE.pad, THREE.SRGBColorSpace), transparent: true, opacity: 0.6, depthWrite: false, toneMapped: false }));
  pad.position.set(x + w / 2, y + h / 2, -0.01); pad.renderOrder = -1; g.add(pad);
  const z = 0.02, P = (a, b) => new THREE.Vector3(a, b, z);
  const rim = [P(x, y), P(x + w, y), P(x + w, y + h), P(x, y + h), P(x, y)];
  g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(rim), new THREE.LineBasicMaterial({ color: STAGE.edge, transparent: true, opacity: 0.35, toneMapped: false })));
  const k = Math.min(w, h) * 0.06, br = [];
  for (const [cx, cy, sx, sy] of [[x, y, 1, 1], [x + w, y, -1, 1], [x + w, y + h, -1, -1], [x, y + h, 1, -1]])
    br.push(P(cx, cy), P(cx + sx * k, cy), P(cx, cy), P(cx, cy + sy * k));
  g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(br), new THREE.LineBasicMaterial({ color: STAGE.edge, toneMapped: false })));
  return g;
}

// 包絡（近づけない範囲）を 1 つの殻として描く。
// 1) 奥行きだけを書く下塗り 2) いちばん手前の面だけに色を塗る。重なっても濃くならず、縁だけが光る
export function envelopeShell(primitives, color = 0xff4d4d) {
  const g = new THREE.Group();
  if (!primitives.length) return g;
  const geo = mergeCapsules(primitives);
  const pre = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: true, transparent: true }));
  pre.renderOrder = 10; g.add(pre);
  const shell = new THREE.Mesh(geo, new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, depthFunc: THREE.LessEqualDepth, toneMapped: false,
    uniforms: { col: { value: new THREE.Color(color) } },
    vertexShader: `varying vec3 vN; varying vec3 vV;
      void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vN = normalize(normalMatrix * normal); vV = -mv.xyz; gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform vec3 col; varying vec3 vN; varying vec3 vV;
      void main(){ float r = 1.0 - abs(dot(normalize(vN), normalize(vV))); float a = 0.07 + 0.55 * pow(r, 3.0);
        gl_FragColor = vec4(col * (0.75 + 0.6 * r), a); }`,
  }));
  shell.renderOrder = 11; g.add(shell);
  return g;
}

// カプセルを 1 つの形にまとめる（数百本でも描画 2 回で済む）
function mergeCapsules(prims) {
  const pos = [], nor = [], idx = []; let base = 0;
  const up = new THREE.Vector3(0, 1, 0), m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1);
  const nm = new THREE.Matrix3(), v = new THREE.Vector3();
  for (const p of prims) {
    const a = new THREE.Vector3(...p.a), b = new THREE.Vector3(...p.b), len = a.distanceTo(b);
    const c = new THREE.CapsuleGeometry(p.r, len, 3, 12);
    const dir = len > 1e-6 ? b.clone().sub(a).normalize() : up;
    q.setFromUnitVectors(up, dir); m.compose(a.clone().add(b).multiplyScalar(0.5), q, s); nm.getNormalMatrix(m);
    const P = c.attributes.position, N = c.attributes.normal;
    for (let i = 0; i < P.count; i++) {
      v.fromBufferAttribute(P, i).applyMatrix4(m); pos.push(v.x, v.y, v.z);
      v.fromBufferAttribute(N, i).applyMatrix3(nm).normalize(); nor.push(v.x, v.y, v.z);
    }
    const I = c.index.array; for (let i = 0; i < I.length; i++) idx.push(I[i] + base);
    base += P.count; c.dispose();
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  geo.setIndex(idx);
  return geo;
}
