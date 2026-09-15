"""
Modulo B, passo 2/2: rende una scene_spec (JSON) come scena Three.js
navigabile. Deterministico -- nessuna AI qui, solo template Unity/Three.js
come discusso nel report (S1.9, punto 3): l'agente sceglie e parametrizza,
il rendering e' un motore fisso.

Uso:
    python3 render_scene.py --spec data/example_scene_spec.json --out ../outputs/scene.html
    python3 render_scene.py --spec data/scene_spec.json --background bg.png --out ../outputs/scene.html
"""
import argparse
import base64
import json
from pathlib import Path

HERE = Path(__file__).parent

SCENE_HTML_TEMPLATE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="margin:0;background:#0d1013;">
<div style="background:#0d1013;">
  <canvas id="scene-canvas-b" style="width:100%;height:100vh;display:block;cursor:grab;"></canvas>
  <div id="annotations-b" style="position:fixed;top:12px;left:14px;display:flex;gap:8px;flex-wrap:wrap;pointer-events:none;max-width:90%;"></div>
  <div style="position:fixed;top:12px;right:14px;max-width:32%;font-family:sans-serif;color:#c7ccd1;background:rgba(22,27,32,.85);padding:10px 14px;border-radius:6px;">
    <h3 style="margin:0 0 6px 0;">{title}</h3>
    <p style="margin:0;font-size:13px;color:#9aa1a8;">{rationale}</p>
  </div>
