import StudyList, {StudyListSkeleton, } from "./components/study-list";
import { Suspense } from "react";

interface ProjectStudyPageProps {
  params: {
    projectId: string;
    reportId: string;
  };
  searchParams: {
    k?: string;
  };
}

export default async function ProjectStudyPage({ params, searchParams }: ProjectStudyPageProps) {
  return (
    <Suspense fallback={<StudyListSkeleton />}>
      <StudyList params={params} searchParams={searchParams} />
    </Suspense>
  );
}