import { useEffect, useRef, useState } from "react";
import { useMotionPreference } from "../lib/motion";
/** Decorative WebGL sculpture. Lazy module, visibility-paused rendering, full disposal. */
export default function Sculpture() {
  const host = useRef<HTMLDivElement>(null);
  const reduced = useMotionPreference();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    const el = host.current;
    if (!el) return;
    import("../lib/three")
      .then((THREE) => {
        if (disposed) return;
        let renderer: InstanceType<typeof THREE.WebGLRenderer>;
        try {
          renderer = new THREE.WebGLRenderer({
            alpha: true,
            antialias: true,
            powerPreference: "low-power",
          });
        } catch {
          return;
        }
        renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
        el.appendChild(renderer.domElement);
        renderer.setClearColor(0x000000, 0);
        const scene = new THREE.Scene(),
          camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
        camera.position.z = 8;
        const geometry = new THREE.TorusKnotGeometry(1.15, 0.37, 180, 28, 2, 3);
        const material = new THREE.MeshPhysicalMaterial({
          color: 0xc66b47,
          roughness: 0.33,
          metalness: 0.32,
          clearcoat: 0.25,
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.rotation.set(0.35, 0.25, -0.3);
        scene.add(mesh);
        scene.add(new THREE.HemisphereLight(0xfff8e7, 0x665747, 3));
        const light = new THREE.DirectionalLight(0xffffff, 4);
        light.position.set(4, 5, 4);
        scene.add(light);
        const rim = new THREE.DirectionalLight(0xffbe87, 2);
        rim.position.set(-4, -2, 2);
        scene.add(rim);
        let frame = 0,
          visible = true,
          x = 0,
          y = 0,
          t = 0;
        const resize = () => {
          const w = el.clientWidth,
            h = el.clientHeight;
          renderer.setSize(w, h);
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          if (reduced) renderer.render(scene, camera);
        };
        resize();
        const ro = new ResizeObserver(resize);
        ro.observe(el);
        const move = (event: PointerEvent) => {
          if (reduced) return;
          const rect = el.getBoundingClientRect();
          x = (event.clientX - rect.left) / rect.width - 0.5;
          y = (event.clientY - rect.top) / rect.height - 0.5;
        };
        const leave = () => {
          x = 0;
          y = 0;
        };
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerleave", leave);
        const draw = () => {
          if (disposed) return;
          if (reduced) {
            renderer.render(scene, camera);
            return;
          }
          if (visible && !document.hidden) {
            t += 0.006;
            mesh.rotation.x += (y * 0.65 + 0.35 - mesh.rotation.x) * 0.04;
            mesh.rotation.y +=
              (x * 0.9 +
                (reduced ? 0.25 : Math.sin(t * 0.4) * 0.18) -
                mesh.rotation.y) *
              0.04;
            mesh.rotation.z = -0.3 + Math.min(window.scrollY * 0.0003, 0.3);
            mesh.position.y = reduced ? 0 : Math.sin(t) * 0.06;
            renderer.render(scene, camera);
          }
          frame = requestAnimationFrame(draw);
        };
        draw();
        setReady(true);
        const observer = new IntersectionObserver(([entry]) => {
          visible = entry.isIntersecting;
        });
        observer.observe(el);
        cleanup = () => {
          cancelAnimationFrame(frame);
          ro.disconnect();
          observer.disconnect();
          el.removeEventListener("pointermove", move);
          el.removeEventListener("pointerleave", leave);
          geometry.dispose();
          material.dispose();
          renderer.dispose();
          renderer.domElement.remove();
        };
      })
      .catch(() => {});
    return () => {
      disposed = true;
      cleanup();
    };
  }, [reduced]);
  return (
    <div className="sculpture" ref={host} aria-hidden="true">
      {!ready && <div className="sculpture-fallback" />}
      <div className="sculpture-shadow" />
    </div>
  );
}
