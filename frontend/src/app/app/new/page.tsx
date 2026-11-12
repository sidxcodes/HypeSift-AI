import { Suspense } from "react";
import { NewProject } from "@/components/NewProject";

export default function NewProjectPage() {
  return (
    <div>
      <h1 className="font-display text-2xl font-bold tracking-tight">New project</h1>
      <p className="mt-1 text-sm text-muted">Add a video, pick your preferences, and let AI Generate make finished clips.</p>
      <div className="mt-6">
        <Suspense>
          <NewProject />
        </Suspense>
      </div>
    </div>
  );
}
