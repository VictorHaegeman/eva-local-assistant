import { useEffect, useRef } from "react";

function useEvaParticleSphere(containerRef, ready) {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    let disposed = false;
    let cleanup = () => {};

    async function mountSphere() {
      const THREE = await import("three");
      if (disposed || !container.isConnected) return;

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
      camera.position.z = 5.1;

      const renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        preserveDrawingBuffer: true,
        powerPreference: "high-performance",
      });
      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      container.appendChild(renderer.domElement);

      const group = new THREE.Group();
      scene.add(group);

      const shellGeometry = new THREE.BufferGeometry();
      const shellCount = 2100;
      const shellPositions = new Float32Array(shellCount * 3);
      const shellColors = new Float32Array(shellCount * 3);
      const cyan = new THREE.Color(0x38cfff);
      const deep = new THREE.Color(0x126dff);
      const white = new THREE.Color(0xdff8ff);

      for (let index = 0; index < shellCount; index += 1) {
        const offset = 2 / shellCount;
        const y = index * offset - 1 + offset / 2;
        const radiusAtY = Math.sqrt(1 - y * y);
        const theta = index * Math.PI * (3 - Math.sqrt(5));
        const surfaceNoise =
          0.95 + Math.sin(index * 13.7) * 0.035 + Math.cos(index * 5.9) * 0.028;
        const radius = 1.62 * surfaceNoise;
        const x = Math.cos(theta) * radiusAtY * radius;
        const z = Math.sin(theta) * radiusAtY * radius;

        shellPositions[index * 3] = x;
        shellPositions[index * 3 + 1] = y * radius;
        shellPositions[index * 3 + 2] = z;

        const color = cyan
          .clone()
          .lerp(deep, Math.abs(y) * 0.42)
          .lerp(white, index % 17 === 0 ? 0.34 : 0);
        shellColors[index * 3] = color.r;
        shellColors[index * 3 + 1] = color.g;
        shellColors[index * 3 + 2] = color.b;
      }

      shellGeometry.setAttribute("position", new THREE.BufferAttribute(shellPositions, 3));
      shellGeometry.setAttribute("color", new THREE.BufferAttribute(shellColors, 3));

      const shellMaterial = new THREE.PointsMaterial({
        size: 0.024,
        vertexColors: true,
        transparent: true,
        opacity: ready ? 0.95 : 0.62,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });

      const shell = new THREE.Points(shellGeometry, shellMaterial);
      group.add(shell);

      const coreGeometry = new THREE.BufferGeometry();
      const coreCount = 520;
      const corePositions = new Float32Array(coreCount * 3);
      for (let index = 0; index < coreCount; index += 1) {
        const r = 1.15 * Math.cbrt((index + 1) / coreCount);
        const theta = index * 2.3999632297;
        const y = Math.sin(index * 1.17) * r * 0.62;
        const ring = Math.sqrt(Math.max(0, r * r - y * y));
        corePositions[index * 3] = Math.cos(theta) * ring;
        corePositions[index * 3 + 1] = y;
        corePositions[index * 3 + 2] = Math.sin(theta) * ring;
      }
      coreGeometry.setAttribute("position", new THREE.BufferAttribute(corePositions, 3));
      const core = new THREE.Points(
        coreGeometry,
        new THREE.PointsMaterial({
          color: 0x71ddff,
          size: 0.018,
          transparent: true,
          opacity: 0.24,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      );
      group.add(core);

      const haloGeometry = new THREE.TorusGeometry(1.86, 0.004, 8, 180);
      const haloMaterial = new THREE.MeshBasicMaterial({
        color: 0x59d9ff,
        transparent: true,
        opacity: 0.36,
        blending: THREE.AdditiveBlending,
      });
      const halo = new THREE.Mesh(haloGeometry, haloMaterial);
      halo.rotation.x = Math.PI / 2.7;
      group.add(halo);

      const resize = () => {
        const rect = container.getBoundingClientRect();
        const width = Math.max(1, Math.floor(rect.width));
        const height = Math.max(1, Math.floor(rect.height));
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height, false);
      };

      const resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(container);
      resize();

      let frameId = 0;
      const clock = new THREE.Clock();
      const animate = () => {
        const elapsed = clock.getElapsedTime();
        group.rotation.y = elapsed * 0.18;
        group.rotation.x = Math.sin(elapsed * 0.32) * 0.14;
        shell.rotation.z = elapsed * 0.045;
        core.rotation.y = -elapsed * 0.28;
        halo.rotation.z = elapsed * 0.34;
        shellMaterial.opacity = ready ? 0.88 + Math.sin(elapsed * 1.8) * 0.08 : 0.58;
        renderer.render(scene, camera);
        frameId = window.requestAnimationFrame(animate);
      };
      animate();

      cleanup = () => {
        window.cancelAnimationFrame(frameId);
        resizeObserver.disconnect();
        shellGeometry.dispose();
        shellMaterial.dispose();
        coreGeometry.dispose();
        core.material.dispose();
        haloGeometry.dispose();
        haloMaterial.dispose();
        renderer.dispose();
        renderer.domElement.remove();
      };
    }

    mountSphere();

    return () => {
      disposed = true;
      cleanup();
    };
  }, [containerRef, ready]);
}

export function EvaOrb({ status }) {
  const isReady = status?.state === "ready";
  const stateLabel = isReady ? "Core local actif" : "Connexion au core";
  const canvasRef = useRef(null);

  useEvaParticleSphere(canvasRef, isReady);

  return (
    <section className="eva-orb-stage" aria-label="Presentation Eva">
      <div className="eva-orb" aria-hidden="true">
        <div className="eva-orb-canvas" ref={canvasRef} />
        <div className="eva-orb-ring ring-one" />
        <div className="eva-orb-ring ring-two" />
        <div className="eva-orb-ring ring-three" />
        <div className="eva-orb-ring ring-four" />
        <div className="eva-orb-axis axis-x" />
        <div className="eva-orb-axis axis-y" />
        <div className="eva-orb-core">
          <span>Eva</span>
        </div>
        <div className="eva-orb-status">
          <span>{isReady ? "ONLINE" : "SYNC"}</span>
          <strong>{status?.model || "local"}</strong>
        </div>
      </div>

      <div className="eva-orb-copy">
        <span className="eyebrow">Assistant local</span>
        <h1>Eva</h1>
        <p>{stateLabel}</p>
      </div>
    </section>
  );
}
