import { Suspense } from "react";
import { NewProject } from "@/components/NewProject";

export default function NewProjectPage() {
  return (
    <Suspense>
      <NewProject />
    </Suspense>
  );
}