</div>
<script>
(function(){{
  function loadScript(src, cb){{
    const s = document.createElement('script');
    s.src = src; s.onload = cb;
    s.onerror = function(){{ console.error('errore caricamento', src); }};
    document.head.appendChild(s);
  }}
  function loadThreeAndControls(cb){{
    if (window.THREE && window.THREE.OrbitControls) {{ cb(); return; }}
    loadScript("https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js", function(){{
      loadScript("https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js", cb);
    }});
  }}

  const spec = __SCENE_SPEC_JSON__;
  const bgImageDataUri = __BG_IMAGE_DATA_URI__;

  loadThreeAndControls(function(){{
    const canvas = document.getElementById('scene-canvas-b');
    const renderer = new THREE.WebGLRenderer({{canvas, antialias:true, alpha:true}});
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 1, 5000);
    scene.add(new THREE.DirectionalLight(0xffffff, 1.0).translateX(600).translateY(900).translateZ(700));
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));

    if (bgImageDataUri) {{
      new THREE.TextureLoader().load(bgImageDataUri, function(tex){{
        tex.colorSpace = THREE.SRGBColorSpace;
        scene.background = tex;
      }});
    }}

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true; controls.dampingFactor = 0.08;
    controls.target.set(0, 200, 0);

    function resize(){{
      const w = canvas.clientWidth || 800, h = canvas.clientHeight || 520;
      renderer.setSize(w, h, false);
      camera.aspect = w/h; camera.updateProjectionMatrix();
    }}

    const DH = [[90,0,0],[-90,0,0],[-90,0,400],[90,0,0],[90,0,390],[-90,0,0],[0,0,0]];
    function deg2rad(d){{return d*Math.PI/180;}}
    function linkTransform(alphaDeg,a,d,thetaDeg){{
      const th=deg2rad(thetaDeg), al=deg2rad(alphaDeg);
      const ct=Math.cos(th), st=Math.sin(th), ca=Math.cos(al), sa=Math.sin(al);
      return [ct,-st*ca,st*sa,a*ct, st,ct*ca,-ct*sa,a*st, 0,sa,ca,d, 0,0,0,1];
    }}
    function mat4mul(A,B){{const C=new Array(16).fill(0);for(let r=0;r<4;r++)for(let c=0;c<4;c++){{let s=0;for(let k=0;k<4;k++)s+=A[r*4+k]*B[k*4+c];C[r*4+c]=s;}}return C;}}
    const IDENTITY=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
    function forwardFrames(qDeg){{
      const frames=[IDENTITY]; let T=IDENTITY;
      for(let i=0;i<7;i++){{const [al,a,d]=DH[i]; T=mat4mul(T, linkTransform(al,a,d,qDeg[i])); frames.push(T);}}
      return frames;
    }}
    function pos(T){{return [T[3],T[7],T[11]];}}
    const REACH_MM = 400+390;

    function makeLabelSprite(text, color){{
      const cnv = document.createElement('canvas');
      const ctx = cnv.getContext('2d');
      const fontSize = 34;
      ctx.font = `600 ${{fontSize}}px monospace`;
      const w = Math.max(120, ctx.measureText(text).width + 28);
      cnv.width = w; cnv.height = fontSize + 20;
      ctx.font = `600 ${{fontSize}}px monospace`;
      ctx.fillStyle = 'rgba(13,16,19,0.85)';
      ctx.fillRect(0,0,cnv.width,cnv.height);
      ctx.fillStyle = color || '#ffffff';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, 10, cnv.height/2);
      const tex = new THREE.CanvasTexture(cnv);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({{map: tex, depthTest:false}}));
      sprite.scale.set(w*0.6, cnv.height*0.6, 1);
      return sprite;
    }}

    function addRobot(highlight){{
      const q = [25,-55,15,85,0,45,0];
      const pts = forwardFrames(q).map(pos);
      const jointMat = new THREE.MeshStandardMaterial({{color:0xc86a1e, roughness:.4, metalness:.3}});
      const linkMat = new THREE.MeshStandardMaterial({{color:0x333b44, roughness:.55, metalness:.25}});
      for(let i=0;i<7;i++){{ const s=new THREE.Mesh(new THREE.SphereGeometry(24,18,14), jointMat); s.position.set(...pts[i+1]); scene.add(s); }}
      for(let i=0;i<6;i++){{
        const a=new THREE.Vector3(...pts[i+1]), b=new THREE.Vector3(...pts[i+2]);
        const mid=a.clone().add(b).multiplyScalar(0.5); const dir=b.clone().sub(a); const len=dir.length();
        const c=new THREE.Mesh(new THREE.CylinderGeometry(12,12,Math.max(len,0.001),12), linkMat);
        c.position.copy(mid);
        if(len>0.001){{ const up=new THREE.Vector3(0,1,0), n=dir.clone().normalize(); const axis=new THREE.Vector3().crossVectors(up,n);
          const angle=Math.acos(Math.min(1,Math.max(-1,up.dot(n)))); if(axis.lengthSq()>1e-8) c.quaternion.setFromAxisAngle(axis.normalize(), angle); }}
        scene.add(c);
      }}
      if(highlight === 'reach_envelope'){{
        scene.add(new THREE.Mesh(new THREE.SphereGeometry(REACH_MM,28,20), new THREE.MeshBasicMaterial({{color:0xc86a1e, transparent:true, opacity:.06}})));
        scene.add(new THREE.Mesh(new THREE.SphereGeometry(REACH_MM,18,12), new THREE.MeshBasicMaterial({{color:0xc86a1e, transparent:true, opacity:.15, wireframe:true}})));
      }} else if (highlight === 'joint_limits') {{
        const label = makeLabelSprite('fine-corsa evidenziati sui giunti', '#e0954a'); label.position.set(0,900,0); scene.add(label);
      }}
      return pts[7];
    }}

    function addTargetMarker(el, nearPos){{
      const colorMap = {{reachable:0x2f8f7a, unreachable:0xb23b3b, unknown:0x8a929d}};
      const color = colorMap[el.reachable_hint] || colorMap.unknown;
      const p = nearPos ? [nearPos[0]+120, nearPos[1]-40, nearPos[2]+80] : [400,0,400];
      const m = new THREE.Mesh(new THREE.SphereGeometry(22,16,12), new THREE.MeshStandardMaterial({{color}})); m.position.set(...p); scene.add(m);
      const label = makeLabelSprite(el.label || 'bersaglio', '#ffffff'); label.position.set(p[0],p[1]+60,p[2]); scene.add(label);
    }}

    function addTissueBlock(el){{
      const m = new THREE.Mesh(new THREE.BoxGeometry(260,90,180), new THREE.MeshStandardMaterial({{color:0xb23b3b, transparent:true, opacity:.35, roughness:.7}}));
      m.position.set(-260,-40,200); scene.add(m);
      const label = makeLabelSprite(el.label || 'tessuto/fantoccio', '#f4dbdb'); label.position.set(-260,20,200); scene.add(label);
    }}

    function addBiochemDiagram(el){{
      const count = Math.max(4, Math.min(12, el.count || 8));
      const style = el.style === 'catena' ? 'catena' : 'ciclo';
      const radius = 260;
      const nodeMat = new THREE.MeshStandardMaterial({{color:0x333b44, roughness:.5, metalness:.2}});
      const hiMat = new THREE.MeshStandardMaterial({{color:0xc86a1e, roughness:.4, metalness:.3, emissive:0x3a2004, emissiveIntensity:.5}});
      const bondMat = new THREE.MeshStandardMaterial({{color:0x8a929d, roughness:.6}});
      const nodePositions = [];
      for(let i=0;i<count;i++){{
        let p;
        if (style === 'ciclo'){{ const a=(i/count)*Math.PI*2; p=[Math.cos(a)*radius,60,Math.sin(a)*radius]; }}
        else {{ p=[(i-count/2)*90,60,0]; }}
        nodePositions.push(p);
        const isHi = el.highlight_index === i;
        const m = new THREE.Mesh(new THREE.SphereGeometry(isHi?26:18,16,12), isHi?hiMat:nodeMat); m.position.set(...p); scene.add(m);
        const lbl = (el.labels && el.labels[i]) || `${{i+1}}`;
        const s = makeLabelSprite(lbl, isHi?'#f0dcc4':'#c7ccd1'); s.position.set(p[0],p[1]+46,p[2]); scene.add(s);
      }}
      const n = style === 'ciclo' ? count : count-1;
      for(let i=0;i<n;i++){{
        const a=nodePositions[i], b=nodePositions[(i+1)%nodePositions.length];
        const va=new THREE.Vector3(...a), vb=new THREE.Vector3(...b);
        const mid=va.clone().add(vb).multiplyScalar(0.5); const dir=vb.clone().sub(va); const len=dir.length();
        const c=new THREE.Mesh(new THREE.CylinderGeometry(4,4,len,8), bondMat); c.position.copy(mid);
        const up=new THREE.Vector3(0,1,0), nn=dir.clone().normalize(); const axis=new THREE.Vector3().crossVectors(up,nn);
        const angle=Math.acos(Math.min(1,Math.max(-1,up.dot(nn)))); if(axis.lengthSq()>1e-8) c.quaternion.setFromAxisAngle(axis.normalize(), angle);
        scene.add(c);
      }}
    }}

    function frameCamera(preset){{
      const presets = {{frontale:[1100,500,1300], dall_alto:[10,1500,10], laterale:[1500,400,10]}};
      const p = presets[preset] || presets.frontale;
      camera.position.set(...p);
    }}

    let robotTip = null;
    (spec.elements || []).forEach(el => {{
      try {{
        if (el.type === 'robot_kuka') robotTip = addRobot(el.highlight);
        else if (el.type === 'target_marker') addTargetMarker(el, robotTip);
        else if (el.type === 'tissue_block') addTissueBlock(el);
        else if (el.type === 'biochem_diagram') addBiochemDiagram(el);
      }} catch(e) {{ console.warn('elemento non renderizzato:', el, e); }}
    }});
    frameCamera(spec.camera);
    resize();
    window.addEventListener('resize', resize);

    const ann = document.getElementById('annotations-b');
    const cards = (spec.annotations || []).slice(0,3);
    (spec.elements||[]).filter(e=>e.type==='label_card').forEach(e=>cards.push(e.text));
    cards.forEach(text => {{
      const d = document.createElement('div');
      d.style.cssText = 'font-family:monospace;font-size:11px;padding:6px 9px;border-radius:3px;background:rgba(22,27,32,.85);color:#c7ccd1;border:1px solid rgba(236,238,239,.14);';
      d.textContent = text; ann.appendChild(d);
    }});

    function animate(){{
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }}
    animate();
  }});
}})();
</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", default=str(HERE / "data" / "example_scene_spec.json"))
    ap.add_argument("--background", help="Immagine PNG/JPG opzionale da usare come sfondo (es. da SD-Turbo)")
    ap.add_argument("--out", default=str(HERE.parent / "outputs" / "scene.html"))
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text())

    bg_data_uri = "null"
    if args.background:
        img_bytes = Path(args.background).read_bytes()
        b64 = base64.b64encode(img_bytes).decode()
        ext = Path(args.background).suffix.lstrip(".") or "png"
        bg_data_uri = json.dumps(f"data:image/{ext};base64,{b64}")

    html = SCENE_HTML_TEMPLATE.format(title=spec.get("title", "Scenario"), rationale=spec.get("rationale", ""))
    html = html.replace("__SCENE_SPEC_JSON__", json.dumps(spec, ensure_ascii=False))
    html = html.replace("__BG_IMAGE_DATA_URI__", bg_data_uri)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    print(f"Scritto {out_path} — apri nel browser per vedere la scena.")


if __name__ == "__main__":
    main()
