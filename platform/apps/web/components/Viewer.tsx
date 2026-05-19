"use client";

import { Canvas, useLoader } from "@react-three/fiber";
import { OrbitControls, Grid, Center, Environment } from "@react-three/drei";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { Suspense, useMemo } from "react";
import * as THREE from "three";

function ObjMesh({ url }: { url: string }) {
  const obj = useLoader(OBJLoader, url);
  const mat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: 0x6aa9ff,
        metalness: 0.08,
        roughness: 0.55,
      }),
    []
  );
  obj.traverse((c: any) => {
    if (c.isMesh) {
      c.material = mat;
      c.geometry.computeVertexNormals();
    }
  });
  return (
    <Center>
      <primitive object={obj} />
    </Center>
  );
}

export default function Viewer({ url }: { url?: string }) {
  return (
    <div className="viewer">
      <Canvas camera={{ position: [80, 60, 80], fov: 45 }} shadows>
        <color attach="background" args={["#06080d"]} />
        <ambientLight intensity={0.45} />
        <directionalLight position={[80, 120, 100]} intensity={1.1} castShadow />
        <directionalLight position={[-60, 30, -60]} intensity={0.35} color="#88aaff" />
        <Grid
          args={[400, 400]}
          cellSize={10}
          sectionSize={50}
          cellColor="#1f2530"
          sectionColor="#2a3142"
          fadeDistance={300}
          infiniteGrid
        />
        <Suspense fallback={null}>
          {url && <ObjMesh url={url} />}
          <Environment preset="city" />
        </Suspense>
        <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
      </Canvas>
    </div>
  );
}
