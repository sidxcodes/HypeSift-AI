"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Clip, ComparePlay, Overlay, Pos, TitleStyle } from "@/lib/types";
import { ComparePlayPicker, PositionPicker, TitleStylePicker } from "./Pickers";
import { useToast } from "./toast";
import { Button, Input, Switch } from "./ui";

/** Per-clip layout: hook title design + spot, caption spot, logo spot, comparison play mode. */
export function LayoutPanel({ clip, onChange }: { clip: Clip; onChange: () => void }) {
  const toast = useToast();
  const e = clip.edits;
  const t0 = (e.overlays ?? []).find((o) => o.kind === "title");
  const [titleOn, setTitleOn] = useState(!!t0);
  const [titleText, setTitleText] = useState(t0?.text ?? clip.title);
  const [design, setDesign] = useState<TitleStyle>(t0?.style ?? "impact");
  const [titlePos, setTitlePos] = useState<Pos | null>(t0?.pos ?? null);
  const [capPos, setCapPos] = useState<Pos | null>(((e.captions?.style as { pos?: Pos } | undefined)?.pos as Pos) ?? null);
  const logo = (e as unknown as { logo?: { key?: string; x?: number; y?: number } }).logo;
  const [logoPos, setLogoPos] = useState<Pos | null>(logo?.x != null && logo?.y != null ? { x: logo.x, y: logo.y } : null);
  const multi = (e as unknown as { multi?: { play?: ComparePlay; parts?: unknown[] } }).multi;
  const [play, setPlay] = useState<ComparePlay>(multi?.play ?? "turns");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const others = (e.overlays ?? []).filter((o) => o.kind !== "title");
      const overlays: Overlay[] = titleOn && titleText.trim()
        ? [{ kind: "title", text: titleText.trim(), start: 0, end: 3, style: design, pos: titlePos }, ...others]
        : others;
      const style = { ...(e.captions?.style ?? {}), pos: capPos };
      const edits: Record<string, unknown> = { overlays, captions: { ...e.captions, style } };
      if (logo?.key) {
        const { x: _x, y: _y, ...rest } = logo;
        void _x;
        void _y;
        edits.logo = logoPos ? { ...rest, x: logoPos.x, y: logoPos.y } : rest;
      }
      if (multi?.parts) edits.multi = { play };
      await api.updateClip(clip.id, { edits, render: true });
      toast("success", "Saved. The clip is re-rendering with the new layout.");
      onChange();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Couldn't save.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {multi?.parts && (
        <section>
          <h3 className="mb-2 font-semibold">How the versions play</h3>
          <ComparePlayPicker value={play} onChange={setPlay} />
        </section>
      )}
      <section>
        <Switch checked={titleOn} onChange={setTitleOn} label="Hook title (first 3 seconds)" />
        {titleOn && (
          <div className="mt-3 space-y-3">
            <Input value={titleText} onChange={(ev) => setTitleText(ev.target.value.slice(0, 90))} aria-label="Title text" />
            <TitleStylePicker value={design} onChange={setDesign} bg={clip.thumb_url} />
            <div>
              <div className="mb-1.5 text-xs text-muted">Title position</div>
              <PositionPicker label="Title position" value={titlePos} onChange={setTitlePos} />
            </div>
          </div>
        )}
      </section>
      <section>
        <h3 className="mb-2 font-semibold">Caption position</h3>
        <PositionPicker label="Caption position" value={capPos} onChange={setCapPos} />
      </section>
      {logo?.key && (
        <section>
          <h3 className="mb-2 font-semibold">Logo position</h3>
          <PositionPicker label="Logo position" value={logoPos} onChange={setLogoPos} />
        </section>
      )}
      <Button onClick={save} loading={busy}>
        Save &amp; re-render
      </Button>
    </div>
  );
}
