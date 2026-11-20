"use client";

import { PageHeader } from "@/components/AppShell";
import { Save } from "lucide-react";
import { useState } from "react";
import { useSession } from "@/components/AppShell";
import { PLATFORM_META, PlatformIcon } from "@/components/PostDrawer";
import { useToast } from "@/components/toast";
import { Button, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";

const PLACEHOLDER: Record<string, string> = {
  youtube: "@yourchannel",
  tiktok: "@yourname",
  instagram: "@yourname",
  linkedin: "linkedin.com/in/you",
  facebook: "facebook.com/yourpage",
  x: "@yourname",
};

export default function SocialsPage() {
  const { user, setUser } = useSession();
  const toast = useToast();
  const [socials, setSocials] = useState<Record<string, string>>(user.brand_kit?.socials ?? {});
  const [tz, setTz] = useState(user.brand_kit?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [saving, setSaving] = useState(false);
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [tz];

  const save = async () => {
    setSaving(true);
    try {
      setUser(await api.saveBrandKit({ socials, timezone: tz }));
      toast("success", "Social profiles saved.");
    } catch (e) {
      toast("error", (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader title="Social profiles" />
      <div className="max-w-2xl">
        <p className="mt-1 text-sm text-muted">
          Your handles appear in the post drawer, and the time zone is used for scheduling. HypeSift doesn&apos;t log in to
          your accounts: “Post now” opens each platform&apos;s own upload page with your video and text ready.
        </p>
      </div>
      <div className="divide-y divide-border rounded-2xl border border-border">
        {Object.entries(PLATFORM_META).map(([p, m]) => (
          <label key={p} className="flex items-center gap-3 px-4 py-3">
            <PlatformIcon p={p} />
            <span className="w-24 text-sm font-medium">{m.label}</span>
            <Input
              value={socials[p] ?? ""}
              onChange={(e) => setSocials((s) => ({ ...s, [p]: e.target.value }))}
              placeholder={PLACEHOLDER[p]}
              className="h-9 flex-1"
              aria-label={`${m.label} handle`}
            />
          </label>
        ))}
      </div>
      <label className="block max-w-sm text-sm font-medium">
        Time zone for scheduling
        <Select value={tz} onChange={setTz} options={zones.map((z) => ({ value: z, label: z.replace(/_/g, " ") }))} className="mt-1.5" />
      </label>
      <Button onClick={save} loading={saving}>
        <Save className="size-4" /> Save
      </Button>
    </div>
  );
}
