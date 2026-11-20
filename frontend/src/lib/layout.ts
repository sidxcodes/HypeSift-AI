// Gameplay (facecam) layout shared by the editor preview and controls.
// Mirrors backend/app/pipeline/render.py facecam_layout(): keep the two in sync.

export type PanelAdj = { x: number; y: number; w: number };
export type GameLayout = { split?: number; cam?: Partial<PanelAdj>; game?: Partial<PanelAdj>; swap?: boolean };
export type Rect = [number, number, number, number]; // x, y, w, h in source pixels

export const FACECAM_TOP = 0.4;
const DEFAULT_CAM_BOX: [number, number, number, number] = [0, 0, 0.3, 0.3];

function cropForRatio(sw: number, sh: number, ratio: number): [number, number] {
  return sw / sh > ratio ? [sh * ratio, sh] : [sw, sw / ratio];
}

function panelCrop(sw: number, sh: number, ratio: number, adj: PanelAdj): Rect {
  let cw = Math.max(16, adj.w * sw);
  let ch = cw / ratio;
  if (ch > sh) {
    ch = sh;
    cw = sh * ratio;
  }
  if (cw > sw) {
    cw = sw;
    ch = sw / ratio;
  }
  const x = Math.min(Math.max(adj.x * sw - cw / 2, 0), sw - cw);
  const y = Math.min(Math.max(adj.y * sh - ch / 2, 0), sh - ch);
  return [x, y, cw, ch];
}

export function facecamLayout(sw: number, sh: number, W: number, H: number, box: number[] | null | undefined, lay: GameLayout | null | undefined) {
  const l = lay ?? {};
  const split = Math.max(0.2, Math.min(0.7, l.split ?? FACECAM_TOP));
  const camH = H * split;
  const gameH = H - camH;
  const [bx, by, bw, bh] = box && box.length === 4 ? box : DEFAULT_CAM_BOX;
  const rCam = W / camH;
  const fw = bw * sw;
  const fh = bh * sh;
  const cw = fw / Math.max(fh, 1) > rCam ? fh * rCam : fw;
  const camDef: PanelAdj = { x: bx + bw / 2, y: by + bh / 2, w: cw / sw };
  const [gw] = cropForRatio(sw, sh, W / gameH);
  let gx = (sw - gw) / 2;
  const camL = bx * sw;
  const camR = (bx + bw) * sw;
  if (camR > gx && camL < gx + gw) gx = (camL + camR) / 2 < sw / 2 ? Math.max(gx, Math.min(camR, sw - gw)) : Math.min(gx, Math.max(camL - gw, 0));
  const gameDef: PanelAdj = { x: (gx + gw / 2) / sw, y: 0.5, w: gw / sw };
  const cam: PanelAdj = { ...camDef, ...strip(l.cam) };
  const game: PanelAdj = { ...gameDef, ...strip(l.game) };
  return {
    split,
    camH,
    gameH,
    cam,
    game,
    camRect: panelCrop(sw, sh, rCam, cam),
    gameRect: panelCrop(sw, sh, W / gameH, game),
    swap: !!l.swap,
    seam: l.swap ? 1 - split : split,
  };
}

function strip(p?: Partial<PanelAdj>): Partial<PanelAdj> {
  const out: Partial<PanelAdj> = {};
  for (const k of ["x", "y", "w"] as const) if (p?.[k] != null) out[k] = p[k];
  return out;
}
