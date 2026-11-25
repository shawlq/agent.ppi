import * as THREE from "three";

/**
 * Orbit around a focus point: drag rotate, wheel zoom, double-click
 * moves focus horizontally on the ground while keeping focus.y fixed.
 */
export class CameraFocus {
  /**
   * @param {THREE.PerspectiveCamera} camera
   * @param {HTMLElement} dom
   * @param {THREE.Object3D} ground
   * @param {{ focusHeight?: number, distance?: number }} opts
   */
  constructor(camera, dom, ground, opts = {}) {
    this.camera = camera;
    this.dom = dom;
    this.ground = ground;
    this.focus = new THREE.Vector3(0, opts.focusHeight ?? 1.7, 0);
    this.distance = opts.distance ?? 4.5;
    this.spherical = new THREE.Spherical(this.distance, Math.PI / 3.2, Math.PI / 4);
    this.minPolar = 0.15;
    this.maxPolar = Math.PI / 2 - 0.05;
    this.minDist = 1.2;
    this.maxDist = 14;

    this._dragging = false;
    this._moved = false;
    this._lastX = 0;
    this._lastY = 0;
    this._raycaster = new THREE.Raycaster();
    this._pointer = new THREE.Vector2();
    this._focusMarker = this._makeMarker();

    this._onPointerDown = this._onPointerDown.bind(this);
    this._onPointerMove = this._onPointerMove.bind(this);
    this._onPointerUp = this._onPointerUp.bind(this);
    this._onWheel = this._onWheel.bind(this);
    this._onDblClick = this._onDblClick.bind(this);

    dom.addEventListener("pointerdown", this._onPointerDown);
    window.addEventListener("pointermove", this._onPointerMove);
    window.addEventListener("pointerup", this._onPointerUp);
    dom.addEventListener("wheel", this._onWheel, { passive: false });
    dom.addEventListener("dblclick", this._onDblClick);

    this.updateCamera();
  }

  _makeMarker() {
    const g = new THREE.Group();
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.12, 0.16, 32),
      new THREE.MeshBasicMaterial({
        color: 0x4fc3f7,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.85,
        depthTest: false,
      })
    );
    ring.rotation.x = -Math.PI / 2;
    const pole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.015, 0.015, 1, 8),
      new THREE.MeshBasicMaterial({
        color: 0x4fc3f7,
        transparent: true,
        opacity: 0.35,
        depthTest: false,
      })
    );
    pole.position.y = 0.5;
    g.add(ring, pole);
    g.renderOrder = 999;
    return g;
  }

  get marker() {
    return this._focusMarker;
  }

  setFocusHeight(h) {
    this.focus.y = h;
    this._syncMarker();
    this.updateCamera();
  }

  getFocusHeight() {
    return this.focus.y;
  }

  _syncMarker() {
    this._focusMarker.position.set(this.focus.x, 0.01, this.focus.z);
    const pole = this._focusMarker.children[1];
    if (pole) {
      pole.scale.y = Math.max(0.1, this.focus.y);
      pole.position.y = this.focus.y / 2;
      // cylinder default height 1 → scale.y stretches it
    }
  }

  updateCamera() {
    this.spherical.radius = this.distance;
    this.spherical.phi = THREE.MathUtils.clamp(
      this.spherical.phi,
      this.minPolar,
      this.maxPolar
    );
    const offset = new THREE.Vector3().setFromSpherical(this.spherical);
    this.camera.position.copy(this.focus).add(offset);
    this.camera.lookAt(this.focus);
    this._syncMarker();
  }

  _onPointerDown(e) {
    if (e.button !== 0) return;
    this._dragging = true;
    this._moved = false;
    this._lastX = e.clientX;
    this._lastY = e.clientY;
    this.dom.setPointerCapture?.(e.pointerId);
  }

  _onPointerMove(e) {
    if (!this._dragging) return;
    const dx = e.clientX - this._lastX;
    const dy = e.clientY - this._lastY;
    if (Math.abs(dx) + Math.abs(dy) > 2) this._moved = true;
    this._lastX = e.clientX;
    this._lastY = e.clientY;
    this.spherical.theta -= dx * 0.005;
    this.spherical.phi -= dy * 0.005;
    this.updateCamera();
  }

  _onPointerUp() {
    this._dragging = false;
  }

  _onWheel(e) {
    e.preventDefault();
    this.distance *= e.deltaY > 0 ? 1.08 : 0.92;
    this.distance = THREE.MathUtils.clamp(this.distance, this.minDist, this.maxDist);
    this.updateCamera();
  }

  _onDblClick(e) {
    const rect = this.dom.getBoundingClientRect();
    this._pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this._pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    this._raycaster.setFromCamera(this._pointer, this.camera);
    const hits = this._raycaster.intersectObject(this.ground, false);
    if (!hits.length) return;
    const p = hits[0].point;
    this.focus.x = p.x;
    this.focus.z = p.z;
    // y stays at configured focus height
    this.updateCamera();
  }

  dispose() {
    this.dom.removeEventListener("pointerdown", this._onPointerDown);
    window.removeEventListener("pointermove", this._onPointerMove);
    window.removeEventListener("pointerup", this._onPointerUp);
    this.dom.removeEventListener("wheel", this._onWheel);
    this.dom.removeEventListener("dblclick", this._onDblClick);
  }
}
